from aind_data_access_api.document_db import MetadataDbClient
from aind_metadata_upgrader.upgrade import Upgrade
import json

client = MetadataDbClient(
    host="api.allenneuraldynamics.org",
    database="metadata_index",
    collection="data_assets",
)

asset1_name = "behavior_754571_2024-09-19_10-59-38"  # fails
asset2_name = "behavior_754574_2024-11-22_09-39-39"  # passes

pipeline1 = [{"$match": {"name": asset1_name}}, {"$limit": 1}]
pipeline2 = [{"$match": {"name": asset2_name}}, {"$limit": 1}]

record1 = client.aggregate_docdb_records(pipeline1)[0]
record2 = client.aggregate_docdb_records(pipeline2)[0]

# Check required files
required_files = [
    "data_description",
    "procedures",
    "instrument",
    "acquisition",
]

print("=" * 80)
print("REQUIRED FILES CHECK:")
print("=" * 80)

print("\nAsset 1 (fails):")
for file in required_files:
    has_file = file in record1 and record1.get(file)
    # Also check for rig if looking for instrument
    if file == "instrument" and not has_file:
        has_rig = "rig" in record1 and record1.get("rig")
        print(f"  {file}: {has_file} (rig exists: {bool(has_rig)})")
    else:
        print(f"  {file}: {bool(has_file)}")

print("\nAsset 2 (passes):")
for file in required_files:
    has_file = file in record2 and record2.get(file)
    # Also check for rig if looking for instrument
    if file == "instrument" and not has_file:
        has_rig = "rig" in record2 and record2.get("rig")
        print(f"  {file}: {has_file} (rig exists: {bool(has_rig)})")
    else:
        print(f"  {file}: {bool(has_file)}")

print("\n" + "=" * 80)

print("=" * 80)
print("ASSET 1 (FAILS):", asset1_name)
print("=" * 80)
if "rig" in record1 and record1["rig"]:
    mouse_platform1 = record1["rig"].get("mouse_platform")
    if mouse_platform1:
        print("mouse_platform keys:", list(mouse_platform1.keys()))
        print(
            "mouse_platform:",
            json.dumps(mouse_platform1, indent=2, default=str),
        )
    else:
        print("mouse_platform: None or missing")
else:
    print("rig: None or missing")

print("\n" + "=" * 80)
print("ASSET 2 (PASSES):", asset2_name)
print("=" * 80)
if "rig" in record2 and record2["rig"]:
    mouse_platform2 = record2["rig"].get("mouse_platform")
    if mouse_platform2:
        print("mouse_platform keys:", list(mouse_platform2.keys()))
        print(
            "mouse_platform:",
            json.dumps(mouse_platform2, indent=2, default=str),
        )
    else:
        print("mouse_platform: None or missing")
else:
    print("rig: None or missing")

print("\n" + "=" * 80)
print("TESTING RIG UPGRADE:")
print("=" * 80)

from aind_metadata_upgrader.upgrade import Upgrade

# Test asset 1 rig upgrade
print("\nAsset 1 (should fail):")
try:
    test_record1 = {
        "name": record1["name"],
        "location": record1.get("location"),
        "rig": record1["rig"],
    }
    test_upgrader1 = Upgrade(test_record1, skip_metadata_validation=True)
    print("  SUCCESS - rig upgraded")
except Exception as e:
    print(f"  FAILED: {type(e).__name__}: {str(e)}")

# Test asset 2 rig upgrade
print("\nAsset 2 (should pass):")
try:
    test_record2 = {
        "name": record2["name"],
        "location": record2.get("location"),
        "rig": record2["rig"],
    }
    test_upgrader2 = Upgrade(test_record2, skip_metadata_validation=True)
    print("  SUCCESS - rig upgraded")
except Exception as e:
    print(f"  FAILED: {type(e).__name__}: {str(e)}")

# Compare full rig structures
print("\n" + "=" * 80)
print("RIG STRUCTURE DIFFERENCES:")
print("=" * 80)

if "rig" in record1 and record1["rig"] and "rig" in record2 and record2["rig"]:
    rig1 = record1["rig"]
    rig2 = record2["rig"]

    all_keys = set(rig1.keys()) | set(rig2.keys())

    for key in sorted(all_keys):
        val1 = rig1.get(key)
        val2 = rig2.get(key)
        if val1 != val2:
            print(f"\n{key}:")
            if key == "mouse_platform":
                # Already compared, skip
                continue
            print(f"  Asset 1: {str(val1)[:200]}...")
            print(f"  Asset 2: {str(val2)[:200]}...")
