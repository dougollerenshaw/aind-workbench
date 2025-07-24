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
import pandas as pd

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

def format_session_name(session_name: str, subject_id: str, session_datetime: datetime) -> str:
    """
    Format a session name according to AIND standards.
    
    Args:
        session_name: Original session name
        subject_id: Mapped AIND subject ID
        session_datetime: Timezone-aware datetime object for precise timing
        
    Returns:
        str: Formatted session name (subject_id_YYYY-MM-DD_HH-MM-SS)
    """
    # Use the provided datetime (which should be timezone-aware)
    date_str = session_datetime.strftime('%Y-%m-%d')
    time_str = session_datetime.strftime('%H-%M-%S')
    
    # Create formatted name
    return f"{subject_id}_{date_str}_{time_str}"

def get_experiment_metadata_dir(metadata_base_dir: Path, session_name: str, subject_id: str, session_datetime: datetime) -> Path:
    """
    Get the directory path for an experiment's metadata.
    
    Args:
        metadata_base_dir: Base directory for metadata
        session_name: Original session name
        subject_id: Subject ID (mapped to AIND ID if applicable)
        session_datetime: Timezone-aware datetime object for precise timing
        
    Returns:
        Path: Path to the experiment's metadata directory
    """
    # Format the session name for the folder
    aind_name = format_session_name(session_name, subject_id, session_datetime)
    
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


def get_session_details(subject_id: str, session_date: str) -> dict:
    """
    Get session details for a specific subject and date from CSV files.
    
    Args:
        subject_id: Subject ID (e.g., 'ZS059', 'ZS060', etc.)
        session_date: Session date in YYYY-MM-DD format
        
    Returns:
        dict: Session metadata dictionary, empty if not found
        
    Example:
        >>> get_session_details('ZS059', '2021-03-24')
        {
            'time_started': '2:20 PM',
            'time_ended': '3:25 PM',
            'start_contingency': '90/10',
            'num_reward_left': 92,
            'num_reward_right': 145,
            'num_trials': 435,
            'weight': 26.2,
            'water_received': 0.69,
            'behavior_notes': 'Good. left bias'
        }
    """
    # Find the CSV file for this subject
    csv_path = SCRIPT_DIR / "session_details" / f"ZS059_060_061_062 - {subject_id}.csv"
    
    if not csv_path.exists():
        return {}
    
    try:
        # Read CSV without headers
        df = pd.read_csv(csv_path, header=None)
        
        # Find date row and the column for our target date
        target_col = None
        for i, row in df.iterrows():
            if str(row.iloc[0]).strip().lower() == 'date':
                # Found the date row, now find our target date
                for col_idx in range(1, len(row)):
                    date_str = str(row.iloc[col_idx]).strip()
                    if date_str and date_str != 'nan':
                        try:
                            # Parse date formats: 2021/03/24 or 3/24/2021
                            if '/' in date_str and date_str.count('/') == 2:
                                parts = date_str.split('/')
                                if len(parts[0]) == 4:  # YYYY/MM/DD
                                    parsed_date = datetime.strptime(date_str, '%Y/%m/%d')
                                else:  # M/D/YYYY
                                    parsed_date = datetime.strptime(date_str, '%m/%d/%Y')
                                
                                if parsed_date.strftime('%Y-%m-%d') == session_date:
                                    target_col = col_idx
                                    break
                        except ValueError:
                            continue
                break
        
        if target_col is None:
            return {}
        
        # Extract values for this date from relevant rows
        result = {}
        
        # Map of what we want to extract
        wanted_rows = {
            'Time Started': 'time_started',
            'Time Ended': 'time_ended',
            'Start contingency': 'start_contingency', 
            'Num. of reward L/R': 'rewards_lr',
            'No. of trials': 'num_trials',
            'Reward size': 'reward_size',
            'Behavior': 'behavior_notes',
            'Weight': 'weight',
            'Water received': 'water_received',
            'Position': 'tetrode_position'
        }
        
        # Go through each row and extract data
        for i, row in df.iterrows():
            row_label = str(row.iloc[0]).strip()
            if row_label in wanted_rows:
                value = str(row.iloc[target_col]).strip()
                if value and value != 'nan':
                    key = wanted_rows[row_label]
                    
                    # Handle special cases
                    if key == 'rewards_lr' and '/' in value:
                        # Split "92/145" into separate left/right values
                        try:
                            left, right = value.split('/')
                            result['num_reward_left'] = int(left.strip())
                            result['num_reward_right'] = int(right.strip())
                        except ValueError:
                            result[key] = value
                    elif key in ['num_trials']:
                        # Convert to int
                        try:
                            result[key] = int(value)
                        except ValueError:
                            result[key] = value
                    elif key in ['reward_size', 'weight', 'water_received', 'tetrode_position']:
                        # Convert to float
                        try:
                            result[key] = float(value)
                        except ValueError:
                            result[key] = value
                    else:
                        # Keep as string
                        result[key] = value
        
        return result
        
    except Exception as e:
        print(f"Error reading session details for {subject_id} on {session_date}: {str(e)}")
        return {}


