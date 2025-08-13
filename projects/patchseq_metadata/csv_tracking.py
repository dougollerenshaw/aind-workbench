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
        # Handle both object attributes and dictionary keys
        experimenters = []
        if hasattr(proc, 'experimenters'):
            experimenters = proc.experimenters if proc.experimenters else []
        elif isinstance(proc, dict) and 'experimenters' in proc:
            experimenters = proc['experimenters'] if proc['experimenters'] else []
        experimenter = ", ".join(experimenters)
        
        start_date = ""
        if hasattr(proc, 'start_date'):
            start_date = str(proc.start_date) if proc.start_date else ""
        elif isinstance(proc, dict) and 'start_date' in proc:
            start_date = str(proc['start_date']) if proc['start_date'] else ""
            
        end_date = ""
        if hasattr(proc, 'end_date'):
            end_date = str(proc.end_date) if proc.end_date else ""
        elif isinstance(proc, dict) and 'end_date' in proc:
            end_date = str(proc['end_date']) if proc['end_date'] else ""
            
        notes = ""
        if hasattr(proc, 'notes'):
            notes = proc.notes if proc.notes else ""
        elif isinstance(proc, dict) and 'notes' in proc:
            notes = proc['notes'] if proc['notes'] else ""
            
        protocol_id = ""
        if hasattr(proc, 'protocol_id'):
            protocol_id = ", ".join(proc.protocol_id) if proc.protocol_id else ""
        elif isinstance(proc, dict) and 'protocol_id' in proc:
            pid = proc['protocol_id']
            if isinstance(pid, list):
                protocol_id = ", ".join(pid)
            else:
                protocol_id = str(pid) if pid else ""
        
        procedure_name = ""
        if hasattr(proc, 'procedure_name'):
            procedure_name = proc.procedure_name
        elif isinstance(proc, dict) and 'procedure_name' in proc:
            procedure_name = proc['procedure_name']
        
        if procedure_name == "SHIELD OFF":
            procedure_data['shield_off.start_date'] = start_date
            procedure_data['shield_off.end_date'] = end_date
            procedure_data['shield_off.experimenter'] = experimenter
            procedure_data['shield_off.notes'] = notes
            
            # Extract specific reagent lots
            procedure_details = []
            if hasattr(proc, 'procedure_details'):
                procedure_details = proc.procedure_details if proc.procedure_details else []
            elif isinstance(proc, dict) and 'procedure_details' in proc:
                procedure_details = proc['procedure_details'] if proc['procedure_details'] else []
                
            for reagent in procedure_details:
                reagent_name = ""
                lot_number = ""
                if hasattr(reagent, 'name'):
                    reagent_name = reagent.name
                    lot_number = reagent.lot_number if hasattr(reagent, 'lot_number') else ""
                elif isinstance(reagent, dict):
                    reagent_name = reagent.get('name', '')
                    lot_number = reagent.get('lot_number', '')
                    
                if reagent_name == "SHIELD Buffer" and lot_number:
                    procedure_data['shield_off.shield_buffer_lot'] = lot_number
                elif reagent_name == "SHIELD Epoxy" and lot_number:
                    procedure_data['shield_off.shield_epoxy_lot'] = lot_number
        
        elif procedure_name == "SHIELD ON":
            procedure_data['shield_on.start_date'] = start_date
            procedure_data['shield_on.end_date'] = end_date
            procedure_data['shield_on.experimenter'] = experimenter
            procedure_data['shield_on.notes'] = notes
            
            # Extract Shield On lot
            procedure_details = []
            if hasattr(proc, 'procedure_details'):
                procedure_details = proc.procedure_details if proc.procedure_details else []
            elif isinstance(proc, dict) and 'procedure_details' in proc:
                procedure_details = proc['procedure_details'] if proc['procedure_details'] else []
                
            for reagent in procedure_details:
                reagent_name = ""
                lot_number = ""
                if hasattr(reagent, 'name'):
                    reagent_name = reagent.name
                    lot_number = reagent.lot_number if hasattr(reagent, 'lot_number') else ""
                elif isinstance(reagent, dict):
                    reagent_name = reagent.get('name', '')
                    lot_number = reagent.get('lot_number', '')
                    
                if reagent_name == "SHIELD On" and lot_number:
                    procedure_data['shield_on.shield_on_lot'] = lot_number
        
        elif procedure_name == "Passive Delipidation":
            procedure_data['passive_delipidation.start_date'] = start_date
            procedure_data['passive_delipidation.end_date'] = end_date
            procedure_data['passive_delipidation.experimenter'] = experimenter
            procedure_data['passive_delipidation.notes'] = notes
            
            # Extract Delipidation Buffer lot
            procedure_details = []
            if hasattr(proc, 'procedure_details'):
                procedure_details = proc.procedure_details if proc.procedure_details else []
            elif isinstance(proc, dict) and 'procedure_details' in proc:
                procedure_details = proc['procedure_details'] if proc['procedure_details'] else []
                
            for reagent in procedure_details:
                reagent_name = ""
                lot_number = ""
                if hasattr(reagent, 'name'):
                    reagent_name = reagent.name
                    lot_number = reagent.lot_number if hasattr(reagent, 'lot_number') else ""
                elif isinstance(reagent, dict):
                    reagent_name = reagent.get('name', '')
                    lot_number = reagent.get('lot_number', '')
                    
                if reagent_name == "Delipidation Buffer" and lot_number:
                    procedure_data['passive_delipidation.delipidation_buffer_lot'] = lot_number
        
        elif procedure_name == "Active Delipidation":
            procedure_data['active_delipidation.start_date'] = start_date
            procedure_data['active_delipidation.end_date'] = end_date
            procedure_data['active_delipidation.experimenter'] = experimenter
            procedure_data['active_delipidation.notes'] = notes
            
            # Extract Conductivity Buffer lot
            procedure_details = []
            if hasattr(proc, 'procedure_details'):
                procedure_details = proc.procedure_details if proc.procedure_details else []
            elif isinstance(proc, dict) and 'procedure_details' in proc:
                procedure_details = proc['procedure_details'] if proc['procedure_details'] else []
                
            for reagent in procedure_details:
                reagent_name = ""
                lot_number = ""
                if hasattr(reagent, 'name'):
                    reagent_name = reagent.name
                    lot_number = reagent.lot_number if hasattr(reagent, 'lot_number') else ""
                elif isinstance(reagent, dict):
                    reagent_name = reagent.get('name', '')
                    lot_number = reagent.get('lot_number', '')
                    
                if reagent_name == "Conductivity Buffer" and lot_number:
                    procedure_data['active_delipidation.conductivity_buffer_lot'] = lot_number
        
        elif procedure_name == "EasyIndex":
            procedure_data['easyindex.start_date'] = start_date
            procedure_data['easyindex.end_date'] = end_date
            procedure_data['easyindex.experimenter'] = experimenter
            procedure_data['easyindex.notes'] = notes
            procedure_data['easyindex.protocol_id'] = protocol_id
            
            # Extract Easy Index lot
            procedure_details = []
            if hasattr(proc, 'procedure_details'):
                procedure_details = proc.procedure_details if proc.procedure_details else []
            elif isinstance(proc, dict) and 'procedure_details' in proc:
                procedure_details = proc['procedure_details'] if proc['procedure_details'] else []
                
            for reagent in procedure_details:
                reagent_name = ""
                lot_number = ""
                if hasattr(reagent, 'name'):
                    reagent_name = reagent.name
                    lot_number = reagent.lot_number if hasattr(reagent, 'lot_number') else ""
                elif isinstance(reagent, dict):
                    reagent_name = reagent.get('name', '')
                    lot_number = reagent.get('lot_number', '')
                    
                if reagent_name == "Easy Index" and lot_number:
                    procedure_data['easyindex.easy_index_lot'] = lot_number
    
    return procedure_data


