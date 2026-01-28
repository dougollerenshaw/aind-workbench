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
                        print(
                            f"  [OK] {field_name}"
                            + (f" -> {upgraded_field_name}" if field_name != upgraded_field_name else "")
                        )
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
            # Use the ACTUAL asset data_description (if present) rather than a placeholder
            print(f"\nTrying to identify which specific fields have validation errors...")
            
            # First pass: Try to upgrade each field and collect all errors
            field_errors = {}  # field_name -> (error_str, traceback, is_direct_error, used_data_description)
            fields_using_data_description = set()  # Track which fields were tested with data_description
            
            for field_name in core_files:
                if field_name in asset_data and asset_data[field_name] is not None:
                    # Create test asset with this field + data_description from actual asset
                    test_asset = {
                        "_id": asset_data.get("_id"),
                        "name": asset_data.get("name"),
                        "created": asset_data.get("created"),
                        field_name: asset_data[field_name],
                    }

                    # Add data_description if it exists and isn't the field we're testing
                    used_dd = False
                    if "data_description" in asset_data and field_name != "data_description":
                        test_asset["data_description"] = asset_data["data_description"]
                        used_dd = True
                        fields_using_data_description.add(field_name)

                    try:
                        test_upgrader = Upgrade(test_asset)
                        test_upgraded = test_upgrader.metadata.model_dump()

                        # This field upgraded successfully!
                        upgraded_field_name = field_conversion_map.get(field_name, field_name)

                        if upgraded_field_name in test_upgraded:
                            field_results[field_name] = {
                                "success": True,
                                "original": json.loads(json.dumps(asset_data[field_name], default=str)),
                                "upgraded": json.loads(json.dumps(test_upgraded[upgraded_field_name], default=str)),
                                "converted_to": upgraded_field_name if field_name != upgraded_field_name else None,
                            }
                            successful_fields.append(field_name)
                            print(
                                f"  [SUCCESS] {field_name}"
                                + (f" -> {upgraded_field_name}" if field_name != upgraded_field_name else "")
                            )
                        else:
                            # Field not in upgraded output (unusual)
                            field_errors[field_name] = ("Field not present in upgraded output", None, True, used_dd)
                            print(f"  [WARN] {field_name}: Not in upgraded output")

                    except Exception as field_error:
                        test_error_str = str(field_error)
                        tb = traceback.format_exc()
                        field_errors[field_name] = (test_error_str, tb, None, used_dd)  # None means we'll determine later
                        print(f"  [ERROR] {field_name}: {test_error_str[:100]}")
            
            # Second pass: First identify all direct validation errors
            direct_validation_errors = {}
            for field_name, (error_str, tb, is_direct, used_dd) in field_errors.items():
                if is_direct is True:
                    # Already marked as direct error
                    direct_validation_errors[field_name] = error_str
                elif field_name == "data_description":
                    # data_description is always a direct error (no dependencies)
                    direct_validation_errors[field_name] = error_str
                else:
                    # Check if this error is about a dependency field
                    dependency_field = None
                    for dep_field in core_files:
                        if dep_field != field_name:
                            # Check if error mentions this dependency field
                            # Common patterns: "Failed to validate {field}", "{field} validation", etc.
                            dep_patterns = [
                                f"Failed to validate {dep_field}",
                                f"validate {dep_field}",
                                f"{dep_field} validation",
                                f"{dep_field} error",
                            ]
                            error_lower = error_str.lower()
                            if any(pattern.lower() in error_lower for pattern in dep_patterns):
                                dependency_field = dep_field
                                break
                    
                    # If error is about a dependency, it's not a direct error (yet)
                    # Otherwise, it's a direct validation error
                    if not dependency_field:
                        direct_validation_errors[field_name] = error_str
            
            # Third pass: Now classify errors as direct vs dependency
            # IMPORTANT: Check for dependencies FIRST, before treating as direct error
            for field_name, (error_str, tb, is_direct, used_dd) in field_errors.items():
                if is_direct is True:
                    # Already marked as direct error
                    field_results[field_name] = {
                        "success": False,
                        "error": error_str,
                        "traceback": tb,
                        "original": json.loads(json.dumps(asset_data[field_name], default=str)),
                    }
                    failed_fields.append(field_name)
                else:
                    # Check if this error is about a dependency field that has a direct error
                    dependency_field = None
                    
                    # data_description should never be a dependency - it's always a direct error if it fails
                    if field_name == "data_description":
                        # This is a direct validation error
                        field_results[field_name] = {
                            "success": False,
                            "error": error_str,
                            "traceback": tb,
                            "original": json.loads(json.dumps(asset_data[field_name], default=str)),
                        }
                        failed_fields.append(field_name)
                        print(f"  [FAIL] {field_name}: {error_str[:100]}")
                        continue
                    
                    # Special case: if this field was tested with data_description and data_description has a direct error,
                    # then it's likely a dependency issue (unless the error clearly indicates this field has its own problem)
                    if used_dd and "data_description" in direct_validation_errors:
                        dd_error = direct_validation_errors["data_description"]
                        # Check if errors match (first 50 chars) - if they do, it's the same error = dependency
                        error_start = error_str.strip()[:50]
                        dd_error_start = dd_error.strip()[:50]
                        if error_start == dd_error_start:
                            dependency_field = "data_description"
                    
                    # General case: check if error mentions any dependency field
                    if not dependency_field:
                        for dep_field in core_files:
                            if dep_field != field_name and dep_field in direct_validation_errors:
                                dep_error = direct_validation_errors[dep_field]
                                
                                # Check if error mentions this dependency field explicitly
                                dep_patterns = [
                                    f"Failed to validate {dep_field}",
                                    f"validate {dep_field}",
                                    f"{dep_field} validation",
                                    f"{dep_field} error",
                                ]
                                error_lower = error_str.lower()
                                if any(pattern.lower() in error_lower for pattern in dep_patterns):
                                    dependency_field = dep_field
                                    break
                                
                                # Also check if the error message is the same or very similar
                                if error_str.strip() == dep_error.strip() or error_str.strip()[:100] == dep_error.strip()[:100]:
                                    dependency_field = dep_field
                                    break
                    
                    if dependency_field:
                        # This is a dependency error
                        field_results[field_name] = {
                            "success": None,  # Neither success nor failure - dependency issue
                            "original": json.loads(json.dumps(asset_data[field_name], default=str)),
                            "info": f"Cannot upgrade {field_name} because a valid {dependency_field} is required. See the {dependency_field} upgrade error above.",
                        }
                        print(f"  [DEPENDENCY] {field_name}: Requires valid {dependency_field}")
                    else:
                        # This is a direct validation error
                        field_results[field_name] = {
                            "success": False,
                            "error": error_str,
                            "traceback": tb,
                            "original": json.loads(json.dumps(asset_data[field_name], default=str)),
                        }
                        failed_fields.append(field_name)
                        print(f"  [FAIL] {field_name}: {error_str[:100]}")
            
            # Handle fields that don't exist in the original asset
            for field_name in core_files:
                if field_name not in asset_data or asset_data[field_name] is None:
                    field_results[field_name] = {
                        "success": None,
                        "original": None,
                        "info": "Field not present in original asset",
                    }
                    print(f"  [INFO] {field_name}: Not present in original asset")

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
