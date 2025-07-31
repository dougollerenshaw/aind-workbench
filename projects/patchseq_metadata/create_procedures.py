#!/usr/bin/env python3
"""
Simple script to create procedures.json files for patchseq subjects.
"""

import pandas as pd
import requests
import json
import argparse
import copy
from pathlib import Path
from datetime import date, datetime

from aind_data_schema.core.procedures import Procedures, Surgery, SpecimenProcedure
from aind_data_schema.components.coordinates import CoordinateSystemLibrary, Translation, Rotation
from aind_data_schema.components.surgery_procedures import BrainInjection, Perfusion, Anaesthetic
from aind_data_schema.components.injection_procedures import InjectionDynamics, InjectionProfile, ViralMaterial, TarsVirusIdentifiers
from aind_data_schema.components.reagent import Reagent
from aind_data_schema_models.organizations import Organization
from aind_data_schema_models.units import VolumeUnit, TimeUnit, AngleUnit
from aind_data_schema_models.pid_names import PIDName


def get_subjects_list():
    """
    Read the CSV file and return a list of subject IDs.
    
    Returns:
        list: List of subject IDs
    """
    csv_file = "patchseq_subject_ids.csv"
    df = pd.read_csv(csv_file)
    subjects = df['subject_id'].tolist()
    print(f"Found {len(subjects)} subjects in {csv_file}")
    return subjects


def extract_specimen_procedure_details(specimen_procedures_list, batch_tracking_info=None):
    """
    Extract specimen procedure details for CSV tracking.
    Uses wide format with predefined columns for the 5 known procedures.
    
    Args:
        specimen_procedures_list: List of SpecimenProcedure objects
        batch_tracking_info: Dict with batch_number and date_range_tab for tracking
        
    Returns:
        dict: Single dict with all procedure details in wide format
    """
    # Initialize wide format structure for the 5 known procedures
    procedure_data = {
        'batch_number': "",
        'date_range_tab': "",
        'shield_off.start_date': "",
        'shield_off.end_date': "",
        'shield_off.experimenter': "",
        'shield_off.notes': "",
        'shield_off.shield_buffer_lot': "",
        'shield_off.shield_epoxy_lot': "",
        'shield_on.start_date': "",
        'shield_on.end_date': "",
        'shield_on.experimenter': "",
        'shield_on.notes': "",
        'shield_on.shield_on_lot': "",
        'passive_delipidation.start_date': "",
        'passive_delipidation.end_date': "",
        'passive_delipidation.experimenter': "",
        'passive_delipidation.notes': "",
        'passive_delipidation.delipidation_buffer_lot': "",
        'active_delipidation.start_date': "",
        'active_delipidation.end_date': "",
        'active_delipidation.experimenter': "",
        'active_delipidation.notes': "",
        'active_delipidation.conductivity_buffer_lot': "",
        'easyindex.start_date': "",
        'easyindex.end_date': "",
        'easyindex.experimenter': "",
        'easyindex.notes': "",
        'easyindex.protocol_id': "",
        'easyindex.easy_index_lot': ""
    }
    
    # Populate batch tracking information if available
    if batch_tracking_info:
        procedure_data['batch_number'] = batch_tracking_info.get('batch_number', "")
        procedure_data['date_range_tab'] = batch_tracking_info.get('date_range_tab', "")
    
    # Map procedures to their data
    for proc in specimen_procedures_list:
        experimenter = ", ".join(proc.experimenters) if hasattr(proc, 'experimenters') and proc.experimenters else ""
        start_date = str(proc.start_date) if hasattr(proc, 'start_date') and proc.start_date else ""
        end_date = str(proc.end_date) if hasattr(proc, 'end_date') and proc.end_date else ""
        notes = proc.notes if hasattr(proc, 'notes') and proc.notes else ""
        protocol_id = ", ".join(proc.protocol_id) if hasattr(proc, 'protocol_id') and proc.protocol_id else ""
        
        if hasattr(proc, 'procedure_name'):
            if proc.procedure_name == "SHIELD OFF":
                procedure_data['shield_off.start_date'] = start_date
                procedure_data['shield_off.end_date'] = end_date
                procedure_data['shield_off.experimenter'] = experimenter
                procedure_data['shield_off.notes'] = notes
                
                # Extract specific reagent lots
                if hasattr(proc, 'procedure_details') and proc.procedure_details:
                    for reagent in proc.procedure_details:
                        if hasattr(reagent, 'name'):
                            if reagent.name == "SHIELD Buffer" and hasattr(reagent, 'lot_number'):
                                procedure_data['shield_off.shield_buffer_lot'] = reagent.lot_number
                            elif reagent.name == "SHIELD Epoxy" and hasattr(reagent, 'lot_number'):
                                procedure_data['shield_off.shield_epoxy_lot'] = reagent.lot_number
            
            elif proc.procedure_name == "SHIELD ON":
                procedure_data['shield_on.start_date'] = start_date
                procedure_data['shield_on.end_date'] = end_date
                procedure_data['shield_on.experimenter'] = experimenter
                procedure_data['shield_on.notes'] = notes
                
                # Extract Shield On lot
                if hasattr(proc, 'procedure_details') and proc.procedure_details:
                    for reagent in proc.procedure_details:
                        if hasattr(reagent, 'name') and reagent.name == "SHIELD On" and hasattr(reagent, 'lot_number'):
                            procedure_data['shield_on.shield_on_lot'] = reagent.lot_number
            
            elif proc.procedure_name == "Passive Delipidation":
                procedure_data['passive_delipidation.start_date'] = start_date
                procedure_data['passive_delipidation.end_date'] = end_date
                procedure_data['passive_delipidation.experimenter'] = experimenter
                procedure_data['passive_delipidation.notes'] = notes
                
                # Extract Delipidation Buffer lot
                if hasattr(proc, 'procedure_details') and proc.procedure_details:
                    for reagent in proc.procedure_details:
                        if hasattr(reagent, 'name') and reagent.name == "Delipidation Buffer" and hasattr(reagent, 'lot_number'):
                            procedure_data['passive_delipidation.delipidation_buffer_lot'] = reagent.lot_number
            
            elif proc.procedure_name == "Active Delipidation":
                procedure_data['active_delipidation.start_date'] = start_date
                procedure_data['active_delipidation.end_date'] = end_date
                procedure_data['active_delipidation.experimenter'] = experimenter
                procedure_data['active_delipidation.notes'] = notes
                
                # Extract Conductivity Buffer lot
                if hasattr(proc, 'procedure_details') and proc.procedure_details:
                    for reagent in proc.procedure_details:
                        if hasattr(reagent, 'name') and reagent.name == "Conductivity Buffer" and hasattr(reagent, 'lot_number'):
                            procedure_data['active_delipidation.conductivity_buffer_lot'] = reagent.lot_number
            
            elif proc.procedure_name == "EasyIndex":
                procedure_data['easyindex.start_date'] = start_date
                procedure_data['easyindex.end_date'] = end_date
                procedure_data['easyindex.experimenter'] = experimenter
                procedure_data['easyindex.notes'] = notes
                procedure_data['easyindex.protocol_id'] = protocol_id
                
                # Extract Easy Index lot
                if hasattr(proc, 'procedure_details') and proc.procedure_details:
                    for reagent in proc.procedure_details:
                        if hasattr(reagent, 'name') and reagent.name == "Easy Index" and hasattr(reagent, 'lot_number'):
                            procedure_data['easyindex.easy_index_lot'] = reagent.lot_number
    
    return procedure_data


