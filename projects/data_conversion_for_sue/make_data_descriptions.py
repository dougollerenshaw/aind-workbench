#!/usr/bin/env python3
"""
Generate data_description.json files for each session in the asset inventory.

This script creates AIND data schema 2.0 compliant data_description.json files
for each experimental session, containing administrative information about the data asset.

This script is part of a metadata workflow with get_procedures_and_subject_metadata.py:
1. get_procedures_and_subject_metadata.py: Fetches subject and procedures metadata
2. make_data_descriptions.py (this script): Creates data_description files

Together, these scripts ensure that all required metadata files are saved to
experiment-specific folders using a consistent naming convention based on the
asset_inventory.csv file.
"""

import os
import pandas as pd
from datetime import datetime, timezone
import zoneinfo
from pathlib import Path
import re
import glob
import argparse
import json
import yaml
from typing import List, Optional

from aind_data_schema.core.data_description import DataDescription, Funding, DataLevel
from aind_data_schema.components.identifiers import Person
from aind_data_schema_models.modalities import Modality
from aind_data_schema_models.organizations import Organization

from utils import construct_file_path
from metadata_utils import (
    load_config, 
    get_mapped_subject_id,
    get_experiment_metadata_dir,
    save_metadata_file,
    check_experiment_metadata_completion
)

# Get the directory containing this script
SCRIPT_DIR = Path(__file__).parent.absolute()

# Load the configuration
config = load_config()
SUBJECT_ID_MAPPING = config['subject_id_mapping']
ORCID_MAPPING = config['orcid_mapping']

# Default session start time when not specified
DEFAULT_SESSION_TIME = "12:00:00"  # Noon

# Organization mappings
COLLECTION_SITE_TO_ORG = {
    'AIND': Organization.AIND,
    'hopkins': Organization.JHU  # Johns Hopkins University
}

# Funding source mappings
FUNDING_SOURCE_TO_ORG = {
    'AIND': Organization.AI,    # For AIND internal funding, use Allen Institute
    'AI': Organization.AI,      # Allen Institute (legacy)
    # Add more mappings as needed
}


def parse_investigators(investigator_string: str) -> List[Person]:
    """
    Parse the investigators string from the CSV into Person objects.
    
    Args:
        investigator_string: Comma-separated string of investigator names
        
    Returns:
        List[Person]: List of Person objects
    """
    if pd.isna(investigator_string) or not investigator_string.strip():
        return []
    
    investigators = []
    names = [name.strip() for name in investigator_string.split(',')]
    
    for name in names:
        if name:
            investigators.append(Person(name=name))
    
    return investigators


def create_person_list(names: List[str]) -> List[Person]:
    """
    Create a list of Person objects from a list of names.
    
    Args:
        names: List of person names
        
    Returns:
        List[Person]: List of Person objects with ORCID registry
    """
    return [
        Person(
            name=name.strip(),
            registry_identifier=ORCID_MAPPING.get(name.strip())
        )
        for name in names
    ]


def parse_funding_sources(funding_string: str, collection_site: str) -> List[Funding]:
    """
    Parse the funding source string into Funding objects.
    
    Args:
        funding_string: Funding source string from CSV
        collection_site: Collection site to help determine funding
        
    Returns:
        List[Funding]: List of Funding objects
    """
    # Use specific funding information based on collection site and data type
    if collection_site.upper() == 'AIND':
        # AIND fiber photometry data has two funding sources:
        # 1. Allen Institute (internal funding)
        # 2. NIMH grant 1R01MH134833
        ai_fundees = create_person_list([
            "Alex Piet", "Jeremiah Cohen", "Kanghoon Jung", "Polina Kosillo", "Sue Su"
        ])
        nimh_fundees = create_person_list([
            "Jeremiah Cohen", "Jonathan Ting", "Kenta Hagihara", "Polina Kosillo", "Yoav Ben-Simon"
        ])
        
        return [
            Funding(
                funder=Organization.AI,
                grant_number=None,
                fundee=ai_fundees
            ),
            Funding(
                funder=Organization.NIMH,
                grant_number="1R01MH134833",
                fundee=nimh_fundees
            )
        ]
    else:
        # Hopkins ephys data is funded by NINDS grant R01NS104834
        ninds_fundees = create_person_list([
            "Jeremiah Cohen", "Kanghoon Jung", "Sue Su"
        ])
        
        return [
            Funding(
                funder=Organization.NINDS,
                grant_number="R01NS104834", 
                fundee=ninds_fundees
            )
        ]


