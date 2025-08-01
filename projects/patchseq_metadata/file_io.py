"""
File I/O operations for procedures.json files.
"""

import json
from pathlib import Path


def save_procedures_json(subject_id, data, is_v1=False, output_dir="procedures"):
    """
    Save procedures data to a JSON file.
    If is_v1=True, saves as procedures.json.v1
    If is_v1=False, saves as procedures.json (v2 format)
    
    Args:
        subject_id: Subject ID
        data: Procedures data to save
        is_v1: Whether this is a v1.x schema file (default: False)
        output_dir: Base directory for procedures files
    """
    # Create procedures directory and subject subdirectory
    procedures_dir = Path(output_dir)
    subject_dir = procedures_dir / str(subject_id)
    subject_dir.mkdir(parents=True, exist_ok=True)
    
    # Determine the filename based on version
    if is_v1:
        filename = "procedures.json.v1"
    else:
        filename = "procedures.json"
    
    # Save procedures file
    filepath = subject_dir / filename
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, default=str)
    
    print(f"    Saved {filename} to: {filepath}")


def check_existing_procedures(subject_id, output_dir="procedures"):
    """
    Check if procedures files already exist for a subject.
    Returns tuple: (v1_exists: bool, v2_exists: bool, v1_data: dict or None, v2_data: dict or None)
    """
    procedures_dir = Path(output_dir) / str(subject_id)
    v1_path = procedures_dir / "procedures.json.v1"
    v2_path = procedures_dir / "procedures.json"
    
    v1_exists = v1_path.exists()
    v2_exists = v2_path.exists()
    
    v1_data = None
    v2_data = None
    
    if v1_exists:
        try:
            with open(v1_path, 'r') as f:
                v1_data = json.load(f)
        except Exception as e:
            print(f"  Warning: Could not load existing v1 file: {e}")
    
    if v2_exists:
        try:
            with open(v2_path, 'r') as f:
                v2_data = json.load(f)
        except Exception as e:
            print(f"  Warning: Could not load existing v2 file: {e}")
    
    return v1_exists, v2_exists, v1_data, v2_data
