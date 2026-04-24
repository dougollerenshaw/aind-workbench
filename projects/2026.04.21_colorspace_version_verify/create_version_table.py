from aind_data_access_api.document_db import MetadataDbClient
import pandas as pd

CLIENT = MetadataDbClient(
    host="api.allenneuraldynamics.org",
    database="metadata_index",
    collection="data_assets",
)

pipeline = [
    {"$match": {
        "created": {"$gte": "2025-11-20", "$lte": "2025-12-15"},
        "processing.processing_pipeline.data_processes": {
            "$elemMatch": {
                "code_url": {"$regex": "aind-behavior-video-transformation", "$options": "i"}
            }
        }
    }},
    {"$unwind": "$processing.processing_pipeline.data_processes"},
    {"$match": {
        "processing.processing_pipeline.data_processes.code_url": {
            "$regex": "aind-behavior-video-transformation", "$options": "i"
        }
    }},
    {"$project": {
        "date": {"$substr": ["$created", 0, 10]},
        "version": "$processing.processing_pipeline.data_processes.software_version"
    }}
]

records = CLIENT.aggregate_docdb_records(pipeline=pipeline)
df = pd.DataFrame(records)
table = df.groupby(["date", "version"]).size().unstack(fill_value=0)
all_dates = pd.date_range("2025-11-20", "2025-12-15")
table.index = pd.to_datetime(table.index)
table = table.reindex(all_dates, fill_value=0)
table.index = table.index.strftime("%Y-%m-%d")
table.index.name = "date"
print(table.to_markdown())