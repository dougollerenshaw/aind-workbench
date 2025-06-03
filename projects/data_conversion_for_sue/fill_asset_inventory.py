import os
import pandas as pd
import argparse
from pathlib import Path
import numpy as np
from utils import (
    load_session_data,
    extract_behavioral_metrics,
    construct_file_path,
)

# Get the directory containing this script
SCRIPT_DIR = Path(__file__).parent.absolute()

# Define the desired column order - behavioral metrics right after vast_path
COLUMN_ORDER = [
    "session_name",
    "physiology_modality",
    "subject_id",
    "collection_date",
    "collection_site",
    "investigators",
    "rig_id",
    "funding_source",
    "on_vast",
    "vast_path",
    # Behavioral metrics right after vast_path
    "ISSUE_DESCRIPTION",
    "REWARD_CONSUMED_TOTAL_MICROLITER",
    "SESSION_DURATION_MINUTES",
    "TOTAL_TRIALS",
    "TOTAL_REWARDS",
    "TOTAL_LICKS",
    "LEFT_REWARDS",
    "RIGHT_REWARDS",
    "LEFT_LICKS",
    "RIGHT_LICKS",
    "SESSION_DURATION_SECONDS",
    "TRIAL_TYPE_CSPLUS_COUNT",
    "TRIAL_TYPE_CSMINUS_COUNT",
    # Original empty columns after behavioral metrics
    "SESSION_NOTES",
    "SESSION_START_TIME",
    "SESSION_END_TIME",
    "DATA_STREAM_START_TIME",
    "DATA_STREAM_END_TIME",
    "IACUC_PROTOCOL",
    "EXPERIMENTER_FULL_NAME_LIST",
    "SUBJECT_WEIGHT_PRIOR",
    "SUBJECT_WEIGHT_POST",
    "DATE_OF_BIRTH",
    "BREEDING_INFO",
    "GENOTYPE",
    "SUBJECT_SEX",
]


def fill_behavioral_metrics(row, base_path: str):
    """
    Extract behavioral metrics for a single session and return updated row data.

    Args:
        row: Row from the asset inventory DataFrame
        base_path: Base path to the data files

    Returns:
        dict: Dictionary of updated values for this row
    """
    session_name = row["session_name"]

    # Construct file path
    mat_path = construct_file_path(base_path, row["vast_path"], session_name)

    print(f"Processing session: {session_name}")
    print(f"Data file path: {mat_path}")

    # Initialize return dictionary with current values
    updated_values = {}

    try:
        # Check if file exists
        if not os.path.exists(mat_path):
            print(f"  WARNING: File not found: {mat_path}")
            updated_values["ISSUE_DESCRIPTION"] = "File not found"
            return updated_values

        # Load behavioral data
        beh_df, licks_L, licks_R = load_session_data(mat_path)

        if beh_df.empty:
            print(f"  WARNING: No behavioral data loaded for {session_name}")
            updated_values["ISSUE_DESCRIPTION"] = "No behavioral data loaded"
            return updated_values

        # Extract behavioral metrics with default reward volume
        metrics = extract_behavioral_metrics(beh_df, licks_L, licks_R)

        # Map metrics to CSV columns that are relevant to AIND schema
        updated_values.update(
            {
                "REWARD_CONSUMED_TOTAL_MICROLITER": metrics[
                    "reward_volume_microliters"
                ],
                "ISSUE_DESCRIPTION": "Success",  # Mark successful processing
            }
        )

        # Print summary of extracted data
        print(f"  Behavioral DataFrame shape: {beh_df.shape}")
        print(
            f"  Session duration: {metrics['session_duration_seconds']:.1f} seconds ({metrics['session_duration_seconds']/60:.2f} minutes)"
        )
        print(f"  Total trials: {metrics['total_trials']}")
        print(f"  Total rewards: {metrics['total_rewards']}")
        print(
            f"  Total licks: {metrics['total_licks']} (L: {metrics['total_left_licks']}, R: {metrics['total_right_licks']})"
        )
        print(
            f"  Reward volume: {metrics['reward_volume_microliters']:.1f} μL"
        )

        # Add additional metrics as new columns for analysis purposes
        additional_metrics = {
            "TOTAL_TRIALS": metrics["total_trials"],
            "TOTAL_LICKS": metrics["total_licks"],
            "LEFT_LICKS": metrics["total_left_licks"],
            "RIGHT_LICKS": metrics["total_right_licks"],
            "LEFT_REWARDS": metrics["left_rewards"],
            "RIGHT_REWARDS": metrics["right_rewards"],
            "SESSION_DURATION_SECONDS": metrics["session_duration_seconds"],
            "SESSION_DURATION_MINUTES": metrics["session_duration_seconds"]
            / 60.0,
        }

        # Add trial type breakdowns if available
        for key, value in metrics.items():
            if key.startswith("trial_type_"):
                column_name = key.upper()
                additional_metrics[column_name] = value

        updated_values.update(additional_metrics)

    except Exception as e:
        print(f"  ERROR processing {session_name}: {str(e)}")
        updated_values["ISSUE_DESCRIPTION"] = f"Error: {str(e)}"

    return updated_values


