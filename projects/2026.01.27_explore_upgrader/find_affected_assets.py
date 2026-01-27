"""
Find all assets that have fiber connections without channel data
"""

import pandas as pd
from aind_data_access_api.document_db import MetadataDbClient


def check_fiber_connections(asset_id: str, session_data: dict) -> dict:
    """Check if fiber connections have channel data"""
    result = {
        "_id": asset_id,
        "session_version": session_data.get("schema_version", "N/A"),
        "has_fiber_connections": False,
        "num_fiber_connections": 0,
        "missing_channel_data": False,
        "num_missing_channel": 0,
    }

    data_streams = session_data.get("data_streams", [])

    for stream in data_streams:
        fiber_connections = stream.get("fiber_connections", [])

        if fiber_connections:
            result["has_fiber_connections"] = True
            result["num_fiber_connections"] += len(fiber_connections)

            # Check each fiber connection for channel data
            for fc in fiber_connections:
                if "channel" not in fc or not fc.get("channel"):
                    result["missing_channel_data"] = True
                    result["num_missing_channel"] += 1

    return result


def find_affected_assets(limit: int = 100):
    """Find all assets with session v1.1.2 that have fiber connections"""
    client = MetadataDbClient(host="api.allenneuraldynamics.org", database="metadata_index", collection="data_assets")

    # Query for assets with session version 1.1.2 (or any v1 version)
    pipeline = [
        {"$match": {"session.schema_version": {"$regex": "^1\\."}}},  # All v1 sessions
        {
            "$project": {
                "_id": 1,
                "name": 1,
                "created": 1,
                "session": 1,
            }
        },
        {"$limit": limit},
    ]

    print(f"Querying DocDB for assets with v1 session schemas (limit: {limit})...")
    results = list(client.aggregate_docdb_records(pipeline=pipeline))
    print(f"Found {len(results)} assets with v1 session schemas")

    # Check each asset for fiber connections without channel data
    affected = []
    for idx, record in enumerate(results):
        if idx % 10 == 0:
            print(f"Checking asset {idx+1}/{len(results)}...")

        check_result = check_fiber_connections(record["_id"], record.get("session", {}))

        # Only keep assets that have fiber connections
        if check_result["has_fiber_connections"]:
            check_result["name"] = record.get("name", "N/A")
            check_result["created"] = record.get("created", "N/A")
            affected.append(check_result)

    # Create DataFrame
    df = pd.DataFrame(affected)

    if len(df) > 0:
        # Summary statistics
        print(f"\n=== Summary ===")
        print(f"Total assets checked: {len(results)}")
        print(f"Assets with fiber connections: {len(df)}")
        print(f"Assets missing channel data: {df['missing_channel_data'].sum()}")

        print(f"\nSession version breakdown:")
        print(df.groupby(["session_version", "missing_channel_data"]).size())

        # Save results
        output_file = "affected_assets.csv"
        df.to_csv(output_file, index=False)
        print(f"\nResults saved to: {output_file}")

        # Show examples of affected assets
        if df["missing_channel_data"].sum() > 0:
            print(f"\nExample assets missing channel data:")
            problematic = df[df["missing_channel_data"] == True].head(10)
            for _, row in problematic.iterrows():
                print(
                    f"  {row['_id']}: {row['name']} ({row['num_missing_channel']}/{row['num_fiber_connections']} missing)"
                )
    else:
        print("\nNo assets with fiber connections found in the sample.")


if __name__ == "__main__":
    find_affected_assets(limit=1000)
