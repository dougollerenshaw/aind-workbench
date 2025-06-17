#!/usr/bin/env python3
"""
Test script to specifically test metadata retrieval for Hopkins subjects with the new mapping.
"""
import sys
import pandas as pd
import requests
from pathlib import Path

# Add the project directory to path to import our modules
sys.path.append(str(Path(__file__).parent))

from get_procedures_and_subject_metadata import get_mapped_subject_id, fetch_metadata

def test_hopkins_metadata_retrieval():
    """Test metadata retrieval for Hopkins subjects using the mapping."""
    print("Testing Hopkins Subject Metadata Retrieval")
    print("=" * 50)
    
    # Test specific Hopkins subjects that should be in the inventory
    hopkins_subjects = ['KJ005', 'KJ007', 'KJ009']
    
    for subject_id in hopkins_subjects:
        print(f"\nTesting subject: {subject_id}")
        mapped_id = get_mapped_subject_id(subject_id)
        print(f"  Mapped to: {mapped_id}")
        
        # Test procedures metadata
        print(f"  Testing procedures metadata...")
        proc_success, proc_data, proc_message = fetch_metadata(
            subject_id, "procedures", "http://aind-metadata-service"
        )
        if proc_success:
            print(f"    ✓ Procedures metadata retrieved successfully")
            print(f"    Data keys: {list(proc_data.keys()) if proc_data else 'None'}")
        else:
            print(f"    ✗ Failed to retrieve procedures metadata: {proc_message}")
        
        # Test subject metadata
        print(f"  Testing subject metadata...")
        subj_success, subj_data, subj_message = fetch_metadata(
            subject_id, "subject", "http://aind-metadata-service"
        )
        if subj_success:
            print(f"    ✓ Subject metadata retrieved successfully")
            print(f"    Data keys: {list(subj_data.keys()) if subj_data else 'None'}")
        else:
            print(f"    ✗ Failed to retrieve subject metadata: {subj_message}")

if __name__ == "__main__":
    test_hopkins_metadata_retrieval()
