#!/usr/bin/env python3
"""
Organize JHU metadata on VAST by ensuring all session folders have complete JSON files,
copying them to VAST locations, and creating an inventory CSV with paths to all files.
"""

import pandas as pd
import shutil
import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional

# Import functions from copy_metadata_files.py
from copy_metadata_files import get_subject_id_from_json, copy_to_vast_locations


def ensure_complete_session_metadata(metadata_dir: Path, subjects_dir: Path, procedures_dir: Path, 
                                    jhu_instrument_file: Path, jhu_sessions: set) -> Dict[str, int]:
    """
    Ensure every session folder has all 5 JSON files, copying missing ones.
    
    Returns:
        Dict with counts of files copied per type
    """
    print("="*60)
    print("ENSURING COMPLETE SESSION METADATA")
    print("="*60)
    
    # Get all session folders
    session_folders = [d for d in metadata_dir.iterdir() 
                      if d.is_dir() and d.name not in ['subjects', 'procedures', 'instrument']]
    
    # Build lookup tables
    subject_files = {}  # subject_id -> file_path
    procedure_files = {}  # subject_id -> file_path
    
    # Index subject files (v2)
    for json_file in subjects_dir.glob("*.json"):
        subject_id = get_subject_id_from_json(json_file)
        if subject_id:
            subject_files[subject_id] = json_file
    
    # Index procedure files
    for json_file in procedures_dir.glob("*.json"):
        subject_id = get_subject_id_from_json(json_file)
        if subject_id:
            procedure_files[subject_id] = json_file
    
    copy_counts = {
        'subject': 0,
        'procedures': 0, 
        'instrument': 0,
        'missing_files': 0
    }
    
    for session_folder in session_folders:
        subject_id = session_folder.name.split('_')[0]
        
        # Convert to session name format for JHU check
        session_name_parts = session_folder.name.split('_')
        if len(session_name_parts) >= 2:
            date_part = session_name_parts[1].replace('-', '')
            session_name = f"m{subject_id}d{date_part}"
        else:
            session_name = session_folder.name
        
        print(f"Checking {session_folder.name}...")
        
        # Check for required JSON files
        required_files = ['acquisition.json', 'data_description.json', 'subject.json', 
                         'procedures.json', 'instrument.json']
        missing_files = []
        
        for required_file in required_files:
            if not (session_folder / required_file).exists():
                missing_files.append(required_file)
        
        if not missing_files:
            print(f"  ✓ All files present")
            continue
        
        print(f"  Missing: {', '.join(missing_files)}")
        
        # Copy missing subject.json
        if 'subject.json' in missing_files and subject_id in subject_files:
            shutil.copy2(subject_files[subject_id], session_folder / "subject.json")
            print(f"    ✓ Copied subject.json")
            copy_counts['subject'] += 1
        
        # Copy missing procedures.json
        if 'procedures.json' in missing_files and subject_id in procedure_files:
            shutil.copy2(procedure_files[subject_id], session_folder / "procedures.json")
            print(f"    ✓ Copied procedures.json")
            copy_counts['procedures'] += 1
        
        # Copy missing instrument.json (JHU sessions only)
        if ('instrument.json' in missing_files and 
            session_name in jhu_sessions and 
            jhu_instrument_file.exists()):
            shutil.copy2(jhu_instrument_file, session_folder / "instrument.json")
            print(f"    ✓ Copied instrument.json")
            copy_counts['instrument'] += 1
        
        # Count remaining missing files
        still_missing = []
        for required_file in required_files:
            if not (session_folder / required_file).exists():
                still_missing.append(required_file)
        
        if still_missing:
            print(f"    ⚠ Still missing: {', '.join(still_missing)}")
            copy_counts['missing_files'] += len(still_missing)
    
    return copy_counts


def verify_session_names_match_data_description(metadata_dir: Path) -> bool:
    """
    Verify that session folder names match the 'name' field in data_description.json files.
    
    Returns:
        True if all match, False otherwise
    """
    print("\n" + "="*60)
    print("VERIFYING SESSION NAMES")
    print("="*60)
    
    session_folders = [d for d in metadata_dir.iterdir() 
                      if d.is_dir() and d.name not in ['subjects', 'procedures', 'instrument']]
    
    all_match = True
    
    for session_folder in session_folders:
        data_desc_file = session_folder / "data_description.json"
        
        if not data_desc_file.exists():
            print(f"⚠ {session_folder.name}: Missing data_description.json")
            all_match = False
            continue
        
        try:
            with open(data_desc_file, 'r') as f:
                data = json.load(f)
                name_field = data.get('name', '')
                
                if name_field == session_folder.name:
                    print(f"✓ {session_folder.name}: Matches name field")
                else:
                    print(f"✗ {session_folder.name}: Name field is '{name_field}'")
                    all_match = False
        except Exception as e:
            print(f"✗ {session_folder.name}: Error reading file - {e}")
            all_match = False
    
    return all_match


def find_nwb_zarr_files(vast_path: Path) -> Optional[str]:
    """
    Find behavior .zarr files in the specific sorted/session/ subdirectory.
    
    Returns:
        Full path to the behavior .zarr file, or None if not found
    """
    if not vast_path.exists():
        return None
    
    # Look specifically in sorted/session/ subdirectory
    session_dir = vast_path / "sorted" / "session"
    if not session_dir.exists():
        return None
    
    # Look for behavior_*.zarr files
    for zarr_file in session_dir.glob("behavior_*.zarr"):
        if "nwb" in zarr_file.name.lower():
            return str(zarr_file)
    
    return None


