"""
Standalone script to test metadata upgrade for a specific asset.
Can be used from command line or imported by the Flask app.
"""

import argparse
import copy
import json
import traceback
from aind_data_access_api.document_db import MetadataDbClient
from aind_metadata_upgrader.upgrade import Upgrade


def get_mongodb_client():
    """Get MongoDB client for metadata index"""
    return MetadataDbClient(host="api.allenneuraldynamics.org", database="metadata_index", collection="data_assets")


def upgrade_asset_by_field(asset_identifier: str):
    """
    Upgrade an asset and break down results per-field for comparison.

    Two-step approach:
    1. Try to upgrade the whole asset
    2. If that fails, test each field individually with skip_metadata_validation=True

    Returns:
        dict: Result with per-field comparison showing original vs upgraded (or error)
    """
    result = {"asset_identifier": asset_identifier, "success": False}

    try:
        # Connect and fetch asset
        client = get_mongodb_client()

        # Try by ID first (UUID format)
        if len(asset_identifier) == 36 and "-" in asset_identifier:
            records = client.retrieve_docdb_records(filter_query={"_id": asset_identifier}, limit=1)
        else:
            # Try by name
            records = client.retrieve_docdb_records(filter_query={"name": asset_identifier}, limit=1)

        if not records:
            result["error"] = f"Asset not found: {asset_identifier}"
            print(f"\n[ERROR] Asset not found: {asset_identifier}")
            return result

        asset_data = records[0]
        result["asset_id"] = asset_data.get("_id", "N/A")
        result["asset_name"] = asset_data.get("name", "N/A")
        result["created"] = asset_data.get("created", "N/A")

        print(f"\nAsset found: {result['asset_name']}")
        print(f"  ID: {result['asset_id']}")

        # Save a clean copy of the original data BEFORE any upgrade attempts
        original_asset_data = copy.deepcopy(asset_data)

        # Track per-field results
        field_results = {}
        successful_fields = []
        failed_fields = []

        # List of core metadata files
        core_files = [
            "data_description",
            "procedures",
            "subject",
            "session",
            "rig",
            "processing",
            "quality_control",
        ]

        # Map v1 field names to v2 field names
        field_conversion_map = {
            "session": "acquisition",
            "rig": "instrument",
        }

        # STEP 1: Try to upgrade the whole asset
        try:
            upgrader = Upgrade(asset_data)
            upgraded_metadata = upgrader.metadata.model_dump()

            print(f"\n[SUCCESS] Full asset upgrade succeeded")

            # Break down per-field to show what changed
            for field_name in core_files:
                if field_name in original_asset_data and original_asset_data[field_name] is not None:
                    upgraded_field_name = field_conversion_map.get(field_name, field_name)

                    if upgraded_field_name in upgraded_metadata:
                        field_results[field_name] = {
                            "success": True,
                            "original": json.loads(json.dumps(original_asset_data[field_name], default=str)),
                            "upgraded": json.loads(json.dumps(upgraded_metadata[upgraded_field_name], default=str)),
                            "converted_to": upgraded_field_name if field_name != upgraded_field_name else None,
                        }
                        successful_fields.append(field_name)
                        print(
                            f"  [OK] {field_name}"
                            + (f" -> {upgraded_field_name}" if field_name != upgraded_field_name else "")
                        )

            result["success"] = True

        except Exception as e:
            # STEP 2: Full upgrade failed - test each field individually
            error_str = str(e)
            tb = traceback.format_exc()

            print(f"\n[FAILED] Full asset upgrade failed: {error_str}")
            print(f"\nTesting each field individually...")

            result["overall_error"] = error_str
            result["overall_traceback"] = tb

            # Test each field individually using skip_metadata_validation=True
            for field_name in core_files:
                if field_name not in original_asset_data or original_asset_data[field_name] is None:
                    # Field doesn't exist in original asset - skip it entirely
                    continue

                # Create minimal test dict with just this field
                # Add subject if we're not testing subject (helps avoid "no required files" errors)
                test_dict = {
                    "_id": asset_data.get("_id"),
                    "name": asset_data.get("name"),
                    "created": asset_data.get("created"),
                    field_name: original_asset_data[field_name],
                }

                # Add subject as a companion field (unless we're testing subject itself)
                if field_name != "subject" and "subject" in original_asset_data:
                    test_dict["subject"] = original_asset_data["subject"]

                try:
                    print(f"  Testing {field_name}...")
                    # Use skip_metadata_validation=True to test field in isolation
                    field_upgrader = Upgrade(test_dict, skip_metadata_validation=True)

                    # Get upgraded result
                    if hasattr(field_upgrader.metadata, "model_dump"):
                        field_upgraded = field_upgrader.metadata.model_dump()
                    else:
                        field_upgraded = field_upgrader.metadata

                    # Check if our field is in the result
                    upgraded_field_name = field_conversion_map.get(field_name, field_name)

                    if upgraded_field_name in field_upgraded:
                        field_results[field_name] = {
                            "success": True,
                            "original": json.loads(json.dumps(original_asset_data[field_name], default=str)),
                            "upgraded": json.loads(json.dumps(field_upgraded[upgraded_field_name], default=str)),
                            "converted_to": upgraded_field_name if field_name != upgraded_field_name else None,
                        }
                        successful_fields.append(field_name)
                        print(
                            f"    [SUCCESS] {field_name}"
                            + (f" -> {upgraded_field_name}" if field_name != upgraded_field_name else "")
                        )
                    else:
                        raise ValueError(f"Field {upgraded_field_name} not found in upgraded result")

                except Exception as field_error:
                    # This field failed to upgrade
                    field_error_str = str(field_error)
                    field_tb = traceback.format_exc()

                    field_results[field_name] = {
                        "success": False,
                        "original": json.loads(json.dumps(original_asset_data[field_name], default=str)),
                        "error": field_error_str,
                        "traceback": field_tb,
                    }
                    failed_fields.append(field_name)
                    print(f"    [FAILED] {field_name}: {field_error_str[:100]}")

        # Store results
        result["field_results"] = field_results
        result["successful_fields"] = successful_fields
        result["failed_fields"] = failed_fields
        result["partial_success"] = len(successful_fields) > 0 and len(failed_fields) > 0

        print(f"\n[SUMMARY]")
        print(f"  Successful: {len(successful_fields)}")
        print(f"  Failed: {len(failed_fields)}")

    except Exception as e:
        error_str = str(e)
        tb = traceback.format_exc()
        result["error"] = error_str
        result["traceback"] = tb
        print(f"\n[FAILED] Unexpected error: {error_str}")
        print(tb)

    return result


