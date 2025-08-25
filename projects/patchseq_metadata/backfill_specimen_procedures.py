"""
Specimen Procedures Backfill Module

This module generates specimen procedures in the exact format returned by the metadata service,
using the Excel spreadsheet as the source of truth. This allows for consistent backfilling
of missing or incorrectly formatted specimen procedures.
"""

import pandas as pd
import os
import json
import requests
from datetime import datetime
from typing import Dict, List, Any, Optional
from excel_loader import (
    load_specimen_procedures_excel,
    get_specimen_procedures_for_subject,
)

# Load the Excel data once when module is imported
EXCEL_FILE = "DT_HM_TissueClearingTracking_.xlsx"
sheet_data = load_specimen_procedures_excel(EXCEL_FILE)


def get_specimen_procedures_from_spreadsheet(
    subject_id: str,
) -> List[Dict[str, Any]]:
    """
    Generate specimen procedures from Excel spreadsheet data, representing the data faithfully
    without forcing it into metadata service format. This allows for clean comparison.

    Args:
        subject_id: The subject ID to look up

    Returns:
        List of specimen procedure dictionaries representing what's actually in the spreadsheet
    """
    if sheet_data is None:
        raise ValueError("Excel data not loaded")

    # Get the procedures from Excel using existing function
    procedures, batch_info = get_specimen_procedures_for_subject(
        subject_id, sheet_data
    )

    if not procedures:
        return []

    # Convert to clean format representing spreadsheet data faithfully
    specimen_procedures = []

    for proc in procedures:
        # Create a clean representation of what's in the spreadsheet
        specimen_proc = {
            "procedure_type": getattr(proc, "procedure_type", "Unknown"),
            "procedure_name": getattr(proc, "procedure_name", "Unknown"),
            "specimen_id": subject_id,
            "start_date": (
                proc.start_date.isoformat() if proc.start_date else None
            ),
            "end_date": proc.end_date.isoformat() if proc.end_date else None,
            "experimenter_full_name": getattr(
                proc, "experimenter_full_name", "Unknown"
            ),
            "protocol_id": getattr(proc, "protocol_id", None),
            "reagents": convert_reagents_to_clean_format(
                proc.procedure_details
            ),
            "notes": getattr(proc, "notes", None),
            "batch_info": batch_info,  # Include batch info for reference
        }

        specimen_procedures.append(specimen_proc)

    return specimen_procedures


def convert_reagents_to_clean_format(
    procedure_details: Any,
) -> List[Dict[str, Any]]:
    """
    Convert reagents to a clean format representing what's in the spreadsheet.

    Args:
        procedure_details: Procedure details from Excel loader

    Returns:
        List of reagent dictionaries
    """
    if not procedure_details:
        return []

    reagents = []

    # Extract reagent information from procedure details
    if hasattr(procedure_details, "reagents"):
        for reagent in procedure_details.reagents:
            reagent_dict = {
                "name": getattr(reagent, "name", "Unknown"),
                "source": getattr(reagent, "source", None),
                "rrid": getattr(reagent, "rrid", None),
                "lot_number": getattr(reagent, "lot_number", None),
                "expiration_date": getattr(reagent, "expiration_date", None),
            }
            reagents.append(reagent_dict)

    return reagents


def convert_procedure_to_metadata_service_format(
    proc: Any, subject_id: str
) -> Optional[Dict[str, Any]]:
    """
    Convert a procedure from Excel format to metadata service format.

    Args:
        proc: Procedure object from Excel loader
        subject_id: The subject ID

    Returns:
        Dictionary in metadata service format, or None if conversion fails
    """
    try:
        # Map procedure type and name
        procedure_type, procedure_name = map_procedure_type_and_name(
            proc.procedure_type, proc.procedure_name
        )

        # Get dates
        start_date = proc.start_date.isoformat() if proc.start_date else None
        end_date = proc.end_date.isoformat() if proc.end_date else None

        # Get experimenter
        experimenter = getattr(proc, "experimenter_full_name", "Unknown")

        # Get protocol ID
        protocol_id = getattr(proc, "protocol_id", None)

        # Convert reagents to metadata service format
        reagents = convert_reagents_to_metadata_service_format(
            proc.procedure_details
        )

        # Create the specimen procedure in metadata service format
        specimen_proc = {
            "procedure_type": procedure_type,
            "procedure_name": procedure_name,
            "specimen_id": subject_id,
            "start_date": start_date,
            "end_date": end_date,
            "experimenter_full_name": experimenter,
            "protocol_id": protocol_id,
            "reagents": reagents,
            "hcr_series": None,
            "antibodies": None,
            "sectioning": None,
            "notes": None,
        }

        return specimen_proc

    except Exception as e:
        print(
            f"Error converting procedure {getattr(proc, 'procedure_name', 'Unknown')}: {e}"
        )
        return None


