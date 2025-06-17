#!/usr/bin/env python3
"""
Generate data_description.json files for each session in the asset inventory.

This script creates AIND data schema 2.0 compliant data_description.json files
for each experimental session, containing administrative information about the data asset.
"""

import os
import pandas as pd
from datetime import datetime, timezone
import zoneinfo
from pathlib import Path
import argparse
import json
import yaml
from typing import List, Optional

from aind_data_schema.core.data_description import DataDescription, Funding, DataLevel
from aind_data_schema.components.identifiers import Person
from aind_data_schema_models.modalities import Modality
from aind_data_schema_models.organizations import Organization

from utils import construct_file_path

# Get the directory containing this script
SCRIPT_DIR = Path(__file__).parent.absolute()

# Load configuration from YAML file
def load_config():
    config_path = SCRIPT_DIR / "config.yaml"
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

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
        # Hopkins ephys data is funded by NINDS grant 1RF1NS131984
        ninds_fundees = create_person_list([
            "Jeremiah Cohen", "Kanghoon Jung", "Sue Su"
        ])
        
        return [
            Funding(
                funder=Organization.NINDS,
                grant_number="1RF1NS131984", 
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


def create_session_datetime(collection_date: str, session_time: Optional[str] = None) -> datetime:
    """
    Create a timezone-aware datetime for the session.
    
    Args:
        collection_date: Date string from CSV
        session_time: Optional session time, defaults to DEFAULT_SESSION_TIME
        
    Returns:
        datetime: Timezone-aware datetime object
    """
    if session_time is None:
        session_time = DEFAULT_SESSION_TIME
    
    # Parse date
    date_obj = pd.to_datetime(collection_date).date()
    
    # Combine with time
    datetime_str = f"{date_obj} {session_time}"
    dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
    
    # Make timezone-aware (assuming UTC for consistency)
    return dt.replace(tzinfo=timezone.utc)


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
    
    # Create session datetime
    creation_time = create_session_datetime(row["collection_date"])
    
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
    output_dir: Path
) -> Path:
    """
    Save the data description to a JSON file.
    
    Args:
        data_description: DataDescription object to save
        output_dir: Directory to save the file
        
    Returns:
        Path: Path to the saved file
    """
    # Create session directory using the data description's name field
    session_dir = output_dir / data_description.name
    session_dir.mkdir(parents=True, exist_ok=True)
    
    # Save to data_description.json
    output_path = session_dir / "data_description.json"
    
    # Use the schema's built-in JSON serialization
    with open(output_path, 'w') as f:
        json.dump(data_description.model_dump(mode='json'), f, indent=2, default=str)
    
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
    # Create output directory
    descriptions_dir = output_base_dir / "data_descriptions"
    descriptions_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Creating data descriptions in: {descriptions_dir}")
    print(f"Processing {len(inventory_df)} sessions...")
    
    success_count = 0
    skip_count = 0
    error_count = 0
    
    for idx, row in inventory_df.iterrows():
        session_name = row["session_name"]
        
        try:
            print(f"  Processing {session_name}...")
            
            # Create data description
            data_description = create_data_description(row)
            
            # Check if file already exists (using the data description name)
            session_dir = descriptions_dir / data_description.name
            output_path = session_dir / "data_description.json"
            
            if output_path.exists() and not force_overwrite:
                print(f"    Skipping {data_description.name} - file already exists")
                skip_count += 1
                continue
            
            # Save to file
            saved_path = save_data_description(data_description, descriptions_dir)
            
            print(f"    ✓ Saved to: {saved_path}")
            success_count += 1
            
        except Exception as e:
            print(f"    ✗ Error processing {session_name}: {str(e)}")
            error_count += 1
    
    # Print summary
    print(f"\n" + "=" * 60)
    print(f"DATA DESCRIPTION GENERATION SUMMARY")
    print(f"=" * 60)
    print(f"Total sessions processed: {len(inventory_df)}")
    print(f"Successfully created: {success_count}")
    print(f"Skipped (already exist): {skip_count}")
    print(f"Errors: {error_count}")
    print(f"Files saved to: {descriptions_dir}")


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


if __name__ == "__main__":
    main()
