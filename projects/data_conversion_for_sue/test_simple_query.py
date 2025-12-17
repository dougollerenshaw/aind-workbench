#!/usr/bin/env python3
"""
Simple test query to AIND metadata database
"""

# Try to import AIND Data Access API
try:
    from aind_data_access_api.document_db import MetadataDbClient

    HAS_DATA_ACCESS = True
except ImportError:
    print("ERROR: AIND Data Access API not available")
    HAS_DATA_ACCESS = False


def test_simple_query():
    """Test with a simple query for one specific session."""
    if not HAS_DATA_ACCESS:
        return

    try:
        client = MetadataDbClient(
            host="api.allenneuraldynamics.org",
            database="metadata_index",
            collection="data_assets",
        )

        # Test with a simple query for one session
        filter_query = {
            "data_description.name": {
                "$regex": "ZS059_2021-03-24_14-22-04",
                "$options": "i",
            }
        }

        projection = {
            "_id": 0,
            "data_description.name": 1,
            "subject.subject_id": 1,
            "data_description.data_level": 1,
        }

        print("Testing simple query for ZS059_2021-03-24_14-22-04...")
        results = client.retrieve_docdb_records(
            filter_query=filter_query, projection=projection, limit=10
        )

        print(f"Found {len(results)} records")
        for result in results:
            name = result.get("data_description", {}).get("name", "unknown")
            subject_id = result.get("subject", {}).get("subject_id", "unknown")
            data_level = result.get("data_description", {}).get(
                "data_level", "unknown"
            )
            print(f"  {name} (subject: {subject_id}, level: {data_level})")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    test_simple_query()
