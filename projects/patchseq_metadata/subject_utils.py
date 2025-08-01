"""
Utility functions for getting subject lists.
"""

import pandas as pd


def get_subjects_list(csv_file="patchseq_subject_ids.csv"):
    """
    Read the CSV file and return a list of subject IDs.
    
    Args:
        csv_file: Path to CSV file with subject IDs
        
    Returns:
        list: List of subject IDs
    """
    df = pd.read_csv(csv_file)
    subjects = df['subject_id'].tolist()
    print(f"Found {len(subjects)} subjects in {csv_file}")
    return subjects
