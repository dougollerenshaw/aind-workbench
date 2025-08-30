#!/usr/bin/env python3
"""
Script to generate metadata for fiber photometry (FIP) sessions.

This script:
1. Reads the FPsessions_to_upload.csv file
2. Extracts timestamps from zarr paths in the vast_path column
3. Creates session-specific metadata folders with proper AIND naming
4. Copies existing subject.json, procedures.json, and instrument.json files
5. Generates only acquisition.json and data_description.json using AIND schema classes

Required files per session:
- subject.json (copied from existing metadata)
- procedures.json (copied from existing metadata)
- data_description.json (created using AIND schema)
- acquisition.json (created using AIND schema)
- instrument.json (copied from existing fib instrument)
"""

import os
import re
import json
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import zoneinfo
from typing import Optional, Dict, Any, List, Tuple
import shutil

# Import AIND data schema classes
from aind_data_schema.core.data_description import DataDescription, Funding
from aind_data_schema.core.acquisition import (
    Acquisition,
    DataStream,
    AcquisitionSubjectDetails,
    StimulusEpoch,
    PerformanceMetrics,
)
from aind_data_schema.components.identifiers import Person
from aind_data_schema_models.modalities import Modality
from aind_data_schema_models.organizations import Organization

# Add scipy for loading .mat files
import scipy.io as sio


def load_config():
    """Load configuration from config.yaml."""
    import yaml

    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)


def get_mapped_subject_id(subject_id: str, config: dict) -> str:
    """Map subject ID to AIND ID using config."""
    if subject_id.startswith("KJ"):
        return config["subject_id_mapping"].get(subject_id, subject_id)
    return subject_id


def format_session_name(mapped_id: str, session_datetime: datetime) -> str:
    """Format session name in AIND format: subject_id_YYYY-MM-DD_HH-MM-SS."""
    return f"{mapped_id}_{session_datetime.strftime('%Y-%m-%d_%H-%M-%S')}"


def get_experiment_metadata_dir(
    metadata_base_dir: Path,
    session_name: str,
    mapped_id: str,
    session_datetime: datetime,
) -> Path:
    """Get the metadata directory for a session."""
    formatted_name = format_session_name(mapped_id, session_datetime)
    return metadata_base_dir / formatted_name


def save_metadata_file(data: dict, metadata_dir: Path, filename: str) -> Path:
    """Save metadata to a JSON file."""
    metadata_dir.mkdir(parents=True, exist_ok=True)
    filepath = metadata_dir / filename

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

    print(f"    Saved {filename}")
    return filepath


def extract_behavioral_metrics_from_data(
    vast_path: str, original_session_name: str
) -> dict:
    """
    Extract behavioral metrics from real behavioral data (.mat file).

    Args:
        vast_path: Path to the session directory
        original_session_name: Original session name (e.g., mKJ005d20230624)

    Returns:
        dict: Dictionary containing behavioral metrics including session_duration_seconds
    """
    try:
        # Convert SMB path to mounted path (same logic as extract_timestamp_from_zarr_path)
        if vast_path.startswith("smb://"):
            # Remove smb://allen/aind and replace with /Volumes/aind
            mounted_path = vast_path.replace(
                "smb://allen/aind", "/Volumes/aind"
            )
        elif vast_path.startswith("/allen/aind"):
            # Replace /allen/aind with /Volumes/aind
            mounted_path = vast_path.replace("/allen/aind", "/Volumes/aind")
        else:
            # Assume it's already a mounted path
            mounted_path = vast_path

        # Look for behavioral data file using the original session name
        # Files are named like mKJ005d20230624_sessionData_behav.mat
        mat_path = os.path.join(
            mounted_path,
            "sorted",
            "session",
            f"{original_session_name}_sessionData_behav.mat",
        )

        if not os.path.exists(mat_path):
            print(f"      Warning: Behavioral data file not found: {mat_path}")
            return {"session_duration_seconds": 0.0}

        # Use the existing utils functions to load and analyze the data
        from utils import (
            load_session_data,
            calculate_session_duration,
            extract_behavioral_metrics,
        )

        # Load the behavioral data
        beh_df, licks_L, licks_R = load_session_data(mat_path)

        if beh_df.empty:
            print(f"      Warning: No behavioral data found in {mat_path}")
            return {"session_duration_seconds": 0.0}

        # Extract all behavioral metrics using the real function
        metrics = extract_behavioral_metrics(beh_df, licks_L, licks_R)

        # Calculate session duration using the real function
        duration_seconds = calculate_session_duration(beh_df)
        metrics["session_duration_seconds"] = duration_seconds

        if duration_seconds > 0:
            print(
                f"      Found real session duration: {duration_seconds:.2f} seconds ({duration_seconds/60:.1f} minutes)"
            )
            print(
                f"      Total rewards: {metrics.get('total_rewards', 'unknown')}"
            )
            print(
                f"      Total trials: {metrics.get('total_trials', 'unknown')}"
            )
            return metrics
        else:
            print(
                f"      Warning: Could not calculate session duration from behavioral data"
            )
            return {"session_duration_seconds": 0.0}

    except Exception as e:
        print(f"      Warning: Error extracting behavioral metrics: {e}")
        return {"session_duration_seconds": 0.0}


