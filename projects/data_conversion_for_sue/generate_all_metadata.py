#!/usr/bin/env python3
"""
Wrapper script to generate all metadata files for experiments.

This script runs both get_procedures_and_subject_metadata.py and make_data_descriptions.py
in sequence to ensure that all required metadata files are created for each experiment.

Usage:
    python generate_all_metadata.py [--output-dir OUTPUT_DIR] [--force-overwrite]
"""

import argparse
import subprocess
import sys
from pathlib import Path

def run_script(script_name: str, args: argparse.Namespace) -> bool:
    """
    Run a metadata generation script with the provided arguments.
    
    Args:
        script_name: Name of the script to run
        args: Command line arguments
        
    Returns:
        bool: True if script ran successfully, False otherwise
    """
    # Build command
    cmd = ["python", script_name]
    
    if args.output_dir:
        cmd.extend(["--output-dir", args.output_dir])
        
    if args.force_overwrite:
        cmd.append("--force-overwrite")
    
    print(f"Running: {' '.join(cmd)}")
    print("=" * 60)
    
    # Run the script
    try:
        result = subprocess.run(cmd, check=True, capture_output=False)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"Error running {script_name}: {e}")
        return False
    except FileNotFoundError:
        print(f"Error: {script_name} not found. Make sure you're in the correct directory.")
        return False

def main():
    """Main function to process command line arguments and run both scripts."""
    parser = argparse.ArgumentParser(
        description="Generate all metadata files for experiments by running both metadata scripts in sequence."
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for metadata files (default: same directory as script)",
    )
    parser.add_argument(
        "--force-overwrite",
        action="store_true",
        help="Force overwrite existing metadata files (default: skip existing files)",
    )
    
    args = parser.parse_args()
    
    print("AIND Metadata Generation Workflow")
    print("=" * 60)
    print("This script will run both metadata generation scripts in sequence:")
    print("1. get_procedures_and_subject_metadata.py - Fetches subject and procedures metadata")
    print("2. make_data_descriptions.py - Creates data description files")
    print("")
    
    # Check if required files exist
    script_dir = Path(__file__).parent
    script1 = script_dir / "get_procedures_and_subject_metadata.py"
    script2 = script_dir / "make_data_descriptions.py"
    inventory_file = script_dir / "asset_inventory.csv"
    
    missing_files = []
    if not script1.exists():
        missing_files.append(str(script1))
    if not script2.exists():
        missing_files.append(str(script2))
    if not inventory_file.exists():
        missing_files.append(str(inventory_file))
    
    if missing_files:
        print("Error: Required files not found:")
        for file in missing_files:
            print(f"  {file}")
        sys.exit(1)
    
    # Run the scripts in sequence
    success = True
    
    # Step 1: Get procedures and subject metadata
    print("\nSTEP 1: Fetching procedures and subject metadata...")
    if not run_script("get_procedures_and_subject_metadata.py", args):
        print("❌ Failed to fetch procedures and subject metadata")
        success = False
    else:
        print("✅ Successfully fetched procedures and subject metadata")
    
    print("\n" + "=" * 60)
    
    # Step 2: Generate data descriptions
    print("\nSTEP 2: Generating data description files...")
    if not run_script("make_data_descriptions.py", args):
        print("❌ Failed to generate data description files")
        success = False
    else:
        print("✅ Successfully generated data description files")
    
    # Final summary
    print("\n" + "=" * 60)
    print("METADATA GENERATION WORKFLOW COMPLETE")
    print("=" * 60)
    
    if success:
        print("✅ All metadata files have been generated successfully!")
        print("\nEach experiment now has its own folder with:")
        print("  - subject.json")
        print("  - procedures.json") 
        print("  - data_description.json")
        
        if args.output_dir:
            metadata_dir = Path(args.output_dir) / "metadata"
        else:
            metadata_dir = script_dir / "metadata"
        print(f"\nMetadata files are located in: {metadata_dir}")
    else:
        print("❌ Some errors occurred during metadata generation.")
        print("Please check the output above for details.")
        sys.exit(1)

if __name__ == "__main__":
    main()