def process_asset_inventory(
    inventory_df: pd.DataFrame,
    base_path: str,
    output_path: Path,
    all_sessions: bool = False,
):
    """
    Process the asset inventory and fill in behavioral metrics.

    Args:
        inventory_df: DataFrame containing session inventory
        base_path: Base path to the data files
        output_path: Path to save the updated CSV
        all_sessions: If True, process all sessions; if False, only process the first few
    """
    # Make a copy of the DataFrame to avoid modifying the original
    updated_df = inventory_df.copy()

    # Get sessions to process
    if all_sessions:
        sessions_to_process = updated_df
        print(f"Processing all {len(sessions_to_process)} sessions...")
    else:
        sessions_to_process = updated_df.iloc[
            :5
        ]  # Process first 5 for testing
        print(
            f"Test mode: Processing first {len(sessions_to_process)} sessions..."
        )

    # Track processing statistics
    success_count = 0
    error_count = 0
    file_not_found_count = 0

    # Process each session
    for idx, row in sessions_to_process.iterrows():
        try:
            updated_values = fill_behavioral_metrics(row, base_path)

            if updated_values:
                # Update the DataFrame with new values
                for column, value in updated_values.items():
                    # Add new columns if they don't exist
                    if column not in updated_df.columns:
                        updated_df[column] = np.nan
                    updated_df.at[idx, column] = value

                # Check the issue description to categorize the result
                issue_desc = updated_values.get("ISSUE_DESCRIPTION", "Unknown")
                if issue_desc == "Success":
                    success_count += 1
                    print(f"  ✓ Successfully processed {row['session_name']}")
                elif "File not found" in issue_desc:
                    file_not_found_count += 1
                    print(f"  ⚠ File not found for {row['session_name']}")
                else:
                    error_count += 1
                    print(
                        f"  ⚠ Issue with {row['session_name']}: {issue_desc}"
                    )
            else:
                # This shouldn't happen now, but just in case
                error_count += 1
                updated_df.at[idx, "ISSUE_DESCRIPTION"] = "No data returned"
                print(f"  ✗ No data returned for {row['session_name']}")

        except Exception as e:
            error_count += 1
            # Make sure ISSUE_DESCRIPTION column exists
            if "ISSUE_DESCRIPTION" not in updated_df.columns:
                updated_df["ISSUE_DESCRIPTION"] = np.nan
            updated_df.at[idx, "ISSUE_DESCRIPTION"] = (
                f"Processing error: {str(e)}"
            )
            print(f"  ✗ Error processing {row['session_name']}: {str(e)}")

        print()  # Add blank line between sessions

    # Reorder columns using the predefined COLUMN_ORDER
    # Only include columns that actually exist in the DataFrame
    final_columns = [col for col in COLUMN_ORDER if col in updated_df.columns]

    # Add any columns that exist in the DataFrame but aren't in COLUMN_ORDER (as a safeguard)
    remaining_columns = [
        col for col in updated_df.columns if col not in COLUMN_ORDER
    ]
    if remaining_columns:
        print(
            f"Warning: Found {len(remaining_columns)} columns not in COLUMN_ORDER: {remaining_columns}"
        )
        final_columns.extend(remaining_columns)

    # Save the updated DataFrame with the specified column order
    updated_df[final_columns].to_csv(output_path, index=False)
    print(f"Updated asset inventory saved to: {output_path}")

    # Print summary statistics
    print(f"\nProcessing Summary:")
    print(f"Successfully processed: {success_count} sessions")
    print(f"File not found: {file_not_found_count} sessions")
    print(f"Errors encountered: {error_count} sessions")
    print(
        f"Total processed: {success_count + file_not_found_count + error_count} sessions"
    )

    # Print issue breakdown
    if "ISSUE_DESCRIPTION" in updated_df.columns:
        issue_counts = updated_df["ISSUE_DESCRIPTION"].value_counts()
        print(f"\nIssue Breakdown:")
        for issue, count in issue_counts.items():
            print(f"  {issue}: {count} sessions")

    # Print column summary
    new_columns = [
        col for col in updated_df.columns if col not in inventory_df.columns
    ]
    if new_columns:
        print(f"\nNew columns added: {len(new_columns)}")
        for col in new_columns:
            non_null_count = updated_df[col].notna().sum()
            print(f"  {col}: {non_null_count} non-null values")

    # Print some basic statistics for key metrics
    if success_count > 0:
        print(
            f"\nBehavioral Metrics Summary (for successfully processed sessions):"
        )

        if "SESSION_DURATION_MINUTES" in updated_df.columns:
            durations = updated_df["SESSION_DURATION_MINUTES"].dropna()
            if len(durations) > 0:
                print(
                    f"  Session duration: {durations.mean():.1f} ± {durations.std():.1f} minutes (mean ± std)"
                )
                print(
                    f"  Duration range: {durations.min():.1f} - {durations.max():.1f} minutes"
                )

        if "REWARD_CONSUMED_TOTAL_MICROLITER" in updated_df.columns:
            rewards = updated_df["REWARD_CONSUMED_TOTAL_MICROLITER"].dropna()
            if len(rewards) > 0:
                print(
                    f"  Reward volume: {rewards.mean():.1f} ± {rewards.std():.1f} μL (mean ± std)"
                )
                print(
                    f"  Reward range: {rewards.min():.1f} - {rewards.max():.1f} μL"
                )

        if "TOTAL_TRIALS" in updated_df.columns:
            trials = updated_df["TOTAL_TRIALS"].dropna()
            if len(trials) > 0:
                print(
                    f"  Trial count: {trials.mean():.1f} ± {trials.std():.1f} trials (mean ± std)"
                )
                print(
                    f"  Trial range: {int(trials.min())} - {int(trials.max())} trials"
                )

        if "TOTAL_LICKS" in updated_df.columns:
            licks = updated_df["TOTAL_LICKS"].dropna()
            if len(licks) > 0:
                print(
                    f"  Lick count: {licks.mean():.1f} ± {licks.std():.1f} licks (mean ± std)"
                )
                print(
                    f"  Lick range: {int(licks.min())} - {int(licks.max())} licks"
                )


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Fill asset inventory CSV with behavioral metrics extracted from .mat files."
    )
    parser.add_argument(
        "--all-sessions",
        action="store_true",
        help="Process all sessions (default: only process first 5 sessions for testing)",
    )
    parser.add_argument(
        "--data-path",
        type=str,
        required=True,
        help="Base path to the data files containing the .mat files",
    )
    args = parser.parse_args()

    # Read the asset inventory from the script directory
    inventory_path = SCRIPT_DIR / "asset_inventory.csv"
    if not inventory_path.exists():
        print(f"Error: Asset inventory file not found: {inventory_path}")
        return

    inventory_df = pd.read_csv(inventory_path)
    print(f"Loaded asset inventory with {len(inventory_df)} sessions")
    print(f"Original columns: {len(inventory_df.columns)}")

    # Process the inventory and save back to the same file
    process_asset_inventory(
        inventory_df, args.data_path, inventory_path, args.all_sessions
    )


if __name__ == "__main__":
    main()