def get_modality_from_physiology(physiology_modality: str) -> List[Modality]:
    """
    Convert physiology modality to AIND modality enums.
    
    Args:
        physiology_modality: Value from physiology_modality column
        
    Returns:
        List[Modality]: List of relevant modalities
    """
    modalities = [Modality.BEHAVIOR]  # All sessions have behavioral data
    
    if physiology_modality == "fiber_photometry":
        modalities.append(Modality.FIB)
    elif physiology_modality == "ephys":
        modalities.append(Modality.ECEPHYS)
    
    return modalities


def extract_session_start_time_from_path(vast_path: str, session_name: str) -> Optional[str]:
    """
    Extract session start time from the session folder structure.
    
    Args:
        vast_path: Path from the vast_path column (e.g. 'scratch/sueSu/ZS061/mZS061d20210404')
        session_name: Session name to look for
        
    Returns:
        Optional[str]: Session start time in YYYY-MM-DD_HH-MM-SS format, or None if not found
    """
    # Construct the base path to look for session folders
    if vast_path.startswith("scratch/sueSu/"):
        relative_path = vast_path[len("scratch/sueSu/"):]
    else:
        relative_path = vast_path
    
    # Base path where data is stored
    base_path = "/allen/aind/scratch/sueSu"
    session_base_path = os.path.join(base_path, relative_path, "neuralynx", "session")
    
    if not os.path.exists(session_base_path):
        return None
    
    # Look for session folders with timestamp format YYYY-MM-DD_HH-MM-SS
    pattern = re.compile(r'(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})')
    
    try:
        for folder_name in os.listdir(session_base_path):
            folder_path = os.path.join(session_base_path, folder_name)
            if os.path.isdir(folder_path):
                match = pattern.match(folder_name)
                if match:
                    return match.group(1)
    except (OSError, PermissionError):
        return None
    
    return None


def create_session_datetime(collection_date: str, vast_path: str, session_name: str, collection_site: str, session_time: Optional[str] = None) -> datetime:
    """
    Create a timezone-aware datetime for the session.
    
    Args:
        collection_date: Date string from CSV
        vast_path: Path from the vast_path column
        session_name: Session name
        collection_site: Collection site (JHU=east coast, AIND=west coast)
        session_time: Optional session time, will try to extract from folder structure first
        
    Returns:
        datetime: Timezone-aware datetime object with proper offset format
                 (e.g., 2021-04-04T17:43:18-04:00 for Eastern time)
                 Uses zoneinfo for proper timezone handling including DST
    """
    # Try to extract session time from folder structure first
    extracted_time = extract_session_start_time_from_path(vast_path, session_name)
    
    if extracted_time:
        # Parse the extracted timestamp: YYYY-MM-DD_HH-MM-SS
        dt = datetime.strptime(extracted_time, "%Y-%m-%d_%H-%M-%S")
    else:
        # Fall back to provided session_time or default
        if session_time is None:
            session_time = DEFAULT_SESSION_TIME
        
        # Parse date
        date_obj = pd.to_datetime(collection_date).date()
        
        # Combine with time
        datetime_str = f"{date_obj} {session_time}"
        dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
    
    # Set timezone based on collection site
    if collection_site.upper() in ['JHU', 'HOPKINS']:
        # Johns Hopkins is East Coast (US/Eastern)
        eastern = zoneinfo.ZoneInfo("US/Eastern")
        return dt.replace(tzinfo=eastern)
    else:
        # AIND is West Coast (US/Pacific) 
        pacific = zoneinfo.ZoneInfo("US/Pacific")
        return dt.replace(tzinfo=pacific)