def update_specimen_procedure_tracking_csv(subjects_processed, all_specimen_procedure_data):
    """
    Update or create a CSV file with specimen procedure tracking information.
    Uses wide format: one row per subject with columns for each of the 5 procedures.
    
    Args:
        subjects_processed: List of subject IDs that were processed
        all_specimen_procedure_data: Dict mapping subject_id -> procedure details dict
    """
    csv_file = "specimen_procedure_tracking.csv"
    
    # Count subjects with procedures vs total subjects
    subjects_with_procedures = len([s for s in subjects_processed if all_specimen_procedure_data.get(s)])
    
    print(f"  Total subjects to track: {len(subjects_processed)} (including {subjects_with_procedures} with specimen procedures)")
    
    # Define columns for wide format with predefined procedure columns
    columns = [
        'subject_id', 'batch_number', 'date_range_tab',
        'shield_off.start_date', 'shield_off.end_date', 'shield_off.experimenter', 'shield_off.notes',
        'shield_off.shield_buffer_lot', 'shield_off.shield_epoxy_lot',
        'shield_on.start_date', 'shield_on.end_date', 'shield_on.experimenter', 'shield_on.notes',
        'shield_on.shield_on_lot',
        'passive_delipidation.start_date', 'passive_delipidation.end_date', 'passive_delipidation.experimenter', 'passive_delipidation.notes',
        'passive_delipidation.delipidation_buffer_lot',
        'active_delipidation.start_date', 'active_delipidation.end_date', 'active_delipidation.experimenter', 'active_delipidation.notes',
        'active_delipidation.conductivity_buffer_lot',
        'easyindex.start_date', 'easyindex.end_date', 'easyindex.experimenter', 'easyindex.notes',
        'easyindex.protocol_id', 'easyindex.easy_index_lot'
    ]
    
    # Load existing CSV if it exists, otherwise create new DataFrame
    try:
        existing_df = pd.read_csv(csv_file)
        print(f"  Loaded existing {csv_file} with {len(existing_df)} rows")
        # Remove rows for subjects we're updating to avoid duplicates
        existing_df = existing_df[~existing_df['subject_id'].isin(subjects_processed)]
        print(f"  Removed {len(subjects_processed)} subjects for update, {len(existing_df)} rows remaining")
    except FileNotFoundError:
        existing_df = pd.DataFrame(columns=columns)
        print(f"  Creating new {csv_file}")
    
    # Create new rows for current subjects - include ALL subjects (even with missing data)
    new_rows = []
    for subject_id in subjects_processed:
        procedure_data = all_specimen_procedure_data.get(subject_id, {})
        
        # Always add row for every processed subject
        row_data = {'subject_id': subject_id}
        
        # Add all procedure details (will be empty strings if no data)
        for key, value in procedure_data.items():
            if key in columns:  # Only include columns we want
                row_data[key] = value
        
        new_rows.append(row_data)
    
    # Convert new rows to DataFrame
    if new_rows:
        new_df = pd.DataFrame(new_rows)
        # Combine existing and new data
        combined_df = pd.concat([existing_df, new_df], ignore_index=True)
    else:
        combined_df = existing_df
    
    # Ensure all columns exist and are in the right order
    combined_df = combined_df.reindex(columns=columns, fill_value="")
    
    # Sort by subject_id for easy reading
    combined_df = combined_df.sort_values(['subject_id']).reset_index(drop=True)
    
    # Save the updated CSV
    combined_df.to_csv(csv_file, index=False)
    print(f"  Updated {csv_file} with {len(new_rows)} subject rows ({subjects_with_procedures} with specimen procedures)")


def extract_injection_details(v1_data):
    """
    Extract injection details from v1 procedures data for CSV tracking.
    
    Args:
        v1_data: V1 procedures data dict
        
    Returns:
        list: List of injection detail dicts, one per injection
    """
    injections = []
    
    for proc_data in v1_data.get("subject_procedures", []):
        if proc_data.get("procedure_type") == "Surgery":
            for sub_proc in proc_data.get("procedures", []):
                if sub_proc.get("procedure_type") == "Nanoject injection":
                    # Extract coordinates
                    ap = sub_proc.get("injection_coordinate_ap", "")
                    ml = sub_proc.get("injection_coordinate_ml", "")
                    depths = sub_proc.get("injection_coordinate_depth", [])
                    if not isinstance(depths, list):
                        depths = [depths]
                    
                    # Extract volumes
                    volumes = sub_proc.get("injection_volume", [])
                    if not isinstance(volumes, list):
                        volumes = [volumes]
                    
                    # Initialize all viral material fields
                    viral_material_fields = {
                        'name': "",
                        'tars_identifiers.virus_tars_id': "",
                        'tars_identifiers.plasmid_tars_alias': "",
                        'tars_identifiers.prep_lot_number': "",
                        'tars_identifiers.prep_date': "",
                        'tars_identifiers.prep_type': "",
                        'tars_identifiers.prep_protocol': "",
                        'addgene_id.name': "",
                        'addgene_id.abbreviation': "",
                        'addgene_id.registry': "",
                        'addgene_id.registry_identifier': "",
                        'titer': "",
                        'titer_unit': ""
                    }
                    
                    # Get viral material details from injection_materials
                    injection_materials = sub_proc.get("injection_materials", [])
                    if injection_materials and len(injection_materials) > 0:
                        material = injection_materials[0]  # Take first material
                        
                        # Basic material info
                        viral_material_fields['name'] = material.get("name", "")
                        viral_material_fields['titer'] = material.get("titer", "")
                        viral_material_fields['titer_unit'] = material.get("titer_unit", "")
                        
                        # Extract TARS information
                        tars_info = material.get("tars_identifiers", {})
                        if tars_info:
                            viral_material_fields['tars_identifiers.virus_tars_id'] = tars_info.get("virus_tars_id", "")
                            # Handle plasmid_tars_alias array - join with semicolon if multiple
                            plasmid_alias = tars_info.get("plasmid_tars_alias", "")
                            if isinstance(plasmid_alias, list):
                                viral_material_fields['tars_identifiers.plasmid_tars_alias'] = "; ".join(plasmid_alias)
                            else:
                                viral_material_fields['tars_identifiers.plasmid_tars_alias'] = str(plasmid_alias)
                            viral_material_fields['tars_identifiers.prep_lot_number'] = tars_info.get("prep_lot_number", "")
                            viral_material_fields['tars_identifiers.prep_date'] = str(tars_info.get("prep_date", ""))
                            viral_material_fields['tars_identifiers.prep_type'] = tars_info.get("prep_type", "")
                            viral_material_fields['tars_identifiers.prep_protocol'] = tars_info.get("prep_protocol", "")
                        
                        # Extract Addgene information
                        addgene_info = material.get("addgene_id", {})
                        if addgene_info:
                            viral_material_fields['addgene_id.name'] = addgene_info.get("name", "")
                            viral_material_fields['addgene_id.abbreviation'] = addgene_info.get("abbreviation", "")
                            # Registry should always be "Addgene" for Addgene IDs
                            viral_material_fields['addgene_id.registry'] = "Addgene" if addgene_info.get("registry_identifier") else ""
                            # Normalize registry_identifier: remove "Addgene #" prefix if present
                            raw_registry_id = addgene_info.get("registry_identifier", "")
                            if isinstance(raw_registry_id, str) and "Addgene #" in raw_registry_id:
                                normalized_id = raw_registry_id.replace("Addgene #", "").strip()
                                viral_material_fields['addgene_id.registry_identifier'] = normalized_id
                            else:
                                viral_material_fields['addgene_id.registry_identifier'] = raw_registry_id
                    
                    # Create one entry per depth/volume combination
                    for i, depth in enumerate(depths):
                        volume = volumes[i] if i < len(volumes) else volumes[0] if volumes else ""
                        
                        injection_details = {
                            'coordinates_ap': ap,
                            'coordinates_ml': ml, 
                            'coordinates_si': depth,
                            'volume_nl': volume,
                            'hemisphere': sub_proc.get("injection_hemisphere", ""),
                            'angle_degrees': sub_proc.get("injection_angle", ""),
                            'recovery_time': sub_proc.get("recovery_time", ""),
                            'recovery_time_unit': sub_proc.get("recovery_time_unit", ""),
                            'protocol_id': sub_proc.get("protocol_id", ""),
                        }
                        # Add all viral material fields
                        injection_details.update(viral_material_fields)
                        
                        injections.append(injection_details)
    
    return injections


