#!/usr/bin/env python3
"""
Simple script to create procedures.json files for patchseq subjects.
By default, this will create procedures for the 32 mice defined in the subjects list in extract_patchseq_subjects.py.
It's also possible to generate procedures for a specific subject using --subjects argument followed by a space separated list of subject IDs
"""

import argparse


# Import functions from modules
from excel_loader import load_specimen_procedures_excel
from metadata_service import fetch_procedures_metadata  
from schema_conversion import convert_procedures_to_v2
from file_io import save_procedures_json, check_existing_procedures
from csv_tracking import extract_injection_details, update_injection_tracking_csv, extract_specimen_procedure_details, update_specimen_procedure_tracking_csv
from subject_utils import get_subjects_list


def process_single_subject(
    subject_id, 
    excel_sheet_data=None, 
    skip_existing=False,
    all_injection_data=None, 
    all_specimen_procedure_data=None, 
    subjects_with_missing_injection_coords=None, 
    subjects_with_missing_specimen_procedures=None
):
    """
    Process a single subject: check existing files, fetch/convert data, track injection coordinates and specimen procedures.
    
    Args:
        subject_id: Subject ID to process
        excel_sheet_data: Excel sheet data for specimen procedures (optional)
        skip_existing: Skip processing if v2.0 procedures.json already exists
        all_injection_data: Dict to store injection data for CSV tracking (optional)
        all_specimen_procedure_data: Dict to store specimen procedure data for CSV tracking (optional)
        subjects_with_missing_injection_coords: List to track subjects with missing injection coordinates (optional)
        subjects_with_missing_specimen_procedures: List to track subjects with missing specimen procedures (optional)
        
    Returns:
        bool: True if processing was successful, False if it failed
    """
    # Initialize optional parameters with defaults
    if excel_sheet_data is None:
        excel_sheet_data = {}
    if all_injection_data is None:
        all_injection_data = {}
    if all_specimen_procedure_data is None:
        all_specimen_procedure_data = {}
    if subjects_with_missing_injection_coords is None:
        subjects_with_missing_injection_coords = []
    if subjects_with_missing_specimen_procedures is None:
        subjects_with_missing_specimen_procedures = []
    
    print(f"\n--- Processing Subject: {subject_id} ---")
    
    # Check if files already exist
    v1_exists, v2_exists, v1_data, v2_data = check_existing_procedures(subject_id)
    
    if v2_exists and skip_existing:
        print(f"  ✓ v2.0 procedures.json already exists, skipping (--skip-existing flag set)")
        return True
    
    # Fetch v1 data from API if not cached
    if v1_exists and v1_data:
        print(f"  ✓ Using cached v1 data")
        success, data, message = True, v1_data, "Loaded from cache"
    else:
        success, data, message = fetch_procedures_metadata(subject_id)
        
        if success and data:
            print(f"  ✓ Fetched procedures from API: {message}")
            # Save v1 data for debugging
            save_procedures_json(subject_id, data, is_v1=True)
        else:
            print(f"  ✗ Failed to fetch procedures: {message}")
            return False
    
    # Convert to v2 schema
    print(f"  📄 Converting to v2 schema...")
    v2_data, missing_injection_coords_info, batch_tracking_info = convert_procedures_to_v2(data, excel_sheet_data)
    
    if v2_data is None:
        print(f"  ✗ Schema conversion failed")
        return False
    
    # Track injection coordinate and specimen procedure issues for this subject
    if missing_injection_coords_info['has_missing_injection_coords']:
        subjects_with_missing_injection_coords.append(subject_id)
        print(f"    ⚠️  Missing injection coordinates detected:")
        for detail in missing_injection_coords_info['missing_injection_details']:
            print(f"      - {detail}")
    
    # Extract injection details for CSV tracking
    injection_details = extract_injection_details(data)
    if injection_details:
        all_injection_data[subject_id] = injection_details
        print(f"    ✓ Extracted {len(injection_details)} injection details for CSV tracking")
    
    # Extract specimen procedure details for CSV tracking
    if v2_data.get('specimen_procedures'):
        specimen_procedure_details = extract_specimen_procedure_details(v2_data['specimen_procedures'], batch_tracking_info)
        all_specimen_procedure_data[subject_id] = specimen_procedure_details
        print(f"    ✓ Extracted specimen procedure details for CSV tracking")
    else:
        subjects_with_missing_specimen_procedures.append(subject_id)
        print(f"    ⚠️  No specimen procedures found for this subject")
        # Still add empty record for CSV tracking consistency
        empty_specimen_procedure_details = extract_specimen_procedure_details([], batch_tracking_info)
        all_specimen_procedure_data[subject_id] = empty_specimen_procedure_details
    
    # Save v2 data
    save_procedures_json(subject_id, v2_data, is_v1=False)
    print(f"  ✓ Successfully saved v2.0 procedures.json")
    
    return True


