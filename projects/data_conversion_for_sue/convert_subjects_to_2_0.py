#!/usr/bin/env python3
"""
Convert subject.json files from schema 1.x to 2.0.

This script reads existing subject.json files and converts them to the new 2.0 schema format
where subject details are organized under a `subject_details` field containing MouseSubject.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import argparse

from aind_data_schema.core.subject import Subject
from aind_data_schema.components.subjects import BreedingInfo, Housing, Sex, MouseSubject
from aind_data_schema_models.organizations import Organization
from aind_data_schema_models.species import Species, Strain


def convert_sex(sex_str: str) -> Sex:
    """Convert sex string to Sex enum."""
    sex_mapping = {
        "Male": Sex.MALE,
        "Female": Sex.FEMALE,
    }
    if sex_str not in sex_mapping:
        raise ValueError(f"Unknown sex value: {sex_str}. Only 'Male' and 'Female' are supported in AIND 2.0 schema.")
    return sex_mapping[sex_str]


def convert_species(species_data: Dict[str, Any]) -> Species:
    """Convert species data to Species enum."""
    species_name = species_data.get("name", "")
    if "Mus musculus" in species_name:
        return Species.HOUSE_MOUSE
    # Add other species mappings as needed
    return Species.HOUSE_MOUSE  # Default for now


def convert_strain(genotype: str, background_strain: Optional[str]) -> Strain:
    """Convert genotype/background strain to Strain enum."""
    # Map common genotypes to strains
    strain_mapping = {
        "C57BL/6J": Strain.C57BL_6J,
        "C57BL/6": Strain.C57BL_6J,
        "BALB/c": Strain.BALB_C,
        "BALB/C": Strain.BALB_C,
    }
    
    # Check background strain first
    if background_strain:
        for key, strain in strain_mapping.items():
            if key.upper() in background_strain.upper():
                return strain
    
    # Check genotype for strain indicators
    if genotype:
        for key, strain in strain_mapping.items():
            if key.upper() in genotype.upper():
                return strain
    
    # Default to C57BL/6J for most lab mice
    return Strain.C57BL_6J


def convert_organization(source_data: Dict[str, Any]) -> Organization:
    """Convert source data to Organization enum."""
    source_name = source_data.get("name", "").lower()
    if "allen" in source_name:
        return Organization.AI
    elif "hopkins" in source_name or "jhu" in source_name:
        return Organization.JHU
    elif "jackson" in source_name or "jax" in source_name:
        return Organization.JAX
    # Add more organization mappings as needed
    return Organization.OTHER


def convert_subject_1x_to_2x(old_subject_data: Dict[str, Any]) -> Subject:
    """
    Convert a 1.x subject JSON to 2.0 Subject object.
    
    Args:
        old_subject_data: Dictionary from 1.x subject.json file
        
    Returns:
        Subject: New 2.0 Subject object
    """
    # Extract basic fields
    subject_id = old_subject_data.get("subject_id", "")
    
    # Convert date of birth
    date_of_birth_str = old_subject_data.get("date_of_birth")
    if date_of_birth_str:
        date_of_birth = datetime.fromisoformat(date_of_birth_str).date()
    else:
        # Default date if missing
        date_of_birth = datetime(2020, 1, 1).date()
    
    # Convert enums
    sex = convert_sex(old_subject_data.get("sex", "Unknown"))
    species = convert_species(old_subject_data.get("species", {}))
    strain = convert_strain(
        old_subject_data.get("genotype", ""),
        old_subject_data.get("background_strain")
    )
    source = convert_organization(old_subject_data.get("source", {}))
    
    # Convert breeding info
    breeding_info_data = old_subject_data.get("breeding_info", {})
    breeding_info = None
    if breeding_info_data:
        breeding_info = BreedingInfo(
            breeding_group=breeding_info_data.get("breeding_group", ""),
            maternal_id=breeding_info_data.get("maternal_id", ""),
            maternal_genotype=breeding_info_data.get("maternal_genotype", ""),
            paternal_id=breeding_info_data.get("paternal_id", ""),
            paternal_genotype=breeding_info_data.get("paternal_genotype", "")
        )
    
    # Convert housing info
    housing_data = old_subject_data.get("housing")
    housing = None
    if housing_data:
        housing = Housing(
            cage_id=housing_data.get("cage_id"),
            home_cage_enrichment=housing_data.get("home_cage_enrichment", [])
        )
    
    # Create MouseSubject details
    mouse_subject = MouseSubject(
        species=species,
        strain=strain,
        sex=sex,
        date_of_birth=date_of_birth,
        source=source,
        breeding_info=breeding_info,
        genotype=old_subject_data.get("genotype", ""),
        housing=housing,
        wellness_reports=old_subject_data.get("wellness_reports", [])
    )
    
    # Create new 2.0 Subject
    new_subject = Subject(
        subject_id=subject_id,
        subject_details=mouse_subject,
        notes=old_subject_data.get("notes")
    )
    
    return new_subject


def convert_subject_file(input_path: Path, output_path: Path, backup: bool = True):
    """
    Convert a single subject file from 1.x to 2.0.
    
    Args:
        input_path: Path to input 1.x subject.json file
        output_path: Path for output 2.0 subject.json file
        backup: Whether to create a backup of the original file
    """
    print(f"Converting {input_path.name}...")
    
    # Read the old file
    with open(input_path, 'r') as f:
        old_data = json.load(f)
    
    # Check if it's already 2.0
    schema_version = old_data.get("schema_version", "")
    if schema_version.startswith("2."):
        print(f"  File {input_path.name} is already version {schema_version}, skipping...")
        return
    
    # Create backup if requested
    if backup and input_path == output_path:
        backup_path = input_path.with_suffix('.json.backup')
        print(f"  Creating backup: {backup_path.name}")
        with open(backup_path, 'w') as f:
            json.dump(old_data, f, indent=2)
    
    # Convert to 2.0
    try:
        new_subject = convert_subject_1x_to_2x(old_data)
        
        # Save the new file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            # Use model_dump to get the JSON representation
            json.dump(new_subject.model_dump(), f, indent=2, default=str)
        
        print(f"  ✓ Converted to 2.0 schema: {output_path}")
        
        # Validate the new file can be loaded
        with open(output_path, 'r') as f:
            test_data = json.load(f)
        Subject.model_validate(test_data)
        print(f"  ✓ Validation successful")
        
    except Exception as e:
        print(f"  ✗ Error converting {input_path.name}: {str(e)}")
        raise


def main():
    """Main function to convert subject files."""
    parser = argparse.ArgumentParser(
        description="Convert subject.json files from schema 1.x to 2.0"
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default="metadata/subjects",
        help="Directory containing 1.x subject.json files (default: metadata/subjects)"
    )
    parser.add_argument(
        "--output-dir", 
        type=str,
        default=None,
        help="Output directory for 2.0 files (default: same as input-dir)"
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Don't create backup files when overwriting"
    )
    
    args = parser.parse_args()
    
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir) if args.output_dir else input_dir
    
    if not input_dir.exists():
        print(f"Error: Input directory not found: {input_dir}")
        return
    
    # Find all subject JSON files
    subject_files = list(input_dir.glob("subject_*.json"))
    
    if not subject_files:
        print(f"No subject_*.json files found in {input_dir}")
        return
    
    print(f"Found {len(subject_files)} subject files to convert")
    print(f"Input directory: {input_dir}")
    print(f"Output directory: {output_dir}")
    print(f"Create backups: {not args.no_backup}")
    print()
    
    success_count = 0
    error_count = 0
    
    for input_file in subject_files:
        output_file = output_dir / input_file.name
        
        try:
            convert_subject_file(input_file, output_file, backup=not args.no_backup)
            success_count += 1
        except Exception as e:
            print(f"Failed to convert {input_file.name}: {str(e)}")
            error_count += 1
    
    print(f"\nConversion complete:")
    print(f"  Successfully converted: {success_count}")
    print(f"  Errors: {error_count}")
    
    if error_count == 0:
        print(f"\n✓ All subject files have been converted to 2.0 schema!")


if __name__ == "__main__":
    main()
