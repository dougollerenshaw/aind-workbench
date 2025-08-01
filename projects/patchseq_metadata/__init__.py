"""
Main API exports and convenience functions for patchseq procedures.
"""

# High-level convenience functions
from schema_conversion import create_procedures_for_subject, create_procedures_for_subjects

# Module-level imports for advanced users
from excel_loader import load_specimen_procedures_excel, get_specimen_procedures_for_subject
from metadata_service import fetch_procedures_metadata
from schema_conversion import convert_procedures_to_v2
from file_io import save_procedures_json, check_existing_procedures
from csv_tracking import extract_injection_details, extract_specimen_procedure_details, update_injection_tracking_csv, update_specimen_procedure_tracking_csv

__all__ = [
    # High-level API
    'create_procedures_for_subject',
    'create_procedures_for_subjects',
    
    # Excel operations
    'load_specimen_procedures_excel',
    'get_specimen_procedures_for_subject',
    
    # Metadata service
    'fetch_procedures_metadata',
    
    # Schema conversion
    'convert_procedures_to_v2',
    
    # File I/O
    'save_procedures_json',
    'check_existing_procedures',
    
    # CSV tracking
    'extract_injection_details',
    'extract_specimen_procedure_details', 
    'update_injection_tracking_csv',
    'update_specimen_procedure_tracking_csv'
]