def extract_timestamp_from_zarr_path(vast_path: str) -> str:
    """Extract timestamp from zarr path like behavior_KJ007_2023-07-01_19-25-23_nwb.zarr."""
    # Convert SMB path to mounted path
    # smb://allen/aind/scratch/sueSu/... -> /Volumes/aind/scratch/sueSu/...
    if vast_path.startswith("smb://"):
        # Remove smb://allen/aind and replace with /Volumes/aind
        mounted_path = vast_path.replace("smb://allen/aind", "/Volumes/aind")
    elif vast_path.startswith("/allen/aind"):
        # Replace /allen/aind with /Volumes/aind
        mounted_path = vast_path.replace("/allen/aind", "/Volumes/aind")
    else:
        # Assume it's already a mounted path
        mounted_path = vast_path

    # The vast_path is the base session directory, we need to look in sorted/session/
    # for zarr files with timestamps
    session_path = Path(mounted_path) / "sorted" / "session"

    if not session_path.exists():
        print(f"      Warning: Session path not found: {session_path}")
        print(f"      Original path: {vast_path}")
        print(f"      Converted path: {mounted_path}")
        return None

    # Look for zarr folders with the expected naming pattern
    # Pattern: behavior_{subject_id}_{date}_{time}_nwb.zarr
    pattern = re.compile(
        r"behavior_([A-Z]+\d+|\d+)_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})_nwb\.zarr"
    )

    try:
        for item in session_path.iterdir():
            if item.is_dir() and item.name.endswith(".zarr"):
                match = pattern.match(item.name)
                if match:
                    subject_id = match.group(1)
                    timestamp_str = match.group(2)
                    print(
                        f"      Found timestamp in zarr path: {timestamp_str} for subject {subject_id}"
                    )
                    return timestamp_str
    except Exception as e:
        print(f"      Error searching zarr paths: {e}")

    # Fallback: look for any timestamp pattern in the session directory
    pattern_fallback = re.compile(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})")

    try:
        for item in session_path.iterdir():
            if item.is_dir():
                match = pattern_fallback.search(item.name)
                if match:
                    timestamp_str = match.group(1)
                    print(f"      Found timestamp (fallback): {timestamp_str}")
                    return timestamp_str
    except Exception as e:
        print(f"      Error in fallback timestamp search: {e}")

    print(f"      Warning: No timestamp found in zarr paths")
    return None


def create_fip_session_datetime(
    collection_date: str, vast_path: str, session_name: str, timestamp: str
) -> datetime:
    """
    Create a timezone-aware datetime for the FIP session.

    Args:
        collection_date: Date string from CSV (YYYY-MM-DD format)
        vast_path: Path from vast_path column
        session_name: Session name
        timestamp: Timestamp string (YYYY-MM-DD_HH-MM-SS format)

    Returns:
        datetime: Timezone-aware datetime object (US/Pacific for AIND)
    """
    try:
        # Parse the full timestamp (YYYY-MM-DD_HH-MM-SS)
        session_datetime = datetime.strptime(timestamp, "%Y-%m-%d_%H-%M-%S")

        # AIND is West Coast (US/Pacific)
        pacific = zoneinfo.ZoneInfo("US/Pacific")
        return session_datetime.replace(tzinfo=pacific)

    except ValueError as e:
        print(f"  Error parsing datetime for {session_name}: {e}")
        print(f"    Collection date: {collection_date}")
        print(f"    Timestamp: {timestamp}")
        return None