def extract_session_start_time_from_path(vast_path: str, session_name: str) -> str:
    """
    Extract session start time from the session folder structure.
    
    Args:
        vast_path: Path from the vast_path column (e.g. 'scratch/sueSu/ZS061/mZS061d20210404')
        session_name: Session name to look for
        
    Returns:
        Optional[str]: Session start time in YYYY-MM-DD_HH-MM-SS format, or None if not found
    """
    import re
    
    # Construct the base path to look for session folders
    if vast_path.startswith("scratch/sueSu/"):
        relative_path = vast_path[len("scratch/sueSu/"):]
    else:
        relative_path = vast_path
    
    # Base path where data is stored
    base_path = "/allen/aind/stage/hopkins_data"
    session_base_path = os.path.join(base_path, relative_path, "neuralynx", "session")
    
    if not os.path.exists(session_base_path):
        return None
    
    # Look for session folders with timestamp format YYYY-MM-DD_HH-MM-SS
    pattern = re.compile(r'(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})')
    
    try:
        for folder_name in os.listdir(session_base_path):
            folder_path = os.path.join(session_base_path, folder_name)
            if os.path.isdir(folder_path):
                match = pattern.match(folder_name)
                if match:
                    return match.group(1)
    except (OSError, PermissionError):
        return None
    
    return None


def create_session_datetime(collection_date: str, vast_path: str, session_name: str, collection_site: str, session_details: dict = None) -> datetime:
    """
    Create a timezone-aware datetime for the session.
    
    Uses a two-tier fallback system:
    1. Try to extract timestamp from Neuralynx folder structure
    2. Fall back to 'time_started' value from session details CSV
    3. If neither available, raise ValueError
    
    Args:
        collection_date: Date string from CSV (YYYY-MM-DD format)
        vast_path: Path from the vast_path column
        session_name: Session name
        collection_site: Collection site (JHU=east coast, AIND=west coast)
        session_details: Session details dict from CSV files (for fallback)
        
    Returns:
        datetime: Timezone-aware datetime object with proper offset format
                 (e.g., 2021-04-04T17:43:18-04:00 for Eastern time)
                 Uses zoneinfo for proper timezone handling including DST
                 
    Raises:
        ValueError: If timestamp cannot be extracted from either source
    """
    import zoneinfo
    from datetime import datetime
    
    # Try to extract session time from Neuralynx folder structure first
    extracted_time = extract_session_start_time_from_path(vast_path, session_name)
    
    if extracted_time:
        # Parse the extracted timestamp: YYYY-MM-DD_HH-MM-SS
        dt = datetime.strptime(extracted_time, "%Y-%m-%d_%H-%M-%S")
        print(f"  Using timestamp from Neuralynx folder: {extracted_time}")
    else:
        # Fall back to "time_started" value from session details CSV
        time_started = session_details.get('time_started') if session_details else None
        if time_started and str(time_started).strip():
            # Try to parse the time_started value - format may vary
            time_str = str(time_started).strip()
            print(f"  Neuralynx folder timestamp not found, using 'time_started' from session details: {time_str}")
            
            # Try common time formats
            for fmt in ["%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p"]:
                try:
                    time_obj = datetime.strptime(time_str, fmt).time()
                    # Combine with collection date
                    date_obj = datetime.strptime(collection_date, "%Y-%m-%d").date()
                    dt = datetime.combine(date_obj, time_obj)
                    break
                except ValueError:
                    continue
            else:
                raise ValueError(f"Could not parse 'time_started' value: {time_str} for session {session_name}")
        else:
            raise ValueError(f"Could not extract session start time from Neuralynx path and no 'time_started' value available for {session_name}")
    
    # Set timezone based on collection site
    if collection_site.upper() in ['JHU', 'HOPKINS']:
        # Johns Hopkins is East Coast (US/Eastern)
        eastern = zoneinfo.ZoneInfo("US/Eastern")
        return dt.replace(tzinfo=eastern)
    else:
        # AIND is West Coast (US/Pacific) 
        pacific = zoneinfo.ZoneInfo("US/Pacific")
        return dt.replace(tzinfo=pacific)
