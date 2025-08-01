"""
Schema conversion from v1.x to v2.0.
"""

from datetime import datetime
import copy

from aind_data_schema.core.procedures import Procedures, Surgery
from aind_data_schema.components.coordinates import CoordinateSystemLibrary, Translation, Rotation
from aind_data_schema.components.surgery_procedures import BrainInjection, Perfusion, Anaesthetic
from aind_data_schema.components.injection_procedures import InjectionDynamics, InjectionProfile, ViralMaterial, TarsVirusIdentifiers
from aind_data_schema_models.units import VolumeUnit, TimeUnit, AngleUnit
from aind_data_schema_models.pid_names import PIDName


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
                            angles=[angle, 0.0, 0.0],
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
                    pass
            
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
            from excel_loader import get_specimen_procedures_for_subject
            specimen_procedures_list, batch_tracking_info = get_specimen_procedures_for_subject(subject_id, excel_sheet_data)
            
            if specimen_procedures_list:
                print(f"    ✓ Found {len(specimen_procedures_list)} specimen procedures in Excel data")
                # Add specimen procedures to the main procedures object
                procedures_obj.specimen_procedures = specimen_procedures_list
            else:
                print(f"    ⚠️  No specimen procedures found for subject {subject_id} in Excel data")
        
        # Convert to dict using model_dump()
        return procedures_obj.model_dump(exclude_unset=True), missing_injection_coords_info, batch_tracking_info
        
    except Exception as e:
        print(f"    ✗ Error converting to v2: {e}")
        return None, missing_injection_coords_info, batch_tracking_info


def create_procedures_for_subject(subject_id, excel_file="DT_HM_TissueClearingTracking_.xlsx", metadata_source="service", output_dir="procedures"):
    """
    High-level convenience function to create procedures for a single subject.
    
    Args:
        subject_id: Subject ID to process
        excel_file: Path to Excel file with specimen procedures (optional)
        metadata_source: Source for v1 metadata ("service" or provide dict)
        output_dir: Directory to save procedures.json files
        
    Returns:
        dict: Result with success status and any errors
    """
    from file_io import save_procedures_json, check_existing_procedures
    from metadata_service import fetch_procedures_metadata
    from excel_loader import load_specimen_procedures_excel
    
    result = {"success": False, "subject_id": subject_id, "errors": []}
    
    try:
        # Load Excel data if file provided
        excel_sheet_data = None
        if excel_file:
            excel_sheet_data = load_specimen_procedures_excel(excel_file)
        
        # Get v1 data
        if metadata_source == "service":
            success, v1_data, message = fetch_procedures_metadata(subject_id)
            if not success:
                result["errors"].append(f"Failed to fetch metadata: {message}")
                return result
        else:
            v1_data = metadata_source
        
        # Convert to v2
        v2_data, missing_coords_info, batch_info = convert_procedures_to_v2(v1_data, excel_sheet_data)
        if not v2_data:
            result["errors"].append("Failed to convert to v2 schema")
            return result
        
        # Save
        save_procedures_json(subject_id, v2_data, output_dir=output_dir)
        
        result["success"] = True
        result["missing_coordinates"] = missing_coords_info
        result["batch_info"] = batch_info
        
    except Exception as e:
        result["errors"].append(str(e))
    
    return result


def create_procedures_for_subjects(subject_ids, excel_file="DT_HM_TissueClearingTracking_.xlsx", output_dir="procedures"):
    """
    High-level convenience function to create procedures for multiple subjects.
    
    Args:
        subject_ids: List of subject IDs to process
        excel_file: Path to Excel file with specimen procedures (optional)
        output_dir: Directory to save procedures.json files
        
    Returns:
        list: List of result dicts, one per subject
    """
    from excel_loader import load_specimen_procedures_excel
    
    # Load Excel data once for all subjects
    excel_sheet_data = None
    if excel_file:
        excel_sheet_data = load_specimen_procedures_excel(excel_file)
    
    results = []
    for subject_id in subject_ids:
        result = create_procedures_for_subject(
            subject_id, 
            excel_file=None,  # Don't reload Excel for each subject
            metadata_source="service",
            output_dir=output_dir
        )
        results.append(result)
    
    return results
