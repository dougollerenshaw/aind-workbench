#!/usr/bin/env python3
"""
Generate acquisition.json files for each session in the asset inventory.

This script creates AIND data schema 2.0 compliant acquisition.json files
for each experimental session, containing detailed acquisition metadata.

This script is part of a metadata workflow and should be run after make_data_descriptions.py
to ensure experiment directories exist with proper naming.
"""

import os
import pandas as pd
from datetime import datetime, timedelta
import zoneinfo
from pathlib import Path
import argparse
import json
import re
from typing import List, Optional

from aind_data_schema.core.acquisition import (
    Acquisition,
    DataStream,
    AcquisitionSubjectDetails,
    StimulusEpoch,
    PerformanceMetrics,
    EphysAssemblyConfig,
    ManipulatorConfig
)
from aind_data_schema_models.modalities import Modality
from aind_data_schema_models.units import VolumeUnit
from aind_data_schema.components.coordinates import CoordinateSystem, Axis, Translation

from utils import (
    load_session_data,
    calculate_session_duration,
    count_rewards,
    extract_behavioral_metrics,
)
from metadata_utils import (
    load_config,
    get_mapped_subject_id,
    get_experiment_metadata_dir,
    save_metadata_file
)

# Get the directory containing this script
SCRIPT_DIR = Path(__file__).parent.absolute()

# Load the configuration
config = load_config()
SUBJECT_ID_MAPPING = config['subject_id_mapping']


def extract_session_start_time_from_path(vast_path: str, session_name: str) -> Optional[str]:
    """
    Extract session start time from the session folder structure.
    
    Args:
        vast_path: Full absolute path from the vast_path column
        session_name: Session name to look for
        
    Returns:
        Optional[str]: Session start time in YYYY-MM-DD_HH-MM-SS format, or None if not found
    """
    # Check if neuralynx/session directory exists
    session_base_path = os.path.join(vast_path, "neuralynx", "session")
    
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


