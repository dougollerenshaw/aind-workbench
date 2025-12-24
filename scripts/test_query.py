from aind_data_access_api.document_db import MetadataDbClient
import pandas as pd

# Initialize client with public API endpoint
client = MetadataDbClient(
    host="api.allenneuraldynamics.org",
    database="metadata_index",
    collection="data_assets",
)

# Run the aggregation
pipeline = [
    {
        "$match": {
            "data_description.project_name": "Cognitive flexibility in patch foraging"
        }
    },
    {
        "$project": {
            "bucket": {"$arrayElemAt": [{"$split": ["$location", "/"]}, 2]},
            "created": 1,
        }
    },
    {
        "$group": {
            "_id": "$bucket",
            "count": {"$sum": 1},
            "first_date": {"$min": "$created"},
            "last_date": {"$max": "$created"},
        }
    },
    {"$sort": {"first_date": 1}},
]

results = client.aggregate_docdb_records(pipeline)

# Convert to pandas DataFrame
df = pd.DataFrame(results)
df.rename(columns={"_id": "bucket"}, inplace=True)

# Clean up dates to just show YYYY-MM-DD
df["first_date"] = df["first_date"].str[:10]
df["last_date"] = df["last_date"].str[:10]

# Print as markdown
print(df.to_markdown(index=False))
