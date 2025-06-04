import os
import pandas as pd
import requests
import json
import argparse
from pathlib import Path
import numpy as np

# Get the directory containing this script
SCRIPT_DIR = Path(__file__).parent.absolute()


def get_unique_subjects(inventory_df: pd.DataFrame):
    """
    Get unique subject IDs from the asset inventory.

    Args:
        inventory_df: DataFrame containing session inventory

    Returns:
        list: List of unique subject IDs
    """
    unique_subjects = inventory_df["subject_id"].unique()
    # Remove any NaN values
    unique_subjects = [subj for subj in unique_subjects if pd.notna(subj)]
    return sorted(unique_subjects)


def fetch_metadata(
    subject_id: str,
    metadata_type: str,
    base_url: str = "http://aind-metadata-service",
):
    """
    Fetch metadata for a subject from the AIND metadata service.

    Args:
        subject_id: Subject ID to fetch metadata for
        metadata_type: Type of metadata ('procedures' or 'subject')
        base_url: Base URL for the metadata service

    Returns:
        tuple: (success: bool, data: dict or None, message: str)
    """
    try:
        url = f"{base_url}/{metadata_type}/{subject_id}"
        print(f"  Fetching {metadata_type} from: {url}")

        response = requests.get(url)
        print(f"    Response status: {response.status_code}")

        # Handle both successful responses (200) and 406 responses that contain data
        if response.status_code == 200:
            rj = response.json()
            data = rj.get("data")
            message = rj.get("message", "Success")

            if data is not None:
                return True, data, message
            else:
                return False, None, f"No data returned: {message}"

        elif response.status_code == 406:
            # 406 responses often still contain the data we need
            try:
                rj = response.json()
                data = rj.get("data")
                message = rj.get(
                    "message", "Success despite validation errors"
                )

                if data is not None:
                    return (
                        True,
                        data,
                        f"Success (with validation warnings): {message}",
                    )
                else:
                    return False, None, f"406 error and no data: {message}"
            except json.JSONDecodeError:
                return False, None, f"406 error and invalid JSON response"
        else:
            # For other error codes, raise the exception
            response.raise_for_status()

    except requests.exceptions.RequestException as e:
        return False, None, f"Request failed: {str(e)}"
    except json.JSONDecodeError as e:
        return False, None, f"JSON decode error: {str(e)}"
    except Exception as e:
        return False, None, f"Unexpected error: {str(e)}"


def save_metadata(
    data: dict, subject_id: str, metadata_type: str, metadata_base_dir: Path
):
    """
    Save metadata to a JSON file in the subject's folder.

    Args:
        data: Metadata dictionary to save
        subject_id: Subject ID
        metadata_type: Type of metadata ('procedures' or 'subject')
        metadata_base_dir: Base metadata directory
    """
    # Create subject-specific directory
    subject_dir = metadata_base_dir / subject_id
    subject_dir.mkdir(parents=True, exist_ok=True)

    # Use standardized filename based on metadata type
    filename = f"{metadata_type}.json"
    filepath = subject_dir / filename

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

    print(f"  Saved {metadata_type} metadata to: {filepath}")


def update_inventory_metadata_status(
    inventory_df: pd.DataFrame,
    subject_id: str,
    has_procedures: bool,
    has_subject: bool,
):
    """
    Update the asset inventory with metadata availability status.

    Args:
        inventory_df: DataFrame to update
        subject_id: Subject ID to update
        has_procedures: Whether procedures metadata was successfully fetched
        has_subject: Whether subject metadata was successfully fetched
    """
    # Add columns if they don't exist, with proper dtype
    if "has_procedure_metadata" not in inventory_df.columns:
        inventory_df["has_procedure_metadata"] = pd.Series(dtype="object")
    if "has_subject_metadata" not in inventory_df.columns:
        inventory_df["has_subject_metadata"] = pd.Series(dtype="object")

    # Update all rows for this subject
    subject_mask = inventory_df["subject_id"] == subject_id
    inventory_df.loc[subject_mask, "has_procedure_metadata"] = bool(
        has_procedures
    )
    inventory_df.loc[subject_mask, "has_subject_metadata"] = bool(has_subject)


