#!/usr/bin/env python3
"""
Find processed sessions with FIB modality where the corresponding raw session
does not have FIB.

This identifies cases where FIB was incorrectly added during processing.
"""

from aind_data_access_api.document_db import MetadataDbClient
from typing import Dict, Any
from tqdm import tqdm

# Initialize the database client
client = MetadataDbClient(host="api.allenneuraldynamics.org", database="metadata_index", collection="data_assets")


def extract_raw_name(processed_name: str) -> str:
    """Extract the raw session name from a processed session name."""
    # Handle both "_processed_" and "_videoprocessed_"
    if "_videoprocessed_" in processed_name:
        return processed_name.split("_videoprocessed_")[0]
    elif "_processed_" in processed_name:
        return processed_name.split("_processed_")[0]
    else:
        return processed_name


def has_fib_modality(record: Dict[str, Any]) -> bool:
    """Check if a record has FIB in its modalities."""
    modalities = record.get("data_description", {}).get("modality", [])
    return any(mod.get("abbreviation") == "fib" for mod in modalities)


def main():
    print("Step 1: Finding all processed sessions with FIB modality...")

    # Find all processed records with FIB
    # Use projection to only fetch name and modality fields
    processed_with_fib = list(
        client.retrieve_docdb_records(
            filter_query={
                "name": {"$regex": "processed"},
                "data_description.modality": {"$elemMatch": {"abbreviation": "fib"}},
            },
            projection={"_id": 0, "name": 1, "data_description.modality": 1},
            limit=20000,  # Adjust if needed
        )
    )

    print(f"Found {len(processed_with_fib)} processed records with FIB")

    # Group by raw session name to avoid duplicate checks
    raw_sessions_to_check = {}
    for record in tqdm(processed_with_fib, desc="Grouping by raw session name"):
        raw_name = extract_raw_name(record["name"])
        if raw_name not in raw_sessions_to_check:
            raw_sessions_to_check[raw_name] = []
        raw_sessions_to_check[raw_name].append(record)

    print(f"Unique raw sessions to check: {len(raw_sessions_to_check)}")

    print("\nStep 2: Checking each raw session for FIB modality...")

    problematic_cases = []

    for raw_name, processed_records in tqdm(
        raw_sessions_to_check.items(), desc="Checking raw sessions", total=len(raw_sessions_to_check)
    ):
        # Find the raw record
        # Use projection to only fetch name, modality, and subject_id
        raw_records = list(
            client.retrieve_docdb_records(
                filter_query={"name": raw_name},
                projection={"_id": 0, "name": 1, "data_description.modality": 1, "subject.subject_id": 1},
                limit=10,
            )
        )

        if not raw_records:
            tqdm.write(f"  WARNING: No raw record found for {raw_name}")
            continue

        # Check if raw has FIB
        raw_has_fib = any(has_fib_modality(r) for r in raw_records)

        # If raw doesn't have FIB, this is problematic
        if not raw_has_fib:
            # Get subject ID from the first raw record
            subject_id = raw_records[0].get("subject", {}).get("subject_id")

            # This is problematic: processed has FIB, raw doesn't
            problematic_cases.append(
                {
                    "raw_name": raw_name,
                    "subject_id": subject_id,
                    "processed_records": [r["name"] for r in processed_records],
                    "num_processed": len(processed_records),
                }
            )

    print(f"\n{'='*80}")
    print(f"RESULTS: Found {len(problematic_cases)} problematic cases")
    print(f"{'='*80}\n")

    if problematic_cases:
        print("Cases where processed records have FIB but raw doesn't:\n")

        for case in problematic_cases:
            print(f"Subject: {case['subject_id']}")
            print(f"  Raw session: {case['raw_name']}")
            print(f"  Number of problematic processed records: {case['num_processed']}")
            print(f"  Processed records:")
            for proc_name in case["processed_records"]:
                print(f"    - {proc_name}")
            print()
    else:
        print("No problematic cases found!")

    # Save results to file
    output_file = "fib_modality_issues.txt"
    with open(output_file, "w") as f:
        f.write(f"Found {len(problematic_cases)} problematic cases\n")
        f.write(f"{'='*80}\n\n")

        for case in problematic_cases:
            f.write(f"Subject: {case['subject_id']}\n")
            f.write(f"  Raw session: {case['raw_name']}\n")
            f.write(f"  Number of problematic processed records: {case['num_processed']}\n")
            f.write(f"  Processed records:\n")
            for proc_name in case["processed_records"]:
                f.write(f"    - {proc_name}\n")
            f.write("\n")

    print(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    main()
