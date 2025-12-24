from aind_data_access_api.document_db import MetadataDbClient

client = MetadataDbClient(
    host="api.allenneuraldynamics.org",
    database="metadata_index",
    collection="data_assets",
)

# First, get total count
count_pipeline = [
    {
        "$match": {
            "location": {"$regex": "^s3://aind-private-data"},
            "procedures": {"$in": [None, ""]},
        }
    },
    {"$count": "total"},
]

count_result = client.aggregate_docdb_records(count_pipeline)
total_count = count_result[0]["total"] if count_result else 0

# Query for records in private bucket missing procedures
pipeline = [
    {
        "$match": {
            "location": {"$regex": "^s3://aind-private-data"},
            "procedures": {"$in": [None, ""]},
        }
    },
    {
        "$project": {
            "name": 1,
            "location": 1,
            "procedures": 1,
            "data_description": 1,
            "acquisition": 1,
            "rig": 1,
            "instrument": 1,
        }
    },
    {"$limit": 100},
]

results = client.aggregate_docdb_records(pipeline)

print(f"Total records in private bucket missing procedures: {total_count}")
print(f"Showing first {len(results)} records")
print("=" * 80)

# Track statistics
stats = {
    "missing_data_description": 0,
    "missing_procedures": 0,
    "missing_acquisition": 0,
    "missing_instrument": 0,
    "has_rig": 0,
}

for record in results:
    name = record.get("name", "unknown")
    location = record.get("location", "unknown")

    # Check which required files are missing
    has_data_description = bool(record.get("data_description"))
    has_procedures = bool(record.get("procedures"))
    has_acquisition = bool(record.get("acquisition"))
    has_rig = bool(record.get("rig"))
    has_instrument = bool(record.get("instrument"))

    # Update stats
    if not has_data_description:
        stats["missing_data_description"] += 1
    if not has_procedures:
        stats["missing_procedures"] += 1
    if not has_acquisition:
        stats["missing_acquisition"] += 1
    if not has_rig and not has_instrument:
        stats["missing_instrument"] += 1
    if has_rig:
        stats["has_rig"] += 1

    missing = []
    if not has_data_description:
        missing.append("data_description")
    if not has_procedures:
        missing.append("procedures")
    if not has_acquisition:
        missing.append("acquisition")
    if not has_rig and not has_instrument:
        missing.append("instrument (no rig or instrument)")

    print(f"\n{name}")
    print(f"  Location: {location}")
    print(f"  Missing: {', '.join(missing) if missing else 'none'}")
    print(
        f"  Has: data_description={has_data_description}, rig={has_rig}, instrument={has_instrument}"
    )

print("\n" + "=" * 80)
print("SUMMARY (of shown records):")
print("=" * 80)
print(f"Missing data_description: {stats['missing_data_description']}")
print(f"Missing procedures: {stats['missing_procedures']}")
print(f"Missing acquisition: {stats['missing_acquisition']}")
print(
    f"Missing instrument (no rig or instrument): {stats['missing_instrument']}"
)
print(f"Has rig (can be converted to instrument): {stats['has_rig']}")