def process_subjects(
    inventory_df: pd.DataFrame,
    output_base_dir: Path,
    base_url: str = "http://aind-metadata-service",
):
    """
    Process all unique subjects and fetch their metadata.

    Args:
        inventory_df: DataFrame containing session inventory
        output_base_dir: Base directory for saving metadata
        base_url: Base URL for the metadata service
    """
    # Create output directory
    metadata_dir = output_base_dir / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)

    print(f"Created metadata directory: {metadata_dir}")

    # Get unique subjects
    unique_subjects = get_unique_subjects(inventory_df)
    print(f"\nFound {len(unique_subjects)} unique subjects: {unique_subjects}")

    # Track statistics
    procedures_success = 0
    procedures_failed = 0
    subject_success = 0
    subject_failed = 0

    # Process each subject
    for subject_id in unique_subjects:
        print(f"\nProcessing subject: {subject_id}")

        # Fetch procedures metadata
        print(f"  Fetching procedures metadata...")
        proc_success, proc_data, proc_message = fetch_metadata(
            subject_id, "procedures", base_url
        )

        if proc_success:
            save_metadata(proc_data, subject_id, "procedures", metadata_dir)
            procedures_success += 1
            print(f"  ✓ Procedures metadata fetched successfully")
        else:
            procedures_failed += 1
            print(f"  ✗ Failed to fetch procedures metadata: {proc_message}")

        # Fetch subject metadata
        print(f"  Fetching subject metadata...")
        subj_success, subj_data, subj_message = fetch_metadata(
            subject_id, "subject", base_url
        )

        if subj_success:
            save_metadata(subj_data, subject_id, "subject", metadata_dir)
            subject_success += 1
            print(f"  ✓ Subject metadata fetched successfully")
        else:
            subject_failed += 1
            print(f"  ✗ Failed to fetch subject metadata: {subj_message}")

        # Update inventory with metadata status
        update_inventory_metadata_status(
            inventory_df, subject_id, proc_success, subj_success
        )

    # Print summary
    print(f"\n" + "=" * 60)
    print(f"METADATA FETCHING SUMMARY")
    print(f"=" * 60)
    print(f"Total subjects processed: {len(unique_subjects)}")
    print(f"")
    print(f"Procedures metadata:")
    print(f"  Successfully fetched: {procedures_success}")
    print(f"  Failed to fetch: {procedures_failed}")
    print(f"")
    print(f"Subject metadata:")
    print(f"  Successfully fetched: {subject_success}")
    print(f"  Failed to fetch: {subject_failed}")
    print(f"")
    print(f"Files saved to subject folders in: {metadata_dir}")

    # List created subject directories
    subject_dirs = [d for d in metadata_dir.iterdir() if d.is_dir()]
    if subject_dirs:
        print(f"Created {len(subject_dirs)} subject directories:")
        for subject_dir in sorted(subject_dirs):
            files = list(subject_dir.glob("*.json"))
            print(f"  {subject_dir.name}/: {len(files)} JSON files")


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Fetch procedures and subject metadata from AIND metadata service for each unique subject in the asset inventory."
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default="http://aind-metadata-service",
        help="Base URL for the AIND metadata service (default: http://aind-metadata-service)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for metadata files (default: same directory as script)",
    )
    args = parser.parse_args()

    # Set output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = SCRIPT_DIR

    # Read the asset inventory
    inventory_path = SCRIPT_DIR / "asset_inventory.csv"
    if not inventory_path.exists():
        print(f"Error: Asset inventory file not found: {inventory_path}")
        return

    print(f"Loading asset inventory from: {inventory_path}")
    inventory_df = pd.read_csv(inventory_path)
    print(f"Loaded {len(inventory_df)} sessions from asset inventory")

    # Process subjects and fetch metadata
    process_subjects(inventory_df, output_dir, args.base_url)

    # Save updated inventory with metadata status
    updated_inventory_path = inventory_path
    inventory_df.to_csv(updated_inventory_path, index=False)
    print(f"\nUpdated asset inventory saved to: {updated_inventory_path}")

    # Print final column summary
    if "has_procedure_metadata" in inventory_df.columns:
        proc_counts = inventory_df["has_procedure_metadata"].value_counts()
        print(f"\nProcedure metadata status in asset inventory:")
        for status, count in proc_counts.items():
            print(f"  {status}: {count} sessions")

    if "has_subject_metadata" in inventory_df.columns:
        subj_counts = inventory_df["has_subject_metadata"].value_counts()
        print(f"\nSubject metadata status in asset inventory:")
        for status, count in subj_counts.items():
            print(f"  {status}: {count} sessions")


if __name__ == "__main__":
    main()