def update_injection_tracking_csv(subjects_processed, all_injection_data):
    """
    Update or create a CSV file with injection material tracking information.
    This creates a separate CSV file dedicated to viral material tracking,
    keeping the original patchseq_subject_ids.csv unchanged.
    Uses tidy format: one row per injection with injection_number column.
    
    Args:
        subjects_processed: List of subject IDs that were processed
        all_injection_data: Dict mapping subject_id -> list of injection details
    """
    csv_file = "viral_material_tracking.csv"
    
    # Count total injections across all subjects
    total_injections = sum(len(all_injection_data.get(subject_id, [])) for subject_id in subjects_processed)
    
    if total_injections == 0:
        print(f"  No injections found, skipping CSV update")
        return
    
    print(f"  Total injections to track: {total_injections}")
    
    # Define columns for tidy format with comprehensive viral material fields
    columns = [
        'subject_id', 'injection_number',
        'coordinates_ap', 'coordinates_ml', 'coordinates_si', 'volume_nl',
        'hemisphere', 'angle_degrees', 'recovery_time', 'recovery_time_unit', 'protocol_id',
        'name', 
        'tars_identifiers.virus_tars_id',
        'tars_identifiers.plasmid_tars_alias',
        'tars_identifiers.prep_lot_number',
        'tars_identifiers.prep_date',
        'tars_identifiers.prep_type',
        'tars_identifiers.prep_protocol',
        'addgene_id.name',
        'addgene_id.abbreviation',
        'addgene_id.registry',
        'addgene_id.registry_identifier',
        'titer',
        'titer_unit'
    ]
    
    # Load existing CSV if it exists, otherwise create new DataFrame
    try:
        existing_df = pd.read_csv(csv_file)
        print(f"  Loaded existing {csv_file} with {len(existing_df)} rows")
        # Remove rows for subjects we're updating to avoid duplicates
        existing_df = existing_df[~existing_df['subject_id'].isin(subjects_processed)]
        print(f"  Removed {len(subjects_processed)} subjects for update, {len(existing_df)} rows remaining")
    except FileNotFoundError:
        existing_df = pd.DataFrame(columns=columns)
        print(f"  Creating new {csv_file}")
    
    # Create new rows for current subjects
    new_rows = []
    for subject_id in subjects_processed:
        injections = all_injection_data.get(subject_id, [])
        
        for injection_num, injection in enumerate(injections, 1):
            row_data = {
                'subject_id': subject_id,
                'injection_number': injection_num
            }
            
            # Add all injection details
            for key, value in injection.items():
                if key in columns:  # Only include columns we want
                    row_data[key] = value
            
            new_rows.append(row_data)
    
    # Convert new rows to DataFrame
    if new_rows:
        new_df = pd.DataFrame(new_rows)
        # Combine existing and new data
        combined_df = pd.concat([existing_df, new_df], ignore_index=True)
    else:
        combined_df = existing_df
    
    # Ensure all columns exist and are in the right order
    combined_df = combined_df.reindex(columns=columns, fill_value="")
    
    # Sort by subject_id and injection_number for easy reading
    combined_df = combined_df.sort_values(['subject_id', 'injection_number']).reset_index(drop=True)
    
    # Save the updated CSV
    combined_df.to_csv(csv_file, index=False)
    print(f"  Updated {csv_file} with {len(new_rows)} injection rows for {len(subjects_processed)} subjects")


def load_specimen_procedures_excel(excel_file="DT_HM_TissueClearingTracking_.xlsx"):
    """
    Load Excel file with specimen procedures data and return a dictionary of DataFrames.
    Currently handles:
    - "Batch Info" sheet: Clean format with headers in first row
    - Time-based sheets: Complex multi-level headers (rows 1-3) with data starting at row 4
    - Silently ignores specified sheets
    
    Args:
        excel_file: Path to the Excel file
        
    Returns:
        dict: Dictionary where keys are sheet names and values are DataFrames
    """
    # Sheets to ignore (silently skip these)
    sheets_to_ignore = ["TestBrains"]
    
    try:
        print(f"Loading Excel file: {excel_file}")
        
        # First, get all sheet names to identify which ones to process
        all_sheets = pd.ExcelFile(excel_file).sheet_names
        print(f"Found {len(all_sheets)} total sheets")
        
        sheet_data = {}
        
        # Load Batch Info sheet with proper headers
        if "Batch Info" in all_sheets:
            print(f"\n--- Loading 'Batch Info' sheet ---")
            batch_info_df = pd.read_excel(excel_file, sheet_name="Batch Info", header=0)
            
            # Clean up any unnamed columns
            batch_info_df.columns = [str(col) if not str(col).startswith('Unnamed:') else f"Column_{i}" 
                                    for i, col in enumerate(batch_info_df.columns)]
            
            print(f"✓ Batch Info loaded - Shape: {batch_info_df.shape}")
            print(f"  Columns: {list(batch_info_df.columns)}")
            
            sheet_data["Batch Info"] = batch_info_df
        
        # Process time-based sheets (complex multi-level headers)
        time_based_sheets = [sheet for sheet in all_sheets 
                           if sheet not in sheets_to_ignore and sheet != "Batch Info"]
        
        for sheet_name in time_based_sheets:
            print(f"\n--- Loading '{sheet_name}' sheet ---")
            
            # Load with multi-level headers (rows 0, 1, 2)
            df_raw = pd.read_excel(excel_file, sheet_name=sheet_name, header=None)
            
            if len(df_raw) < 4:
                print(f"  ⚠️  Sheet too small ({len(df_raw)} rows), skipping")
                continue
            
            # Extract the three header rows
            header_row1 = df_raw.iloc[0].fillna('')  # Top-level categories
            header_row2 = df_raw.iloc[1].fillna('')  # Sub-categories  
            header_row3 = df_raw.iloc[2].fillna('')  # Column names
            
            # Create meaningful column names by combining the three levels
            combined_headers = []
            for i in range(len(header_row3)):
                level1 = str(header_row1.iloc[i]).strip() if pd.notna(header_row1.iloc[i]) else ''
                level2 = str(header_row2.iloc[i]).strip() if pd.notna(header_row2.iloc[i]) else ''
                level3 = str(header_row3.iloc[i]).strip() if pd.notna(header_row3.iloc[i]) else ''
                
                # Build hierarchical column name ensuring uniqueness
                parts = []
                if level1 and level1 != '':
                    parts.append(level1)
                if level2 and level2 != '':
                    parts.append(level2)
                if level3 and level3 != '':
                    parts.append(level3)
                
                if parts:
                    combined_name = '_'.join(parts)
                else:
                    combined_name = f"Column_{i}"
                
                # Ensure uniqueness by adding index if name already exists
                original_name = combined_name
                counter = 1
                while combined_name in combined_headers:
                    combined_name = f"{original_name}_{counter}"
                    counter += 1
                
                combined_headers.append(combined_name)
            
            # Create DataFrame with data starting from row 4 (index 3)
            data_df = df_raw.iloc[3:].copy()
            data_df.columns = combined_headers
            data_df = data_df.reset_index(drop=True)
            
            # Remove completely empty rows
            data_df = data_df.dropna(how='all')
            
            print(f"✓ {sheet_name} loaded - Shape: {data_df.shape}")
            print(f"  Sample columns: {list(data_df.columns)[:5]}...")
            
            sheet_data[sheet_name] = data_df
        
        print(f"\n✓ Successfully loaded {len(sheet_data)} sheets")
        return sheet_data
        
    except Exception as e:
        print(f" Error loading Excel file: {e}")
        return None