def create_session_datetime(collection_date: str, vast_path: str, session_name: str, collection_site: str) -> datetime:
    """
    Create a timezone-aware datetime for the session.
    
    Args:
        collection_date: Date string from CSV
        vast_path: Path from the vast_path column
        session_name: Session name
        collection_site: Collection site (determines timezone)
        
    Returns:
        datetime: Timezone-aware datetime object
    """
    # Try to extract session time from folder structure
    extracted_time = extract_session_start_time_from_path(vast_path, session_name)
    
    if extracted_time:
        # Parse the extracted timestamp: YYYY-MM-DD_HH-MM-SS
        dt = datetime.strptime(extracted_time, "%Y-%m-%d_%H-%M-%S")
    else:
        raise ValueError(f"Could not extract session start time from path for {session_name}")
    
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
    Check if the session path exists on the file system with neuralynx structure.
    
    Args:
        vast_path: Full absolute path from the vast_path column
        session_name: Session name
        
    Returns:
        bool: True if the session has neuralynx/session structure, False otherwise
    """
    # Check if neuralynx/session directory exists
    session_base_path = os.path.join(vast_path, "neuralynx", "session")
    return os.path.exists(session_base_path)


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


def add_ephys_config(active_devices: List[str], configurations: List) -> None:
    """
    Add ephys-specific device configurations for custom tetrode/Neuralynx system.
    
    Args:
        active_devices: List to append device names to
        configurations: List to append device configurations to
    """
    # Add Neuralynx recording system and tetrode probe
    active_devices.extend([
        "Neuralynx recording system",
        "Custom tetrode probe"
    ])
    
    # Create minimal ephys assembly config for tetrode/Neuralynx system
    ephys_config = EphysAssemblyConfig(
        device_name="Custom tetrode probe",
        manipulator=ManipulatorConfig(
            device_name="unknown",
            coordinate_system=CoordinateSystem(
                name="Custom Tetrode Coordinate System",
                origin="Tip",
                axes=[
                    Axis(name="X", direction="Left_to_right"),
                    Axis(name="Y", direction="Back_to_front"),
                    Axis(name="Z", direction="Up_to_down")
                ],
                axis_unit="millimeter"
            ),
            local_axis_positions=Translation(
                translation=[0, 0, 0]  # Unknown positions
            )
        ),
        probes=[],  # Empty for custom tetrodes
        modules=[]  # No modules for basic tetrode setup
    )
    configurations.append(ephys_config)


def create_acquisition(row: pd.Series, base_path: str) -> Acquisition:
    """
    Create an Acquisition object for a single session row.
    
    Args:
        row: Row from the asset inventory DataFrame
        base_path: Base path to the data files
        
    Returns:
        Acquisition: Validated acquisition object
    """
    session_name = row["session_name"]
    original_subject_id = row["subject_id"]
    collection_site = row["collection_site"]
    
    # Map Hopkins KJ subjects to their AIND subject IDs
    subject_id = SUBJECT_ID_MAPPING.get(original_subject_id, original_subject_id)
    
    print(f"Processing session: {session_name} (Subject: {subject_id})")
    
    # Create session datetime with timezone-aware formatting
    acquisition_start_time = create_session_datetime(
        row["collection_date"], 
        row["vast_path"], 
        session_name, 
        collection_site
    )
    
    # Load behavioral data to get session duration and metrics
    mat_path = os.path.join(row["vast_path"], "sorted", "session", f"{session_name}_sessionData_behav.mat")
    print(f"Loading behavioral data from: {mat_path}")
    
    beh_df, licks_L, licks_R = load_session_data(mat_path)
    
    # Extract behavioral metrics
    metrics = extract_behavioral_metrics(beh_df, licks_L, licks_R)
    
    # Calculate end time using duration
    acquisition_end_time = acquisition_start_time + timedelta(
        seconds=metrics["session_duration_seconds"]
    )
    
    print(f"Session duration: {metrics['session_duration_seconds']/60:.2f} minutes")
    print(f"Total rewards: {metrics['total_rewards']}")
    
    # Get modalities
    modalities = get_modality_from_physiology(row["physiology_modality"])
    
    # Create device configurations
    active_devices = []
    configurations = []
    
    # Add ephys-specific configurations if this is an ephys session
    if Modality.ECEPHYS in modalities:
        add_ephys_config(active_devices, configurations)
    
    # Create subject details with known information only
    subject_details = AcquisitionSubjectDetails(
        mouse_platform_name="Unknown",  # Required field, use placeholder since we don't have this info
        reward_consumed_total=metrics["reward_volume_microliters"] / 1000,  # Convert μL to mL
        reward_consumed_unit=VolumeUnit.ML,
        animal_weight_prior=(
            row["SUBJECT_WEIGHT_PRIOR"] 
            if pd.notna(row["SUBJECT_WEIGHT_PRIOR"]) 
            else None
        ),
        animal_weight_post=(
            row["SUBJECT_WEIGHT_POST"] 
            if pd.notna(row["SUBJECT_WEIGHT_POST"]) 
            else None
        ),
    )
    
    # Create data stream with minimal, known information
    data_stream = DataStream(
        stream_start_time=acquisition_start_time,
        stream_end_time=acquisition_end_time,
        modalities=modalities,
        active_devices=active_devices,
        configurations=configurations,
        notes=f"{row['physiology_modality']} recording session"
    )
    
    # Create stimulus epoch with only confirmed behavioral data
    stimulus_epoch = StimulusEpoch(
        stimulus_start_time=acquisition_start_time,
        stimulus_end_time=acquisition_end_time,
        stimulus_name="Behavioral foraging task",
        stimulus_modalities=["Auditory"],  # Assuming auditory cues
        performance_metrics=PerformanceMetrics(
            reward_consumed_during_epoch=str(metrics["reward_volume_microliters"]),
            reward_consumed_unit="microliter",
            trials_total=metrics.get("total_trials", None),
            trials_finished=metrics.get("total_trials", None),  # Assuming all trials finished
            trials_rewarded=metrics["total_rewards"]
        ),
        active_devices=[],  # Don't assume specific devices
        configurations=[]
    )
    
    # Create the acquisition object
    acquisition = Acquisition(
        subject_id=str(subject_id),
        acquisition_start_time=acquisition_start_time,
        acquisition_end_time=acquisition_end_time,
        instrument_id=row["rig_id"],
        acquisition_type="Behavioral foraging",
        data_streams=[data_stream],
        stimulus_epochs=[stimulus_epoch],
        subject_details=subject_details,
        experimenters=[investigator.strip() for investigator in row["investigators"].split(",") if investigator.strip()],
        notes=f"{row['physiology_modality']} recording session for subject {subject_id}"
    )
    
    return acquisition


def process_acquisitions(
    inventory_df: pd.DataFrame,
    base_path: str,
    output_base_dir: Path,
    force_overwrite: bool = False
):
    """
    Process acquisitions from the inventory and create acquisition.json files.
    
    Args:
        inventory_df: DataFrame containing session inventory
        base_path: Base path to the data files
        output_base_dir: Base directory for saving files
        force_overwrite: Whether to overwrite existing files
    """
    # Create metadata output directory
    metadata_dir = output_base_dir / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Creating acquisition files in: {metadata_dir}")
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
            
            # Create acquisition first to get the start_time for folder naming
            acquisition = create_acquisition(row, base_path)
            
            # Get the experiment metadata directory path using the timezone-aware datetime
            experiment_dir = get_experiment_metadata_dir(
                metadata_dir,
                session_name,
                aind_subject_id,
                acquisition.acquisition_start_time
            )
            
            # Check if file already exists
            output_path = experiment_dir / "acquisition.json"
            
            if output_path.exists() and not force_overwrite:
                print(f"    Skipping {session_name} - file already exists: {output_path}")
                skip_count += 1
                continue
            
            # Save to file in the experiment's metadata directory
            saved_path = save_metadata_file(
                acquisition.model_dump(mode='json'),
                experiment_dir,
                "acquisition.json"
            )
            
            print(f"    ✓ Saved to: {saved_path}")
            success_count += 1
            
        except Exception as e:
            print(f"    ✗ Error processing {session_name}: {str(e)}")
            error_count += 1
    
    # Print summary
    print(f"\n" + "=" * 60)
    print(f"ACQUISITION GENERATION SUMMARY")
    print(f"=" * 60)
    print(f"Total sessions in inventory: {len(inventory_df)}")
    print(f"Successfully created: {success_count}")
    print(f"Skipped: {skip_count}")
    print(f"  - Already exist: (see individual messages)")
    print(f"  - Missing required fields: (see individual messages)")
    print(f"  - Session path does not exist: (see individual messages)")
    print(f"Errors: {error_count}")
    print(f"Files saved to experiment folders in: {metadata_dir}")
    print(f"\nNote: Only sessions with neuralynx/session structure were processed")


def main():
    """Main function to process command line arguments and run the script."""
    parser = argparse.ArgumentParser(
        description="Generate acquisition.json files for each session in the asset inventory."
    )
    parser.add_argument(
        "--data-path",
        type=str,
        default="/allen/aind/scratch/sueSu",
        help="Base path to the data files containing the .mat files (default: /allen/aind/scratch/sueSu)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for acquisition files (default: same directory as script)",
    )
    parser.add_argument(
        "--force-overwrite",
        action="store_true",
        help="Force overwrite existing acquisition.json files (default: skip existing files)",
    )
    parser.add_argument(
        "--start-row",
        type=int,
        default=0,
        help="Start row index in the asset inventory (0-based, default: 0)",
    )
    parser.add_argument(
        "--end-row",
        type=int,
        default=None,
        help="End row index in the asset inventory (0-based, exclusive, default: process all rows)",
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
    
    # Apply row range filtering
    start_row = args.start_row
    end_row = args.end_row if args.end_row is not None else len(inventory_df)
    
    if start_row < 0 or start_row >= len(inventory_df):
        print(f"Error: start-row {start_row} is out of range (0 to {len(inventory_df)-1})")
        return
    
    if end_row > len(inventory_df):
        print(f"Warning: end-row {end_row} is beyond the data, using {len(inventory_df)}")
        end_row = len(inventory_df)
    
    if start_row >= end_row:
        print(f"Error: start-row ({start_row}) must be less than end-row ({end_row})")
        return
    
    # Slice the dataframe
    inventory_df = inventory_df.iloc[start_row:end_row]
    print(f"Processing rows {start_row} to {end_row-1} ({len(inventory_df)} sessions)")
    
    # Process sessions
    process_acquisitions(inventory_df, args.data_path, output_dir, args.force_overwrite)


if __name__ == "__main__":
    main()