def create_vast_inventory_csv(metadata_dir: Path, asset_inventory_df: pd.DataFrame, 
                             output_file: str = "vast_inventory.csv") -> str:
    """
    Create a CSV inventory with paths to all JSON files and NWB data on VAST.
    
    Returns:
        Path to the created CSV file
    """
    print("\n" + "="*60)
    print("CREATING VAST INVENTORY CSV")
    print("="*60)
    
    session_folders = [d for d in metadata_dir.iterdir() 
                      if d.is_dir() and d.name not in ['subjects', 'procedures', 'instrument']]
    
    inventory_data = []
    
    for session_folder in session_folders:
        # Convert folder name to asset inventory format
        subject_id = session_folder.name.split('_')[0]
        session_name_parts = session_folder.name.split('_')
        if len(session_name_parts) >= 2:
            date_part = session_name_parts[1].replace('-', '')
            session_name = f"m{subject_id}d{date_part}"
        else:
            session_name = session_folder.name
        
        # Find session in asset inventory
        session_row = asset_inventory_df[asset_inventory_df['session_name'] == session_name]
        
        if session_row.empty:
            print(f"⚠ Session {session_name} not found in asset inventory")
            continue
        
        vast_path_str = session_row.iloc[0]['vast_path']
        if pd.isna(vast_path_str) or not vast_path_str.strip():
            print(f"⚠ No VAST path for session {session_name}")
            continue
        
        vast_path = Path(vast_path_str)
        
        # Create row data
        row_data = {
            'session_folder_name': session_folder.name,
            'subject_id': subject_id,
            'vast_path': str(vast_path)
        }
        
        # Add JSON file paths (only if they actually exist)
        json_files = ['acquisition.json', 'data_description.json', 'subject.json', 
                     'procedures.json', 'instrument.json']
        
        for json_file in json_files:
            json_path = vast_path / json_file
            if json_path.exists():
                row_data[f'{json_file.replace(".json", "")}_path'] = str(json_path)
            else:
                row_data[f'{json_file.replace(".json", "")}_path'] = ""
        
        # Find NWB .zarr file
        nwb_path = find_nwb_zarr_files(vast_path)
        row_data['nwb_path'] = nwb_path if nwb_path else ""
        
        inventory_data.append(row_data)
        print(f"✓ {session_folder.name}: Added to inventory")
        if nwb_path:
            print(f"    NWB found: {Path(nwb_path).name}")
        else:
            print(f"    ⚠ No NWB .zarr file found")
    
    # Create DataFrame and save
    inventory_df = pd.DataFrame(inventory_data)
    inventory_df.to_csv(output_file, index=False)
    
    print(f"\n✓ Inventory CSV created: {output_file}")
    print(f"  Sessions processed: {len(inventory_data)}")
    print(f"  Sessions with NWB: {sum(1 for row in inventory_data if row['nwb_path'])}")
    
    return output_file


def main():
    """Main function to organize JHU metadata on VAST."""
    parser = argparse.ArgumentParser(
        description="Organize JHU metadata on VAST with complete file copying and inventory creation"
    )
    parser.add_argument(
        "--skip-vast-copy", 
        action="store_true",
        help="Skip copying files to VAST (useful for testing)"
    )
    parser.add_argument(
        "--output-csv",
        type=str,
        default="vast_inventory.csv",
        help="Output CSV filename (default: vast_inventory.csv)"
    )
    
    args = parser.parse_args()
    
    # Set up paths
    metadata_dir = Path("metadata")
    subjects_dir = metadata_dir / "subjects" / "v2"
    procedures_dir = metadata_dir / "procedures"
    jhu_instrument_file = metadata_dir / "instrument" / "jhu_ephys" / "instrument.json"
    
    # Load asset inventory
    asset_inventory = pd.read_csv("asset_inventory.csv")
    
    # Get JHU sessions
    jhu_sessions = set()
    for _, row in asset_inventory.iterrows():
        if row.get("collection_site") == "hopkins":
            jhu_sessions.add(row["session_name"])
    
    print(f"Found {len(jhu_sessions)} JHU sessions in asset inventory")
    
    # Step 1: Ensure all session folders have complete metadata
    copy_counts = ensure_complete_session_metadata(
        metadata_dir, subjects_dir, procedures_dir, jhu_instrument_file, jhu_sessions
    )
    
    print(f"\nCompletion summary:")
    print(f"  Subject files copied: {copy_counts['subject']}")
    print(f"  Procedure files copied: {copy_counts['procedures']}")
    print(f"  Instrument files copied: {copy_counts['instrument']}")
    if copy_counts['missing_files'] > 0:
        print(f"  ⚠ Files still missing: {copy_counts['missing_files']}")
    
    # Step 2: Verify session names match data_description.json
    names_match = verify_session_names_match_data_description(metadata_dir)
    if not names_match:
        print("\n⚠ WARNING: Some session names don't match data_description.json 'name' fields")
    
    # Step 3: Copy to VAST (unless skipped)
    if not args.skip_vast_copy:
        copy_to_vast_locations(asset_inventory, metadata_dir)
    else:
        print("\n⚠ Skipping VAST copy (--skip-vast-copy flag)")
    
    # Step 4: Create inventory CSV
    csv_file = create_vast_inventory_csv(metadata_dir, asset_inventory, args.output_csv)
    
    print(f"\n" + "="*60)
    print("ORGANIZATION COMPLETE")
    print("="*60)
    print(f"✓ Session metadata completed")
    if not args.skip_vast_copy:
        print(f"✓ Files copied to VAST")
    print(f"✓ Inventory CSV created: {csv_file}")


if __name__ == "__main__":
    main()
