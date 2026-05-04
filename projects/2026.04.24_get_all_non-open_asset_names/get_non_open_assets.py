"""
Query DocDB for all assets NOT located in the aind-open-data bucket.
Saves a CSV with columns:
  name, project_name, num_external_links, code_ocean_external_link, location,
  created, last_modified, acquisition_date, _id, in_lc_paper

The in_lc_paper column is added if lc_paper_assets.csv exists in the same
folder (produced by build_lc_paper_assets_csv.py). Rows where in_lc_paper
is True are sorted to the top.

Usage:
  uv run python get_non_open_assets.py              # fetch all records
  uv run python get_non_open_assets.py --sample 50   # random sample of 50
"""

import argparse
import time
from pathlib import Path

import pandas as pd
from aind_data_access_api.document_db import MetadataDbClient

SCRIPT_DIR = Path(__file__).parent
OUTPUT_FILE = SCRIPT_DIR / "non_open_data_assets.csv"
LC_PAPER_ASSETS_FILE = SCRIPT_DIR / "lc_paper_assets.csv"
BATCH_SIZE = 500

CLIENT = MetadataDbClient(
    host="api.allenneuraldynamics.org",
    database="metadata_index_v2",
    collection="data_assets",
)

MATCH_STAGE = {"$match": {"location": {"$not": {"$regex": "^s3://aind-open-data"}}}}
PROJECT_STAGE = {
    "$project": {
        "_id": 1,
        "name": 1,
        "location": 1,
        "data_description.project_name": 1,
        "_created": 1,
        "_last_modified": 1,
        "acquisition.acquisition_start_time": 1,
        "other_identifiers": 1,
    }
}


def get_total_count():
    pipeline = [MATCH_STAGE, {"$count": "total"}]
    result = CLIENT.aggregate_docdb_records(pipeline=pipeline)
    if result:
        return result[0]["total"]
    return 0


def fetch_sample(n):
    """Return n randomly-sampled records from the matched set."""
    pipeline = [
        MATCH_STAGE,
        {"$sample": {"size": n}},
        PROJECT_STAGE,
    ]
    return CLIENT.aggregate_docdb_records(pipeline=pipeline)


def fetch_batch(skip, limit):
    pipeline = [
        MATCH_STAGE,
        PROJECT_STAGE,
        {"$skip": skip},
        {"$limit": limit},
    ]
    return CLIENT.aggregate_docdb_records(pipeline=pipeline)


def extract_row(record):
    acq = record.get("acquisition") or {}
    acq_start = acq.get("acquisition_start_time", "")
    # Keep just the date portion (first 10 chars of ISO timestamp)
    if acq_start and len(str(acq_start)) >= 10:
        acq_start = str(acq_start)[:10]

    other_ids = record.get("other_identifiers") or {}
    num_external_links = 0
    for value in other_ids.values():
        if isinstance(value, list):
            num_external_links += len(value)
        elif value is not None:
            num_external_links += 1

    if num_external_links == 1:
        co = other_ids.get("Code Ocean") or []
        if isinstance(co, list) and len(co) == 1:
            code_ocean_link = co[0]
        else:
            code_ocean_link = "unspecified"
    elif num_external_links == 0:
        code_ocean_link = ""
    else:
        code_ocean_link = "unspecified"

    return {
        "name": record.get("name"),
        "project_name": (record.get("data_description") or {}).get("project_name"),
        "num_external_links": num_external_links,
        "code_ocean_external_link": code_ocean_link,
        "location": record.get("location"),
        "created": record.get("_created"),
        "last_modified": record.get("_last_modified"),
        "acquisition_date": acq_start,
        "_id": record.get("_id"),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Export non-open-data assets from DocDB to CSV."
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        metavar="N",
        help="Fetch a random sample of N records instead of all records",
    )
    args = parser.parse_args()

    print("Counting matching records...")
    total = get_total_count()
    print(f"Found {total:,} matching records in DocDB.")

    if args.sample:
        n = min(args.sample, total)
        print(f"Fetching random sample of {n:,} records...")
        batch = fetch_sample(n)
        all_rows = [extract_row(r) for r in batch]
    else:
        all_rows = []
        skip = 0

        while skip < total:
            batch = fetch_batch(skip, BATCH_SIZE)
            if not batch:
                break

            all_rows.extend(extract_row(r) for r in batch)
            skip += len(batch)
            print(f"  {len(all_rows):,} / {total:,} fetched...", end="\r")

            time.sleep(0.1)

        print()

    print(f"{len(all_rows):,} records fetched. Writing CSV...")
    df = pd.DataFrame(all_rows)

    excluded_projects = {"unknown", "OpenScope"}
    before = len(df)
    df = df[df["project_name"].notna() & ~df["project_name"].isin(excluded_projects)]
    print(f"Filtered out {before - len(df):,} records (null/unknown/OpenScope project_name); {len(df):,} remain.")

    if LC_PAPER_ASSETS_FILE.exists():
        lc_names = set(pd.read_csv(LC_PAPER_ASSETS_FILE)["asset_name"])
        df["in_lc_paper"] = df["name"].isin(lc_names)
        n_matches = df["in_lc_paper"].sum()
        print(f"Tagged {n_matches:,} records as in_lc_paper.")
        df.sort_values(["in_lc_paper", "name"], ascending=[False, True], inplace=True)
    else:
        print(f"No {LC_PAPER_ASSETS_FILE.name} found; skipping in_lc_paper merge.")
        df.sort_values("name", inplace=True)

    df.to_csv(OUTPUT_FILE, index=False)
    print(f"Done. Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
