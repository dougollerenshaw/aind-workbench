"""
CSV tracking and export functionality.
"""

import pandas as pd


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
        'subject_id', 'injection_number', 'injection_type',
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
    
    # Fill in injection_type for ALL rows based on AP coordinates
    def determine_injection_type(row):
        ap_coord = row['coordinates_ap']
        if pd.isna(ap_coord) or ap_coord == '' or ap_coord is None:
            return 'spinal_cord'
        else:
            return 'brain'
    
    combined_df['injection_type'] = combined_df.apply(determine_injection_type, axis=1)
    
    # Ensure subject_id is string type for consistent sorting
    combined_df['subject_id'] = combined_df['subject_id'].astype(str)
    
    # Sort by subject_id and injection_number for easy reading
    combined_df = combined_df.sort_values(['subject_id', 'injection_number']).reset_index(drop=True)
    
    # Save the updated CSV
    combined_df.to_csv(csv_file, index=False)
    print(f"  Updated {csv_file} with {len(new_rows)} injection rows for {len(subjects_processed)} subjects")


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
    
    # Ensure subject_id is string type for consistent sorting
    combined_df['subject_id'] = combined_df['subject_id'].astype(str)
    
    # Sort by subject_id for easy reading
    combined_df = combined_df.sort_values(['subject_id']).reset_index(drop=True)
    
    # Save the updated CSV
    combined_df.to_csv(csv_file, index=False)
    print(f"  Updated {csv_file} with {len(new_rows)} subject rows ({subjects_with_procedures} with specimen procedures)")