def consolidate_delipidation_procedures(
    delipidation_procedures: List[Dict[str, Any]], subject_id: str
) -> Dict[str, Any]:
    """
    Consolidate multiple Delipidation procedures into one, combining all reagents.

    Args:
        delipidation_procedures: List of Delipidation procedure dictionaries
        subject_id: The subject ID

    Returns:
        Single consolidated Delipidation procedure dictionary
    """
    if not delipidation_procedures:
        return {}

    # Use the first procedure as the base
    base_proc = delipidation_procedures[0]

    # Collect all reagents from all procedures
    all_reagents = []
    for proc in delipidation_procedures:
        if proc.get("reagents"):
            all_reagents.extend(proc["reagents"])

    # Find the earliest start date and latest end date
    start_dates = [
        proc.get("start_date")
        for proc in delipidation_procedures
        if proc.get("start_date")
    ]
    end_dates = [
        proc.get("end_date")
        for proc in delipidation_procedures
        if proc.get("end_date")
    ]

    earliest_start = min(start_dates) if start_dates else None
    latest_end = max(end_dates) if end_dates else None

    # Create consolidated procedure
    consolidated = {
        "procedure_type": "Delipidation",
        "procedure_name": "LifeCanvas Active Whole Mouse Brain Delipidation (UNPUBLISHED)",
        "specimen_id": subject_id,
        "start_date": earliest_start,
        "end_date": latest_end,
        "experimenter_full_name": "HollyM",  # Hardcode for now - should come from spreadsheet
        "protocol_id": "https://www.protocols.io/view/whole-mouse-brain-delipidation-lifecanvas-active-cttawnie",
        "reagents": all_reagents,
        "hcr_series": None,
        "antibodies": None,
        "sectioning": None,
        "notes": None,
    }

    return consolidated


def map_procedure_type_and_name(proc_type: str, proc_name: str) -> tuple:
    """
    Map Excel procedure type and name to metadata service format.

    Args:
        proc_type: Procedure type from Excel
        proc_name: Procedure name from Excel

    Returns:
        Tuple of (procedure_type, procedure_name) in metadata service format
    """
    # Map based on the metadata service example for subject 791054
    if proc_type == "Fixation":
        if "SHIELD OFF" in proc_name:
            return (
                "Delipidation",
                "LifeCanvas Active Whole Mouse Brain Delipidation (UNPUBLISHED)",
            )
        elif "SHIELD ON" in proc_name:
            return (
                "Delipidation",
                "LifeCanvas Active Whole Mouse Brain Delipidation (UNPUBLISHED)",
            )

    elif proc_type == "Delipidation":
        if "Passive" in proc_name:
            return (
                "Delipidation",
                "LifeCanvas Active Whole Mouse Brain Delipidation (UNPUBLISHED)",
            )
        elif "Active" in proc_name:
            return (
                "Delipidation",
                "LifeCanvas Active Whole Mouse Brain Delipidation (UNPUBLISHED)",
            )

    elif proc_type == "Refractive index matching":
        if "EasyIndex" in proc_name:
            return (
                "Refractive index matching",
                "Refractive Index Matching - EasyIndex",
            )

    # Default mapping
    return proc_type, proc_name


