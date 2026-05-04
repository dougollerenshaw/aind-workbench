"""
Query DocDB (v2) for all assets NOT located in the aind-open-data bucket.
Saves a CSV with columns: name, _id, project_name, location.

NOTE: This was written against the aind_data_access MCP tools in Claude.ai,
which may or may not point to v2 DocDB. Verify the connection before running.
The script uses the aind-data-schema-utils or direct DocDB client — adjust
the client instantiation below to match your environment.

Approximate record count: ~55,000 (as of April 2026)
"""

import csv
import time
from pathlib import Path

# ----------------------------------------------------------------------------
# Adjust this import to match how Claude Code / your environment accesses DocDB
# e.g. from aind_data_access_api.document_db import MetadataDbClient
# ----------------------------------------------------------------------------
from aind_data_access_api.document_db import MetadataDbClient

OUTPUT_FILE = Path("non_open_data_assets.csv")
BATCH_SIZE = 500

FILTER = {"location": {"$not": {"$regex": "^s3://aind-open-data"}}}
PROJECTION = {
    "_id": 1,
    "name": 1,
    "location": 1,
    "data_description.project_name": 1,
}


def main():
    client = MetadataDbClient(
        host="...",   # <-- fill in v2 DocDB host
        database="...",  # <-- fill in database name
        collection="...",  # <-- fill in collection name
    )

    print("Counting matching records...")
    total = client.count_records(filter=FILTER)
    print(f"Found {total} records to retrieve.")

    records_written = 0
    skip = 0

    with open(OUTPUT_FILE, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=["name", "_id", "project_name", "location"])
        writer.writeheader()

        while True:
            batch = client.retrieve_docdb_records(
                filter_query=FILTER,
                projection=PROJECTION,
                limit=BATCH_SIZE,
                skip=skip,
            )

            if not batch:
                break

            for record in batch:
                writer.writerow({
                    "name": record.get("name"),
                    "_id": record.get("_id"),
                    "project_name": (record.get("data_description") or {}).get("project_name"),
                    "location": record.get("location"),
                })

            records_written += len(batch)
            skip += BATCH_SIZE
            print(f"  {records_written} / {total} written...", end="\r")

            # Be polite to the DB
            time.sleep(0.1)

    print(f"\nDone. {records_written} records saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()