def copy_metadata_to_allen_and_generate_csv(
    metadata_base_dir: Path,
    processed_sessions: List[Tuple[str, str, str]],
) -> None:
    """
    Copy metadata files to mounted volume locations and generate deployment CSV.

    Args:
        metadata_base_dir: Base directory containing generated metadata
        asset_inventory_df: DataFrame with asset inventory information
        processed_sessions: List of tuples (original_name, formatted_name, vast_path)
    """
    print(f"\nCopying metadata files to mounted volume locations...")

    deployment_data = []

    for original_name, formatted_name, vast_path in processed_sessions:
        # Convert SMB path to mounted volume path (same logic as other functions)
        if vast_path.startswith("smb://"):
            # Remove smb://allen/aind and replace with /Volumes/aind
            mounted_path = vast_path.replace(
                "smb://allen/aind", "/Volumes/aind"
            )
        elif vast_path.startswith("/allen/aind"):
            # Replace /allen/aind with /Volumes/aind
            mounted_path = vast_path.replace("/allen/aind", "/Volumes/aind")
        else:
            print(
                f"  Warning: Cannot determine mounted path for {original_name}: {vast_path}"
            )
            continue

            # Copy all 5 metadata files directly to the base session directory
        local_metadata_dir = metadata_base_dir / formatted_name
        files_copied = 0

        for metadata_file in [
            "subject.json",
            "procedures.json",
            "data_description.json",
            "acquisition.json",
            "instrument.json",
        ]:
            local_file = local_metadata_dir / metadata_file
            mounted_file = Path(mounted_path) / metadata_file

            if local_file.exists():
                shutil.copy2(local_file, mounted_file)
                files_copied += 1
            else:
                print(
                    f"  Warning: {metadata_file} not found for {formatted_name}"
                )

        if files_copied == 5:
            print(f"  ✓ Copied {files_copied} files to {mounted_path}")

            # Get the derived name from data_description.json for the CSV
            data_desc_file = local_metadata_dir / "data_description.json"
            if data_desc_file.exists():
                with open(data_desc_file, "r") as f:
                    data_desc = json.load(f)
                    derived_name = data_desc.get("name", formatted_name)
            else:
                derived_name = formatted_name

            # Extract NWB file path from the zarr path
            nwb_file_path = None
            if vast_path.startswith("smb://"):
                # Convert SMB path to mounted path for NWB file lookup
                nwb_mounted_path = vast_path.replace(
                    "smb://allen/aind", "/Volumes/aind"
                )
            elif vast_path.startswith("/allen/aind"):
                nwb_mounted_path = vast_path.replace(
                    "/allen/aind", "/Volumes/aind"
                )
            else:
                nwb_mounted_path = vast_path

            # Look for the NWB file in the sorted/session directory
            nwb_search_path = Path(nwb_mounted_path) / "sorted" / "session"
            if nwb_search_path.exists():
                # Look for files ending with _nwb.zarr
                for item in nwb_search_path.iterdir():
                    if item.is_dir() and item.name.endswith("_nwb.zarr"):
                        nwb_file_path = str(item)
                        break

            # Convert mounted path back to Linux-style /allen path for CSV
            if str(mounted_path).startswith("/Volumes/aind"):
                allen_path_for_csv = str(mounted_path).replace(
                    "/Volumes/aind", "/allen/aind"
                )
            else:
                allen_path_for_csv = str(mounted_path)

            # Convert NWB file path to Linux-style as well
            if nwb_file_path and nwb_file_path.startswith("/Volumes/aind"):
                nwb_file_path_for_csv = nwb_file_path.replace(
                    "/Volumes/aind", "/allen/aind"
                )
            else:
                nwb_file_path_for_csv = nwb_file_path or "Not found"

            deployment_data.append(
                {
                    "allen_path": allen_path_for_csv,
                    "session_name": derived_name,
                    "nwb_file_path": nwb_file_path_for_csv,
                }
            )
        else:
            print(
                f"  ✗ Only copied {files_copied}/5 files for {formatted_name}"
            )

    # Generate deployment CSV
    if deployment_data:
        deployment_df = pd.DataFrame(deployment_data)
        csv_path = metadata_base_dir / "deployment_to_allen.csv"
        deployment_df.to_csv(csv_path, index=False)
        print(f"\nGenerated deployment CSV: {csv_path}")
        print(f"Total sessions ready for deployment: {len(deployment_data)}")
    else:
        print("No sessions were successfully copied to /allen")