def print_summary_reports(summary_data):
    """
    Print summary reports including missing injection coordinates and specimen procedures.
    
    Args:
        summary_data: Dictionary containing all summary information
    """
    subjects = summary_data['subjects']
    success_count = summary_data['success_count']
    failed_count = summary_data['failed_count']
    skipped_count = summary_data['skipped_count']
    all_injection_data = summary_data['all_injection_data']
    all_specimen_procedure_data = summary_data['all_specimen_procedure_data']
    subjects_with_missing_injection_coords = summary_data['subjects_with_missing_injection_coords']
    subjects_with_missing_specimen_procedures = summary_data['subjects_with_missing_specimen_procedures']
    print(f"\n{'='*60}")
    print(f"📊 PROCESSING SUMMARY")
    print(f"{'='*60}")
    print(f"Total subjects: {len(subjects)}")
    print(f"✅ Successful: {success_count}")
    print(f"❌ Failed: {failed_count}")
    print(f"⏭️  Skipped: {skipped_count}")
    
    # Missing injection coordinates report
    if subjects_with_missing_injection_coords:
        print(f"\n⚠️  SUBJECTS WITH MISSING INJECTION COORDINATES ({len(subjects_with_missing_injection_coords)}):")
        for subject_id in subjects_with_missing_injection_coords:
            print(f"  - {subject_id}")
    else:
        print(f"\n✅ All processed subjects have complete injection coordinates")
    
    # Missing specimen procedures report
    if subjects_with_missing_specimen_procedures:
        print(f"\n⚠️  SUBJECTS WITH MISSING SPECIMEN PROCEDURES ({len(subjects_with_missing_specimen_procedures)}):")
        for subject_id in subjects_with_missing_specimen_procedures:
            print(f"  - {subject_id}")
    else:
        print(f"\n✅ All processed subjects have specimen procedures")
    
    # Update CSV tracking files with all processed subjects
    print(f"\n💾 UPDATING CSV TRACKING FILES...")
    subjects_processed = [s for s in subjects if s not in []]  # All subjects were processed
    
    # Update injection tracking CSV
    update_injection_tracking_csv(subjects_processed, all_injection_data)
    
    # Update specimen procedure tracking CSV
    update_specimen_procedure_tracking_csv(subjects_processed, all_specimen_procedure_data)
    
    print(f"\n{'='*60}")


def main():
    """
    Main function that orchestrates the procedure processing workflow.
    """
    parser = argparse.ArgumentParser(description="Create procedures.json files for patchseq subjects")
    parser.add_argument("--skip-existing", action="store_true", help="Skip subjects that already have v2.0 procedures.json files")
    parser.add_argument("--limit", type=int, help="Limit number of subjects to process")
    parser.add_argument("--subjects", nargs="+", help="Process specific subjects (space-separated list)")
    parser.add_argument("--excel", default="DT_HM_TissueClearingTracking_.xlsx", help="Excel file with specimen procedures data")
    
    args = parser.parse_args()
    
    print("🚀 Starting procedures.json creation workflow...")
    
    # Load Excel data for specimen procedures
    print(f"\n📊 Loading Excel data for specimen procedures...")
    excel_sheet_data = load_specimen_procedures_excel(args.excel)
    if excel_sheet_data is None:
        print("❌ Failed to load Excel data. Continuing without specimen procedures...")
        excel_sheet_data = {}
    
    # Get list of subjects to process
    if args.subjects:
        subjects = args.subjects
        print(f"📋 Processing specific subjects: {subjects}")
    else:
        subjects = get_subjects_list()
        if args.limit:
            subjects = subjects[:args.limit]
            print(f"📋 Limited to first {args.limit} subjects")
    
    # Initialize tracking variables
    success_count = 0
    failed_count = 0 
    skipped_count = 0
    all_injection_data = {}
    all_specimen_procedure_data = {}
    subjects_with_missing_injection_coords = []
    subjects_with_missing_specimen_procedures = []
    
    # Process each subject
    for subject_id in subjects:
        try:
            success = process_single_subject(
                subject_id, 
                excel_sheet_data=excel_sheet_data,
                skip_existing=args.skip_existing,
                all_injection_data=all_injection_data,
                all_specimen_procedure_data=all_specimen_procedure_data,
                subjects_with_missing_injection_coords=subjects_with_missing_injection_coords,
                subjects_with_missing_specimen_procedures=subjects_with_missing_specimen_procedures
            )
            
            if success:
                success_count += 1
            else:
                failed_count += 1
                
        except KeyboardInterrupt:
            print(f"\n⚠️  Interrupted by user")
            break
        except Exception as e:
            print(f"  ❌ Unexpected error: {e}")
            failed_count += 1
    
    # Print final summary
    summary_data = {
        'subjects': subjects,
        'success_count': success_count,
        'failed_count': failed_count,
        'skipped_count': skipped_count,
        'all_injection_data': all_injection_data,
        'all_specimen_procedure_data': all_specimen_procedure_data,
        'subjects_with_missing_injection_coords': subjects_with_missing_injection_coords,
        'subjects_with_missing_specimen_procedures': subjects_with_missing_specimen_procedures
    }
    print_summary_reports(summary_data)


if __name__ == "__main__":
    main()
