#!/usr/bin/env python3
"""
Generate Code Ocean commands to process affected assets through Galen's metadata fix capsule.

Usage:
    python generate_codeocean_commands.py --input affected_files.json --output batch_commands.sh
"""

import json
import argparse
from pathlib import Path


def generate_codeocean_commands(affected_assets, capsule_id="3921827", output_file=None):
    """
    Generate Code Ocean API commands to process affected assets

    Args:
        affected_assets: List of asset dictionaries with _id and location
        capsule_id: Code Ocean capsule ID (default: Galen's fix capsule)
        output_file: Optional file to write commands to
    """
    commands = []

    # Header
    commands.append("#!/bin/bash")
    commands.append("# Batch processing commands for ffmpeg metadata fix")
    commands.append(f"# Total assets to process: {len(affected_assets)}")
    commands.append(f"# Capsule ID: {capsule_id}")
    commands.append("")

    # Generate a command for each asset
    for i, asset in enumerate(affected_assets, 1):
        asset_id = asset["_id"]
        location = asset.get("location", "")
        name = asset.get("name", asset_id)

        # Extract S3 path
        # Format: s3://bucket/prefix

        command = f"# Asset {i}/{len(affected_assets)}: {name}"
        commands.append(command)

        # Code Ocean command format (this is a placeholder - adjust based on actual API)
        # You'll need to fill in the actual Code Ocean API command format
        co_command = f"# TODO: Code Ocean command to process {location}"
        commands.append(co_command)
        commands.append("")

    # Write to file if specified
    if output_file:
        with open(output_file, "w") as f:
            f.write("\n".join(commands))
        print(f"Commands written to: {output_file}")
    else:
        # Print to stdout
        print("\n".join(commands))


def generate_asset_list_for_capsule(affected_assets, output_file=None):
    """
    Generate a simple list of asset IDs and S3 locations

    Args:
        affected_assets: List of asset dictionaries
        output_file: Optional CSV file to write to
    """
    import csv

    if output_file:
        with open(output_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["asset_id", "asset_name", "s3_location"])

            for asset in affected_assets:
                writer.writerow([asset["_id"], asset.get("name", ""), asset.get("location", "")])

        print(f"Asset list written to: {output_file}")
    else:
        print("asset_id,asset_name,s3_location")
        for asset in affected_assets:
            print(f"{asset['_id']},{asset.get('name', '')},{asset.get('location', '')}")


def main():
    parser = argparse.ArgumentParser(description="Generate Code Ocean batch processing commands")
    parser.add_argument("--input", required=True, help="Input JSON file from identify_affected_mp4_files.py")
    parser.add_argument("--output", help="Output bash script file")
    parser.add_argument("--csv-output", help="Output CSV file with asset list")
    parser.add_argument("--capsule-id", default="3921827", help="Code Ocean capsule ID (default: Galen's fix capsule)")

    args = parser.parse_args()

    # Load input data
    print(f"Loading data from {args.input}...")
    with open(args.input, "r") as f:
        data = json.load(f)

    affected_assets = data.get("affected_assets", [])
    print(f"Loaded {len(affected_assets)} affected assets")

    # Generate commands
    if args.output:
        generate_codeocean_commands(affected_assets, capsule_id=args.capsule_id, output_file=args.output)

    # Generate CSV list
    if args.csv_output:
        generate_asset_list_for_capsule(affected_assets, output_file=args.csv_output)

    if not args.output and not args.csv_output:
        print("\nGenerating asset CSV to stdout:")
        generate_asset_list_for_capsule(affected_assets)


if __name__ == "__main__":
    main()
