#!/usr/bin/env python3
"""
Fix paths in hopkins_hdf5_to_update_simplified.csv to use Linux forward slashes
"""

import pandas as pd
from pathlib import Path


def main():
    """Fix the hdf5_file paths to use Linux forward slashes."""

    # Load the simplified CSV
    csv_path = Path(__file__).parent / "hopkins_hdf5_to_update_simplified.csv"
    df = pd.read_csv(csv_path)

    # Fix the paths: replace \\ with / and convert backslashes to forward slashes
    df["hdf5_file"] = df["hdf5_file"].str.replace("\\\\", "/", regex=False)
    df["hdf5_file"] = df["hdf5_file"].str.replace("\\", "/", regex=False)

    # Save the updated CSV
    df.to_csv(csv_path, index=False)

    print(f"Fixed paths in: {csv_path}")
    print(f"Rows: {len(df)}")

    # Show first few rows to verify
    print("\nFirst 5 rows with fixed paths:")
    print(df[["hdf5_file", "session_name"]].head())


if __name__ == "__main__":
    main()

