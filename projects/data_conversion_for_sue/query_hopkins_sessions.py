#!/usr/bin/env python3
"""
Query AIND metadata database for Hopkins sessions from hopkins_hdf5_to_update.csv
"""

import pandas as pd
import json
from pathlib import Path

# Try to import AIND Data Access API
try:
    from aind_data_access_api.document_db import MetadataDbClient

    HAS_DATA_ACCESS = True
except ImportError:
    print("ERROR: AIND Data Access API not available")
    print("Please install with: pip install aind-data-access-api")
    HAS_DATA_ACCESS = False


def load_hopkins_sessions():
    """Load the Hopkins sessions from CSV file."""
    csv_path = Path(__file__).parent / "hopkins_hdf5_to_update.csv"
    df = pd.read_csv(csv_path)

    # Extract unique session patterns
    session_patterns = df["session_id"].unique()
    print(f"Found {len(session_patterns)} unique session patterns:")
    for pattern in session_patterns[:10]:  # Show first 10
        print(f"  {pattern}")
    if len(session_patterns) > 10:
        print(f"  ... and {len(session_patterns) - 10} more")

    return session_patterns


def query_database_for_sessions(session_patterns):
    """Query the AIND database for sessions matching the patterns."""
    if not HAS_DATA_ACCESS:
        return []

    try:
        client = MetadataDbClient(
            host="api.allenneuraldynamics.org",
            database="metadata_index",
            collection="data_assets",
        )

        all_results = []
        batch_size = (
            20  # Query in smaller batches to avoid URI too large error
        )

        print(
            f"\nQuerying database for sessions matching {len(session_patterns)} patterns in batches of {batch_size}..."
        )

        for i in range(0, len(session_patterns), batch_size):
            batch_patterns = session_patterns[i : i + batch_size]
            print(
                f"  Processing batch {i//batch_size + 1}/{(len(session_patterns) + batch_size - 1)//batch_size} ({len(batch_patterns)} patterns)"
            )

            # Query for sessions that match any of our patterns in this batch
            filter_query = {
                "$or": [
                    {
                        "data_description.name": {
                            "$regex": pattern,
                            "$options": "i",
                        }
                    }
                    for pattern in batch_patterns
                ]
            }

            projection = {
                "_id": 0,
                "data_description.name": 1,
                "subject.subject_id": 1,
                "data_description.data_level": 1,
                "data_description.modality": 1,
            }

            batch_results = client.retrieve_docdb_records(
                filter_query=filter_query, projection=projection, limit=1000
            )

            all_results.extend(batch_results)
            print(f"    Found {len(batch_results)} records in this batch")

        print(
            f"\nTotal found: {len(all_results)} matching records in database"
        )
        return all_results

    except Exception as e:
        print(f"Error querying database: {e}")
        return []


def analyze_results(results, session_patterns):
    """Analyze the query results."""
    if not results:
        print("No results to analyze")
        return

    print(f"\n=== ANALYSIS ===")
    print(f"Total records found: {len(results)}")

    # Group by data level
    data_levels = {}
    for result in results:
        data_level = result.get("data_description", {}).get(
            "data_level", "unknown"
        )
        if data_level not in data_levels:
            data_levels[data_level] = []
        data_levels[data_level].append(result)

    print(f"\nRecords by data level:")
    for level, records in data_levels.items():
        print(f"  {level}: {len(records)} records")

    # Show sample records
    print(f"\nSample records:")
    for i, result in enumerate(results[:5]):
        name = result.get("data_description", {}).get("name", "unknown")
        subject_id = result.get("subject", {}).get("subject_id", "unknown")
        data_level = result.get("data_description", {}).get(
            "data_level", "unknown"
        )
        print(f"  {i+1}. {name} (subject: {subject_id}, level: {data_level})")

    if len(results) > 5:
        print(f"  ... and {len(results) - 5} more")

    # Check which patterns have matches
    matched_patterns = set()
    for result in results:
        name = result.get("data_description", {}).get("name", "")
        for pattern in session_patterns:
            if pattern.lower() in name.lower():
                matched_patterns.add(pattern)

    print(
        f"\nPatterns with matches: {len(matched_patterns)}/{len(session_patterns)}"
    )
    unmatched_patterns = set(session_patterns) - matched_patterns
    if unmatched_patterns:
        print(f"Unmatched patterns ({len(unmatched_patterns)}):")
        for pattern in list(unmatched_patterns)[:10]:
            print(f"  {pattern}")
        if len(unmatched_patterns) > 10:
            print(f"  ... and {len(unmatched_patterns) - 10} more")


def main():
    """Main function."""
    print("=== Hopkins Session Database Query ===")

    # Load session patterns from CSV
    session_patterns = load_hopkins_sessions()

    # Query database
    results = query_database_for_sessions(session_patterns)

    # Analyze results
    analyze_results(results, session_patterns)

    # Save results to file
    if results:
        output_file = (
            Path(__file__).parent / "hopkins_session_query_results.json"
        )
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    main()
