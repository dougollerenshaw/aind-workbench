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


def extract_all_errors_from_traceback(tb_str: str, last_error: str) -> list:
    """
    Extract all error messages from a traceback string.
    Handles cases where exceptions occur during exception handling.
    
    Returns a list of error messages, with the most specific ones first.
    """
    errors = []
    
    # Check if traceback contains "During handling of the above exception"
    if "During handling of the above exception" in tb_str:
        # Split on this marker to get separate error sections
        parts = tb_str.split("During handling of the above exception")
        
        # Extract error from first part (before "During handling")
        first_part = parts[0]
        # Look for ValidationError or other error patterns
        if "ValidationError:" in first_part:
            # Extract ValidationError message
            val_error_start = first_part.find("ValidationError:")
            if val_error_start != -1:
                val_error_section = first_part[val_error_start:]
                # Get the error message (usually a few lines after ValidationError:)
                val_error_lines = val_error_section.split("\n")
                if len(val_error_lines) > 1:
                    # Combine the error type and first few meaningful lines
                    error_msg = val_error_lines[0]
                    for line in val_error_lines[1:6]:  # Get up to 5 more lines
                        if line.strip() and not line.strip().startswith("File"):
                            error_msg += "\n" + line.strip()
                    errors.append(error_msg.strip())
        
        # Extract error from second part (after "During handling")
        if len(parts) > 1:
            second_part = parts[1]
            # Look for the final error
            if "Error:" in second_part or "Exception:" in second_part or "ValueError:" in second_part:
                # Extract the error message
                for error_type in ["ValidationError:", "ValueError:", "TypeError:", "KeyError:", "AttributeError:"]:
                    if error_type in second_part:
                        error_start = second_part.find(error_type)
                        error_section = second_part[error_start:]
                        error_lines = error_section.split("\n")
                        if len(error_lines) > 0:
                            error_msg = error_lines[0]
                            for line in error_lines[1:6]:
                                if line.strip() and not line.strip().startswith("File"):
                                    error_msg += "\n" + line.strip()
                            errors.append(error_msg.strip())
                            break
    
    # If we didn't find multiple errors, just use the last error
    if not errors:
        errors.append(last_error)
    
    return errors


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
            
            # Extract all errors from the full asset upgrade traceback
            all_errors_from_traceback = extract_all_errors_from_traceback(tb, error_str)
            
            # Try to match errors to fields by looking for field names in traceback paths
            # More specific patterns to avoid false matches
            field_errors_from_traceback = {}
            for field_name in core_files:
                # Look for field name in traceback file paths - use more specific patterns
                field_patterns = [
                    f"/{field_name}/v1v2.py",  # Most specific
                    f"/{field_name}/v1v2_",   # Alternative pattern (e.g., v1v2_procedures.py)
                    f"/{field_name}_",        # Even more alternative (e.g., procedures/v1v2_procedures.py)
                    f"\\{field_name}\\v1v2.py",  # Windows path
                ]
                for pattern in field_patterns:
                    if pattern in tb:
                        # Find all occurrences of this pattern
                        pattern_positions = []
                        start = 0
                        while True:
                            pos = tb.find(pattern, start)
                            if pos == -1:
                                break
                            pattern_positions.append(pos)
                            start = pos + 1
                        
                        # For each occurrence, find the nearest error
                        for pattern_pos in pattern_positions:
                            # Look for errors in a window around this field
                            window_start = max(0, pattern_pos - 1000)
                            window_end = min(len(tb), pattern_pos + 2000)
                            window = tb[window_start:window_end]
                            
                            # Check each extracted error to see if it appears in this window
                            for error_msg in all_errors_from_traceback:
                                # Check if key parts of the error appear in this window
                                error_keywords = error_msg.split()[:5]  # First few words
                                if all(keyword in window for keyword in error_keywords[:3] if len(keyword) > 3):
                                    # This error is associated with this field
                                    if field_name not in field_errors_from_traceback:
                                        field_errors_from_traceback[field_name] = error_msg
                                        print(f"  [FOUND] {field_name} error in traceback: {error_msg[:100]}")
                                        break
                            if field_name in field_errors_from_traceback:
                                break
                        if field_name in field_errors_from_traceback:
                            break

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
                    # Note: We'll test fields individually first, and only use traceback errors
                    # if individual testing doesn't reveal the field's own error
                    
                    # First, test the field WITHOUT data_description to see if it has its own errors
                    test_asset_no_dd = {
                        "_id": asset_data.get("_id"),
                        "name": asset_data.get("name"),
                        "created": asset_data.get("created"),
                        field_name: asset_data[field_name],
                    }
                    
                    field_has_own_error = False
                    field_own_error = None
                    field_own_tb = None
                    
                    try:
                        test_upgrader_no_dd = Upgrade(test_asset_no_dd)
                        test_upgraded_no_dd = test_upgrader_no_dd.metadata.model_dump()
                        
                        # Field upgraded successfully without data_description!
                        upgraded_field_name = field_conversion_map.get(field_name, field_name)
                        if upgraded_field_name in test_upgraded_no_dd:
                            field_results[field_name] = {
                                "success": True,
                                "original": json.loads(json.dumps(asset_data[field_name], default=str)),
                                "upgraded": json.loads(json.dumps(test_upgraded_no_dd[upgraded_field_name], default=str)),
                                "converted_to": upgraded_field_name if field_name != upgraded_field_name else None,
                            }
                            successful_fields.append(field_name)
                            print(
                                f"  [SUCCESS] {field_name}"
                                + (f" -> {upgraded_field_name}" if field_name != upgraded_field_name else "")
                            )
                            continue  # Skip to next field
                    except Exception as field_error_no_dd:
                        # Check if error is about missing data_description or if it's the field's own validation error
                        error_str_no_dd = str(field_error_no_dd)
                        error_lower = error_str_no_dd.lower()
                        tb_no_dd = traceback.format_exc()
                        
                        # Extract all errors from traceback (in case there are multiple)
                        all_errors = extract_all_errors_from_traceback(tb_no_dd, error_str_no_dd)
                        
                        # If error mentions data_description, it might be a dependency issue
                        # Otherwise, it's likely the field's own validation error
                        if "data_description" not in error_lower and "data description" not in error_lower:
                            # Field has its own error (not a dependency issue)
                            field_has_own_error = True
                            # Combine all errors if there are multiple
                            if len(all_errors) > 1:
                                field_own_error = "Multiple errors found:\n\n" + "\n\n".join(f"{i+1}. {err}" for i, err in enumerate(all_errors))
                            else:
                                field_own_error = error_str_no_dd
                            field_own_tb = tb_no_dd
                            print(f"  [ERROR] {field_name} (own error): {field_own_error[:100]}")
                        # If error is about data_description, we'll test with data_description below
                    
                    # If field has its own error, record it and skip testing with data_description
                    if field_has_own_error:
                        field_errors[field_name] = (field_own_error, field_own_tb, None, False)
                        continue
                    
                    # Field doesn't have its own error, so test WITH data_description to check for dependency issues
                    test_asset_with_dd = {
                        "_id": asset_data.get("_id"),
                        "name": asset_data.get("name"),
                        "created": asset_data.get("created"),
                        field_name: asset_data[field_name],
                    }
                    
                    used_dd = False
                    if "data_description" in asset_data and field_name != "data_description":
                        test_asset_with_dd["data_description"] = asset_data["data_description"]
                        used_dd = True
                        fields_using_data_description.add(field_name)
                    
                    try:
                        test_upgrader_with_dd = Upgrade(test_asset_with_dd)
                        test_upgraded_with_dd = test_upgrader_with_dd.metadata.model_dump()
                        
                        # This field upgraded successfully with data_description!
                        upgraded_field_name = field_conversion_map.get(field_name, field_name)
                        if upgraded_field_name in test_upgraded_with_dd:
                            field_results[field_name] = {
                                "success": True,
                                "original": json.loads(json.dumps(asset_data[field_name], default=str)),
                                "upgraded": json.loads(json.dumps(test_upgraded_with_dd[upgraded_field_name], default=str)),
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
                    
                    except Exception as field_error_with_dd:
                        test_error_str = str(field_error_with_dd)
                        tb = traceback.format_exc()
                        
                        # Extract all errors from traceback (in case there are multiple)
                        all_errors = extract_all_errors_from_traceback(tb, test_error_str)
                        
                        # Combine all errors if there are multiple
                        if len(all_errors) > 1:
                            combined_error = "Multiple errors found:\n\n" + "\n\n".join(f"{i+1}. {err}" for i, err in enumerate(all_errors))
                            field_errors[field_name] = (combined_error, tb, None, used_dd)
                        else:
                            field_errors[field_name] = (test_error_str, tb, None, used_dd)
                        print(f"  [ERROR] {field_name} (with data_description): {test_error_str[:100]}")
            
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
                        # Check if this field has its own error in the traceback
                        # If so, it's not just a dependency - it has its own validation error
                        if field_name in field_errors_from_traceback:
                            # Field has its own error from traceback - use that instead
                            field_results[field_name] = {
                                "success": False,
                                "error": field_errors_from_traceback[field_name],
                                "traceback": tb,
                                "original": json.loads(json.dumps(asset_data[field_name], default=str)),
                            }
                            failed_fields.append(field_name)
                            print(f"  [FAIL] {field_name} (own error from traceback): {field_errors_from_traceback[field_name][:100]}")
                        else:
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
            # Format with all errors if multiple found
            if len(all_errors_from_traceback) > 1:
                result["overall_error"] = "Multiple errors found:\n\n" + "\n\n".join(f"{i+1}. {err}" for i, err in enumerate(all_errors_from_traceback))
            else:
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