def update_injection_tracking_csv(subjects_processed, all_injection_data):
    """
    Create a fresh CSV file with injection material tracking information.
    Uses tidy format: one row per injection with injection_number column.
    
    Args:
        subjects_processed: List of subject IDs that were processed
        all_injection_data: Dict mapping subject_id -> list of injection details
    """
    csv_file = "viral_material_tracking.csv"
    
    # Count total injections across all subjects
    total_injections = sum(len(all_injection_data.get(subject_id, [])) for subject_id in subjects_processed)
    
    if total_injections == 0:
        print(f"  No injections found, creating empty CSV")
        pd.DataFrame().to_csv(csv_file, index=False)
        return
    
    print(f"  Creating fresh CSV with {total_injections} injections")
    
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
    
    # Create rows for all subjects
    rows = []
    for subject_id in subjects_processed:
        injections = all_injection_data.get(subject_id, [])
        
        for injection_num, injection in enumerate(injections, 1):
            row_data = {
                'subject_id': str(subject_id),
                'injection_number': injection_num
            }
            
            # Add all injection details
            for key, value in injection.items():
                if key in columns:  # Only include columns we want
                    row_data[key] = value
            
            rows.append(row_data)
    
    # Create DataFrame
    df = pd.DataFrame(rows)
    
    # Ensure all columns exist and are in the right order
    df = df.reindex(columns=columns, fill_value="")
    
    # Fill in injection_type based on AP coordinates
    def determine_injection_type(row):
        ap_coord = row['coordinates_ap']
        if pd.isna(ap_coord) or ap_coord == '' or ap_coord is None:
            return 'spinal_cord'
        else:
            return 'brain'
    
    df['injection_type'] = df.apply(determine_injection_type, axis=1)
    
    # Sort by subject_id and injection_number for easy reading
    df = df.sort_values(['subject_id', 'injection_number']).reset_index(drop=True)
    
    # Save the CSV
    df.to_csv(csv_file, index=False)
    print(f"  Created {csv_file} with {len(rows)} injection rows for {len(subjects_processed)} subjects")