def copy_existing_metadata_files(
    metadata_dir: Path, subject_id: str, mapped_id: str
) -> bool:
    """
    Copy existing subject.json, procedures.json, and instrument.json files.

    Args:
        metadata_dir: Target metadata directory for the session
        subject_id: Original subject ID (e.g., KJ005)
        mapped_id: Mapped AIND subject ID (e.g., 669489)

    Returns:
        bool: True if all files were copied successfully
    """
    # Base metadata directory
    base_metadata_dir = Path("metadata")

    # Copy subject.json and procedures.json from existing subject folder
    subject_source = base_metadata_dir / mapped_id / "subject.json"
    procedures_source = base_metadata_dir / mapped_id / "procedures.json"

    # Copy instrument.json from fib instrument folder
    instrument_source = (
        base_metadata_dir / "instrument" / "fib" / "instrument.json"
    )

    success = True

    # Copy subject.json
    if subject_source.exists():
        shutil.copy2(subject_source, metadata_dir / "subject.json")
        print(f"  Copied subject.json from {subject_source}")
    else:
        print(f"  Warning: subject.json not found at {subject_source}")
        success = False

    # Copy procedures.json
    if procedures_source.exists():
        shutil.copy2(procedures_source, metadata_dir / "procedures.json")
        print(f"  Copied procedures.json from {procedures_source}")
    else:
        print(f"  Warning: procedures.json not found at {procedures_source}")
        success = False

    # Copy instrument.json
    if instrument_source.exists():
        shutil.copy2(instrument_source, metadata_dir / "instrument.json")
        print(f"  Copied instrument.json from {instrument_source}")
    else:
        print(f"  Warning: instrument.json not found at {instrument_source}")
        success = False

    return success


def create_fip_data_description(
    subject_id: str,
    mapped_id: str,
    session_datetime: datetime,
    session_name: str,
) -> DataDescription:
    """
    Create data description metadata for FIP sessions using AIND schema classes.

    Args:
        subject_id: Original subject ID
        mapped_id: Mapped AIND subject ID
        session_datetime: Session datetime
        session_name: Formatted session name

    Returns:
        DataDescription: Data description metadata object
    """
    # Add current datetime suffix to make it clear this is derived metadata
    current_datetime = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    derived_name = f"{session_name}_nwb_{current_datetime}"

    return DataDescription(
        name=derived_name,
        subject_id=mapped_id,
        creation_time=session_datetime,
        institution=Organization.AIND,
        investigators=[
            Person(name="Sue Su", registry_identifier="0000-0002-0138-7433")
        ],
        funding_source=[
            Funding(
                funder=Organization.AI,  # Use "Allen Institute" for funding source
                grant_number=None,
                fundee=[
                    Person(
                        name="Sue Su",
                        registry_identifier="0000-0002-0138-7433",
                    ),
                    Person(
                        name="Jeremiah Cohen",
                        registry_identifier="0000-0002-4768-7433",
                    ),
                ],
            )
        ],
        modalities=[Modality.BEHAVIOR, Modality.FIB],
        data_level="derived",
        project_name="Dynamic Foraging with Fiber Photometry",
        data_summary=f"Fiber photometry recording session for subject {mapped_id}",
    )


