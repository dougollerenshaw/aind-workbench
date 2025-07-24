#!/usr/bin/env python3
"""
Generate acquisition.json files specifically for JHU ephys sessions.

This script creates AIND data schema 2.0 compliant acquisition.json files
for Johns Hopkins ephys experimental sessions, containing detailed acquisition metadata
including tetrode configurations and speaker configurations for auditory stimuli.

This script handles Hopkins-specific configurations:
- Hopkins timezone (US/Eastern)
- Tetrode ephys recording configurations
- Speaker configurations for auditory stimuli
- Hopkins rig ID (hopkins_295F_nlyx)
- Hopkins IACUC protocol (MO19M432)
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
from aind_data_schema.components.configs import SpeakerConfig
from aind_data_schema.components.identifiers import Code
from aind_data_schema_models.modalities import Modality
from aind_data_schema_models.units import VolumeUnit, SoundIntensityUnit
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
    save_metadata_file,
    get_session_details,
    create_session_datetime
)

# Get the directory containing this script
SCRIPT_DIR = Path(__file__).parent.absolute()

# Load the configuration
config = load_config()
SUBJECT_ID_MAPPING = config['subject_id_mapping']


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


def create_hopkins_foraging_code(reward_size: float = 3.0) -> Code:
    """
    Create code configuration for Hopkins dynamic foraging task.
    
    Args:
        reward_size: Reward volume in microliters (from session details)
    
    Returns:
        Code: Code object with software, task parameters, and stimulus parameters
    """
    # Task parameters from session template
    task_parameters = {
        "BlockBeta": "15",
        "BlockMax": "35", 
        "BlockMin": "20",
        "DelayBeta": "0.0",
        "DelayMax": "1.0",
        "DelayMin": "1.0", 
        "ITIBeta": "3.0",
        "ITIMax": "15.0",
        "ITIMin": "2.0",
        "LeftValue_volume": f"{reward_size:.2f}",
        "RightValue_volume": f"{reward_size:.2f}",
        "Task": "Uncoupled Without Baiting",
        "reward_probability": "0.1, 0.5, 0.9"
    }
    
    # Stimulus parameters from session template
    stimulus_parameters = {
        "go_cue_frequency": 7500,
        "no_go_cue_frequency": 15000,
        "sample_frequency": 96000,
        "frequency_unit": "hertz",
        "stimulus_duration_ms": 500,
        "amplitude_db": 60
    }
    
    # Combine task and stimulus parameters
    all_parameters = {**task_parameters, **stimulus_parameters}
    
    return Code(
        name="dynamic-foraging-task",
        version=None,  # Version not specified in session template
        url="https://github.com/JeremiahYCohenLab/sueBehavior.git",
        parameters=all_parameters
    )


def add_ephys_config(active_devices: List[str], configurations: List) -> None:
    """
    Add ephys-specific device configurations for custom tetrode/Neuralynx system.
    
    Args:
        active_devices: List to append device names to
        configurations: List to append device configurations to
    """
    # Add ephys assembly (must match instrument.json device names exactly)
    active_devices.extend([
        "Neuralynx Ephys Assembly",
        "Pupil camera",
        "Arduino", 
        "Lick spout assembly"
    ])
    
    # Create ephys assembly config - device names must match instrument.json exactly
    ephys_config = EphysAssemblyConfig(
        device_name="Neuralynx Ephys Assembly",
        manipulator=ManipulatorConfig(
            device_name="Drive system",
            coordinate_system=CoordinateSystem(
                name="BREGMA_ARI",
                origin="Bregma",
                axes=[
                    Axis(name="AP", direction="Posterior_to_anterior"),
                    Axis(name="ML", direction="Left_to_right"),
                    Axis(name="SI", direction="Superior_to_inferior")
                ],
                axis_unit="millimeter"
            ),
            local_axis_positions=Translation(
                translation=[0, 0, 0]
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
    
    # Try to get additional session details from CSV files first (before creating datetime)
    session_details = {}
    try:
        session_date = row["collection_date"]  # Use collection_date directly
        session_details = get_session_details(subject_id, session_date)
        if session_details:
            print(f"Found session details with {len(session_details)} fields")
    except Exception as e:
        print(f"Could not load session details: {str(e)}")
    
    # Create session datetime with timezone-aware formatting (with session details for fallback)
    acquisition_start_time = create_session_datetime(
        row["collection_date"], 
        row["vast_path"], 
        session_name, 
        collection_site,
        session_details  # Pass session details for fallback time_started
    )
    
    # Load behavioral data to get session duration and metrics
    mat_path = os.path.join(row["vast_path"], "sorted", "session", f"{session_name}_sessionData_behav.mat")
    print(f"Loading behavioral data from: {mat_path}")
    
    beh_df, licks_L, licks_R = load_session_data(mat_path)
    
    # Extract behavioral metrics using actual reward size if available
    reward_size = session_details.get('reward_size', 3.0) if session_details else 3.0
    expected_water = session_details.get('water_received') if session_details else None
    
    metrics = extract_behavioral_metrics(
        beh_df, 
        licks_L, 
        licks_R, 
        volume_per_reward=reward_size, 
        expected_water_received=expected_water
    )
    
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
        mouse_platform_name="mouse_tube_foraging_hopkins",  # Hopkins foraging rig platform
        reward_consumed_total=metrics["reward_volume_microliters"] / 1000,  # Convert μL to mL
        reward_consumed_unit=VolumeUnit.ML,
        animal_weight_prior=(
            session_details.get("weight") or
            (row["SUBJECT_WEIGHT_PRIOR"] if pd.notna(row["SUBJECT_WEIGHT_PRIOR"]) else None)
        ),
        animal_weight_post=(
            row["SUBJECT_WEIGHT_POST"] 
            if pd.notna(row["SUBJECT_WEIGHT_POST"]) 
            else None
        ),
    )
    
    # Create data stream (code belongs in stimulus epoch, not data stream)
    data_stream = DataStream(
        stream_start_time=acquisition_start_time,
        stream_end_time=acquisition_end_time,
        modalities=modalities,
        active_devices=active_devices,
        configurations=configurations,
        notes=f"{row['physiology_modality']} recording session"
    )
    
    # Hopkins sessions always have speaker configuration
    stimulus_active_devices = ["Speaker"]
    
    # Create a SpeakerConfig for Hopkins auditory stimuli
    speaker_config = SpeakerConfig(
        device_name="Speaker",
        volume=60,
        volume_unit=SoundIntensityUnit.DB
    )
    stimulus_configurations = [speaker_config]
    
    stimulus_epoch = StimulusEpoch(
        stimulus_start_time=acquisition_start_time,
        stimulus_end_time=acquisition_end_time,
        stimulus_name="Behavioral foraging task",
        code=create_hopkins_foraging_code(reward_size),
        stimulus_modalities=["Auditory"],  # Assuming auditory cues
        performance_metrics=PerformanceMetrics(
            reward_consumed_during_epoch=str(metrics["reward_volume_microliters"]),
            reward_consumed_unit="microliter",
            trials_total=metrics.get("total_trials", None),
            trials_finished=metrics.get("total_trials", None),  # Assuming all trials finished
            trials_rewarded=metrics["total_rewards"]
        ),
        active_devices=stimulus_active_devices,
        configurations=stimulus_configurations
    )
    
    # Create the acquisition object
    # Build notes with session details if available
    base_notes = f"{row['physiology_modality']} recording session for subject {subject_id}"
    if session_details:
        tetrode_pos = session_details.get('tetrode_position', 'unknown')
        behavior_notes = session_details.get('behavior_notes', 'none')
        enhanced_notes = f"{base_notes}. tetrode depth = {tetrode_pos}. session_notes = '{behavior_notes}'"
    else:
        enhanced_notes = base_notes
    
    acquisition = Acquisition(
        subject_id=str(subject_id),
        acquisition_start_time=acquisition_start_time,
        acquisition_end_time=acquisition_end_time,
        instrument_id="hopkins_295F_nlyx",  # Hopkins rig ID
        acquisition_type="Behavioral foraging",
        data_streams=[data_stream],
        stimulus_epochs=[stimulus_epoch],
        subject_details=subject_details,
        experimenters=["zhixiao su"],  # Sue Su's real name
        ethics_review_id=["MO19M432"],  # Hopkins IACUC protocol
        notes=enhanced_notes
    )
    
    return acquisition


def process_acquisitions(
    inventory_df: pd.DataFrame,
    base_path: str,
    output_base_dir: Path
):
    """
    Process acquisitions from the inventory and create acquisition.json files.
    
    Args:
        inventory_df: DataFrame containing session inventory
        base_path: Base path to the data files
        output_base_dir: Base directory for saving files
    """
    # Create metadata output directory
    metadata_dir = output_base_dir / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Creating acquisition files in: {metadata_dir}")
    print(f"Processing {len(inventory_df)} sessions...")
    
    success_count = 0
    skip_count = 0
    error_count = 0
    
    # Track problematic sessions for detailed reporting
    skipped_sessions = []
    error_sessions = []
    
    for idx, row in inventory_df.iterrows():
        session_name = row["session_name"]
        original_subject_id = row["subject_id"]
        collection_date = row["collection_date"]
        
        # Skip if any required fields are missing
        if pd.isna(original_subject_id) or pd.isna(collection_date):
            reason = f"missing required fields (subject_id: {original_subject_id}, collection_date: {collection_date})"
            print(f"  Skipping {session_name} - {reason}")
            skipped_sessions.append((session_name, reason))
            skip_count += 1
            continue
        
        # Skip if vast_path is missing (needed to check if session exists)
        if pd.isna(row["vast_path"]):
            reason = "missing vast_path"
            print(f"  Skipping {session_name} - {reason}")
            skipped_sessions.append((session_name, reason))
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
            
            # Save to file in the experiment's metadata directory (always overwrite)
            saved_path = save_metadata_file(
                acquisition.model_dump(mode='json'),
                experiment_dir,
                "acquisition.json"
            )
            
            print(f"    ✓ Saved to: {saved_path}")
            success_count += 1
            
        except Exception as e:
            error_msg = str(e)
            print(f"    ✗ Error processing {session_name}: {error_msg}")
            error_sessions.append((session_name, error_msg))
            error_count += 1
    
    # Print summary
    print(f"\n" + "=" * 60)
    print(f"ACQUISITION GENERATION SUMMARY")
    print(f"=" * 60)
    print(f"Total sessions in inventory: {len(inventory_df)}")
    print(f"Successfully created: {success_count}")
    print(f"Skipped: {skip_count}")
    print(f"Errors: {error_count}")
    print(f"Files saved to experiment folders in: {metadata_dir}")
    
    # Detailed reporting of problematic sessions
    if skipped_sessions:
        print(f"\n" + "-" * 40)
        print(f"SKIPPED SESSIONS ({len(skipped_sessions)}):")
        print(f"-" * 40)
        for session_name, reason in skipped_sessions:
            print(f"  {session_name}: {reason}")
    
    if error_sessions:
        print(f"\n" + "-" * 40)
        print(f"ERROR SESSIONS ({len(error_sessions)}):")
        print(f"-" * 40)
        for session_name, error_msg in error_sessions:
            print(f"  {session_name}: {error_msg}")
    
    print(f"\nNote: Only sessions with neuralynx/session structure were processed")


def main():
    """Main function to process JHU ephys sessions."""
    parser = argparse.ArgumentParser(
        description="Generate acquisition.json files for JHU ephys sessions in the asset inventory."
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
    full_inventory_df = pd.read_csv(inventory_path)
    print(f"Loaded {len(full_inventory_df)} total sessions from asset inventory")
    
    # Filter for JHU ephys sessions only
    inventory_df = full_inventory_df[
        (full_inventory_df['collection_site'] == 'hopkins') & 
        (full_inventory_df['physiology_modality'] == 'ephys')
    ].copy()
    
    print(f"Found {len(inventory_df)} JHU ephys sessions to process")
    
    if len(inventory_df) == 0:
        print("No JHU ephys sessions found in asset inventory")
        return
    
    print(f"Processing all {len(inventory_df)} JHU ephys sessions")
    
    # Process sessions
    process_acquisitions(inventory_df, args.data_path, output_dir)


if __name__ == "__main__":
    main()
