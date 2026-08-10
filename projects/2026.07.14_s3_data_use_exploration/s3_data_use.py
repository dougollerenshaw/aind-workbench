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
import re
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
DEFAULT_DOCDB_MAP = _HERE / "docdb_project_map.parquet"

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


def load_docdb_project_map(prefixes=None, path=DEFAULT_DOCDB_MAP):
    """Return a {asset_name: project_name} map, querying DocDB for any gaps.

    Loads the on-disk cache first. If ``prefixes`` is supplied, any names not
    already in the cache are looked up in DocDB (v2 preferred, v1 fallback) and
    the cache is updated. Names with no DocDB hit are recorded as None so they
    are not re-queried on the next call. Requires ``aind-data-access-api`` and
    network access only when there are cache misses.

    Pass ``prefixes=None`` to use the cache as-is (no network call).
    """
    import time

    path = Path(path)

    # --- load existing cache -------------------------------------------------
    if path.exists():
        cached = pd.read_parquet(path)
        # support both the old v1/v2 format and the simpler name/project format
        if "v2_project_name" in cached.columns:
            proj = cached["v2_project_name"].where(
                cached["v2_project_name"].notna(), cached.get("v1_project_name")
            )
            cache_map = dict(zip(cached["name"], proj))
        else:
            cache_map = dict(zip(cached["name"], cached["project_name"]))
    else:
        cache_map = {}

    if prefixes is None:
        return {k: v for k, v in cache_map.items() if v and pd.notna(v)}

    missing = [p for p in set(prefixes) if p not in cache_map]
    if not missing:
        return {k: v for k, v in cache_map.items() if v and pd.notna(v)}

    # --- query DocDB for cache misses ----------------------------------------
    print(f"Querying DocDB for {len(missing):,} uncached asset names...")
    from aind_data_access_api.document_db import MetadataDbClient

    DOCDB_HOST = "api.allenneuraldynamics.org"
    CHUNK = 250
    PROJ = {"_id": 0, "name": 1, "data_description.project_name": 1}

    new_results = {}
    for version in ("v2", "v1"):
        needed = [p for p in missing if new_results.get(p) is None]
        if not needed:
            break
        client = MetadataDbClient(host=DOCDB_HOST, version=version)
        for i in range(0, len(needed), CHUNK):
            chunk = needed[i: i + CHUNK]
            for attempt in range(4):
                try:
                    recs = client.fetch_records_by_filter_list("name", chunk, projection=PROJ)
                    break
                except Exception:
                    if attempt == 3:
                        raise
                    time.sleep(2 ** attempt)
            for r in recs:
                nm = r.get("name")
                proj = (r.get("data_description") or {}).get("project_name")
                if nm not in new_results:
                    new_results[nm] = proj or None

    # record misses as None so we skip them next time
    for p in missing:
        if p not in new_results:
            new_results[p] = None

    cache_map.update(new_results)
    hits = sum(1 for v in new_results.values() if v)
    print(f"  {hits:,} project names found; cache updated ({path.name})")

    # --- save updated cache in simple format ---------------------------------
    pd.DataFrame(
        [{"name": k, "project_name": v} for k, v in cache_map.items()]
    ).to_parquet(path)

    return {k: v for k, v in cache_map.items() if v and pd.notna(v)}


