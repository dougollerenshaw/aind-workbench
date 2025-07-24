#!/usr/bin/env python3
"""
Simple script to extract unique subject IDs from JSON files in the barseq_metadata folder.
"""

import json
import pandas as pd
from pathlib import Path

# Path to the barseq metadata folder
barseq_folder = Path("barseq_metadata")

# Set to store unique subject IDs
subject_ids = set()

# Walk through all JSON files in the barseq_metadata folder
for json_file in barseq_folder.rglob("*.json"):
    try:
        with open(json_file, 'r') as f:
            data = json.load(f)
            # Extract subject_id (handles both direct and nested structures)
            if isinstance(data, dict):
                if "subject_id" in data:
                    subject_ids.add(data["subject_id"])
                elif "data" in data and isinstance(data["data"], dict) and "subject_id" in data["data"]:
                    subject_ids.add(data["data"]["subject_id"])
    except:
        continue  # Skip files that can't be parsed

# Create DataFrame and save to CSV
df = pd.DataFrame({"subject_id": sorted(subject_ids)})
df.to_csv("subject_ids.csv", index=False)

print(f"Found {len(subject_ids)} unique subject IDs: {sorted(subject_ids)}")
print("Results saved to subject_ids.csv")
