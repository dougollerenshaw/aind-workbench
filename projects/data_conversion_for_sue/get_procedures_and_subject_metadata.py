#!/usr/bin/env python3
"""
Fetch procedures and subject metadata from AIND metadata service.

This script retrieves subject and procedures metadata for each unique subject in the asset inventory
and saves it to both subject-specific folders (legacy format) and experiment-specific folders 
(new format). 

This script is part of a metadata workflow with make_data_descriptions.py:
1. get_procedures_and_subject_metadata.py (this script): Fetches subject and procedures metadata
2. make_data_descriptions.py: Creates data_description files

Together, these scripts ensure that all required metadata files are saved to
experiment-specific folders using a consistent naming convention based on the
asset_inventory.csv file.
"""

import os
import pandas as pd
import requests
import json
import argparse
from pathlib import Path
import numpy as np
import yaml

# Local imports
from metadata_utils import (
    load_config, 
    get_mapped_subject_id,
    get_experiment_metadata_dir,
    save_metadata_file,
    copy_metadata_to_experiment
)

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
):
    """
    Fetch metadata for a subject from the AIND metadata service.

    Args:
        subject_id: Original subject ID from asset inventory
        metadata_type: Type of metadata ('procedures' or 'subject')

    Returns:
        tuple: (success: bool, data: dict or None, message: str)
    """
    base_url = "http://aind-metadata-service"
    try:
        # Get the mapped subject ID for the API call
        mapped_subject_id = get_mapped_subject_id(subject_id)
        
        # If mapping was applied, log it
        if mapped_subject_id != subject_id:
            print(f"  Using mapped subject ID: {subject_id} -> {mapped_subject_id}")
        
        url = f"{base_url}/{metadata_type}/{mapped_subject_id}"
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
    data: dict, subject_id: str, metadata_type: str, metadata_base_dir: Path, 
    session_name: str = None, collection_date: str = None
):
    """
    Save metadata to a JSON file in the subject's folder and, if session details provided,
    also save to experiment-specific folders.
    
    Args:
        data: Metadata dictionary to save
        subject_id: Subject ID
        metadata_type: Type of metadata ('procedures' or 'subject')
        metadata_base_dir: Base metadata directory
        session_name: Optional session name for experiment folder
        collection_date: Optional collection date for experiment folder
    """
    # Create subject-specific directory (legacy format)
    subject_dir = metadata_base_dir / subject_id
    subject_dir.mkdir(parents=True, exist_ok=True)

    # Use standardized filename based on metadata type
    filename = f"{metadata_type}.json"
    filepath = subject_dir / filename

    # Save to subject directory (legacy format)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

    print(f"  Saved {metadata_type} metadata to: {filepath}")
    
    # If session details are provided, also save to experiment folder
    if session_name is not None and collection_date is not None:
        try:
            # Get mapped subject ID for folder naming
            aind_subject_id = get_mapped_subject_id(subject_id)
            
            # Get experiment directory
            experiment_dir = get_experiment_metadata_dir(
                metadata_base_dir, 
                session_name,
                collection_date,
                aind_subject_id
            )
            
            # Save directly to experiment directory using shared utility
            save_metadata_file(data, experiment_dir, filename)
            print(f"  Also saved to experiment folder: {experiment_dir}")
        except Exception as e:
            print(f"  Warning: Failed to save to experiment folder: {str(e)}")
    
    # Return the subject-folder path where the metadata was saved
    return filepath


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


def check_existing_metadata(subject_id: str, metadata_dir: Path):
    """
    Check if metadata files already exist for a subject.

    Args:
        subject_id: Subject ID to check
        metadata_dir: Base metadata directory

    Returns:
        tuple: (has_procedures: bool, has_subject: bool)
    """
    subject_dir = metadata_dir / subject_id
    procedures_file = subject_dir / "procedures.json"
    subject_file = subject_dir / "subject.json"

    return procedures_file.exists(), subject_file.exists()