def convert_reagents_to_metadata_service_format(
    procedure_details: List[Any],
) -> List[Dict[str, Any]]:
    """
    Convert reagents from Excel format to metadata service format.

    Args:
        procedure_details: List of reagent objects from Excel

    Returns:
        List of reagent dictionaries in metadata service format
    """
    reagents = []

    for detail in procedure_details:
        try:
            # Extract name and lot number
            name = getattr(detail, "name", None)
            lot_number = getattr(detail, "lot_number", None)

            if name and lot_number:
                # Map reagent names to metadata service format
                mapped_name = map_reagent_name_to_metadata_service(name)

                reagent = {
                    "name": mapped_name,
                    "source": None,
                    "rrid": None,
                    "lot_number": str(lot_number),
                    "expiration_date": None,
                }
                reagents.append(reagent)

        except Exception as e:
            print(f"Error converting reagent {detail}: {e}")
            continue

    return reagents


def map_reagent_name_to_metadata_service(excel_name: str) -> str:
    """
    Map Excel reagent names to metadata service reagent names.

    Args:
        excel_name: Reagent name from Excel

    Returns:
        Reagent name in metadata service format
    """
    # Mapping based on the metadata service example for subject 791054
    name_mapping = {
        "SHIELD Buffer": "DB-500",
        "SHIELD Epoxy": "SH-ON",
        "SHIELD On": "SH-ON",
        "Delipidation Buffer": "DB-500",
        "Conduction Buffer": "CB-450",
        "Conductivity Buffer": "CB-450",
        "Easy Index": "EI-500-1.52",
        "EasyIndex": "EI-500-1.52",
    }

    return name_mapping.get(excel_name, excel_name)


