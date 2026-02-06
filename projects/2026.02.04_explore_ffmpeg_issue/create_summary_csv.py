#!/usr/bin/env python3
"""
Simple script to export affected assets to CSV.

Finds assets with aind-behavior-video-transformation version < 0.2.1
and outputs their details to a CSV file.

Usage:
    python export_affected_assets.py --output affected_assets.csv
"""

import argparse
import pandas as pd
from aind_data_access_api.document_db import MetadataDbClient


def query_affected_assets():
    """
    Query DocDB for affected assets.

    Returns:
        List of assets with relevant fields
    """
    print("Querying DocDB for affected assets...")

    # Initialize DocDB client
    client = MetadataDbClient(
        host="api.allenneuraldynamics.org",
        database="metadata_index",
        collection="data_assets",
    )

    pipeline = [
        {
            "$match": {
                "processing.processing_pipeline.data_processes": {
                    "$elemMatch": {
                        "code_url": {"$regex": "aind-behavior-video-transformation", "$options": "i"},
                        "software_version": {"$lt": "0.2.1"},
                    }
                }
            }
        },
        {"$unwind": "$processing.processing_pipeline.data_processes"},
        {
            "$match": {
                "processing.processing_pipeline.data_processes.code_url": {
                    "$regex": "aind-behavior-video-transformation",
                    "$options": "i",
                },
                "processing.processing_pipeline.data_processes.software_version": {"$lt": "0.2.1"},
            }
        },
        {
            "$project": {
                "_id": 1,
                "name": 1,
                "location": 1,
                "code_url": "$processing.processing_pipeline.data_processes.code_url",
                "software_version": "$processing.processing_pipeline.data_processes.software_version",
                "compression_requested": "$processing.processing_pipeline.data_processes.parameters.compression_requested",
                "start_date_time": "$processing.processing_pipeline.data_processes.start_date_time",
            }
        },
        {"$sort": {"start_date_time": -1}},
    ]

    assets = list(client.aggregate_docdb_records(pipeline))
    print(f"Found {len(assets)} affected assets")

    return assets


def export_to_csv(assets, output_file):
    """
    Export assets to CSV.

    Args:
        assets: List of asset records
        output_file: Path to output CSV file
    """
    print(f"Writing to {output_file}...")

    # Process assets to flatten the data
    processed_assets = []
    for asset in assets:
        compression_requested = asset.get("compression_requested")
        processed_assets.append({
            "asset_id": asset.get("_id", ""),
            "asset_name": asset.get("name", ""),
            "s3_location": asset.get("location", ""),
            "code_url": asset.get("code_url", ""),
            "software_version": asset.get("software_version", ""),
            "start_date_time": asset.get("start_date_time", ""),
            "has_compression_requested": compression_requested is not None,
            "compression_enum": compression_requested.get("compression_enum", "") if isinstance(compression_requested, dict) else "",
        })

    # Convert to DataFrame and save
    df = pd.DataFrame(processed_assets)
    df.to_csv(output_file, index=False)

    print(f"Successfully wrote {len(assets)} records to {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Export affected assets to CSV")
    parser.add_argument(
        "--output", default="affected_assets.csv", help="Output CSV file (default: affected_assets.csv)"
    )

    args = parser.parse_args()

    # Query DocDB
    assets = query_affected_assets()

    # Export to CSV
    export_to_csv(assets, args.output)

    print("\nDone!")


if __name__ == "__main__":
    main()