def create_fip_acquisition(
    subject_id: str,
    mapped_id: str,
    mapped_session_name: str,
    session_datetime: datetime,
    collection_date: str,
    vast_path: str,
    original_session_name: str,
) -> Acquisition:
    """
    Create acquisition metadata for FIP sessions using AIND schema classes.

    Args:
        subject_id: Original subject ID
        mapped_id: Mapped AIND subject ID
        session_datetime: Session datetime
        session_name: Formatted session name
        collection_date: Collection date
        vast_path: Path to session data
        original_session_name: Original session name for behavioral data lookup

    Returns:
        Acquisition: Acquisition metadata object
    """
    # Extract behavioral metrics from behavioral data
    behavioral_metrics = extract_behavioral_metrics_from_data(
        vast_path, original_session_name
    )

    # Get session duration from metrics
    session_duration = behavioral_metrics.get("session_duration_seconds", 0.0)

    # Calculate end time
    if session_duration > 0:
        acquisition_end_time = session_datetime + timedelta(
            seconds=session_duration
        )
        stream_end_time = acquisition_end_time
        print(
            f"      Using calculated session duration: {session_duration:.2f} seconds"
        )
    else:
        # Cannot proceed without real session duration - this is required metadata
        raise ValueError(
            f"Cannot determine session duration for {mapped_session_name}. Session duration is required and cannot be estimated."
        )

    return Acquisition(
        subject_id=mapped_id,
        acquisition_start_time=session_datetime,
        acquisition_end_time=acquisition_end_time,
        experimenters=["Sue Su"],
        ethics_review_id=["2115"],
        instrument_id="FIP_Sue",
        acquisition_type="Fiber photometry recording",
        notes=f"Legacy fiber photometry recording session for subject {mapped_id}. Note: Actual power and exposure duration values are not available in the legacy data.",
        data_streams=[
            DataStream(
                stream_start_time=session_datetime,
                stream_end_time=stream_end_time,
                modalities=[Modality.BEHAVIOR, Modality.FIB],
                active_devices=[
                    "470nm LED",
                    "Fiber optic patch cord",
                    "Green CMOS",
                    "Pupil camera assembly",
                    "Tongue camera assembly",
                    "Lick spout assembly",
                    "Speaker",
                    "Arduino",
                ],
                configurations=[
                    {
                        "object_type": "Light emitting diode config",
                        "device_name": "470nm LED",
                    },
                    {
                        "object_type": "Patch cord config",
                        "device_name": "Fiber optic patch cord",
                        "channels": [
                            {
                                "channel_name": "Fiber channel",
                                "detector": {
                                    "object_type": "Detector config",
                                    "device_name": "Green CMOS",
                                    "exposure_time": 0,
                                    "exposure_time_unit": "second",
                                    "trigger_type": "Internal",
                                },
                            }
                        ],
                    },
                ],
                notes="Fiber photometry recording session",
            )
        ],
        stimulus_epochs=[
            StimulusEpoch(
                stimulus_start_time=session_datetime,
                stimulus_end_time=acquisition_end_time,
                stimulus_name="Behavioral foraging task",
                stimulus_modalities=["Auditory"],
                performance_metrics=PerformanceMetrics(
                    reward_consumed_during_epoch=str(
                        behavioral_metrics.get("reward_volume_microliters", 0)
                    ),
                    reward_consumed_unit="microliter",
                    trials_total=behavioral_metrics.get("total_trials", None),
                    trials_finished=behavioral_metrics.get(
                        "total_trials", None
                    ),  # Assuming all trials finished
                    trials_rewarded=behavioral_metrics.get(
                        "total_rewards", None
                    ),
                ),
                active_devices=["Speaker"],
                notes="Behavioral foraging task during fiber photometry recording",
            )
        ],
        subject_details=AcquisitionSubjectDetails(
            mouse_platform_name="fiber_photometry_platform",
            reward_consumed_total=behavioral_metrics.get(
                "reward_volume_microliters", 0
            )
            / 1000,  # Convert μL to mL
            reward_consumed_unit="milliliter",
        ),
    )