def get_specimen_procedures_for_subject(subject_id, sheet_data):
    """
    Get specimen procedures for a subject using batch-based lookup.
    
    Args:
        subject_id: The subject ID to look up
        sheet_data: Dictionary of DataFrames from load_specimen_procedures_excel()
        
    Returns:
        tuple: (procedures_list, batch_tracking_info)
        - procedures_list: List of SpecimenProcedure objects 
        - batch_tracking_info: Dict with 'batch_number' and 'date_range_tab' for tracking
    """
    def parse_date_range(date_str):
        """Parse date range like '10/3/23 - 10/6/23' into start and end dates"""
        if pd.isna(date_str):
            return None, None
        date_str = str(date_str).strip()
        if ' - ' in date_str:
            parts = date_str.split(' - ')
            if len(parts) == 2:
                return parts[0].strip(), parts[1].strip()
        return date_str, None

    def safe_get_value(row, column_name):
        """Safely get value from row, handling Series case for duplicate columns"""
        value = row.get(column_name)
        if hasattr(value, 'iloc'):
            # It's a Series, get the first value
            return value.iloc[0] if len(value) > 0 else None
        return value

    # Step 1: Find the batch number for this subject in Batch Info
    batch_info = sheet_data["Batch Info"]
    subject_batch = None

    for idx, row in batch_info.iterrows():
        lab_track_ids = str(row['LabTrack IDs']) if pd.notna(row['LabTrack IDs']) else ""
        if subject_id in lab_track_ids:
            subject_batch = row['Batch #']
            break

    if subject_batch is None:
        # Subject not found in Batch Info
        batch_tracking_info = {
            'batch_number': "",
            'date_range_tab': ""
        }
        return [], batch_tracking_info

    # Step 2: Find which date range sheet contains this batch
    target_sheet = None
    for sheet_name, df in sheet_data.items():
        if sheet_name == "Batch Info":
            continue
        
        batch_cols = [col for col in df.columns if 'batch' in col.lower()]
        if batch_cols:
            batch_col = batch_cols[0]
            if subject_batch in df[batch_col].values:
                target_sheet = sheet_name
                break

    if not target_sheet:
        # Batch found in Batch Info but not in any date range tab
        batch_tracking_info = {
            'batch_number': str(subject_batch),
            'date_range_tab': ""
        }
        return [], batch_tracking_info

    # Step 3: Get the batch row data (first row with matching batch)
    df = sheet_data[target_sheet]
    batch_col = [col for col in df.columns if 'batch' in col.lower()][0]
    batch_row = df[df[batch_col] == subject_batch].iloc[0]

    # Extract experimenter
    experimenter = safe_get_value(batch_row, 'Experimenter') or 'Unknown'

    procedures = []

    # Build procedures based on the actual data
    procedure_mappings = [
        {
            'date_col': 'Fixation_SHIELD OFF_Date(s)',
            'procedure_type': 'Fixation',
            'procedure_name': 'SHIELD OFF',
            'notes_col': 'Notes',  # Index 9 - main Notes column
            'reagents': [
                ('SHIELD Buffer_Lot#', 'SHIELD Buffer', 'LifeCanvas'),
                ('SHIELD Epoxy_Lot#', 'SHIELD Epoxy', 'LifeCanvas')
            ]
        },
        {
            'date_col': 'SHIELD ON_Date(s)',
            'procedure_type': 'Fixation', 
            'procedure_name': 'SHIELD ON',
            'notes_col': 'Notes',  # Index 9 - main Notes column
            'reagents': [
                ('SHIELD ON_Lot#', 'SHIELD On', 'LifeCanvas')
            ]
        },
        {
            'date_col': 'Passive delipidation_24 Hr Delipidation_Date(s)',
            'procedure_type': 'Delipidation',
            'procedure_name': 'Passive Delipidation',
            'notes_col': 'Notes_1',  # Index 12 - Passive delipidation Notes
            'reagents': [
                ('Delipidation Buffer_Lot#', 'Delipidation Buffer', 'Other')
            ]
        },
        {
            'date_col': 'Active Delipidation_Active Delipidation_Date(s)',
            'procedure_type': 'Delipidation',
            'procedure_name': 'Active Delipidation',
            'notes_col': 'Notes_2',  # Index 17 - Active Delipidation Notes
            'reagents': [
                ('Conduction Buffer_Lot#', 'Conductivity Buffer', 'Other')
            ]
        },
        {
            'date_col': 'Index matching_50% EasyIndex_Date(s)',
            'end_date_col': '100% EasyIndex_Date(s)',  # Use end date from 100% step
            'procedure_type': 'Refractive index matching',
            'procedure_name': 'EasyIndex',
            'protocol_id': 'dx.doi.org/10.17504/protocols.io.kxygx965kg8j/v1',
            'notes_col': 'Notes_3',  # Index 22 - EasyIndex Notes
            'reagents': [
                ('EasyIndex_Lot#', 'Easy Index', 'LifeCanvas')
            ]
        }
    ]

    for mapping in procedure_mappings:
        date_value = safe_get_value(batch_row, mapping['date_col'])
        
        if pd.notna(date_value):
            start_date, end_date = parse_date_range(date_value)
            
            # Check if there's a separate end date column (for merged procedures like EasyIndex)
            if mapping.get('end_date_col'):
                end_date_value = safe_get_value(batch_row, mapping['end_date_col'])
                if pd.notna(end_date_value):
                    _, end_date_from_col = parse_date_range(end_date_value)
                    if end_date_from_col:
                        end_date = end_date_from_col  # Use the end date from the separate column
            
            # Convert date strings to date objects if they exist
            start_date_obj = None
            end_date_obj = None
            if start_date:
                try:
                    # Parse date format like "10/3/23"
                    start_date_obj = datetime.strptime(start_date, "%m/%d/%y").date()
                except ValueError:
                    print(f"    Warning: Could not parse start date '{start_date}'")
            if end_date:
                try:
                    end_date_obj = datetime.strptime(end_date, "%m/%d/%y").date()
                except ValueError:
                    print(f"    Warning: Could not parse end date '{end_date}'")
            
            # Build reagent details using proper Reagent models
            procedure_details = []
            for lot_col, reagent_name, source_name in mapping['reagents']:
                lot_value = safe_get_value(batch_row, lot_col)
                if pd.notna(lot_value):
                    # Create Organization object for source
                    if source_name == 'LifeCanvas':
                        org = Organization.LIFECANVAS
                    else:
                        org = Organization.OTHER
                    
                    reagent = Reagent(
                        name=reagent_name,
                        source=org,
                        lot_number=str(lot_value).strip()
                    )
                    procedure_details.append(reagent)
            
            # Extract notes from the appropriate column
            notes_value = None
            
            # First check if there's a hardcoded notes value (for backward compatibility)
            if mapping.get('notes'):
                notes_value = mapping['notes']
            # Then check for notes_col_index (for specific Notes column by index)
            elif mapping.get('notes_col_index') is not None:
                col_index = mapping['notes_col_index']
                if col_index < len(df.columns):
                    notes_col_name = df.columns[col_index]
                    notes_raw = safe_get_value(batch_row, notes_col_name)
                    if pd.notna(notes_raw) and str(notes_raw).strip():
                        notes_value = str(notes_raw).strip()
            # Finally check for notes_col by name
            elif mapping.get('notes_col'):
                notes_raw = safe_get_value(batch_row, mapping['notes_col'])
                if pd.notna(notes_raw) and str(notes_raw).strip():
                    notes_value = str(notes_raw).strip()
            
            # Create SpecimenProcedure using proper Pydantic model
            protocol_ids = None
            if mapping.get('protocol_id'):
                protocol_ids = [mapping['protocol_id']]  # Convert to list
            
            specimen_proc = SpecimenProcedure(
                procedure_type=mapping['procedure_type'],
                procedure_name=mapping['procedure_name'],
                specimen_id=subject_id,
                start_date=start_date_obj,
                end_date=end_date_obj,
                experimenters=[experimenter],
                protocol_id=protocol_ids,
                procedure_details=procedure_details,
                notes=notes_value
            )
            
            procedures.append(specimen_proc)

    # Create batch tracking info for successful case
    batch_tracking_info = {
        'batch_number': str(subject_batch),
        'date_range_tab': target_sheet
    }

    return procedures, batch_tracking_info


