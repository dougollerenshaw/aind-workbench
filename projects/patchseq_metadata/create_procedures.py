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

from aind_data_schema.core.procedures import Procedures, Surgery
from aind_data_schema.components.coordinates import CoordinateSystemLibrary, Translation, Rotation
from aind_data_schema.components.surgery_procedures import BrainInjection, Perfusion, Anaesthetic
from aind_data_schema.components.injection_procedures import InjectionDynamics, InjectionProfile, NonViralMaterial
from aind_data_schema.components.reagent import Reagent
from aind_data_schema_models.organizations import Organization
from aind_data_schema_models.units import VolumeUnit


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


def convert_procedures_to_v2(data):
    """
    Convert procedures data from v1.x to schema 2.0 by building proper Pydantic model objects.
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
                        
                        # Handle injection materials - create a minimal non-viral material
                        materials = [NonViralMaterial(
                            name="Unknown viral material",
                            source=Organization.OTHER
                        )]
                        injection_kwargs["injection_materials"] = materials
                        
                        # Handle coordinates
                        if all(k in sub_proc for k in ["injection_coordinate_ml", "injection_coordinate_ap", "injection_coordinate_depth"]):
                            coordinates = []
                            depths = sub_proc["injection_coordinate_depth"]
                            if not isinstance(depths, list):
                                depths = [depths]
                            
                            for depth in depths:
                                coord_transform = Translation(
                                    translation=[
                                        float(sub_proc["injection_coordinate_ml"]),
                                        float(sub_proc["injection_coordinate_ap"]),
                                        float(depth)
                                    ]
                                )
                                coordinates.append([coord_transform])
                            injection_kwargs["coordinates"] = coordinates
                        
                        # Handle injection dynamics
                        if sub_proc.get("injection_volume"):
                            volumes = sub_proc["injection_volume"]
                            if not isinstance(volumes, list):
                                volumes = [volumes]
                            
                            dynamics = []
                            for volume in volumes:
                                dynamics.append(InjectionDynamics(
                                    volume=float(volume),
                                    volume_unit=VolumeUnit.NL,
                                    profile=InjectionProfile.BOLUS
                                ))
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
        v2_data = convert_procedures_to_v2(v1_source_data)
        
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