def load_capsule_map(path=DEFAULT_CAPSULE_MAP):
    """Load the cached capsule_id -> {name, tags} map. Returns ``{}`` if absent
    (in which case pipeline prefixes fall into the 'private/unresolved' category)."""
    path = Path(path)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def add_category(df, capsule_map=None, docdb_map=None, inplace=False):
    """Add a ``category`` column: a data-type/modality label for every prefix.

    Precedence per row: resolved pipeline capsule (batch/results buckets) ->
    named-prefix token -> datasets-bucket project tag ->
    weekly_report project_name -> DocDB project_name -> 'other categories'.
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
    still_uncat = cat.isna()
    cat[still_uncat & has_project] = df["project_name"][still_uncat & has_project]
    if docdb_map is None:
        uncat_prefixes = df.loc[cat.isna(), "prefix"].dropna().unique().tolist()
        docdb_map = load_docdb_project_map(prefixes=uncat_prefixes)
    if docdb_map:
        docdb_project = df["prefix"].map(docdb_map)
        still_uncat2 = cat.isna() & docdb_project.notna()
        cat[still_uncat2] = docdb_project[still_uncat2]
    cat = cat.fillna("other categories")  # unclassifiable: no modality prefix and no project name

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
    per-bucket size across *all* categories, and a ``(below top N)`` row
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
    # rollup row for categories below the top_n (distinct from the "other categories"
    # catch-all category, which is a real category value and may appear in the top_n).
    rollup = f"(below top {top_n})"
    pivot.loc[rollup] = bucket_totals - pivot.sum(axis=0)

    pivot["TOTAL"] = pivot.sum(axis=1)       # row totals
    pivot.loc["TOTAL"] = pivot.sum(axis=0)   # column totals (bottom row)

    key = sort_bucket if sort_bucket in pivot.columns else "TOTAL"
    order = (
        pivot.drop(index=[rollup, "TOTAL"])
        .sort_values(key, ascending=False)
        .index.tolist()
    ) + [rollup, "TOTAL"]
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


# ---------------------------------------------------------------------------
# Reprocessing-waste analysis
#
# AIND derived-asset names follow the schema convention
#   {raw_input}_{process}_{YYYY-MM-DD_HH-MM-SS}
# where raw_input is itself {subject-or-modality}_{acquisition datetime}. So a
# derived name parses into (raw source asset, process, run datetime). When the
# same (raw asset, process) appears with several run datetimes, the raw asset was
# reprocessed; keeping only the latest run, the older ones are reclaimable space.
# ---------------------------------------------------------------------------

DATETIME_RE = r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}"
DERIVED_NAME_RE = re.compile(
    rf"^(?P<input>.+?_{DATETIME_RE})_(?P<process>.+?)_(?P<cdt>{DATETIME_RE})$"
)


def _leading_token(name):
    """Leading alphabetic token of an asset name (e.g. 'exaSPIM'), or None for
    subject-only names like '409828_2018-...'."""
    m = re.match(r"^([A-Za-z][A-Za-z0-9-]*)_", str(name))
    return m.group(1) if m else None


def reprocessing_table(df, bucket=OPEN_DATA_BUCKET):
    """Per derived-asset table for one bucket, parsed for reprocessing analysis.

    Columns added: ``input`` (raw source asset), ``process`` (raw label),
    ``process_norm`` (label with embedded run-timestamps stripped so multi-stage
    reruns group by terminal process), ``cdt`` (run datetime), ``modality``,
    ``runs`` (count for this input+process), ``is_latest``, ``reclaimable``
    (True for every run that is not the most recent = deletable under keep-latest).
    Only derived assets (names matching the schema's DERIVED pattern) are kept.
    """
    _ensure_size(df)
    a = (
        df[df["bucket"] == bucket]
        .groupby("prefix", as_index=False)
        .agg(size_tb=("size_tb", "sum"), n_files=("number_of_files", "sum"))
    )
    a = a.join(a["prefix"].str.extract(DERIVED_NAME_RE))
    a = a[a["input"].notna()].copy()  # derived assets only
    a["process_norm"] = (
        a["process"].str.replace(DATETIME_RE, "", regex=True)
        .str.replace(r"_{2,}", "_", regex=True).str.strip("_")
    )
    a["modality"] = a["input"].map(lambda s: to_modality(s) or _leading_token(s) or "(unlabeled)")
    grp = a.groupby(["input", "process_norm"])
    a["runs"] = grp["prefix"].transform("size")
    a["is_latest"] = grp["cdt"].transform("max") == a["cdt"]
    a["reclaimable"] = ~a["is_latest"]
    return a.reset_index(drop=True)


def reprocessing_summary(table):
    """Headline totals for a ``reprocessing_table`` (keep-latest definition)."""
    sizes = table.groupby(["input", "process_norm"]).size()
    n_groups = int(len(sizes))
    reproc = int((sizes > 1).sum())
    return pd.Series({
        "derived_assets": len(table),
        "derived_tb": round(table["size_tb"].sum(), 1),
        "raw+process_groups": n_groups,
        "groups_reprocessed": reproc,
        "pct_groups_reprocessed": round(100 * reproc / n_groups, 1) if n_groups else 0.0,
        "redundant_runs": int(table["reclaimable"].sum()),
        "raw_assets_affected": int(table.loc[table["reclaimable"], "input"].nunique()),
        "reclaimable_tb": round(table.loc[table["reclaimable"], "size_tb"].sum(), 1),
    })


def reclaimable_by(table, col="process_norm", top_n=15):
    """Reclaimable TB grouped by ``col`` ('process_norm' or 'modality'), desc."""
    out = (
        table[table["reclaimable"]].groupby(col)["size_tb"].sum()
        .sort_values(ascending=False).to_frame("reclaimable_tb").round(2)
    )
    return out if top_n is None else out.head(top_n)


def top_offenders(table, top_n=15):
    """Individual (raw asset, process) pairs wasting the most space."""
    waste = table[table["reclaimable"]].groupby(["input", "process_norm"])["size_tb"].sum()
    runs = table.groupby(["input", "process_norm"])["prefix"].size()
    out = (
        pd.concat([waste.rename("reclaimable_tb"), runs.rename("runs")], axis=1)
        .dropna(subset=["reclaimable_tb"])
        .sort_values("reclaimable_tb", ascending=False)
        .head(top_n).round(2).reset_index()
    )
    out["runs"] = out["runs"].astype(int)
    return out


def rerun_distribution(table):
    """How many (raw asset, process) groups have 1, 2, 3, ... runs."""
    rc = table.groupby(["input", "process_norm"])["prefix"].size()
    return rc.value_counts().sort_index().rename_axis("runs_per_input").to_frame("n_groups")


def runs_for_input(df, input_stem, bucket=OPEN_DATA_BUCKET):
    """Every asset under one raw stem (raw acquisition + all derived runs).

    Columns: ``name``, ``size_tb``, ``level`` ('raw' if the name is just the raw
    stem, 'derived' if it matches the schema's derived pattern), and ``bucket``.
    Pass ``bucket=None`` to search every bucket (not just aind-open-data), which
    surfaces copies of the same asset in private/scratch/etc. The raw asset is
    listed first, then the derived runs in chronological order by their processing
    datetime (the trailing timestamp in the name). Use to inspect a single
    reprocessed asset, e.g. ``runs_for_input(df, "exaSPIM_784896_2025-08-19_10-48-12")``.
    """
    _ensure_size(df)
    sub = df[df["prefix"].str.startswith(input_stem)]
    if bucket is not None:
        sub = sub[sub["bucket"] == bucket]
    a = (
        sub.groupby(["bucket", "prefix"], as_index=False).agg(size_tb=("size_tb", "sum"))
        .rename(columns={"prefix": "name"})
    )
    a["level"] = a["name"].map(lambda n: "derived" if DERIVED_NAME_RE.match(n) else "raw")
    # Order: raw first (rank 0), then derived (rank 1) by processing datetime asc.
    a["_rank"] = (a["level"] != "raw").astype(int)
    a["_date"] = a["name"].str.extract(r"_(" + DATETIME_RE + r")$")[0].fillna("")
    a = a.sort_values(["_rank", "_date"]).reset_index(drop=True)
    return a[["name", "size_tb", "level", "bucket"]].round(3)


def build_reprocessing_report(parquet_path=DEFAULT_PARQUET, bucket=OPEN_DATA_BUCKET,
                              use_cache=True):
    """One-call convenience: load -> parse -> all reprocessing views as a dict.

    Returns {'summary', 'by_process', 'by_modality', 'top_offenders',
    'rerun_distribution'} of DataFrames/Series, ready to render (e.g. Flask).
    """
    table = reprocessing_table(load_weekly_report(parquet_path, use_cache=use_cache), bucket=bucket)
    return {
        "summary": reprocessing_summary(table),
        "by_process": reclaimable_by(table, "process_norm"),
        "by_modality": reclaimable_by(table, "modality"),
        "top_offenders": top_offenders(table),
        "rerun_distribution": rerun_distribution(table),
    }