def fetch_procedures_metadata(subject_id):
    """
    Fetch procedures metadata for a subject from AIND metadata service.
    
    Args:
        subject_id: Subject ID to fetch metadata for
        
    Returns:
        tuple: (success: bool, data: dict or None, message: str)
    """
    base_url = "http://aind-metadata-service"
    url = f"{base_url}/procedures/{str(subject_id)}"
    
    print(f"  Fetching procedures from: {url}")
    
    try:
        response = requests.get(url)
        print(f"    Response status: {response.status_code}")
        
        if response.status_code == 200:
            rj = response.json()
            data = rj.get("data")
            message = rj.get("message", "Success")
            
            if data is not None:
                return True, data, message
            else:
                return False, None, f"No data returned: {message}"
        
        elif response.status_code == 406:
            # 406 responses often still contain the data we need
            rj = response.json()
            data = rj.get("data")
            message = rj.get("message", "Success despite validation errors")
            
            if data is not None:
                return True, data, f"Success (with validation warnings): {message}"
            else:
                return False, None, f"406 error and no data: {message}"
        else:
            response.raise_for_status()
            
    except requests.exceptions.RequestException as e:
        return False, None, f"Request failed: {str(e)}"
    except json.JSONDecodeError as e:
        return False, None, f"JSON decode error: {str(e)}"
    except Exception as e:
        return False, None, f"Unexpected error: {str(e)}"


def create_viral_material_from_v1(material_data, missing_injection_coords_info):
    """
    Create a ViralMaterial object from v1 material data.
    
    Args:
        material_data: Dictionary containing v1 material information
        missing_injection_coords_info: Dict to track any missing coordinate issues
        
    Returns:
        ViralMaterial: Configured ViralMaterial object
    """
    material_name = material_data.get("name", "Viral vector (Nanoject injection)")
    
    # Create ViralMaterial with rich data when available
    viral_kwargs = {"name": material_name}
    
    # Add TARS identifiers if available
    tars_info = material_data.get("tars_identifiers", {})
    if tars_info and any(tars_info.values()):
        tars_kwargs = {}
        if tars_info.get("virus_tars_id"):
            tars_kwargs["virus_tars_id"] = tars_info["virus_tars_id"]
        if tars_info.get("plasmid_tars_alias"):
            # Convert to list if it's a string
            plasmid_alias = tars_info["plasmid_tars_alias"]
            if isinstance(plasmid_alias, str):
                plasmid_alias = [plasmid_alias]
            tars_kwargs["plasmid_tars_alias"] = plasmid_alias
        if tars_info.get("prep_lot_number"):
            tars_kwargs["prep_lot_number"] = tars_info["prep_lot_number"]
        if tars_info.get("prep_date"):
            # Convert string date to date object if needed
            prep_date = tars_info["prep_date"]
            if isinstance(prep_date, str):
                try:
                    prep_date = datetime.strptime(prep_date, "%Y-%m-%d").date()
                except ValueError:
                    prep_date = None
            if prep_date:
                tars_kwargs["prep_date"] = prep_date
        if tars_info.get("prep_type"):
            tars_kwargs["prep_type"] = tars_info["prep_type"]
        if tars_info.get("prep_protocol"):
            tars_kwargs["prep_protocol"] = tars_info["prep_protocol"]
        
        viral_kwargs["tars_identifiers"] = TarsVirusIdentifiers(**tars_kwargs)
    
    # Add addgene_id if available
    addgene_info = material_data.get("addgene_id", {})
    if addgene_info and addgene_info.get("registry_identifier"):
        raw_addgene_id = addgene_info["registry_identifier"]
        # Normalize format: extract just the number
        if isinstance(raw_addgene_id, str) and "Addgene #" in raw_addgene_id:
            addgene_id = raw_addgene_id.replace("Addgene #", "").strip()
        else:
            addgene_id = str(raw_addgene_id).strip()
        
        # Create PIDName for Addgene
        try:
            # Create proper PIDName object
            viral_kwargs["addgene_id"] = PIDName(
                name=addgene_info.get("name", material_name),
                abbreviation=addgene_info.get("abbreviation"),
                registry="Addgene",
                registry_identifier=addgene_id
            )
        except Exception as e:
            # Fall back to simple PIDName with minimal info if creation fails
            try:
                viral_kwargs["addgene_id"] = PIDName(
                    name=material_name,
                    registry="Addgene",
                    registry_identifier=addgene_id
                )
            except:
                # Skip addgene_id if PIDName creation completely fails
                pass
    
    # Add titer information if available
    if material_data.get("titer"):
        try:
            viral_kwargs["titer"] = int(material_data["titer"])
        except (ValueError, TypeError):
            # If conversion to int fails, store as None
            pass
    if material_data.get("titer_unit"):
        viral_kwargs["titer_unit"] = material_data["titer_unit"]
    
    return ViralMaterial(**viral_kwargs)


