#!/usr/bin/env python3
"""
Add actual session names to hopkins_hdf5_to_update.csv
"""

import pandas as pd
from pathlib import Path


def main():
    """Add actual session names to the CSV."""

    # Load the original CSV
    original_csv = Path(__file__).parent / "hopkins_hdf5_to_update.csv"
    df = pd.read_csv(original_csv)

    # Load the mapping
    mapping_csv = Path(__file__).parent / "hopkins_session_mapping.csv"
    mapping_df = pd.read_csv(mapping_csv)

    # Create a mapping dictionary
    mapping_dict = dict(
        zip(mapping_df["original_session"], mapping_df["database_session"])
    )

    # Extract the base session name from session_id (remove 'behavior_' prefix)
    df["base_session_name"] = df["session_id"].str.replace("behavior_", "")

    # Map to actual session names
    df["actual_session_name"] = df["base_session_name"].map(mapping_dict)

    # Check for any missing mappings
    missing_mappings = df[df["actual_session_name"].isna()]
    if not missing_mappings.empty:
        print(
            f"Warning: {len(missing_mappings)} rows have missing session name mappings:"
        )
        print(missing_mappings[["session_id", "base_session_name"]].head())

    # Save the updated CSV
    output_csv = (
        Path(__file__).parent / "hopkins_hdf5_to_update_with_actual_names.csv"
    )
    df.to_csv(output_csv, index=False)

    print(f"Updated CSV saved to: {output_csv}")
    print(f"Total rows: {len(df)}")
    print(f"Rows with actual session names: {len(df) - len(missing_mappings)}")
    print(f"Rows missing session names: {len(missing_mappings)}")

    # Show sample of the updated data
    print(f"\nSample of updated data:")
    print(
        df[["session_id", "base_session_name", "actual_session_name"]].head(10)
    )


if __name__ == "__main__":
    main()
