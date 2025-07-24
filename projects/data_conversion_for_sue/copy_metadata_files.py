#!/usr/bin/env python3
"""
Copy subject.json and procedures.json files to session metadata folders.
"""

import pandas as pd
import shutil
import json
from pathlib import Path

def get_subject_id_from_json(json_file: Path) -> str:
    """Extract subject_id from a JSON file."""
    try:
        with open(json_file, 'r') as f:
            data = json.load(f)
            return data.get('subject_id', '')
    except:
        return ''

def main():
    """Copy metadata files to session folders."""
    
    # Set up paths
    metadata_dir = Path("metadata")
    subjects_dir = metadata_dir / "subjects"
    procedures_dir = metadata_dir / "procedures"
    jhu_instrument_dir = metadata_dir / "instrument" / "jhu_ephys"
    jhu_instrument_file = jhu_instrument_dir / "instrument.json"

    # Load asset inventory to identify JHU sessions
    asset_inventory = pd.read_csv("asset_inventory.csv")
    jhu_sessions = set()
    for _, row in asset_inventory.iterrows():
        if row.get("collection_site") == "hopkins":
            jhu_sessions.add(row["session_name"])
    
    print(f"Found {len(jhu_sessions)} JHU sessions in asset inventory")
    if len(jhu_sessions) > 0:
        print(f"Sample JHU session names: {list(jhu_sessions)[:5]}")  # Show first 5
    
    # Get all existing session folders
    session_folders = [d for d in metadata_dir.iterdir() if d.is_dir() and not d.name in ['subjects', 'procedures']]
    
    print(f"Found {len(session_folders)} session folders")
    
    # Build lookup tables by reading JSON files
    subject_files = {}  # subject_id -> file_path
    procedure_files = {}  # subject_id -> file_path
    
    # Index subject files
    if subjects_dir.exists():
        for json_file in subjects_dir.glob("*.json"):
            subject_id = get_subject_id_from_json(json_file)
            if subject_id:
                subject_files[subject_id] = json_file
    
    # Index procedure files
    if procedures_dir.exists():
        for json_file in procedures_dir.glob("*.json"):
            subject_id = get_subject_id_from_json(json_file)
            if subject_id:
                procedure_files[subject_id] = json_file
    
    print(f"Found {len(subject_files)} subject files, {len(procedure_files)} procedure files")
    print(f"JHU instrument file exists: {jhu_instrument_file.exists()}")
    
    copied = 0
    
    for session_folder in session_folders:
        # Extract subject ID from folder name (format: ZS062_2021-05-11_20-10-59)
        subject_id = session_folder.name.split('_')[0]
        
        # Convert folder name to asset inventory format
        # Folder format: ZS062_2021-05-11_20-10-59
        # Asset inventory format: mZS062d20210511
        session_name_parts = session_folder.name.split('_')
        if len(session_name_parts) >= 2:
            # Convert date from YYYY-MM-DD to YYYYMMDD
            date_part = session_name_parts[1].replace('-', '')
            session_name = f"m{subject_id}d{date_part}"
        else:
            session_name = session_folder.name
        
        print(f"Processing {session_folder.name} (subject: {subject_id}, session: {session_name})...")
        print(f"  Session in JHU list: {session_name in jhu_sessions}")
        
        # Copy subject.json
        if subject_id in subject_files:
            subject_dest = session_folder / "subject.json"
            shutil.copy2(subject_files[subject_id], subject_dest)
            print(f"  ✓ Copied subject.json from {subject_files[subject_id].name}")
            copied += 1
        
        # Copy procedures.json
        if subject_id in procedure_files:
            procedure_dest = session_folder / "procedures.json"
            shutil.copy2(procedure_files[subject_id], procedure_dest)
            print(f"  ✓ Copied procedures.json from {procedure_files[subject_id].name}")
            copied += 1
        
        # Copy instrument.json only for JHU sessions
        if session_name in jhu_sessions and jhu_instrument_file.exists():
            instrument_dest = session_folder / "instrument.json"
            shutil.copy2(jhu_instrument_file, instrument_dest)
            print(f"  ✓ Copied instrument.json from {jhu_instrument_file.name} (JHU session)")
            copied += 1
    
    print(f"\nCopied {copied} files total")

if __name__ == "__main__":
    main()