def create_injection_coordinates(sub_proc, missing_injection_coords_info):
    """
    Create injection coordinates from v1 procedure data with proper handling of missing coordinates.
    
    Args:
        sub_proc: Dictionary containing injection procedure data from v1
        missing_injection_coords_info: Dict to track missing coordinate issues
        
    Returns:
        list: List of coordinate transforms for the injection
    """
    # Handle coordinates with correct AP/ML/SI ordering for BREGMA_ARI
    if all(k in sub_proc and sub_proc[k] is not None for k in ["injection_coordinate_ml", "injection_coordinate_ap", "injection_coordinate_depth"]):
        # All coordinates available - use actual values
        coordinates = []
        depths = sub_proc["injection_coordinate_depth"]
        if not isinstance(depths, list):
            depths = [depths]
        
        for depth in depths:
            coord_transforms = []
            
            # Add translation with correct AP/ML/SI order for BREGMA_ARI
            translation = Translation(
                translation=[
                    float(sub_proc["injection_coordinate_ap"]),  # AP first
                    float(sub_proc["injection_coordinate_ml"]),  # ML second  
                    float(depth)                                 # SI third (depth)
                ]
            )
            coord_transforms.append(translation)
            
            # Add rotation for injection angle if available
            if sub_proc.get("injection_angle"):
                try:
                    angle = float(sub_proc["injection_angle"])
                    if angle != 0.0:  # Only add rotation if non-zero
                        rotation = Rotation(
                            angles=[angle, 0.0, 0.0],  # Assume angle is around x-axis
                            angles_unit=AngleUnit.DEGREES
                        )
                        coord_transforms.append(rotation)
                except (ValueError, TypeError):
                    pass  # Skip if angle conversion fails
            
            coordinates.append(coord_transforms)
        return coordinates
    elif sub_proc.get("injection_coordinate_depth") and sub_proc.get("injection_volume"):
        # Some coordinates missing - create placeholder coordinates for schema compliance
        # Track which coordinates are missing
        missing_injection_coords_info['has_missing_injection_coords'] = True
        missing_injection_coords = []
        if sub_proc.get("injection_coordinate_ap") is None:
            missing_injection_coords.append("AP")
        if sub_proc.get("injection_coordinate_ml") is None:
            missing_injection_coords.append("ML")
        
        missing_injection_detail = f"Injection missing {'/'.join(missing_injection_coords)} coordinate(s), using placeholder values"
        missing_injection_coords_info['missing_injection_details'].append(missing_injection_detail)
        
        # Use 0.0 for missing AP/ML coordinates, but preserve available ones
        coordinates = []
        depths = sub_proc["injection_coordinate_depth"]
        if not isinstance(depths, list):
            depths = [depths]
        
        # Get available coordinate values, use 0.0 for missing
        ap_val = 0.0
        ml_val = 0.0
        if sub_proc.get("injection_coordinate_ap") is not None:
            try:
                ap_val = float(sub_proc["injection_coordinate_ap"])
            except (ValueError, TypeError):
                ap_val = 0.0
        if sub_proc.get("injection_coordinate_ml") is not None:
            try:
                ml_val = float(sub_proc["injection_coordinate_ml"])
            except (ValueError, TypeError):
                ml_val = 0.0
        
        for depth in depths:
            coord_transforms = []
            
            # Add translation with placeholder values for missing coordinates
            translation = Translation(
                translation=[ap_val, ml_val, float(depth)]
            )
            coord_transforms.append(translation)
            
            coordinates.append(coord_transforms)
        return coordinates
    else:
        # No coordinate or volume data - create minimal placeholder for schema compliance
        missing_injection_coords_info['has_missing_injection_coords'] = True
        missing_injection_coords_info['missing_injection_details'].append("No injection coordinate or volume data available, using minimal placeholder")
        return [[Translation(translation=[0.0, 0.0, 0.0])]]


def create_injection_dynamics(sub_proc):
    """
    Create injection dynamics from v1 procedure data.
    
    Args:
        sub_proc: Dictionary containing injection procedure data from v1
        
    Returns:
        list: List of InjectionDynamics objects
    """
    dynamics = []
    if sub_proc.get("injection_volume"):
        volumes = sub_proc["injection_volume"]
        if not isinstance(volumes, list):
            volumes = [volumes]
        
        for volume in volumes:
            dynamics_kwargs = {
                "volume": float(volume),
                "volume_unit": VolumeUnit.NL,
                "profile": InjectionProfile.BOLUS
            }
            
            # Add recovery time as duration if available
            if sub_proc.get("recovery_time"):
                try:
                    recovery_time = float(sub_proc["recovery_time"])
                    dynamics_kwargs["duration"] = recovery_time
                    # Get time unit, default to minutes
                    time_unit_str = sub_proc.get("recovery_time_unit", "minute")
                    if time_unit_str == "minute":
                        dynamics_kwargs["duration_unit"] = TimeUnit.M
                    elif time_unit_str == "second":
                        dynamics_kwargs["duration_unit"] = TimeUnit.S
                    elif time_unit_str == "hour":
                        dynamics_kwargs["duration_unit"] = TimeUnit.HR
                    else:
                        dynamics_kwargs["duration_unit"] = TimeUnit.M
                except (ValueError, TypeError):
                    pass  # Skip if recovery time conversion fails
            
            dynamics.append(InjectionDynamics(**dynamics_kwargs))
    
    return dynamics


def create_brain_injection_from_v1(sub_proc, missing_injection_coords_info):
    """
    Create a BrainInjection object from v1 procedure data.
    
    Args:
        sub_proc: Dictionary containing injection procedure data from v1
        missing_injection_coords_info: Dict to track missing coordinate issues
        
    Returns:
        BrainInjection: Configured BrainInjection object
    """
    # Build BrainInjection
    injection_kwargs = {
        "protocol_id": sub_proc.get("protocol_id"),
        "coordinate_system_name": "BREGMA_ARI"
    }
    
    # Handle injection materials with rich v1 data when available
    materials = []
    injection_materials = sub_proc.get("injection_materials", [])
    
    if injection_materials:
        # Use the detailed viral material information from v1
        for material_data in injection_materials:
            materials.append(create_viral_material_from_v1(material_data, missing_injection_coords_info))
    else:
        # Fallback to generic viral material when no injection_materials present
        materials.append(ViralMaterial(name="Viral vector (Nanoject injection)"))
    
    injection_kwargs["injection_materials"] = materials
    injection_kwargs["coordinates"] = create_injection_coordinates(sub_proc, missing_injection_coords_info)
    injection_kwargs["dynamics"] = create_injection_dynamics(sub_proc)
    
    return BrainInjection(**injection_kwargs)


