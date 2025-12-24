from aind_data_access_api.document_db import MetadataDbClient
from aind_metadata_upgrader.upgrade import Upgrade

# Initialize client for v1 database
client = MetadataDbClient(
    host="api.allenneuraldynamics.org",
    database="metadata_index",
    collection="data_assets",
)

# Get the specific asset that failed to upgrade
# asset_name = "behavior_754571_2024-09-19_10-59-38"
asset_name = "behavior_745306_2024-10-17_13-33-18"
pipeline = [{"$match": {"name": asset_name}}, {"$limit": 1}]

results = client.aggregate_docdb_records(pipeline)

print(f"Running upgrader for asset: {asset_name}")
if not results:
    print(f"Asset '{asset_name}' not found in v1 database")
else:
    record = results[0]

    # Try to upgrade and capture the error
    try:
        upgrader = Upgrade(record, skip_metadata_validation=False)
        print(f"SUCCESS: {asset_name}")
    except Exception as e:
        print(f"FAILED: {asset_name}")
        print(f"  Error: {type(e).__name__}: {str(e)}")

        # Check which required files are actually missing
        required_files = [
            "data_description",
            "procedures",
            "instrument",
            "acquisition",
        ]
        missing = []
        found = []

        for file in required_files:
            # Check if key exists in record (even if None/empty)
            key_exists = file in record
            has_file = key_exists and record.get(file)
            # Special case: instrument can come from rig
            if file == "instrument" and not has_file:
                has_rig = "rig" in record and record.get("rig")
                if has_rig:
                    found.append(f"{file} (via rig)")
                else:
                    missing.append(file)
            elif has_file:
                found.append(file)
            elif key_exists:
                # Key exists but is None/empty - might be invalid
                found.append(f"{file} (exists but empty/None)")
            else:
                missing.append(file)

        if missing:
            print(f"  Missing required files: {missing}")
        if found:
            print(f"  Found required files: {found}")
