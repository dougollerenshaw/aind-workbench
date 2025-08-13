"""
Excel file loading and specimen procedures extraction.
"""

import pandas as pd
from datetime import datetime
from aind_data_schema.core.procedures import SpecimenProcedure
from aind_data_schema.components.reagent import Reagent
from aind_data_schema_models.organizations import Organization


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
        
        # First, get all sheet names to identify which ones to process
        all_sheets = pd.ExcelFile(excel_file).sheet_names
        
        sheet_data = {}
        
        # Load Batch Info sheet with proper headers
        if "Batch Info" in all_sheets:
            batch_info_df = pd.read_excel(excel_file, sheet_name="Batch Info", header=0)
            
            # Clean up any unnamed columns
            batch_info_df.columns = [str(col) if not str(col).startswith('Unnamed:') else f"Column_{i}" 
                                    for i, col in enumerate(batch_info_df.columns)]
            
            
            sheet_data["Batch Info"] = batch_info_df
        
        # Process time-based sheets (complex multi-level headers)
        time_based_sheets = [sheet for sheet in all_sheets 
                           if sheet not in sheets_to_ignore and sheet != "Batch Info"]
        
        for sheet_name in time_based_sheets:
            
            # Load with multi-level headers (rows 0, 1, 2)
            df_raw = pd.read_excel(excel_file, sheet_name=sheet_name, header=None)
            
            if len(df_raw) < 4:
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
            
            
            sheet_data[sheet_name] = data_df
        
        return sheet_data
        
    except Exception as e:
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
