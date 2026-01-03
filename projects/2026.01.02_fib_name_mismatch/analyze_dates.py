#!/usr/bin/env python3
"""
Analyze the FIB modality issues file to extract dates and determine if the issue is ongoing.
"""

import pandas as pd
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple


def extract_dates_from_processed_name(processed_name: str) -> Optional[Tuple[str, str]]:
    """
    Extract collection date and processing date from processed session name.

    Processed format: behavior_<subject_id>_<collection_date>_<time>_processed_<processing_date>_<time>

    Returns: (collection_date, processing_date) or None if parsing fails
    """
    # Pattern: behavior_<subject_id>_<collection_date>_<time>_processed_<processing_date>_<time>
    pattern = r"behavior_\d+_(\d{4}-\d{2}-\d{2})_\d{2}-\d{2}-\d{2}_processed_(\d{4}-\d{2}-\d{2})_\d{2}-\d{2}-\d{2}"

    match = re.search(pattern, processed_name)
    if match:
        collection_date = match.group(1)
        processing_date = match.group(2)
        return (collection_date, processing_date)

    return None


def extract_collection_date_from_raw_name(raw_name: str) -> Optional[str]:
    """
    Extract collection date from raw session name.

    Raw session format: behavior_<subject_id>_<collection_date>_<time>

    Returns: collection_date or None if parsing fails
    """
    pattern = r"behavior_\d+_(\d{4}-\d{2}-\d{2})_\d{2}-\d{2}-\d{2}"
    match = re.search(pattern, raw_name)
    if match:
        return match.group(1)
    return None


def parse_issues_file(file_path: str) -> pd.DataFrame:
    """Parse the issues file and extract relevant information."""
    records = []

    with open(file_path, "r") as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Look for Subject line
        if line.startswith("Subject:"):
            subject_id = line.split("Subject:")[1].strip()

            # Find raw session (skip blank lines)
            raw_session = None
            j = i + 1
            while j < len(lines):
                raw_line = lines[j].strip()
                if raw_line.startswith("Raw session:"):
                    raw_session = raw_line.split("Raw session:")[1].strip()
                    j += 1
                    break
                j += 1

            if not raw_session:
                i = j
                continue

            # Skip "Number of problematic..." line
            while j < len(lines) and not lines[j].strip().startswith("Processed records:"):
                j += 1

            # Skip "Processed records:" line
            if j < len(lines):
                j += 1

            # Collect processed records
            processed_records = []
            while j < len(lines):
                proc_line = lines[j].strip()
                if proc_line.startswith("-"):
                    proc_name = proc_line.lstrip("-").strip()
                    processed_records.append(proc_name)
                    j += 1
                elif proc_line == "" or proc_line.startswith("Subject:"):
                    # End of this entry
                    break
                else:
                    j += 1

            # Extract dates from each processed record
            for proc_record in processed_records:
                dates = extract_dates_from_processed_name(proc_record)
                if dates:
                    collection_date, processing_date = dates
                    records.append(
                        {
                            "subject_id": subject_id,
                            "raw_session": raw_session,
                            "processed_session": proc_record,
                            "collection_date": collection_date,
                            "processing_date": processing_date,
                        }
                    )
                else:
                    # Fallback: try to get collection date from raw session
                    collection_date = extract_collection_date_from_raw_name(raw_session)
                    if collection_date:
                        records.append(
                            {
                                "subject_id": subject_id,
                                "raw_session": raw_session,
                                "processed_session": proc_record,
                                "collection_date": collection_date,
                                "processing_date": None,
                            }
                        )

            i = j
            continue

        i += 1

    return pd.DataFrame(records)


def main():
    file_path = Path(__file__).parent / "fib_modality_issues.txt"

    print("Parsing issues file...")
    df = parse_issues_file(str(file_path))

    print(f"\nParsed {len(df)} processed records")

    # Convert dates to datetime for sorting
    df["collection_date_dt"] = pd.to_datetime(df["collection_date"])
    df["processing_date_dt"] = pd.to_datetime(df["processing_date"])

    # Sort by processing date (most recent first)
    df_sorted = df.sort_values("processing_date_dt", ascending=False)

    print(f"\nDate range:")
    print(f"  Collection dates: {df['collection_date_dt'].min()} to {df['collection_date_dt'].max()}")
    print(f"  Processing dates: {df['processing_date_dt'].min()} to {df['processing_date_dt'].max()}")

    print(f"\nMost recent processing date: {df_sorted['processing_date_dt'].iloc[0]}")
    print(f"Most recent collection date: {df_sorted['collection_date_dt'].iloc[0]}")

    # Show the 10 most recent entries
    print("\n10 most recent problematic cases (by processing date):")
    print("=" * 80)
    for idx, row in df_sorted.head(10).iterrows():
        print(f"Subject: {row['subject_id']}")
        print(f"  Collection: {row['collection_date']}")
        print(f"  Processing: {row['processing_date']}")
        print(f"  Processed session: {row['processed_session']}")
        print()

    # Save sorted dataframe
    output_file = Path(__file__).parent / "fib_modality_issues_analyzed.csv"
    df_sorted.to_csv(output_file, index=False)
    print(f"\nSorted data saved to: {output_file}")

    # Check if issue is ongoing (within last 30 days)
    most_recent = df_sorted["processing_date_dt"].iloc[0]
    days_ago = (datetime.now() - most_recent).days
    print(f"\nMost recent processing was {days_ago} days ago")
    if days_ago <= 30:
        print("⚠️  WARNING: Issue appears to be ongoing (within last 30 days)")
    else:
        print("✓ Issue appears to have stopped (most recent > 30 days ago)")


if __name__ == "__main__":
    main()
