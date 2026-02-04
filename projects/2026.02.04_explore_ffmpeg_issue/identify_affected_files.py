#!/usr/bin/env python3
"""
Script to identify .mp4 files affected by the ffmpeg metadata issue.

This script:
1. Queries DocDB for assets processed with aind-behavior-video-transformation < 0.2.1
2. Loads Jon's S3 file inventory JSON files
3. Cross-references to find all .mp4 files in affected assets
4. Outputs summary statistics and optionally a detailed list

Usage:
    python identify_affected_mp4_files.py --output affected_files.json
"""

import json
import argparse
from pathlib import Path
from typing import List, Dict, Set
from collections import defaultdict
from aind_data_access_api.document_db import MetadataDbClient


def query_affected_assets_from_docdb() -> List[Dict]:
    """
    Query DocDB for all assets with aind-behavior-video-transformation version < 0.2.1

    Returns:
        List of dicts with _id, name, and location fields
    """
    print("Querying DocDB for affected assets...")

    # Initialize DocDB client
    client = MetadataDbClient(
        host="api.allenneuraldynamics.org",
        database="metadata_index",
        collection="data_assets",
    )

    # MongoDB aggregation pipeline
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
        {"$project": {"_id": 1, "name": 1, "location": 1}},
    ]

    # Execute aggregation
    assets = list(client.aggregate_docdb_records(pipeline))
    print(f"Found {len(assets)} affected assets in DocDB")

    return assets


def load_s3_file_inventory(json_path: str) -> List[Dict]:
    """
    Load Jon's S3 file inventory JSON

    Args:
        json_path: Path to the JSON file

    Returns:
        List of file records
    """
    print(f"Loading S3 file inventory from {json_path}...")
    with open(json_path, "r") as f:
        files = json.load(f)
    print(f"Loaded {len(files)} file records")
    return files


def extract_asset_names(assets: List[Dict]) -> Set[str]:
    """
    Extract asset names (prefixes) from S3 locations

    Args:
        assets: List of asset records from DocDB

    Returns:
        Set of asset names/prefixes
    """
    asset_names = set()

    for asset in assets:
        location = asset.get("location", "")
        # Location format: s3://bucket-name/asset_name
        # We want the asset_name part
        if location.startswith("s3://"):
            # Split by '/' and get the last part
            parts = location.split("/")
            if len(parts) >= 4:
                asset_name = parts[-1]
                asset_names.add(asset_name)

        # Also add the 'name' field as a fallback
        if "name" in asset:
            asset_names.add(asset["name"])

    print(f"Extracted {len(asset_names)} unique asset names")
    return asset_names


def find_affected_mp4_files(file_inventory: List[Dict], affected_asset_names: Set[str]) -> List[Dict]:
    """
    Find all .mp4 files within affected asset locations

    This is the key cross-reference: we only want .mp4 files that are:
    1. In Jon's S3 file inventory (file_inventory)
    2. Within assets identified as affected in DocDB (affected_asset_names)

    Args:
        file_inventory: List of S3 file records from Jon
        affected_asset_names: Set of asset names from DocDB with version < 0.2.1

    Returns:
        List of affected .mp4 file records
    """
    print("Cross-referencing: Finding .mp4 files in affected assets...")
    print(f"  - Checking {len(file_inventory)} total S3 files")
    print(f"  - Against {len(affected_asset_names)} affected asset names from DocDB")

    # Diagnostic: Check if we can find any matches at all
    unique_acquisition_names = set(f.get("acquisition_name", "") for f in file_inventory)
    matches_found = len(affected_asset_names & unique_acquisition_names)
    print(f"  - Found {matches_found} matching asset names between DocDB and file inventory")

    affected_files = []
    assets_with_mp4 = set()

    for file_record in file_inventory:
        acquisition_name = file_record.get("acquisition_name", "")
        file_key = file_record.get("file_key", "")

        # Check if this file is in an affected asset (from DocDB)
        if acquisition_name in affected_asset_names:
            # Check if it's an .mp4 file
            if file_key.endswith(".mp4"):
                affected_files.append(file_record)
                assets_with_mp4.add(acquisition_name)

    print(f"Found {len(affected_files)} .mp4 files across {len(assets_with_mp4)} affected assets")
    print(
        f"Note: {len(affected_asset_names) - len(assets_with_mp4)} affected assets have NO .mp4 files (likely still .avi)"
    )
    return affected_files