def upgrade_asset(asset_identifier: str):
    """
    Upgrade a single asset by ID or name.

    Returns:
        dict: Result with success status, asset info, and upgrade details or errors
    """
    result = {"asset_identifier": asset_identifier, "success": False}

    try:
        # Connect and fetch asset
        client = get_mongodb_client()

        # Try to find asset by ID or name
        if len(asset_identifier) == 36 and "-" in asset_identifier:
            query = {"_id": asset_identifier}
        else:
            query = {"name": asset_identifier}

        records = client.retrieve_docdb_records(filter_query=query, limit=1)

        if not records:
            result["error"] = f"Asset not found: {asset_identifier}"
            return result

        asset_data = records[0]
        result["asset_id"] = asset_data.get("_id", "Unknown")
        result["asset_name"] = asset_data.get("name", "Unknown")
        result["created"] = str(asset_data.get("created", "Unknown"))

        # Try to upgrade
        print(f"\nUpgrading asset: {result['asset_id']}")
        print(f"Name: {result['asset_name']}")
        print(f"Created: {result['created']}")

        upgrader = Upgrade(asset_data)
        upgraded_data = upgrader.metadata.model_dump()

        result["success"] = True
        result["original_data"] = json.loads(json.dumps(asset_data, default=str))
        result["upgraded_data"] = json.loads(json.dumps(upgraded_data, default=str))

        print(f"\n[SUCCESS] Upgrade completed")

    except Exception as e:
        error_str = str(e)
        tb = traceback.format_exc()

        result["error"] = error_str
        result["traceback"] = tb
        if "asset_data" in locals():
            result["original_data"] = json.loads(json.dumps(asset_data, default=str))

        print(f"\n[FAILED] Upgrade failed")
        print(f"Error: {error_str}")

    return result


def main():
    parser = argparse.ArgumentParser(description="Test AIND metadata upgrade for a specific asset")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--id", type=str, help="Asset ID (UUID)")
    group.add_argument("--name", type=str, help="Asset name")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    asset_identifier = args.id or args.name
    result = upgrade_asset(asset_identifier)

    if args.json:
        print(json.dumps(result, indent=2, default=str))

    return 0 if result["success"] else 1


if __name__ == "__main__":
    exit(main())