def create_surgery_from_v1(proc_data, missing_injection_coords_info):
    """
    Create a Surgery object from v1 procedure data.
    
    Args:
        proc_data: Dictionary containing surgery procedure data from v1
        missing_injection_coords_info: Dict to track missing coordinate issues
        
    Returns:
        Surgery: Configured Surgery object
    """
    # Build Surgery object
    surgery_kwargs = {
        "start_date": datetime.strptime(proc_data["start_date"], "%Y-%m-%d").date(),
        "experimenters": [proc_data.get("experimenter_full_name", "Unknown")],
        "ethics_review_id": proc_data.get("iacuc_protocol"),
        "protocol_id": proc_data.get("protocol_id"),
    }
    
    # Add optional fields
    if proc_data.get("animal_weight_prior"):
        surgery_kwargs["animal_weight_prior"] = float(proc_data["animal_weight_prior"])
    if proc_data.get("animal_weight_post"):
        surgery_kwargs["animal_weight_post"] = float(proc_data["animal_weight_post"])
    if proc_data.get("weight_unit"):
        surgery_kwargs["weight_unit"] = proc_data["weight_unit"]
    if proc_data.get("workstation_id"):
        surgery_kwargs["workstation_id"] = proc_data["workstation_id"]
    
    # Handle anaesthesia
    if proc_data.get("anaesthesia"):
        anesthesia_data = proc_data["anaesthesia"]
        anaesthesia = Anaesthetic(
            anaesthetic_type=anesthesia_data.get("type", "Unknown"),
            duration=float(anesthesia_data.get("duration", 0)) if anesthesia_data.get("duration") else None,
            level=float(anesthesia_data.get("level", 0)) if anesthesia_data.get("level") else None
        )
        surgery_kwargs["anaesthesia"] = anaesthesia
    
    # Check if we need a coordinate system (for injections)
    has_injections = any(
        sub_proc.get("procedure_type") == "Nanoject injection" 
        for sub_proc in proc_data.get("procedures", [])
    )
    if has_injections:
        surgery_kwargs["coordinate_system"] = CoordinateSystemLibrary.BREGMA_ARI
    
    # Process nested procedures
    procedures_list = []
    for sub_proc in proc_data.get("procedures", []):
        if sub_proc.get("procedure_type") == "Perfusion":
            perfusion = Perfusion(
                protocol_id=sub_proc.get("protocol_id"),
                output_specimen_ids=sub_proc.get("output_specimen_ids", [])
            )
            procedures_list.append(perfusion)
        
        elif sub_proc.get("procedure_type") == "Nanoject injection":
            brain_injection = create_brain_injection_from_v1(sub_proc, missing_injection_coords_info)
            procedures_list.append(brain_injection)
    
    surgery_kwargs["procedures"] = procedures_list
    return Surgery(**surgery_kwargs)


def convert_procedures_to_v2(data, excel_sheet_data=None):
    """
    Convert procedures data from v1.x to schema 2.0 by building proper Pydantic model objects.
    Also adds specimen procedures from Excel data if available.
    Returns tuple: (converted_data_or_None, missing_injection_coords_info, batch_tracking_info)
    
    missing_injection_coords_info is a dict with details about any missing injection coordinate issues:
    {
        'has_missing_injection_coords': bool,
        'missing_injection_details': [list of strings describing what injection coordinates are missing]
    }
    
    batch_tracking_info is a dict with batch number and date range tab information for debugging missing procedures
    """
    missing_injection_coords_info = {
        'has_missing_injection_coords': False,
        'missing_injection_details': []
    }
    
    batch_tracking_info = None
    
    try:
        # Extract basic info
        subject_id = data["subject_id"]
        subject_procedures = []
        
        # Process each subject procedure
        for proc_data in data.get("subject_procedures", []):
            if proc_data.get("procedure_type") == "Surgery":
                surgery = create_surgery_from_v1(proc_data, missing_injection_coords_info)
                subject_procedures.append(surgery)
        
        # Build final Procedures object
        procedures_obj = Procedures(
            subject_id=subject_id,
            subject_procedures=subject_procedures
        )
        
        # Add specimen procedures from Excel data if available
        if excel_sheet_data:
            try:
                specimen_procedures_list, batch_tracking_info = get_specimen_procedures_for_subject(subject_id, excel_sheet_data)
                if specimen_procedures_list:
                    print(f"    ✓ Found {len(specimen_procedures_list)} specimen procedures in Excel data")
                    # The specimen_procedures_list already contains proper SpecimenProcedure objects
                    procedures_obj.specimen_procedures = specimen_procedures_list
                else:
                    print(f"    ⚠️  No specimen procedures found for subject {subject_id} in Excel data")
            except Exception as e:
                print(f"    ⚠️  Error extracting specimen procedures: {e}")
                batch_tracking_info = None
        
        return procedures_obj, missing_injection_coords_info, batch_tracking_info
        
    except Exception as e:
        print(f"    ✗ Schema conversion failed: {e}")
        return None, missing_injection_coords_info, None


def save_procedures_json(subject_id, data, is_v1=False):
    """
    Save procedures data to a JSON file.
    If is_v1=True, saves as procedures.json.v1
    If is_v1=False, saves as procedures.json (v2 format)
    
    Args:
        subject_id: Subject ID
        data: Procedures data to save
        is_v1: Whether this is a v1.x schema file (default: False)
    """
    # Create procedures directory and subject subdirectory
    procedures_dir = Path("procedures")
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
        if is_v1:
            # v1 data is already a dict, use regular JSON serialization
            json.dump(data, f, indent=2)
        else:
            # v2 data comes from Pydantic model, use model's JSON serialization
            if hasattr(data, 'model_dump_json'):
                # If it's a Pydantic model instance
                f.write(data.model_dump_json(indent=2))
            else:
                # If it's already a dict from model_dump()
                json.dump(data, f, indent=2, default=str)
    
    print(f"    Saved {filename} to: {filepath}")


def check_existing_procedures(subject_id):
    """
    Check if procedures files already exist for a subject.
    Returns tuple: (v1_exists: bool, v2_exists: bool, v1_data: dict or None, v2_data: dict or None)
    """
    procedures_dir = Path("procedures") / str(subject_id)
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
            print(f"    Warning: Could not read existing procedures.json.v1: {e}")
            v1_exists = False
    
    if v2_exists:
        try:
            with open(v2_path, 'r') as f:
                v2_data = json.load(f)
        except Exception as e:
            print(f"    Warning: Could not read existing procedures.json: {e}")
            v2_exists = False
    
    return v1_exists, v2_exists, v1_data, v2_data


def process_single_subject(subject_id, excel_sheet_data, args, all_injection_data, all_specimen_procedure_data, subjects_with_missing_injection_coords, subjects_with_missing_specimen_procedures):
    """
    Process a single subject: check existing files, fetch/convert data, track injection coordinates and specimen procedures.
    
    Args:
        subject_id: Subject ID to process
        excel_sheet_data: Excel sheet data for specimen procedures
        args: Command line arguments
        all_injection_data: Dict to store injection data for CSV tracking
        all_specimen_procedure_data: Dict to store specimen procedure data for CSV tracking
        subjects_with_missing_injection_coords: List to track subjects with missing injection coordinates
        subjects_with_missing_specimen_procedures: List to track subjects with missing specimen procedures
        
    Returns:
        str: Result status - 'success', 'failed', or 'skipped'
    """
    print(f"\nProcessing subject: {subject_id}")
    
    # Check if procedures files already exist
    v1_exists, v2_exists, v1_data, v2_data = check_existing_procedures(subject_id)
    
    # Skip if v2.0 file already exists and avoid_overwrite is True
    if v2_exists and args.avoid_overwrite:
        print(f"  Skipping - procedures.json (v2.0) already exists (--avoid-overwrite)")
        return 'skipped'
    
    # Use existing v1 data if available, never overwrite it from service
    if v1_exists:
        print(f"  Using existing procedures.json.v1")
        v1_source_data = v1_data
    else:
        # Fetch from service only if no v1 file exists
        print(f"  Fetching procedures metadata from service...")
        success, v1_source_data, message = fetch_procedures_metadata(subject_id)
        
        if not success:
            print(f"  ✗ Failed to fetch: {message}")
            return 'failed'
        
        # Save the v1 data (only when fetching for first time)
        save_procedures_json(subject_id, v1_source_data, is_v1=True)
    
    # Extract injection details for tracking
    injection_details = extract_injection_details(v1_source_data)
    all_injection_data[subject_id] = injection_details
    if injection_details:
        print(f"  Found {len(injection_details)} injections for material tracking")
    
    # Convert to schema 2.0
    print(f"  Converting to schema 2.0...")
    v2_data, missing_injection_coords_info, batch_tracking_info = convert_procedures_to_v2(v1_source_data, excel_sheet_data)
    
    # Track subjects with missing injection coordinates
    if missing_injection_coords_info['has_missing_injection_coords']:
        subjects_with_missing_injection_coords.append({
            'subject_id': subject_id,
            'details': missing_injection_coords_info['missing_injection_details']
        })
    
    # Extract specimen procedure details for tracking
    if v2_data and hasattr(v2_data, 'specimen_procedures') and v2_data.specimen_procedures:
        specimen_procedure_details = extract_specimen_procedure_details(v2_data.specimen_procedures, batch_tracking_info)
        all_specimen_procedure_data[subject_id] = specimen_procedure_details
        print(f"  Found specimen procedures for tracking")
    else:
        # Track subjects with missing specimen procedures - include batch tracking for debugging
        subjects_with_missing_specimen_procedures.append(subject_id)
        # Still add batch tracking info even if no procedures found
        if batch_tracking_info:
            all_specimen_procedure_data[subject_id] = {
                'batch_number': batch_tracking_info.get('batch_number', ""),
                'date_range_tab': batch_tracking_info.get('date_range_tab', "")
            }
        else:
            all_specimen_procedure_data[subject_id] = {}
    
    # Check if conversion was successful
    if v2_data is None:
        # Conversion failed
        print(f"  ✗ Schema 2.0 conversion failed - keeping v1 format only")
        return 'failed'
    
    # Save the v2.0 compliant data
    save_procedures_json(subject_id, v2_data, is_v1=False)
    print(f"  ✓ Successfully created schema 2.0 compliant procedures.json")
    return 'success'


