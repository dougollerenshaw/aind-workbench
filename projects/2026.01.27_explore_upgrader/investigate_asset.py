"""
Script to investigate why asset 733a1052-683c-46d2-96ca-8f89bd270192 is not upgrading
"""

import json
import sys
from aind_data_access_api.document_db import MetadataDbClient
from aind_metadata_upgrader.upgrade import Upgrade


def fetch_asset_metadata(asset_id: str) -> dict:
    """Fetch asset metadata from DocDB V1"""
    client = MetadataDbClient(host="api.allenneuraldynamics.org", database="metadata_index", collection="data_assets")
    record = client.retrieve_docdb_records(filter_query={"_id": asset_id}, limit=1)

    if not record:
        raise ValueError(f"Asset {asset_id} not found")

    return record[0]


def investigate_upgrade(asset_id: str):
    """Investigate the upgrade process for a specific asset"""
    print(f"Fetching asset: {asset_id}")

    # Fetch the asset
    asset_data = fetch_asset_metadata(asset_id)

    # Print basic info
    print(f"\nAsset found:")
    print(f"  Name: {asset_data.get('name', 'N/A')}")
    print(f"  Created: {asset_data.get('created', 'N/A')}")

    # Check which metadata files exist
    print(f"\nMetadata files present:")
    for key in asset_data.keys():
        if key not in ["_id", "name", "created", "location", "external_links"]:
            print(f"  - {key}")

    # Try to run the upgrader (automatically upgrades everything in __init__)
    print(f"\nAttempting to upgrade...")
    try:
        upgrader = Upgrade(asset_data)
        upgraded_data = upgrader.metadata.model_dump()

        print(f"\nUpgrade successful!")
        print(f"Upgraded keys: {list(upgraded_data.keys())}")

        # Check what changed
        changes_found = False
        for key in upgraded_data.keys():
            if key in asset_data:
                if upgraded_data[key] != asset_data[key]:
                    print(f"\n{key} was upgraded")
                    changes_found = True
            else:
                print(f"\n{key} was added")
                changes_found = True

        if not changes_found:
            print("\nNo changes detected - asset may already be up to date")

        # Save the upgraded data for inspection
        output_file = f"{asset_id}_upgraded.json"
        with open(output_file, "w") as f:
            json.dump(upgraded_data, f, indent=2, default=str)
        print(f"\nUpgraded data saved to: {output_file}")

    except Exception as e:
        print(f"\nUpgrade failed with error: {e}")
        import traceback

        traceback.print_exc()

    # Save the original data for comparison
    original_file = f"{asset_id}_original.json"
    with open(original_file, "w") as f:
        json.dump(asset_data, f, indent=2, default=str)
    print(f"Original data saved to: {original_file}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        asset_id = sys.argv[1]
    else:
        asset_id = "733a1052-683c-46d2-96ca-8f89bd270192"

    investigate_upgrade(asset_id)
