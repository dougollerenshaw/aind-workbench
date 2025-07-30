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
from aind_data_schema.components.injection_procedures import InjectionDynamics, InjectionProfile, NonViralMaterial, ViralMaterial
from aind_data_schema.components.reagent import Reagent
from aind_data_schema_models.organizations import Organization
from aind_data_schema_models.units import VolumeUnit, TimeUnit, AngleUnit


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
    sheets_to_ignore = ["TestBrains", "Additional batch info"]
    
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
        print(f"❌ Error loading Excel file: {e}")
        return None


def get_specimen_procedures_for_subject(subject_id, sheet_data):
    """
    Get specimen procedures for a subject using batch-based lookup.
    
    Args:
        subject_id: The subject ID to look up
        sheet_data: Dictionary of DataFrames from load_specimen_procedures_excel()
        
    Returns:
        List of specimen procedure dictionaries matching AIND schema format
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
        return []

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
        return []

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
            'procedure_type': 'Refractive index matching',
            'procedure_name': 'EasyIndex 50%',
            'notes_col': 'Notes_3',  # Index 22 - EasyIndex Notes
            'reagents': [
                ('EasyIndex_Lot#', 'Easy Index', 'LifeCanvas')
            ]
        },
        {
            'date_col': '100% EasyIndex_Date(s)',
            'procedure_type': 'Refractive index matching',
            'procedure_name': 'EasyIndex 100%',
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
            specimen_proc = SpecimenProcedure(
                procedure_type=mapping['procedure_type'],
                procedure_name=mapping['procedure_name'],
                specimen_id=subject_id,
                start_date=start_date_obj,
                end_date=end_date_obj,
                experimenters=[experimenter],
                procedure_details=procedure_details,
                notes=notes_value
            )
            
            procedures.append(specimen_proc)

    return procedures


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


def convert_procedures_to_v2(data, excel_sheet_data=None):
    """
    Convert procedures data from v1.x to schema 2.0 by building proper Pydantic model objects.
    Also adds specimen procedures from Excel data if available.
    Returns the converted data if successful, or None if conversion fails.
    """
    try:
        # Extract basic info
        subject_id = data["subject_id"]
        subject_procedures = []
        
        # Process each subject procedure
        for proc_data in data.get("subject_procedures", []):
            if proc_data.get("procedure_type") == "Surgery":
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
                        # Build BrainInjection
                        injection_kwargs = {
                            "protocol_id": sub_proc.get("protocol_id"),
                            "coordinate_system_name": "BREGMA_ARI"
                        }
                        
                        # Handle injection materials - create a more descriptive viral material
                        material_name = "Viral vector (Nanoject injection)"
                        if sub_proc.get("injection_hemisphere"):
                            material_name += f" - {sub_proc['injection_hemisphere']} hemisphere"
                        
                        materials = [ViralMaterial(
                            name=material_name
                        )]
                        injection_kwargs["injection_materials"] = materials
                        
                        # Handle coordinates with injection angle
                        if all(k in sub_proc for k in ["injection_coordinate_ml", "injection_coordinate_ap", "injection_coordinate_depth"]):
                            coordinates = []
                            depths = sub_proc["injection_coordinate_depth"]
                            if not isinstance(depths, list):
                                depths = [depths]
                            
                            for depth in depths:
                                coord_transforms = []
                                
                                # Add translation
                                translation = Translation(
                                    translation=[
                                        float(sub_proc["injection_coordinate_ml"]),
                                        float(sub_proc["injection_coordinate_ap"]),
                                        float(depth)
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
                            injection_kwargs["coordinates"] = coordinates
                        
                        # Handle injection dynamics with recovery time
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
                            
                        injection_kwargs["dynamics"] = dynamics
                        
                        brain_injection = BrainInjection(**injection_kwargs)
                        procedures_list.append(brain_injection)
                
                surgery_kwargs["procedures"] = procedures_list
                surgery = Surgery(**surgery_kwargs)
                subject_procedures.append(surgery)
        
        # Build final Procedures object
        procedures_obj = Procedures(
            subject_id=subject_id,
            subject_procedures=subject_procedures
        )
        
        # Add specimen procedures from Excel data if available
        if excel_sheet_data:
            try:
                specimen_procedures_list = get_specimen_procedures_for_subject(subject_id, excel_sheet_data)
                if specimen_procedures_list:
                    print(f"    ✓ Found {len(specimen_procedures_list)} specimen procedures in Excel data")
                    # The specimen_procedures_list already contains proper SpecimenProcedure objects
                    procedures_obj.specimen_procedures = specimen_procedures_list
                else:
                    print(f"    ⚠️  No specimen procedures found for subject {subject_id} in Excel data")
            except Exception as e:
                print(f"    ⚠️  Error extracting specimen procedures: {e}")
        
        return procedures_obj
        
    except Exception as e:
        print(f"    ✗ Schema conversion failed: {e}")
        return None


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


def main():
    """
    Main function to process all subjects and create procedures.json files.
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Create procedures.json files for patchseq subjects")
    parser.add_argument("--limit", type=int, default=None, 
                       help="Limit the number of subjects to process (default: process all)")
    parser.add_argument("--force-overwrite", action="store_true", 
                       help="Overwrite existing procedures.json files (default: skip existing files)")
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
    
    for subject_id in subjects:
        print(f"\nProcessing subject: {subject_id}")
        
        # Check if procedures files already exist
        v1_exists, v2_exists, v1_data, v2_data = check_existing_procedures(subject_id)
        
        # Skip if v2.0 file already exists (unless force_overwrite)
        if v2_exists and not args.force_overwrite:
            print(f"  Skipping - procedures.json (v2.0) already exists")
            skipped_count += 1
            continue
        
        # Determine source of v1 data
        if v1_exists and not args.force_overwrite:
            print(f"  Using existing procedures.json.v1")
            v1_source_data = v1_data
        else:
            # Fetch from service
            print(f"  Fetching procedures metadata from service...")
            success, v1_source_data, message = fetch_procedures_metadata(subject_id)
            
            if not success:
                failed_count += 1
                print(f"  ✗ Failed to fetch: {message}")
                continue
            
            # Save the v1 data
            save_procedures_json(subject_id, v1_source_data, is_v1=True)
        
        # Convert to schema 2.0
        print(f"  Converting to schema 2.0...")
        v2_data = convert_procedures_to_v2(v1_source_data, excel_sheet_data)
        
        # Check if conversion was successful
        if v2_data is None:
            # Conversion failed
            failed_count += 1
            print(f"  ✗ Schema 2.0 conversion failed - keeping v1 format only")
            continue
        
        # Save the v2.0 compliant data
        save_procedures_json(subject_id, v2_data, is_v1=False)
        success_count += 1
        print(f"  ✓ Successfully created schema 2.0 compliant procedures.json")
    
    # Summary
    print(f"\n" + "=" * 60)
    print(f"SUMMARY")
    print(f"=" * 60)
    print(f"Total subjects processed: {len(subjects)}")
    print(f"Successfully processed: {success_count}")
    print(f"Failed: {failed_count}")
    print(f"Skipped (already exist): {skipped_count}")


if __name__ == "__main__":
    main()