def create_session_procedure_summary(
    inventory_df: pd.DataFrame, output_dir: Path
):
    """
    Create a summary CSV with one row per subject showing metadata availability.

    Args:
        inventory_df: DataFrame containing session inventory with metadata status
        output_dir: Directory to save the summary file
    """
    # Group by subject and get the metadata status (should be same for all sessions of a subject)
    summary_data = []

    for subject_id in inventory_df["subject_id"].unique():
        if pd.isna(subject_id):
            continue

        subject_sessions = inventory_df[
            inventory_df["subject_id"] == subject_id
        ]

        # Get metadata status (should be consistent across all sessions for this subject)
        has_procedures = (
            subject_sessions["has_procedure_metadata"].iloc[0]
            if "has_procedure_metadata" in subject_sessions.columns
            else False
        )
        has_subject = (
            subject_sessions["has_subject_metadata"].iloc[0]
            if "has_subject_metadata" in subject_sessions.columns
            else False
        )

        # Count sessions for this subject
        total_sessions = len(subject_sessions)

        summary_data.append(
            {
                "subject_id": subject_id,
                "total_sessions": total_sessions,
                "has_procedure_metadata": has_procedures,
                "has_subject_metadata": has_subject,
            }
        )

    # Create summary DataFrame
    summary_df = pd.DataFrame(summary_data)
    summary_df = summary_df.sort_values("subject_id")

    # Save summary
    summary_path = output_dir / "session_procedure_summary.csv"
    summary_df.to_csv(summary_path, index=False)

    print(f"\nSession procedure summary saved to: {summary_path}")
    print(f"Summary contains {len(summary_df)} subjects")

    # Print summary statistics
    if len(summary_df) > 0:
        proc_success = summary_df["has_procedure_metadata"].sum()
        subj_success = summary_df["has_subject_metadata"].sum()
        print(
            f"Subjects with procedure metadata: {proc_success}/{len(summary_df)}"
        )
        print(
            f"Subjects with subject metadata: {subj_success}/{len(summary_df)}"
        )


