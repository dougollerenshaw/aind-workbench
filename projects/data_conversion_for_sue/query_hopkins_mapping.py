#!/usr/bin/env python3
"""
Query AIND database for specific Hopkins sessions and create mapping
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
    HAS_DATA_ACCESS = False


def load_hopkins_sessions():
    """Load the Hopkins sessions from CSV file."""
    csv_path = Path(__file__).parent / "hopkins_hdf5_to_update.csv"
    df = pd.read_csv(csv_path)

    # Extract unique session patterns (remove 'behavior_' prefix)
    session_patterns = []
    for session_id in df["session_id"].unique():
        # Remove 'behavior_' prefix to get the actual session name
        if session_id.startswith("behavior_"):
            actual_session = session_id.replace("behavior_", "")
            session_patterns.append(actual_session)

    print(f"Found {len(session_patterns)} unique session patterns:")
    for pattern in session_patterns[:10]:  # Show first 10
        print(f"  {pattern}")
    if len(session_patterns) > 10:
        print(f"  ... and {len(session_patterns) - 10} more")

    return session_patterns


def query_single_session(client, session_pattern):
    """Query for a single session pattern."""
    try:
        filter_query = {
            "data_description.name": {
                "$regex": session_pattern,
                "$options": "i",
            }
        }

        projection = {
            "_id": 0,
            "data_description.name": 1,
            "subject.subject_id": 1,
            "data_description.data_level": 1,
            "data_description.modality": 1,
        }

        results = client.retrieve_docdb_records(
            filter_query=filter_query, projection=projection, limit=10
        )

        return results

    except Exception as e:
        print(f"Error querying {session_pattern}: {e}")
        return []


def query_all_sessions(session_patterns):
    """Query all sessions one by one."""
    if not HAS_DATA_ACCESS:
        return []

    try:
        client = MetadataDbClient(
            host="api.allenneuraldynamics.org",
            database="metadata_index",
            collection="data_assets",
        )

        all_results = []
        found_sessions = set()

        print(f"\nQuerying {len(session_patterns)} sessions one by one...")

        for i, pattern in enumerate(session_patterns):
            if i % 10 == 0:
                print(f"  Progress: {i}/{len(session_patterns)}")

            results = query_single_session(client, pattern)

            for result in results:
                name = result.get("data_description", {}).get("name", "")
                if name not in found_sessions:
                    found_sessions.add(name)
                    all_results.append(result)

        print(f"\nTotal unique sessions found: {len(all_results)}")
        return all_results

    except Exception as e:
        print(f"Error querying database: {e}")
        return []


def analyze_results(results):
    """Analyze the query results."""
    if not results:
        print("No results to analyze")
        return

    print(f"\n=== ANALYSIS ===")
    print(f"Total unique sessions found: {len(results)}")

    # Group by data level
    data_levels = {}
    for result in results:
        data_level = result.get("data_description", {}).get(
            "data_level", "unknown"
        )
        if data_level not in data_levels:
            data_levels[data_level] = []
        data_levels[data_level].append(result)

    print(f"\nSessions by data level:")
    for level, records in data_levels.items():
        print(f"  {level}: {len(records)} sessions")

    # Show sample records
    print(f"\nSample sessions:")
    for i, result in enumerate(results[:10]):
        name = result.get("data_description", {}).get("name", "unknown")
        subject_id = result.get("subject", {}).get("subject_id", "unknown")
        data_level = result.get("data_description", {}).get(
            "data_level", "unknown"
        )
        print(f"  {i+1}. {name} (subject: {subject_id}, level: {data_level})")

    if len(results) > 10:
        print(f"  ... and {len(results) - 10} more")

    # Create mapping from original pattern to found session name
    mapping = {}
    for result in results:
        name = result.get("data_description", {}).get("name", "")
        # Extract the base session name (remove _nwb_* suffix)
        if "_nwb_" in name:
            base_name = name.split("_nwb_")[0]
            mapping[base_name] = name

    print(f"\nSession name mapping (original -> database name):")
    for original, db_name in list(mapping.items())[:10]:
        print(f"  {original} -> {db_name}")
    if len(mapping) > 10:
        print(f"  ... and {len(mapping) - 10} more mappings")

    return mapping


def main():
    """Main function."""
    print("=== Hopkins Session Database Query ===")

    # Load session patterns from CSV
    session_patterns = load_hopkins_sessions()

    # Query database
    results = query_all_sessions(session_patterns)

    # Analyze results
    mapping = analyze_results(results)

    # Save results to file
    if results:
        output_file = Path(__file__).parent / "hopkins_session_mapping.json"
        with open(output_file, "w") as f:
            json.dump(
                {"mapping": mapping, "all_results": results},
                f,
                indent=2,
                default=str,
            )
        print(f"\nResults saved to: {output_file}")

        # Also create a simple CSV for easy viewing
        csv_file = Path(__file__).parent / "hopkins_session_mapping.csv"
        mapping_df = pd.DataFrame(
            [
                {"original_session": orig, "database_session": db_name}
                for orig, db_name in mapping.items()
            ]
        )
        mapping_df.to_csv(csv_file, index=False)
        print(f"Mapping CSV saved to: {csv_file}")


if __name__ == "__main__":
    main()