def backfill_specimen_procedures_for_subject(
    subject_id: str, current_procedures: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Backfill specimen procedures for a subject, preserving existing data structure.

    Args:
        subject_id: The subject ID
        current_procedures: Current procedures data from database

    Returns:
        Updated procedures data with specimen_procedures field populated
    """
    # Generate new specimen procedures from spreadsheet
    new_specimen_procedures = get_specimen_procedures_from_spreadsheet(
        subject_id
    )

    # Create a copy of current procedures
    updated_procedures = current_procedures.copy()

    # Update or add specimen_procedures field
    updated_procedures["specimen_procedures"] = new_specimen_procedures

    return updated_procedures


def check_if_subject_needs_backfill(
    subject_id: str, current_procedures: Dict[str, Any]
) -> bool:
    """
    Check if a subject needs specimen procedures backfilled.

    Args:
        subject_id: The subject ID
        current_procedures: Current procedures data from database

    Returns:
        True if backfill is needed, False otherwise
    """
    # Check if specimen_procedures field exists and has content
    specimen_procedures = current_procedures.get("specimen_procedures", [])

    if not specimen_procedures:
        return True

    # Check if it's in the correct format (has standardized reagent names)
    for proc in specimen_procedures:
        reagents = proc.get("reagents", [])
        for reagent in reagents:
            name = reagent.get("name", "")
            # Check if it's using the new standardized format
            if any(
                standard_name in name
                for standard_name in [
                    "DB-500",
                    "SH-ON",
                    "CB-450",
                    "EI-500-1.52",
                ]
            ):
                return False  # Already in correct format

    return True  # Needs backfill


def test_specimen_procedures_match(subject_id: str) -> Dict[str, Any]:
    """
    Test function to compare specimen procedures from our backfill module
    with what's actually in the metadata service for a given subject.

    Args:
        subject_id: The subject ID to test

    Returns:
        Dictionary with comparison results
    """
    print(f"Testing specimen procedures match for subject {subject_id}")
    print("=" * 80)

    # Get specimen procedures from our backfill module
    try:
        spreadsheet_procedures = get_specimen_procedures_from_spreadsheet(
            subject_id
        )
        print(
            f"✓ Successfully generated procedures from spreadsheet for {subject_id}"
        )
    except Exception as e:
        print(f"✗ Failed to generate procedures from spreadsheet: {e}")
        return {"error": str(e)}

        # Get specimen procedures from the metadata service (with caching)
    try:
        # Check if we have cached data
        cache_dir = f"procedures/{subject_id}"
        cache_file = f"{cache_dir}/procedures.json.v1"

        if os.path.exists(cache_file):
            print(f"✓ Using cached data from {cache_file}")
            with open(cache_file, "r") as f:
                cached_data = json.load(f)
            db_procedures = cached_data.get("specimen_procedures", [])
            asset_name = "cached_data"
        else:
            print(f"Querying metadata service for subject {subject_id}...")
            print(f"  This may take 30-90 seconds...")

            # Create cache directory if it doesn't exist
            os.makedirs(cache_dir, exist_ok=True)

            # Query metadata service
            url = f"http://aind-metadata-service/procedures/{subject_id}"
            print(f"  Sending request to: {url}")
            response = requests.get(url, timeout=90)
            print(f"  Response received: HTTP {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                db_procedures = data.get("specimen_procedures", [])

                # Cache the result
                with open(cache_file, "w") as f:
                    json.dump(data, f, indent=2, default=str)
                print(f"✓ Cached result to {cache_file}")

            elif response.status_code == 406:
                # Handle validation errors - extract data from response
                data = response.json()
                if "data" in data:
                    db_procedures = data["data"].get("specimen_procedures", [])
                    # Cache the extracted data
                    with open(cache_file, "w") as f:
                        json.dump(data["data"], f, indent=2, default=str)
                    print(f"✓ Cached result from 406 response to {cache_file}")
                else:
                    db_procedures = []
                    print(f"⚠️  Got 406 but no data field found")

            else:
                print(f"✗ HTTP {response.status_code}: {response.text}")
                return {"error": f"HTTP {response.status_code}"}

            asset_name = f"metadata_service_response"

        if not db_procedures:
            print(
                f"✗ No specimen procedures found in metadata service for subject {subject_id}"
            )
            return {"error": "No specimen procedures in metadata service"}

        print(
            f"✓ Found specimen procedures in metadata service for asset: {asset_name}"
        )

    except Exception as e:
        print(f"✗ Failed to query metadata service: {e}")
        return {"error": str(e)}

    # Compare the two sets of procedures
    print(f"\nComparing procedures:")
    print(f"  Spreadsheet count: {len(spreadsheet_procedures)}")
    print(f"  Metadata service count: {len(db_procedures)}")

    # Convert to comparable format (sort by start_date and procedure_type)
    def normalize_procedures(procedures):
        """Normalize procedures for comparison by sorting and removing None values"""
        normalized = []
        for proc in procedures:
            # Create a copy and clean up None values
            clean_proc = {}
            for key, value in proc.items():
                if value is not None:
                    clean_proc[key] = value
            normalized.append(clean_proc)

        # Sort by start_date, then procedure_type
        normalized.sort(
            key=lambda x: (
                x.get("start_date", ""),
                x.get("procedure_type", ""),
            )
        )
        return normalized

    spreadsheet_normalized = normalize_procedures(spreadsheet_procedures)
    db_normalized = normalize_procedures(db_procedures)

    # Check if they match exactly
    exact_match = spreadsheet_normalized == db_normalized

    print(f"  Exact match: {'✓ YES' if exact_match else '✗ NO'}")

    if not exact_match:
        print(f"\nDetailed comparison:")

        # Find differences
        for i, (spreadsheet_proc, db_proc) in enumerate(
            zip(spreadsheet_normalized, db_normalized)
        ):
            if spreadsheet_proc != db_proc:
                print(f"  Procedure {i+1} differs:")
                print(f"    Spreadsheet: {spreadsheet_proc}")
                print(f"    Metadata service: {db_proc}")
                print()

        # Check if counts differ
        if len(spreadsheet_normalized) != len(db_normalized):
            print(
                f"  Count mismatch: {len(spreadsheet_normalized)} vs {len(db_normalized)}"
            )

    result = {
        "subject_id": subject_id,
        "spreadsheet_count": len(spreadsheet_procedures),
        "metadata_service_count": len(db_procedures),
        "exact_match": exact_match,
        "spreadsheet_procedures": spreadsheet_procedures,
        "metadata_service_procedures": db_procedures,
    }

    print(f"\nTest completed for subject {subject_id}")
    print("=" * 80)

    return result