def process_subjects(
    inventory_df: pd.DataFrame,
    output_base_dir: Path,
    force_overwrite: bool = False,
):
    """
    Process all unique subjects and fetch their metadata.

    Args:
        inventory_df: DataFrame containing session inventory
        output_base_dir: Base directory for saving metadata
        force_overwrite: If False, skip subjects that already have metadata files
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
    skipped_subjects = 0

    # Process each subject
    for subject_id in unique_subjects:
        print(f"\nProcessing subject: {subject_id}")

        # Check if metadata already exists (unless force_overwrite is True)
        if not force_overwrite:
            existing_procedures, existing_subject = check_existing_metadata(
                subject_id, metadata_dir
            )
            if existing_procedures and existing_subject:
                print(
                    f"  Skipping {subject_id} - both metadata files already exist"
                )
                skipped_subjects += 1
                # Update inventory with existing status
                update_inventory_metadata_status(
                    inventory_df, subject_id, True, True
                )
                procedures_success += 1
                subject_success += 1
                continue
            elif existing_procedures:
                print(f"  Procedures metadata already exists for {subject_id}")
                procedures_success += 1
            elif existing_subject:
                print(f"  Subject metadata already exists for {subject_id}")
                subject_success += 1

        # Fetch procedures metadata (if not already exists or force_overwrite)
        proc_success = False
        if (
            force_overwrite
            or not check_existing_metadata(subject_id, metadata_dir)[0]
        ):
            print(f"  Fetching procedures metadata...")
            proc_success, proc_data, proc_message = fetch_metadata(
                subject_id, "procedures"
            )

            if proc_success:
                # Find any sessions for this subject to get session details
                subject_sessions = inventory_df[inventory_df["subject_id"] == subject_id]
                if not subject_sessions.empty:
                    # Use the first session's details (assuming procedure metadata is the same for all sessions)
                    session_row = subject_sessions.iloc[0]
                    save_metadata(
                        proc_data, subject_id, "procedures", metadata_dir,
                        session_row.get("session_name"), session_row.get("collection_date")
                    )
                else:
                    # No session data, just save to subject folder
                    save_metadata(
                        proc_data, subject_id, "procedures", metadata_dir
                    )
                    
                if not check_existing_metadata(subject_id, metadata_dir)[
                    0
                ]:  # Wasn't already counted
                    procedures_success += 1
                print(f"  ✓ Procedures metadata fetched successfully")
            else:
                procedures_failed += 1
                print(
                    f"  ✗ Failed to fetch procedures metadata: {proc_message}"
                )
        else:
            proc_success = True  # Already exists

        # Fetch subject metadata (if not already exists or force_overwrite)
        subj_success = False
        if (
            force_overwrite
            or not check_existing_metadata(subject_id, metadata_dir)[1]
        ):
            print(f"  Fetching subject metadata...")
            subj_success, subj_data, subj_message = fetch_metadata(
                subject_id, "subject"
            )

            if subj_success:
                # Find any sessions for this subject to get session details
                subject_sessions = inventory_df[inventory_df["subject_id"] == subject_id]
                if not subject_sessions.empty:
                    # Use the first session's details (assuming subject metadata is the same for all sessions)
                    session_row = subject_sessions.iloc[0]
                    save_metadata(
                        subj_data, subject_id, "subject", metadata_dir,
                        session_row.get("session_name"), session_row.get("collection_date")
                    )
                else:
                    # No session data, just save to subject folder
                    save_metadata(
                        subj_data, subject_id, "subject", metadata_dir
                    )
                    
                if not check_existing_metadata(subject_id, metadata_dir)[
                    1
                ]:  # Wasn't already counted
                    subject_success += 1
                print(f"  ✓ Subject metadata fetched successfully")
            else:
                subject_failed += 1
                print(f"  ✗ Failed to fetch subject metadata: {subj_message}")
        else:
            subj_success = True  # Already exists

        # Update inventory with metadata status
        update_inventory_metadata_status(
            inventory_df, subject_id, proc_success, subj_success
        )

    # Print summary
    print(f"\n" + "=" * 60)
    print(f"METADATA FETCHING SUMMARY")
    print(f"=" * 60)
    print(f"Total subjects processed: {len(unique_subjects)}")
    if not force_overwrite:
        print(f"Subjects skipped (already had both files): {skipped_subjects}")
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


def copy_metadata_to_experiments(
    inventory_df: pd.DataFrame,
    metadata_base_dir: Path,
):
    """
    Copy subject and procedures metadata to experiment-specific folders.
    
    Args:
        inventory_df: DataFrame containing session inventory
        metadata_base_dir: Base directory for metadata
    """
    print(f"\n" + "=" * 60)
    print(f"COPYING METADATA TO EXPERIMENT FOLDERS")
    print(f"=" * 60)
    print(f"Processing {len(inventory_df)} sessions for metadata copying...")
    
    # Define the metadata directory
    metadata_dir = metadata_base_dir / "metadata"
    
    # Count statistics
    success_count = 0
    skipped_count = 0
    error_count = 0
    
    for idx, row in inventory_df.iterrows():
        session_name = row['session_name']
        original_subject_id = row['subject_id']
        collection_date = row['collection_date']
        
        # Skip if any required fields are missing
        if pd.isna(original_subject_id) or pd.isna(collection_date):
            print(f"  Skipping {session_name} - missing required fields")
            skipped_count += 1
            continue
            
        # Get mapped subject ID
        aind_subject_id = get_mapped_subject_id(original_subject_id)
        
        # Get the experiment metadata directory
        experiment_dir = get_experiment_metadata_dir(
            metadata_dir, 
            session_name,
            collection_date,
            aind_subject_id
        )
        
        print(f"  Processing {session_name} -> {experiment_dir.name}")
        
        # Check for required files
        subject_file = metadata_dir / original_subject_id / "subject.json"
        procedures_file = metadata_dir / original_subject_id / "procedures.json"
        
        if not subject_file.exists() or not procedures_file.exists():
            print(f"    ✗ Missing required metadata files for {original_subject_id}")
            error_count += 1
            continue
        
        # Copy metadata files to experiment directory
        try:
            # Create experiment directory
            experiment_dir.mkdir(parents=True, exist_ok=True)
            
            # Check if files already exist in experiment folder
            target_subject_file = experiment_dir / "subject.json"
            target_procedures_file = experiment_dir / "procedures.json"
            
            if target_subject_file.exists() and target_procedures_file.exists():
                print(f"    ✓ All metadata files already exist in {experiment_dir}")
                success_count += 1
                continue
            
            # Copy files that don't already exist
            success1 = True
            success2 = True
            
            if not target_subject_file.exists():
                success1 = copy_metadata_to_experiment(
                    metadata_dir,
                    experiment_dir,
                    original_subject_id,
                    "subject"
                )
            
            if not target_procedures_file.exists():
                success2 = copy_metadata_to_experiment(
                    metadata_dir,
                    experiment_dir,
                    original_subject_id,
                    "procedures"
                )
            
            if success1 and success2:
                print(f"    ✓ Copied metadata to {experiment_dir}")
                success_count += 1
            else:
                print(f"    ✗ Error copying some metadata files")
                error_count += 1
                
        except Exception as e:
            print(f"    ✗ Error processing {session_name}: {str(e)}")
            error_count += 1
    
    # Print summary
    print(f"\n" + "=" * 60)
    print(f"METADATA COPYING SUMMARY")
    print(f"=" * 60)
    print(f"Total sessions: {len(inventory_df)}")
    print(f"Successfully copied: {success_count}")
    print(f"Skipped: {skipped_count}")
    print(f"Errors: {error_count}")
    print(f"=" * 60)


def print_experiment_metadata_status(metadata_dir: Path):
    """
    Print a summary of which experiment directories have complete metadata.
    
    Args:
        metadata_dir: Base metadata directory
    """
    # Find all experiment directories (those that follow the naming pattern)
    import re
    exp_pattern = re.compile(r"[A-Za-z0-9]+_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}")
    experiment_dirs = [d for d in metadata_dir.iterdir() if d.is_dir() and exp_pattern.match(d.name)]
    
    print(f"\n" + "=" * 60)
    print(f"EXPERIMENT METADATA STATUS")
    print(f"=" * 60)
    print(f"Found {len(experiment_dirs)} experiment directories")
    
    # Count files by type
    files_count = {
        "subject.json": 0,
        "procedures.json": 0,
        "data_description.json": 0,
        "complete": 0
    }
    
    # Check each experiment directory
    for exp_dir in experiment_dirs:
        # Import the checker function (which should be in metadata_utils)
        from metadata_utils import check_experiment_metadata_completion
        status = check_experiment_metadata_completion(exp_dir)
        
        # Update counts
        for file_type, exists in status.items():
            if exists:
                files_count[file_type] += 1
        
        # Check if experiment has all required files
        if all(status.values()):
            files_count["complete"] += 1
    
    # Print summary
    print(f"Experiment directories with:")
    print(f"  subject.json: {files_count['subject.json']}/{len(experiment_dirs)}")
    print(f"  procedures.json: {files_count['procedures.json']}/{len(experiment_dirs)}")
    print(f"  data_description.json: {files_count['data_description.json']}/{len(experiment_dirs)}")
    print(f"  Complete (all files): {files_count['complete']}/{len(experiment_dirs)}")
    
    # Print instructions for missing data_description files
    if files_count['data_description.json'] < len(experiment_dirs):
        print(f"\nTo add missing data_description.json files, run:")
        print(f"  python make_data_descriptions.py")
    
    print(f"=" * 60)


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Fetch procedures and subject metadata from AIND metadata service for each unique subject in the asset inventory."
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
    process_subjects(inventory_df, output_dir, args.force_overwrite)

    # Save updated inventory with metadata status
    updated_inventory_path = inventory_path
    inventory_df.to_csv(updated_inventory_path, index=False)
    print(f"\nUpdated asset inventory saved to: {updated_inventory_path}")

    # Create session procedure summary
    create_session_procedure_summary(inventory_df, output_dir)

    # Copy metadata to experiment folders
    copy_metadata_to_experiments(inventory_df, output_dir)

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
    
    # Print final note about metadata organization
    print(f"\n" + "=" * 60)
    print(f"METADATA ORGANIZATION")
    print(f"=" * 60)
    print(f"Metadata files are saved in two locations:")
    print(f"1. Subject-based folders (legacy format): {output_dir / 'metadata' / '<subject_id>'}")
    print(f"2. Experiment-based folders (new format): {output_dir / 'metadata' / '<subject_id>_<date>_<time>'}")
    print(f"Run the make_data_descriptions.py script to create data_description.json files in each experiment folder.")
    print(f"=" * 60)
    
    # Print experiment metadata status
    metadata_dir = output_dir / "metadata"
    print_experiment_metadata_status(metadata_dir)


if __name__ == "__main__":
    main()