def session_path_exists(vast_path: str, session_name: str) -> bool:
    """
    Check if the session path exists on the file system.
    
    Args:
        vast_path: Path from the vast_path column
        session_name: Session name
        
    Returns:
        bool: True if the session path exists, False otherwise
    """
    # Construct the base path to check
    if vast_path.startswith("scratch/sueSu/"):
        relative_path = vast_path[len("scratch/sueSu/"):]
    else:
        relative_path = vast_path
    
    # Base path where data is stored
    base_path = "/allen/aind/scratch/sueSu"
    session_base_path = os.path.join(base_path, relative_path, "neuralynx", "session")
    
    return os.path.exists(session_base_path)


def create_data_description(row: pd.Series) -> DataDescription:
    """
    Create a DataDescription object for a single session row.
    
    Args:
        row: Row from the asset inventory DataFrame
        
    Returns:
        DataDescription: Validated data description object
    """
    session_name = row["session_name"]
    original_subject_id = row["subject_id"]
    
    # Map Hopkins KJ subjects to their AIND subject IDs
    subject_id = SUBJECT_ID_MAPPING.get(original_subject_id, original_subject_id)
    
    # Parse basic info
    investigators = parse_investigators(row["investigators"])
    collection_site = row["collection_site"]
    funding_sources = parse_funding_sources(row["funding_source"], collection_site)
    modalities = get_modality_from_physiology(row["physiology_modality"])
    
    # Get institution
    institution = COLLECTION_SITE_TO_ORG.get(collection_site, Organization.OTHER)
    
    # Create session datetime with timezone-aware formatting
    creation_time = create_session_datetime(
        row["collection_date"], 
        row["vast_path"], 
        session_name, 
        collection_site
    )
    
    # Generate name in the required format: label_YYYY-MM-DD_HH-MM-SS
    # The AIND schema expects the name to match the DataRegex.DATA pattern
    datetime_str = creation_time.strftime("%Y-%m-%d_%H-%M-%S")
    # Use subject_id as label since that's the convention for RAW data
    data_name = f"{subject_id}_{datetime_str}"
    
    # Create data description
    data_description = DataDescription(
        name=data_name,
        subject_id=str(subject_id),
        creation_time=creation_time,
        institution=institution,
        investigators=investigators,
        funding_source=funding_sources,
        modalities=modalities,
        data_level=DataLevel.RAW,  # Sue's data appears to be raw data
        project_name="Discovery-Neuromodulator circuit dynamics during foraging",  # Project name
        data_summary=f"Behavioral {row['physiology_modality']} recording session for subject {subject_id}",
        tags=[]
    )
    
    return data_description


def save_data_description(
    data_description: DataDescription, 
    output_dir: Path,
    session_name: str,
    collection_date: str,
    subject_id: str
) -> Path:
    """
    Save the data description to a JSON file.
    
    Args:
        data_description: DataDescription object to save
        output_dir: Base directory for metadata
        session_name: Original session name
        collection_date: Collection date
        subject_id: Subject ID (already mapped to AIND ID if applicable)
        
    Returns:
        Path: Path to the saved file
    """
    # Get experiment metadata directory using shared utility with timezone-aware datetime
    experiment_dir = get_experiment_metadata_dir(
        output_dir,
        session_name,
        subject_id,
        data_description.creation_time
    )
    
    # Create directory if it doesn't exist
    experiment_dir.mkdir(parents=True, exist_ok=True)
    
    # Save to data_description.json using the shared utility
    output_path = save_metadata_file(
        data_description.model_dump(mode='json'),
        experiment_dir,
        "data_description.json"
    )
    
    return output_path


