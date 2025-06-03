import os
import pandas as pd
from datetime import datetime, timedelta
import zoneinfo
from pathlib import Path
import argparse
from aind_data_schema.core.acquisition import (
    Acquisition,
    DataStream,
    AcquisitionSubjectDetails,
)
from aind_data_schema_models.modalities import Modality
from aind_data_schema_models.units import VolumeUnit
from utils import (
    load_session_data,
    calculate_session_duration,
    count_rewards,
    construct_file_path,
    extract_behavioral_metrics,
)

DEFAULT_SESSION_TIME = "12:00:00"  # Noon
TIME_ASSUMPTION_NOTE = "Note: Session start time is assumed to be 12:00:00 (noon) as exact time was not recorded."

# Get the directory containing this script
SCRIPT_DIR = Path(__file__).parent.absolute()


def get_acquisition_type_and_modality(physiology_modality: str):
    """
    Determine acquisition type and modality from physiology_modality column.

    Args:
        physiology_modality: Value from the physiology_modality column

    Returns:
        tuple: (acquisition_type, modality_enum)
    """
    if physiology_modality == "fiber_photometry":
        return "behavior_fiber_photometry", Modality.FIB
    elif physiology_modality == "ephys":
        return "behavior_ephys", Modality.ECEPHYS
    else:
        raise ValueError(f"Unknown physiology modality: {physiology_modality}")


def create_acquisition_metadata(row, base_path: str) -> Acquisition:
    """
    Create an Acquisition object for a single row of the asset inventory.

    Args:
        row: Row from the asset inventory DataFrame
        base_path: Base path to the data files

    Returns:
        Acquisition: Validated acquisition metadata
    """
    session_name = row["session_name"]

    # Construct file path using shared utility
    mat_path = construct_file_path(base_path, row["vast_path"], session_name)

    print(f"\nProcessing session: {session_name}")
    print(f"Data file path: {mat_path}")

    # Load behavioral data
    beh_df, licks_L, licks_R = load_session_data(mat_path)

    # Print verbose information about the loaded data
    print(f"Behavioral DataFrame shape: {beh_df.shape}")
    print(f"Behavioral DataFrame columns: {list(beh_df.columns)}")
    print(f"Number of left licks: {len(licks_L)}")
    print(f"Number of right licks: {len(licks_R)}")

    # Extract behavioral metrics using shared utility with default reward volume
    metrics = extract_behavioral_metrics(beh_df, licks_L, licks_R)

    print(f"\nSession metrics:")
    print(
        f"Session duration: {metrics['session_duration_seconds']} seconds ({metrics['session_duration_seconds']/60:.2f} minutes)"
    )
    print(f"Total rewards counted: {metrics['total_rewards']}")

    # Use collection_date from CSV and add default time
    collection_date = pd.to_datetime(row["collection_date"]).date()
    datetime_str = f"{collection_date} {DEFAULT_SESSION_TIME}"
    acquisition_start = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
    acquisition_start = acquisition_start.replace(
        tzinfo=zoneinfo.ZoneInfo("UTC")
    )

    # Calculate end time using duration
    acquisition_end = acquisition_start + timedelta(
        seconds=metrics["session_duration_seconds"]
    )

    # Get acquisition type and modality
    acquisition_type, modality = get_acquisition_type_and_modality(
        row["physiology_modality"]
    )

    # Create subject details
    subject_details = AcquisitionSubjectDetails(
        mouse_platform_name="rotating_platform_v1",  # Default value
        reward_consumed_total=metrics["reward_volume_microliters"]
        / 1000,  # Convert μL to mL
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

    # Create minimal data stream (we'll need to add configurations later)
    data_stream = DataStream(
        stream_start_time=acquisition_start,
        stream_end_time=acquisition_end,
        modalities=[modality],
        active_devices=["behavior_rig"],  # Minimal device list
        configurations=[],  # TODO: Add minimal configurations
        notes=TIME_ASSUMPTION_NOTE,
    )

    # Create the acquisition object
    acquisition = Acquisition(
        subject_id=row["subject_id"],
        acquisition_start_time=acquisition_start,
        acquisition_end_time=acquisition_end,
        instrument_id=row["rig_id"],
        acquisition_type=acquisition_type,
        data_streams=[data_stream],
        subject_details=subject_details,
    )

    return acquisition


def process_acquisitions(
    inventory_df: pd.DataFrame,
    base_path: str,
    output_dir: Path,
    all_sessions: bool = False,
):
    """
    Process acquisitions from the inventory and create metadata files.

    Args:
        inventory_df: DataFrame containing session inventory
        base_path: Base path to the data files
        output_dir: Directory to save metadata files
        all_sessions: If True, process all sessions; if False, only process the first session
    """
    # Create output directory
    output_dir.mkdir(exist_ok=True)

    # Get sessions to process
    if all_sessions:
        sessions_to_process = inventory_df
        print(f"Processing all {len(sessions_to_process)} acquisitions...")
    else:
        sessions_to_process = inventory_df.iloc[:1]
        print("Test mode: Processing only the first acquisition...")

    # Process selected sessions
    success_count = 0
    error_count = 0

    for idx, row in sessions_to_process.iterrows():
        try:
            # Create acquisition metadata
            acquisition = create_acquisition_metadata(row, base_path)

            # Save as JSON
            output_path = (
                output_dir / f"{row['session_name']}_acquisition.json"
            )
            with open(output_path, "w") as f:
                f.write(acquisition.model_dump_json(indent=2))

            print(f"Created acquisition metadata for {row['session_name']}")
            success_count += 1

        except Exception as e:
            print(f"Error processing {row['session_name']}: {str(e)}")
            error_count += 1

    # Print summary
    print(f"\nProcessing complete:")
    print(f"Successfully processed: {success_count} acquisitions")
    if error_count > 0:
        print(f"Errors encountered: {error_count} acquisitions")


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Generate acquisition metadata files."
    )
    parser.add_argument(
        "--all-sessions",
        action="store_true",
        help="Process all sessions (default: only process first session)",
    )
    parser.add_argument(
        "--data-path",
        type=str,
        required=True,
        help="Base path to the data files containing the .mat files",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        help="Directory to save acquisition metadata files (default: acquisitions/ in the script directory)",
    )
    args = parser.parse_args()

    # Convert paths to Path objects
    data_path = Path(args.data_path)
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = SCRIPT_DIR / "acquisitions"

    # Read the asset inventory from the script directory
    inventory_path = SCRIPT_DIR / "asset_inventory.csv"
    inventory_df = pd.read_csv(inventory_path)

    # Process acquisitions
    process_acquisitions(
        inventory_df, str(data_path), output_dir, args.all_sessions
    )


if __name__ == "__main__":
    main()