def process_fip_sessions(
    csv_path: str,
    metadata_base_dir: Path,
    force_overwrite: bool = False,
    copy_to_allen: bool = False,
):
    """
    Process all FIP sessions from the CSV file.

    Args:
        csv_path: Path to FPsessions_to_upload.csv
        metadata_base_dir: Base directory for metadata
        force_overwrite: Whether to overwrite existing files
    """
    # Load configuration
    config = load_config()

    # Read the CSV file
    df = pd.read_csv(csv_path)

    print(f"Processing {len(df)} FIP sessions...")

    # Track processed sessions for potential copying to /allen
    processed_sessions = []

    for idx, row in df.iterrows():
        session_name = row["all_to_upload"]

        # Skip header row if present
        if session_name == "all_to_upload":
            continue

        print(f"\nProcessing session {idx + 1}/{len(df)}: {session_name}")

        # Extract subject ID and date from session name
        # Format: mKJ005d20230624 -> KJ005, 2023-06-24
        # Format: m699461d20231217 -> 699461, 2023-12-17
        match = re.match(
            r"m([A-Z]+\d+|\d+)d(\d{4})(\d{2})(\d{2})", session_name
        )
        if not match:
            print(f"  Warning: Could not parse session name: {session_name}")
            continue

        subject_id = match.group(1)
        year = match.group(2)
        month = match.group(3)
        day = match.group(4)
        collection_date = f"{year}-{month}-{day}"

        # Get mapped subject ID
        mapped_id = get_mapped_subject_id(subject_id, config)
        print(f"  Subject: {subject_id} -> {mapped_id}")
        print(f"  Date: {collection_date}")

        # Construct vast_path directly from session name
        # Format: /allen/aind/scratch/sueSu/{subject_id}/{session_name}
        vast_path = f"/allen/aind/scratch/sueSu/{subject_id}/{session_name}"
        print(f"  Vast path: {vast_path}")

        # Extract timestamp from zarr path
        timestamp = extract_timestamp_from_zarr_path(vast_path)

        if timestamp:
            # Create session datetime
            session_datetime = create_fip_session_datetime(
                collection_date, vast_path, session_name, timestamp
            )

            # Format session name
            formatted_name = format_session_name(mapped_id, session_datetime)
            print(f"  Formatted name: {formatted_name}")

            # Get metadata directory
            metadata_dir = get_experiment_metadata_dir(
                metadata_base_dir,
                session_name,
                mapped_id,
                session_datetime,
            )

            # Check if directory already exists
            if metadata_dir.exists() and not force_overwrite:
                print(f"  Directory already exists, skipping: {metadata_dir}")
                continue

            # Create metadata files
            print(f"  Creating metadata files in: {metadata_dir}")

            # Ensure the target directory exists
            metadata_dir.mkdir(parents=True, exist_ok=True)

            try:
                # Copy existing metadata files
                if not copy_existing_metadata_files(
                    metadata_dir, subject_id, mapped_id
                ):
                    print(
                        f"  Warning: Some existing files could not be copied"
                    )

                # Create data description metadata
                data_desc_metadata = create_fip_data_description(
                    subject_id,
                    mapped_id,
                    session_datetime,
                    formatted_name,
                )
                save_metadata_file(
                    data_desc_metadata.model_dump(mode="json"),
                    metadata_dir,
                    "data_description.json",
                )

                # Create acquisition metadata
                acquisition_metadata = create_fip_acquisition(
                    subject_id,
                    mapped_id,
                    formatted_name,
                    session_datetime,
                    collection_date,
                    vast_path,
                    session_name,  # Pass original session name for behavioral data lookup
                )
                save_metadata_file(
                    acquisition_metadata.model_dump(mode="json"),
                    metadata_dir,
                    "acquisition.json",
                )

                print(f"  Successfully created metadata for {formatted_name}")

                # Track successfully processed session for potential copying to /allen
                processed_sessions.append(
                    (session_name, formatted_name, vast_path)
                )

            except Exception as e:
                print(f"  Error creating metadata for {session_name}: {e}")
                continue

        else:
            print(f"  Warning: Could not extract timestamp for {session_name}")

    print(f"\nCompleted processing {len(df)} FIP sessions.")

    # Copy files to /allen if requested
    if copy_to_allen and processed_sessions:
        copy_metadata_to_allen_and_generate_csv(
            metadata_base_dir, processed_sessions
        )


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate metadata for FIP sessions"
    )
    parser.add_argument(
        "--csv-file",
        default="FPsessions_to_upload.csv",
        help="Path to FPsessions_to_upload.csv",
    )
    parser.add_argument(
        "--output-dir",
        default="metadata",
        help="Output directory for metadata",
    )
    parser.add_argument(
        "--force-overwrite",
        action="store_true",
        help="Overwrite existing metadata files",
    )
    parser.add_argument(
        "--copy-to-allen",
        action="store_true",
        help="Copy metadata files to /allen locations and generate deployment CSV",
    )

    args = parser.parse_args()

    # Convert to Path objects
    csv_path = Path(args.csv_file)
    metadata_base_dir = Path(args.output_dir)

    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}")
        return

    # Process the sessions
    process_fip_sessions(
        csv_path, metadata_base_dir, args.force_overwrite, args.copy_to_allen
    )


if __name__ == "__main__":
    main()