def process_sessions(
    inventory_df: pd.DataFrame,
    output_base_dir: Path,
    force_overwrite: bool = False
):
    """
    Process all sessions and create data_description.json files.
    
    Args:
        inventory_df: DataFrame containing session inventory
        output_base_dir: Base directory for saving files
        force_overwrite: Whether to overwrite existing files
    """
    # Create metadata output directory
    metadata_dir = output_base_dir / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Creating data descriptions in: {metadata_dir}")
    print(f"Processing {len(inventory_df)} sessions...")
    
    success_count = 0
    skip_count = 0
    error_count = 0
    
    for idx, row in inventory_df.iterrows():
        session_name = row["session_name"]
        original_subject_id = row["subject_id"]
        collection_date = row["collection_date"]
        
        # Skip if any required fields are missing
        if pd.isna(original_subject_id) or pd.isna(collection_date):
            print(f"  Skipping {session_name} - missing required fields")
            skip_count += 1
            continue
        
        # Skip if vast_path is missing (needed to check if session exists)
        if pd.isna(row["vast_path"]):
            print(f"  Skipping {session_name} - missing vast_path")
            skip_count += 1
            continue
            
        # Check if the session path exists on the file system
        if not session_path_exists(row["vast_path"], session_name):
            print(f"  Skipping {session_name} - session path does not exist")
            skip_count += 1
            continue
            
        try:
            print(f"  Processing {session_name}...")
            
            # Get mapped subject ID
            aind_subject_id = get_mapped_subject_id(original_subject_id)
            
            # Create data description first to get the creation_time
            data_description = create_data_description(row)
            
            # Get the experiment metadata directory path using the timezone-aware datetime
            experiment_dir = get_experiment_metadata_dir(
                metadata_dir,
                session_name,
                aind_subject_id,
                data_description.creation_time
            )
            
            # Check if file already exists
            output_path = experiment_dir / "data_description.json"
            
            if output_path.exists() and not force_overwrite:
                print(f"    Skipping {session_name} - file already exists: {output_path}")
                skip_count += 1
                continue
            
            # Save to file in the experiment's metadata directory
            saved_path = save_data_description(
                data_description,
                metadata_dir,
                session_name,
                collection_date,
                aind_subject_id
            )
            
            print(f"    ✓ Saved to: {saved_path}")
            success_count += 1
            
        except Exception as e:
            print(f"    ✗ Error processing {session_name}: {str(e)}")
            error_count += 1
    
    # Print summary
    print(f"\n" + "=" * 60)
    print(f"DATA DESCRIPTION GENERATION SUMMARY")
    print(f"=" * 60)
    print(f"Total sessions in inventory: {len(inventory_df)}")
    print(f"Successfully created: {success_count}")
    print(f"Skipped: {skip_count}")
    print(f"  - Already exist: (see individual messages)")
    print(f"  - Missing required fields: (see individual messages)")
    print(f"  - Session path does not exist: (see individual messages)")
    print(f"Errors: {error_count}")
    print(f"Files saved to experiment folders in: {metadata_dir}")
    print(f"\nNote: Only sessions with existing paths in /allen/aind/scratch/sueSu were processed")


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
    
    # Print instructions for missing files
    if files_count['subject.json'] < len(experiment_dirs) or files_count['procedures.json'] < len(experiment_dirs):
        print(f"\nTo add missing subject/procedures files, run:")
        print(f"  python get_procedures_and_subject_metadata.py")
    
    print(f"=" * 60)


def main():
    """Main function to process command line arguments and run the script."""
    parser = argparse.ArgumentParser(
        description="Generate data_description.json files for each session in the asset inventory."
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for data description files (default: same directory as script)",
    )
    parser.add_argument(
        "--force-overwrite",
        action="store_true",
        help="Force overwrite existing data_description.json files (default: skip existing files)",
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
    
    # Process sessions
    process_sessions(inventory_df, output_dir, args.force_overwrite)
    
    # Final message about metadata structure
    metadata_dir = output_dir / "metadata"
    print(f"\n" + "=" * 60)
    print(f"METADATA DIRECTORY STRUCTURE")
    print(f"=" * 60)
    print(f"Data description files have been saved to experiment-specific folders.")
    print(f"Each experiment will have its own folder in: {metadata_dir}")
    print(f"Example structure:")
    print(f"  {metadata_dir}/")
    print(f"  └── subject_YYYY-MM-DD_HH-MM-SS/")
    print(f"      ├── subject.json")
    print(f"      ├── procedures.json")
    print(f"      └── data_description.json")
    print(f"To have all required metadata files in each experiment folder,")
    print(f"make sure to run get_procedures_and_subject_metadata.py")
    print(f"=" * 60)
    
    # Print experiment metadata status
    print_experiment_metadata_status(metadata_dir)


if __name__ == "__main__":
    main()
