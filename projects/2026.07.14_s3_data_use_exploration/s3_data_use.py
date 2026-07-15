"""Reusable functions for the AIND S3 storage-usage analysis.

The notebook (and any app, e.g. a Flask portal) imports from here instead of
duplicating logic. There are two data inputs, both cached next to this module:

  - ``weekly_report.parquet`` : a snapshot of the storage-lens ``weekly_report``
    RDS table (one row per S3 prefix).
  - ``capsule_map.json``      : cached Code Ocean ``capsule_id -> {name, tags}``
    map, produced by ``resolve_capsules.py``.

Functions that read only those two files need **no** AWS or Code Ocean
credentials, so they are safe to call from a web request. ``load_weekly_report``
can also refresh the parquet from the database, but that path needs AWS creds
and imports ``awswrangler`` lazily.

Typical use (notebook or Flask view)::

    import s3_data_use as s3
    table = s3.build_category_by_bucket()   # -> DataFrame, ready to render
    html = table.to_html(classes="table", border=0)

Or step by step for custom views::

    df = s3.add_category(s3.load_weekly_report())
    s3.size_by_bucket(df)
    s3.category_by_bucket(df, sort_bucket="aind-open-data")
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent

# --- storage layout constants ----------------------------------------------
RESULTS_BUCKET = "codeocean-s3resultsbucket-1182nktl2bh9f"
BATCH_BUCKET = "codeocean-s3batchbucket-16itpvq060udk"
DATASETS_BUCKET = "codeocean-s3datasetsbucket-1u41qdg42ur9"
OPEN_DATA_BUCKET = "aind-open-data"

# --- default artifact locations (next to this module) ----------------------
DEFAULT_PARQUET = _HERE / "weekly_report.parquet"
DEFAULT_CAPSULE_MAP = _HERE / "capsule_map.json"

# --- database source (only used when refreshing the parquet cache) ----------
RDS_SECRET = "/aind/prod/rds/storage-lens-metrics/credentials/readonly"
RDS_TABLE = "weekly_report"

UUID_RE = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"

# Ordered keyword -> canonical data type. First match wins, so specific patterns
# (multiplane-ophys) come before general ones (ophys). Edit freely.
MODALITY_RULES = [
    ("exaspim", "exaSPIM"), ("smartspim", "SmartSPIM"), ("z1-fuse", "SmartSPIM"),
    ("dispim", "diSPIM"), ("mesospim", "mesoSPIM"), ("fmost", "fMOST"),
    ("multiplane", "multiplane-ophys"),
    ("single-plane", "single-plane-ophys"), ("singleplane", "single-plane-ophys"),
    ("single_plane", "single-plane-ophys"), ("slap2", "SLAP2"), ("iglusnfr", "iGluSnFR"),
    ("pophys", "ophys"), ("ophys", "ophys"), ("suite2p", "ophys"), ("cnmf", "ophys"),
    ("cellpose", "ophys"), ("decrosstalk", "ophys"), ("motion correction", "ophys"),
    ("ecephys", "ecephys"), ("kilosort", "ecephys"), ("dartsort", "ecephys"),
    ("spike sort", "ecephys"), ("electrophysiolog", "ecephys"), ("ephys", "ecephys"),
    ("hcr", "HCR"), ("merscope", "spatial-transcriptomics"),
    ("mfish", "spatial-transcriptomics"), ("mersc", "spatial-transcriptomics"),
    ("foraging", "behavior"), ("dynamic-routing", "behavior"),
    ("dynamic routing", "behavior"), ("behavior", "behavior"), ("anipose", "behavior"),
    ("fip", "FIP"), ("proteomics", "proteomics"), ("atac", "ATAC"),
    ("taxonomy", "cell-typing"), ("scrattch", "cell-typing"),
    ("celltype", "cell-typing"), ("cell type", "cell-typing"),
]


def to_modality(s):
    """Map a free-text string (capsule name/tag or name token) to a canonical
    data type, or ``None`` if no keyword in ``MODALITY_RULES`` matches."""
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return None
    t = str(s).lower()
    for sub, label in MODALITY_RULES:
        if sub in t:
            return label
    return None


def _ensure_size(df):
    """Add ``size_tb``/``size_gb`` columns from ``size_in_bytes`` if missing."""
    if "size_tb" not in df.columns:
        df["size_tb"] = df["size_in_bytes"] / 1e12
    if "size_gb" not in df.columns:
        df["size_gb"] = df["size_in_bytes"] / 1e9
    return df


def load_weekly_report(parquet_path=DEFAULT_PARQUET, use_cache=True,
                       secret_name=RDS_SECRET, table=RDS_TABLE):
    """Load the weekly_report snapshot as a DataFrame (with ``size_tb``/``size_gb``).

    Reads the local parquet cache when present. If the cache is missing or
    ``use_cache=False``, queries the RDS table via ``awswrangler`` (needs AWS
    credentials) and writes the cache. Pass ``use_cache=False`` to force a
    refresh from the database.
    """
    parquet_path = Path(parquet_path)
    if use_cache and parquet_path.exists():
        df = pd.read_parquet(parquet_path)
    else:
        import awswrangler as wr  # lazy: only needed to refresh from the DB
        with wr.postgresql.connect(secret_id=secret_name) as con:
            df = wr.postgresql.read_sql_table(table=table, con=con)
        df.to_parquet(parquet_path)
    return _ensure_size(df)


def load_capsule_map(path=DEFAULT_CAPSULE_MAP):
    """Load the cached capsule_id -> {name, tags} map. Returns ``{}`` if absent
    (in which case pipeline prefixes fall into the 'private/unresolved' category)."""
    path = Path(path)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def add_category(df, capsule_map=None, inplace=False):
    """Add a ``category`` column: a data-type/modality label for every prefix.

    Precedence per row: resolved pipeline capsule (batch/results buckets) ->
    named-prefix token -> datasets-bucket project tag -> bucket fallback. See
    the module docstring for the storage-layout rationale.
    """
    if capsule_map is None:
        capsule_map = load_capsule_map()
    if not inplace:
        df = df.copy()
    _ensure_size(df)

    prefix = df["prefix"]
    # Named prefixes -> leading token; exclude UUID-shaped prefixes (a hex UUID
    # starting a-f would otherwise look like a named token).
    is_uuid = prefix.str.match(UUID_RE, na=False)
    named = prefix.str.match(r"^[A-Za-z]", na=False) & ~is_uuid
    lead_token = prefix.where(named).str.split("_").str[0]

    # Capsule id per row: batch -> top-level prefix; results -> 2nd path segment.
    cap_id = pd.Series(
        np.where(
            df["bucket"].eq(BATCH_BUCKET), prefix,
            np.where(df["bucket"].eq(RESULTS_BUCKET),
                     df["subprefix"].str.split("/").str[1], None),
        ),
        index=df.index,
    )
    cap_source_map = {
        cid: ((v["tags"][0] + " " if v["tags"] else "") + v["name"])
        for cid, v in capsule_map.items() if v
    }
    cap_source = cap_id.map(cap_source_map)

    # Modality lookups over distinct values only (fast), mapped back to rows.
    uniq = pd.unique(pd.concat([cap_source, lead_token], ignore_index=True).dropna())
    mod = {s: to_modality(s) for s in uniq}
    mod_from_cap = cap_source.map(mod)
    mod_from_token = lead_token.map(mod)
    has_project = df["project_name"].notna() & (df["project_name"].str.lower() != "unknown")

    cat = pd.Series(pd.NA, index=df.index, dtype="object")
    is_pipe = cap_id.notna()
    cat[is_pipe] = mod_from_cap[is_pipe]
    cat[is_pipe & cat.isna() & cap_source.notna()] = "other-pipeline"
    cat[is_pipe & cat.isna()] = "codeocean-pipeline (private/unresolved)"
    is_named = cat.isna() & lead_token.notna()
    cat[is_named] = mod_from_token[is_named].fillna(lead_token[is_named])
    is_ds = cat.isna() & df["bucket"].eq(DATASETS_BUCKET)
    cat[is_ds] = np.where(has_project[is_ds], df["project_name"][is_ds],
                          "codeocean-dataset (unresolved)")
    cat = cat.fillna(df["bucket"].astype(str) + " (uuid)")

    df["category"] = cat
    return df


def size_by_bucket(df):
    """Total TB per bucket, largest first."""
    _ensure_size(df)
    return (
        df.groupby("bucket")["size_tb"].sum()
        .sort_values(ascending=False)
        .to_frame("total_tb")
    )


def size_by_category(df, top_n=40):
    """Total TB and distinct-prefix count per category, largest first.

    Requires ``add_category(df)`` to have been called. ``top_n=None`` returns all.
    """
    if "category" not in df.columns:
        raise ValueError("call add_category(df) first")
    _ensure_size(df)
    out = (
        df.groupby("category")
        .agg(total_tb=("size_tb", "sum"), n_prefixes=("prefix", "nunique"))
        .sort_values("total_tb", ascending=False)
    )
    return out if top_n is None else out.head(top_n)


def category_by_bucket(df, top_n=20, sort_bucket=OPEN_DATA_BUCKET, round_tb=2):
    """Pivot of TB by category (rows) x bucket (columns) -- the main portal view.

    Bucket columns are ordered by total bucket size (largest on the left). A
    ``TOTAL`` column gives row sums; the bottom ``TOTAL`` row gives the true
    per-bucket size across *all* categories, and an ``(other categories)`` row
    rolls up everything below the top ``top_n`` so the columns add up exactly.
    Category rows are sorted by ``sort_bucket`` (falls back to ``TOTAL`` if that
    bucket isn't present). Requires ``add_category(df)`` first.
    """
    if "category" not in df.columns:
        raise ValueError("call add_category(df) first")
    _ensure_size(df)

    by = df.groupby(["category", "bucket"])["size_tb"].sum()
    top_cats = by.groupby("category").sum().sort_values(ascending=False).head(top_n).index
    bucket_order = df.groupby("bucket")["size_tb"].sum().sort_values(ascending=False).index

    pivot = by.loc[top_cats].unstack("bucket").reindex(columns=bucket_order)
    bucket_totals = df.groupby("bucket")["size_tb"].sum().reindex(bucket_order)
    pivot.loc["(other categories)"] = bucket_totals - pivot.sum(axis=0)

    pivot["TOTAL"] = pivot.sum(axis=1)       # row totals
    pivot.loc["TOTAL"] = pivot.sum(axis=0)   # column totals (bottom row)

    key = sort_bucket if sort_bucket in pivot.columns else "TOTAL"
    order = (
        pivot.drop(index=["(other categories)", "TOTAL"])
        .sort_values(key, ascending=False)
        .index.tolist()
    ) + ["(other categories)", "TOTAL"]
    pivot = pivot.loc[order].fillna(0)
    return pivot.round(round_tb) if round_tb is not None else pivot


def build_category_by_bucket(parquet_path=DEFAULT_PARQUET,
                             capsule_map_path=DEFAULT_CAPSULE_MAP,
                             use_cache=True, top_n=20,
                             sort_bucket=OPEN_DATA_BUCKET, round_tb=2):
    """One-call convenience: load -> add category -> category_by_bucket pivot.

    Intended for an app: returns the ready-to-render DataFrame from the cached
    artifacts, no AWS/Code Ocean credentials needed (with ``use_cache=True``).
    """
    df = load_weekly_report(parquet_path, use_cache=use_cache)
    df = add_category(df, load_capsule_map(capsule_map_path), inplace=True)
    return category_by_bucket(df, top_n=top_n, sort_bucket=sort_bucket, round_tb=round_tb)