def update_specimen_procedure_tracking_csv(subjects_processed, all_specimen_procedure_data):
    """
    Create a fresh CSV file with specimen procedure tracking information.
    Uses wide format: one row per subject with columns for each of the 5 procedures.
    
    Args:
        subjects_processed: List of subject IDs that were processed
        all_specimen_procedure_data: Dict mapping subject_id -> procedure details dict
    """
    csv_file = "specimen_procedure_tracking.csv"
    
    # Count subjects with procedures vs total subjects
    subjects_with_procedures = len([s for s in subjects_processed if all_specimen_procedure_data.get(s)])
    
    print(f"  Creating fresh CSV for {len(subjects_processed)} subjects ({subjects_with_procedures} with specimen procedures)")
    
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
    
    # Create rows for all subjects
    rows = []
    for subject_id in subjects_processed:
        procedure_data = all_specimen_procedure_data.get(subject_id, {})
        
        # Always add row for every processed subject
        row_data = {'subject_id': str(subject_id)}
        
        # Add all procedure details (will be empty strings if no data)
        for key, value in procedure_data.items():
            if key in columns:  # Only include columns we want
                row_data[key] = value
        
        rows.append(row_data)
    
    # Create DataFrame
    df = pd.DataFrame(rows)
    
    # Ensure all columns exist and are in the right order
    df = df.reindex(columns=columns, fill_value="")
    
    # Sort by subject_id for easy reading
    df = df.sort_values(['subject_id']).reset_index(drop=True)
    
    # Save the CSV
    df.to_csv(csv_file, index=False)
    print(f"  Created {csv_file} with {len(rows)} subject rows ({subjects_with_procedures} with specimen procedures)")
