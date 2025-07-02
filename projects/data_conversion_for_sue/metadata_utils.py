#!/usr/bin/env python3
"""
Utility functions for metadata handling that are shared between scripts.
"""

import os
import yaml
from pathlib import Path
import json
import shutil
from datetime import datetime

# Get the directory containing this script
SCRIPT_DIR = Path(__file__).parent.absolute()

# Load configuration from YAML file
def load_config():
    """
    Load configuration from config.yaml file.
    
    Returns:
        dict: Configuration dictionary
    """
    config_path = SCRIPT_DIR / "config.yaml"
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

# Load the subject ID mapping from config
config = load_config()
SUBJECT_ID_MAPPING = config.get('subject_id_mapping', {})
ORCID_MAPPING = config.get('orcid_mapping', {})

def get_mapped_subject_id(original_subject_id: str) -> str:
    """
    Get the mapped subject ID for metadata service lookup.
    
    Args:
        original_subject_id: Original subject ID from asset inventory
        
    Returns:
        str: Mapped subject ID for metadata service, or original if no mapping exists
    """
    return SUBJECT_ID_MAPPING.get(original_subject_id, original_subject_id)

def format_session_name(session_name: str, collection_date: str, subject_id: str) -> str:
    """
    Format a session name according to AIND standards.
    
    Args:
        session_name: Original session name
        collection_date: Collection date string
        subject_id: Mapped AIND subject ID
        
    Returns:
        str: Formatted session name (subject_id_YYYY-MM-DD_HH-MM-SS)
    """
    # Convert date to datetime if it's a string
    if isinstance(collection_date, str):
        try:
            date_obj = datetime.strptime(collection_date, '%Y-%m-%d').date()
        except ValueError:
            # Try parsing with pandas
            import pandas as pd
            date_obj = pd.to_datetime(collection_date).date()
    else:
        date_obj = collection_date
    
    # Default time is noon if not provided
    time_str = "12-00-00"
    
    # Format date
    date_str = date_obj.strftime('%Y-%m-%d')
    
    # Create formatted name
    return f"{subject_id}_{date_str}_{time_str}"

def get_experiment_metadata_dir(metadata_base_dir: Path, session_name: str, collection_date: str, subject_id: str) -> Path:
    """
    Get the directory path for an experiment's metadata.
    
    Args:
        metadata_base_dir: Base directory for metadata
        session_name: Original session name
        collection_date: Collection date
        subject_id: Subject ID (mapped to AIND ID if applicable)
        
    Returns:
        Path: Path to the experiment's metadata directory
    """
    # Format the session name for the folder
    aind_name = format_session_name(session_name, collection_date, subject_id)
    
    # Create experiment directory path
    return metadata_base_dir / aind_name

def save_metadata_file(data: dict, metadata_dir: Path, filename: str):
    """
    Save metadata to a JSON file in the experiment's folder.

    Args:
        data: Metadata dictionary to save
        metadata_dir: Metadata directory for the experiment
        filename: Filename for the metadata file (e.g., 'procedures.json')
    """
    # Create directory
    metadata_dir.mkdir(parents=True, exist_ok=True)

    # Save file
    filepath = metadata_dir / filename
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

    print(f"  Saved {filename} to: {filepath}")
    
    return filepath

def copy_metadata_to_experiment(
    source_metadata_dir: Path,
    target_metadata_dir: Path,
    subject_id: str,
    file_type: str
):
    """
    Copy metadata files from subject-based directory to experiment-based directory.
    
    Args:
        source_metadata_dir: Source directory containing subject metadata
        target_metadata_dir: Target directory for experiment metadata
        subject_id: Subject ID
        file_type: Type of metadata file ('subject' or 'procedures')
    
    Returns:
        bool: True if copy was successful, False otherwise
    """
    # Create paths
    source_file = source_metadata_dir / subject_id / f"{file_type}.json"
    target_file = target_metadata_dir / f"{file_type}.json"
    
    # Check if source exists
    if not source_file.exists():
        print(f"  Warning: Source file not found: {source_file}")
        return False
    
    # Create target directory if needed
    target_metadata_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy file
    shutil.copy2(source_file, target_file)
    print(f"  Copied {file_type}.json to: {target_file}")
    
    return True

def check_experiment_metadata_completion(experiment_dir: Path) -> dict:
    """
    Check if an experiment directory has all required metadata files.
    
    Args:
        experiment_dir: Path to experiment directory
        
    Returns:
        dict: Dictionary with each file type as key and existence as boolean value
    """
    required_files = {
        "subject.json": False,
        "procedures.json": False,
        "data_description.json": False
        # Add other required files as needed
    }
    
    # Check each required file
    for filename in required_files.keys():
        filepath = experiment_dir / filename
        required_files[filename] = filepath.exists()
    
    return required_files
