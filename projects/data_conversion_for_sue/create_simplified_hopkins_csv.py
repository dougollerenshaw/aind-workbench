#!/usr/bin/env python3
"""
Create a simplified version of hopkins_hdf5_to_update.csv
"""

import pandas as pd
from pathlib import Path


def main():
    """Create simplified CSV with only required columns."""

    # Load the original CSV
    original_csv = Path(__file__).parent / "hopkins_hdf5_to_update.csv"
    df = pd.read_csv(original_csv)

    # Select only the required columns and rename them
    simplified_df = df[
        [
            "raw_data_CO_dataasset_id",
            "hdf5_file",
            "dir_in_asset",
            "actual_session_name",
        ]
    ].copy()

    # Fix the typo in the column name and rename actual_session_name
    simplified_df = simplified_df.rename(
        columns={
            "raw_data_CO_dataasset_id": "raw_data_CO_data_asset_id",
            "actual_session_name": "session_name",
        }
    )

    # Save the simplified CSV
    output_csv = (
        Path(__file__).parent / "hopkins_hdf5_to_update_simplified.csv"
    )
    simplified_df.to_csv(output_csv, index=False)

    print(f"Simplified CSV created: {output_csv}")
    print(f"Rows: {len(simplified_df)}")
    print(f"Columns: {list(simplified_df.columns)}")

    # Show first few rows
    print("\nFirst 5 rows:")
    print(simplified_df.head())


if __name__ == "__main__":
    main()