def print_summary_reports(subjects, success_count, failed_count, skipped_count, all_injection_data, all_specimen_procedure_data, subjects_with_missing_injection_coords, subjects_with_missing_specimen_procedures):
    """
    Print comprehensive summary reports for the processing results.
    
    Args:
        subjects: List of all subjects processed
        success_count: Number of successful conversions
        failed_count: Number of failed conversions
        skipped_count: Number of skipped subjects
        all_injection_data: Dict of injection data by subject
        all_specimen_procedure_data: Dict of specimen procedure data by subject
        subjects_with_missing_injection_coords: List of subjects with missing injection coordinates
        subjects_with_missing_specimen_procedures: List of subjects with missing specimen procedures
    """
    # Summary
    print(f"\n" + "=" * 60)
    print(f"SUMMARY")
    print(f"=" * 60)
    print(f"Total subjects processed: {len(subjects)}")
    print(f"Successfully processed: {success_count}")
    print(f"Failed: {failed_count}")
    print(f"Skipped (already exist): {skipped_count}")
    if all_injection_data:
        total_injections = sum(len(inj_list) for inj_list in all_injection_data.values())
        print(f"Injection materials tracked: {total_injections} injections across {len(all_injection_data)} subjects")
    if all_specimen_procedure_data:
        subjects_with_procedures = len([s for s in all_specimen_procedure_data if all_specimen_procedure_data[s]])
        total_tracked_subjects = len(all_specimen_procedure_data)
        print(f"Specimen procedures tracked: {total_tracked_subjects} subjects total ({subjects_with_procedures} with procedure data)")
    
    # Report subjects with missing injection coordinate information
    if subjects_with_missing_injection_coords:
        print(f"\n" + "⚠️  SUBJECTS WITH MISSING INJECTION COORDINATE DATA")
        print(f"=" * 60)
        print(f"Found {len(subjects_with_missing_injection_coords)} subjects with incomplete injection coordinate information:")
        for subject_info in subjects_with_missing_injection_coords:
            print(f"\n  Subject {subject_info['subject_id']}:")
            for detail in subject_info['details']:
                print(f"    • {detail}")
        print(f"\nNote: Placeholder injection coordinates (0.0) were used for missing values to maintain schema compliance.")
    else:
        print(f"\n✓ All subjects had complete injection coordinate data")
    
    # Report subjects with missing specimen procedures
    if subjects_with_missing_specimen_procedures:
        print(f"\n" + "⚠️  SUBJECTS WITH MISSING SPECIMEN PROCEDURES")
        print(f"=" * 60)
        print(f"Found {len(subjects_with_missing_specimen_procedures)} subjects with no specimen procedures from Excel data:")
        for subject_id in subjects_with_missing_specimen_procedures:
            print(f"  • Subject {subject_id}")
        print(f"\nNote: These subjects were not found in the Excel specimen procedures data or had no valid procedures.")
    else:
        print(f"\n✓ All subjects had specimen procedures from Excel data")


def main():
    """
    Main function to process all subjects and create procedures.json files.
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Create procedures.json files for patchseq subjects")
    parser.add_argument("--limit", type=int, default=None, 
                       help="Limit the number of subjects to process (default: process all)")
    parser.add_argument("--avoid-overwrite", action="store_true", 
                       help="Skip existing procedures.json (v2.0) files instead of overwriting them")
    args = parser.parse_args()
    
    print("Creating procedures.json files for patchseq subjects")
    print("=" * 60)
    
    # Load Excel specimen procedures data once at the beginning
    print("Loading specimen procedures from Excel...")
    excel_sheet_data = load_specimen_procedures_excel()
    if excel_sheet_data:
        print(f"✓ Loaded Excel data with {len(excel_sheet_data)} sheets")
    else:
        print("⚠️  No Excel data loaded - will proceed without specimen procedures")
    
    # Step 1: Get list of subjects
    subjects = get_subjects_list()
    
    # Apply limit if specified
    if args.limit is not None:
        subjects = subjects[:args.limit]
        print(f"Limiting to first {args.limit} subjects: {subjects}")
    
    # Step 2: Process each subject
    success_count = 0
    failed_count = 0
    skipped_count = 0
    
    # Track injection data for CSV
    all_injection_data = {}
    subjects_processed = []
    
    # Track subjects with missing injection coordinate information
    subjects_with_missing_injection_coords = []
    
    # Track subjects with missing specimen procedures
    subjects_with_missing_specimen_procedures = []
    
    # Track specimen procedure data for CSV
    all_specimen_procedure_data = {}
    
    for subject_id in subjects:
        result = process_single_subject(
            subject_id, 
            excel_sheet_data, 
            args, 
            all_injection_data, 
            all_specimen_procedure_data, 
            subjects_with_missing_injection_coords, 
            subjects_with_missing_specimen_procedures
        )
        
        if result == 'success':
            success_count += 1
            subjects_processed.append(subject_id)
        elif result == 'failed':
            failed_count += 1
        elif result == 'skipped':
            skipped_count += 1
    
    # Update injection materials tracking CSV
    if subjects_processed:
        print(f"\n" + "=" * 60)
        print(f"Creating viral material tracking CSV")
        print(f"=" * 60)
        update_injection_tracking_csv(subjects_processed, all_injection_data)
        
        print(f"\n" + "=" * 60)
        print(f"Creating specimen procedure tracking CSV")
        print(f"=" * 60)
        update_specimen_procedure_tracking_csv(subjects_processed, all_specimen_procedure_data)
    
    # Print comprehensive summary reports
    print_summary_reports(
        subjects, 
        success_count, 
        failed_count, 
        skipped_count, 
        all_injection_data, 
        all_specimen_procedure_data, 
        subjects_with_missing_injection_coords, 
        subjects_with_missing_specimen_procedures
    )


if __name__ == "__main__":
    main()
