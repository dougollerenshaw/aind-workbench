from aind_data_access_api.document_db import MetadataDbClient
from aind_metadata_upgrader.upgrade import Upgrade

client = MetadataDbClient(
    host="api.allenneuraldynamics.org",
    database="metadata_index",
    collection="data_assets",
)

record = client.aggregate_docdb_records(
    [{"$match": {"name": "behavior_754574_2024-11-22_09-39-39"}}]
)[0]

try:
    Upgrade(record, skip_metadata_validation=False)
    print("SUCCESS")
except Exception as e:
    print(f"FAILED: {e}")
