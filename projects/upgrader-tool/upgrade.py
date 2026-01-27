"""
Standalone script to test metadata upgrade for a specific asset.
Can be used from command line or imported by the Flask app.
"""

import argparse
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
        
        # Track per-field results
        field_results = {}
        successful_fields = []
        failed_fields = []
        
        # List of core metadata files
        core_files = [
            "acquisition",
            "data_description",
            "instrument",
            "procedures",
            "processing",
            "rig",
            "session",
            "subject",
            "quality_control",
        ]
        
        # Try to upgrade the whole asset
        try:
            upgrader = Upgrade(asset_data)
            upgraded_metadata = upgrader.metadata.model_dump()
            
            print(f"\n[SUCCESS] Full asset upgrade succeeded")
            
            # Break down per-field to show what changed
            # Map v1 field names to v2 field names
            field_conversion_map = {
                "session": "acquisition",
                "rig": "instrument",
            }
            
            for field_name in core_files:
                if field_name in asset_data and asset_data[field_name] is not None:
                    # Check if field was upgraded (with name conversion)
                    upgraded_field_name = field_conversion_map.get(field_name, field_name)
                    
                    if upgraded_field_name in upgraded_metadata:
                        field_results[field_name] = {
                            "success": True,
                            "original": json.loads(json.dumps(asset_data[field_name], default=str)),
                            "upgraded": json.loads(json.dumps(upgraded_metadata[upgraded_field_name], default=str)),
                            "converted_to": upgraded_field_name if field_name != upgraded_field_name else None,
                        }
                        successful_fields.append(field_name)
                        print(f"  [OK] {field_name}" + (f" -> {upgraded_field_name}" if field_name != upgraded_field_name else ""))
                    else:
                        # Field existed but isn't in upgraded version (unusual)
                        field_results[field_name] = {
                            "success": False,
                            "error": f"Field {field_name} not present in upgraded metadata",
                            "original": json.loads(json.dumps(asset_data[field_name], default=str)),
                        }
                        failed_fields.append(field_name)
                        print(f"  [WARN] {field_name}: Missing in upgraded metadata")
            
            result["success"] = True
            
        except Exception as e:
            # Full upgrade failed - iteratively identify failing fields and upgrade the rest
            error_str = str(e)
            tb = traceback.format_exc()
            
            print(f"\n[FAILED] Full asset upgrade failed: {error_str}")
            print(f"\nIdentifying failing fields and upgrading working fields...")
            
            field_conversion_map = {
                "session": "acquisition",
                "rig": "instrument",
            }
            
            # Try to identify which fields are causing the failure by testing each one individually
            problematic_fields = []
            for field_name in core_files:
                if field_name in asset_data and asset_data[field_name] is not None:
                    test_asset = {
                        "_id": asset_data.get("_id"),
                        "name": asset_data.get("name"),
                        "created": asset_data.get("created"),
                        "data_description": {  # Minimal valid data_description as placeholder
                            "creation_time": asset_data.get("created"),
                            "name": asset_data.get("name"),
                            "investigators": [],
                            "modality": ["Behavior"],
                            "subject_id": "test",
                        },
                        field_name: asset_data[field_name],
                    }
                    
                    try:
                        test_upgrader = Upgrade(test_asset)
                        print(f"  [OK] {field_name}: No validation errors")
                    except Exception as test_error:
                        test_error_str = str(test_error)
                        # This field has a validation error
                        problematic_fields.append(field_name)
                        field_results[field_name] = {
                            "success": False,
                            "error": test_error_str,
                            "traceback": traceback.format_exc(),
                            "original": json.loads(json.dumps(asset_data[field_name], default=str)),
                        }
                        failed_fields.append(field_name)
                        print(f"  [FAIL] {field_name}: {test_error_str[:100]}")
            
            # Now upgrade each non-problematic field individually with minimal placeholders
            print(f"\nUpgrading non-problematic fields individually...")
            for field_name in core_files:
                if field_name not in problematic_fields and field_name in asset_data and asset_data[field_name] is not None:
                    test_asset = {
                        "_id": asset_data.get("_id"),
                        "name": asset_data.get("name"),
                        "created": asset_data.get("created"),
                        "data_description": {  # Minimal valid data_description as placeholder
                            "creation_time": asset_data.get("created"),
                            "name": asset_data.get("name"),
                            "investigators": [],
                            "modality": ["Behavior"],
                            "subject_id": "test",
                        },
                        field_name: asset_data[field_name],
                    }
                    
                    try:
                        test_upgrader = Upgrade(test_asset)
                        test_upgraded = test_upgrader.metadata.model_dump()
                        
                        upgraded_field_name = field_conversion_map.get(field_name, field_name)
                        
                        if upgraded_field_name in test_upgraded:
                            field_results[field_name] = {
                                "success": True,
                                "original": json.loads(json.dumps(asset_data[field_name], default=str)),
                                "upgraded": json.loads(json.dumps(test_upgraded[upgraded_field_name], default=str)),
                                "converted_to": upgraded_field_name if field_name != upgraded_field_name else None,
                            }
                            successful_fields.append(field_name)
                            print(f"  [SUCCESS] {field_name}" + (f" -> {upgraded_field_name}" if field_name != upgraded_field_name else ""))
                    
                    except Exception as field_error:
                        # Shouldn't happen since we already tested, but handle it
                        print(f"  [WARN] {field_name}: Unexpected error during individual upgrade: {str(field_error)[:100]}")
                        field_results[field_name] = {
                            "success": None,
                            "original": json.loads(json.dumps(asset_data[field_name], default=str)),
                            "info": "Could not be upgraded individually"
                        }
            
            # Store overall error info (for the full asset upgrade failure)
            result["overall_error"] = error_str
            result["overall_traceback"] = tb
        
        result["field_results"] = field_results
        result["successful_fields"] = successful_fields
        result["failed_fields"] = failed_fields
        result["partial_success"] = len(successful_fields) > 0 and len(failed_fields) > 0
        result["original_data"] = json.loads(json.dumps(asset_data, default=str))
        
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

        # Try to upgrade (Upgrade class does everything in __init__)
        print(f"\nUpgrading asset: {result['asset_id']}")
        print(f"Name: {result['asset_name']}")
        print(f"Created: {result['created']}")

        upgrader = Upgrade(asset_data)

        # The upgrader automatically processes everything, we just need to get the result
        upgraded_data = upgrader.metadata.model_dump()

        # Compare original to upgraded to see what changed
        upgraded_files = []
        unchanged_files = []

        for core_file in [
            "acquisition",
            "data_description",
            "instrument",
            "procedures",
            "processing",
            "rig",
            "session",
            "subject",
            "quality_control",
        ]:
            if core_file in upgraded_data:
                if core_file in asset_data:
                    # File existed before
                    if upgraded_data[core_file] != asset_data[core_file]:
                        upgraded_files.append(core_file)
                    else:
                        unchanged_files.append(core_file)
                else:
                    # File is new (e.g., session -> acquisition conversion)
                    upgraded_files.append(f"{core_file} (new)")

        # Check for conversions (session -> acquisition)
        if "session" in asset_data and "session" not in upgraded_data and "acquisition" in upgraded_data:
            upgraded_files.append("session (converted to acquisition)")

        result["success"] = True
        result["upgraded_files"] = upgraded_files
        result["unchanged_files"] = unchanged_files
        # Convert to JSON-serializable format
        result["original_data"] = json.loads(json.dumps(asset_data, default=str))
        result["upgraded_data"] = json.loads(json.dumps(upgraded_data, default=str))

        print(f"\n[SUCCESS] Upgrade completed")
        print(f"  Changed: {', '.join(upgraded_files) if upgraded_files else 'None'}")
        print(f"  Unchanged: {', '.join(unchanged_files) if unchanged_files else 'None'}")

    except Exception as e:
        error_str = str(e)
        tb = traceback.format_exc()

        result["error"] = error_str
        result["traceback"] = tb
        # Include original data even on failure for comparison
        if "asset_data" in locals():
            result["original_data"] = json.loads(json.dumps(asset_data, default=str))

        print(f"\n[FAILED] Upgrade failed")
        print(f"Error: {error_str}")
        print(f"\nTraceback:")
        print(tb)

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