def generate_summary(affected_files: List[Dict], affected_assets: List[Dict]) -> Dict:
    """
    Generate summary statistics

    Args:
        affected_files: List of affected .mp4 files (from cross-reference)
        affected_assets: List of affected assets from DocDB (version < 0.2.1)

    Returns:
        Dictionary with summary statistics
    """
    # Count files per asset
    files_per_asset = defaultdict(int)
    total_size = 0

    for file_record in affected_files:
        acquisition_name = file_record.get("acquisition_name", "")
        files_per_asset[acquisition_name] += 1
        total_size += file_record.get("file_size", 0)

    # Convert bytes to GB
    total_size_gb = total_size / (1024**3)

    # Key metrics
    total_docdb_assets = len(affected_assets)
    assets_with_mp4 = len(files_per_asset)
    assets_without_mp4 = total_docdb_assets - assets_with_mp4

    summary = {
        "total_affected_assets_from_docdb": total_docdb_assets,
        "assets_with_mp4_files": assets_with_mp4,
        "assets_without_mp4_files": assets_without_mp4,
        "pct_with_mp4": round((assets_with_mp4 / total_docdb_assets * 100), 1) if total_docdb_assets > 0 else 0,
        "total_affected_mp4_files": len(affected_files),
        "total_size_bytes": total_size,
        "total_size_gb": round(total_size_gb, 2),
        "avg_mp4_files_per_asset": round(len(affected_files) / assets_with_mp4, 2) if assets_with_mp4 > 0 else 0,
    }

    return summary


def main():
    parser = argparse.ArgumentParser(description="Identify .mp4 files affected by ffmpeg metadata issue")
    parser.add_argument(
        "--private-bucket-json",
        default="/allen/aind/scratch/jon.young/temp_video_file_lists/video_files_in_private_bucket.json",
        help="Path to private bucket JSON file",
    )
    parser.add_argument(
        "--open-bucket-json",
        default="/allen/aind/scratch/jon.young/temp_video_file_lists/video_files_in_open_bucket.json",
        help="Path to open bucket JSON file",
    )
    parser.add_argument("--output", help="Output file for affected files list (JSON format)")
    parser.add_argument(
        "--summary-only", action="store_true", help="Only print summary, do not save detailed file list"
    )

    args = parser.parse_args()

    # Step 1: Query DocDB for affected assets
    try:
        affected_assets = query_affected_assets_from_docdb()
    except Exception as e:
        print(f"Error querying DocDB: {e}")
        print("Continuing with empty asset list...")
        affected_assets = []

    # Step 2: Extract asset names
    affected_asset_names = extract_asset_names(affected_assets)

    # Diagnostic: Show a few sample asset names for verification
    if affected_asset_names:
        sample_names = list(affected_asset_names)[:5]
        print(f"Sample affected asset names (for verification): {sample_names}")

    # Step 3: Load S3 file inventories
    all_files = []

    for json_path in [args.private_bucket_json, args.open_bucket_json]:
        if Path(json_path).exists():
            try:
                files = load_s3_file_inventory(json_path)
                all_files.extend(files)
            except Exception as e:
                print(f"Error loading {json_path}: {e}")
        else:
            print(f"File not found: {json_path}")

    if not all_files:
        print("ERROR: No file inventory loaded. Cannot proceed.")
        return

    # Step 4: Find affected .mp4 files
    # This is the KEY cross-reference step:
    # - We have ~4,410 assets from DocDB with version < 0.2.1
    # - We have Jon's complete S3 file inventory
    # - We find ONLY the .mp4 files that are in BOTH lists
    # - Assets without .mp4 files (still .avi) don't need the fix
    affected_mp4_files = find_affected_mp4_files(all_files, affected_asset_names)

    # Step 5: Generate summary
    summary = generate_summary(affected_mp4_files, affected_assets)

    # Print summary
    print("\n" + "=" * 70)
    print("SUMMARY - Cross-Reference Results")
    print("=" * 70)
    print(f"Total affected assets (DocDB, version < 0.2.1): {summary['total_affected_assets_from_docdb']}")
    print(
        f"  ├─ Assets WITH .mp4 files:                    {summary['assets_with_mp4_files']} ({summary['pct_with_mp4']}%)"
    )
    print(f"  └─ Assets WITHOUT .mp4 files (likely .avi):   {summary['assets_without_mp4_files']}")
    print(f"\nTotal .mp4 files needing metadata fix:         {summary['total_affected_mp4_files']}")
    print(f"Total size of affected .mp4 files:             {summary['total_size_gb']} GB")
    print(f"Average .mp4 files per asset (with .mp4):      {summary['avg_mp4_files_per_asset']}")
    print("=" * 70)
    print("\nNote: Assets without .mp4 files likely still have original .avi files")
    print("      and do NOT need the metadata fix.")
    print("=" * 70)

    # Save detailed output if requested
    if args.output and not args.summary_only:
        output_data = {"summary": summary, "affected_assets": affected_assets, "affected_mp4_files": affected_mp4_files}

        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2)

        print(f"\nDetailed results saved to: {args.output}")

    # Also save just the asset IDs for easy batch processing
    if args.output and not args.summary_only:
        asset_ids_file = args.output.replace(".json", "_asset_ids.txt")
        with open(asset_ids_file, "w") as f:
            for asset in affected_assets:
                f.write(f"{asset['_id']}\n")
        print(f"Asset IDs saved to: {asset_ids_file}")


if __name__ == "__main__":
    main()
