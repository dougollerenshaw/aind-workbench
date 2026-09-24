"""Standalone builder for the S3-usage + DocDB project-name dataframe.

Reproduces the shared dataframe WITHOUT importing this project's `s3_data_use`
module: every needed helper is inlined here so a colleague can copy this one
file and run it.

What it produces (one row per S3 prefix+subprefix, from the storage-lens
`weekly_report` table) with these added columns:
  - size_tb, size_gb
  - exists_in_v1, v1_project_name             (DocDB v1, by asset name)
  - exists_in_v2, v2_project_name             (DocDB v2, by asset name)
  - exists_in_docdb                           (in v1 OR v2)
  - has_project_name_in_table                 (weekly_report project_name set, not 'unknown')
  - has_project_name_in_docdb                 (v1 or v2 project set, not 'unknown')
  - unexplained_missing_project_name_in_table (null in table but present in DocDB)

Inputs (looked for next to this script; rebuilt on demand):
  - weekly_report.parquet : cached storage-lens table. If absent, the script
    queries the RDS `weekly_report` table (needs AWS creds + awswrangler).
  - docdb_project_map.parquet : cache of the DocDB lookups. If absent, the
    script queries DocDB v1+v2 over the network (~1 min for ~142k names).

Run (needs AIND network access for DocDB, AWS SSO only if the parquet is absent):
  uv run --with 'awswrangler[postgres]' --with aind-data-access-api \
    --with pandas --with pyarrow python build_dataframe.py
"""

import time
from pathlib import Path

import pandas as pd
from aind_data_access_api.document_db import MetadataDbClient

SCRIPT_DIR = Path(__file__).resolve().parent
WEEKLY_REPORT_PARQUET = SCRIPT_DIR / "weekly_report.parquet"
DOCDB_PROJECT_MAP_PARQUET = SCRIPT_DIR / "docdb_project_map.parquet"
OUTPUT_PARQUET = SCRIPT_DIR / "s3_usage_with_docdb.parquet"

RDS_SECRET = "/aind/prod/rds/storage-lens-metrics/credentials/readonly"
RDS_TABLE = "weekly_report"
DOCDB_HOST = "api.allenneuraldynamics.org"


def add_size_columns(usage_df):
    """Add size_tb / size_gb columns derived from size_in_bytes."""
    if "size_tb" not in usage_df.columns:
        usage_df["size_tb"] = usage_df["size_in_bytes"] / 1e12
    if "size_gb" not in usage_df.columns:
        usage_df["size_gb"] = usage_df["size_in_bytes"] / 1e9
    return usage_df


def load_weekly_report(parquet_path=WEEKLY_REPORT_PARQUET, use_cache=True):
    """Load the storage-lens weekly_report table (parquet cache, else RDS)."""
    parquet_path = Path(parquet_path)
    if use_cache and parquet_path.exists():
        usage_df = pd.read_parquet(parquet_path)
    else:
        import awswrangler  # lazy: only needed to refresh from the database
        with awswrangler.postgresql.connect(secret_id=RDS_SECRET) as connection:
            usage_df = awswrangler.postgresql.read_sql_table(table=RDS_TABLE, con=connection)
        usage_df.to_parquet(parquet_path)
    return add_size_columns(usage_df)


def fetch_docdb_project_names(docdb_version, asset_names, chunk_size=250):
    """Return {asset_name: data_description.project_name} for the asset names
    that exist in this DocDB version (queried by exact name, in chunks)."""
    docdb_client = MetadataDbClient(host=DOCDB_HOST, version=docdb_version)
    projection = {"_id": 0, "name": 1, "data_description.project_name": 1}
    project_name_by_asset = {}
    for chunk_start in range(0, len(asset_names), chunk_size):
        name_chunk = asset_names[chunk_start:chunk_start + chunk_size]
        for attempt in range(4):
            try:
                records = docdb_client.fetch_records_by_filter_list(
                    "name", name_chunk, projection=projection
                )
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        for record in records:
            asset_name = record.get("name")
            if asset_name not in project_name_by_asset:  # first record for a name wins
                project_name_by_asset[asset_name] = (
                    record.get("data_description") or {}
                ).get("project_name")
    return project_name_by_asset


def has_project_name(project_name_column):
    """True where a project name is set (non-null and not 'unknown')."""
    project_name_column = project_name_column.astype("string")
    is_set = project_name_column.notna() & (project_name_column.str.lower() != "unknown")
    return is_set.fillna(False).astype(bool)


def build_dataframe():
    # 1) storage-lens table (with size columns)
    usage_df = load_weekly_report()

    # 2) DocDB v1 + v2 project names, looked up by asset name (cached to disk)
    if DOCDB_PROJECT_MAP_PARQUET.exists():
        docdb_project_df = pd.read_parquet(DOCDB_PROJECT_MAP_PARQUET)
        print(f"Loaded DocDB project map from cache: {len(docdb_project_df):,} names")
    else:
        asset_names = usage_df["prefix"].dropna().unique().tolist()
        print(f"Querying DocDB v1 + v2 for {len(asset_names):,} names (~1 min)...")
        v2_project_by_asset = fetch_docdb_project_names("v2", asset_names)
        v1_project_by_asset = fetch_docdb_project_names("v1", asset_names)
        docdb_project_df = pd.DataFrame({"name": asset_names})
        docdb_project_df["exists_in_v1"] = docdb_project_df["name"].isin(v1_project_by_asset)
        docdb_project_df["v1_project_name"] = docdb_project_df["name"].map(v1_project_by_asset)
        docdb_project_df["exists_in_v2"] = docdb_project_df["name"].isin(v2_project_by_asset)
        docdb_project_df["v2_project_name"] = docdb_project_df["name"].map(v2_project_by_asset)
        docdb_project_df.to_parquet(DOCDB_PROJECT_MAP_PARQUET)

    usage_df = usage_df.merge(
        docdb_project_df, how="left", left_on="prefix", right_on="name"
    ).drop(columns="name")
    usage_df["exists_in_v1"] = usage_df["exists_in_v1"].fillna(False)
    usage_df["exists_in_v2"] = usage_df["exists_in_v2"].fillna(False)

    # 3) derived comparison flags
    usage_df["exists_in_docdb"] = usage_df["exists_in_v1"] | usage_df["exists_in_v2"]
    usage_df["has_project_name_in_table"] = has_project_name(usage_df["project_name"])
    usage_df["has_project_name_in_docdb"] = (
        has_project_name(usage_df["v1_project_name"])
        | has_project_name(usage_df["v2_project_name"])
    )
    usage_df["unexplained_missing_project_name_in_table"] = (
        ~usage_df["has_project_name_in_table"] & usage_df["has_project_name_in_docdb"]
    )
    return usage_df


if __name__ == "__main__":
    usage_df = build_dataframe()
    usage_df.to_parquet(OUTPUT_PARQUET)
    distinct_asset_count = usage_df["prefix"].nunique()
    unexplained_asset_count = usage_df.loc[
        usage_df["unexplained_missing_project_name_in_table"], "prefix"
    ].nunique()
    print(f"\nrows: {len(usage_df):,} | distinct assets: {distinct_asset_count:,}")
    print(f"assets with unexplained missing project (in DocDB, null in table): "
          f"{unexplained_asset_count:,}")
    print(f"saved -> {OUTPUT_PARQUET}")
