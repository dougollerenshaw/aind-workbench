#!/usr/bin/env python3
"""Generate spreadsheet of assets with incorrect (non-null) project names."""

import argparse
from datetime import datetime

import pandas as pd
from aind_data_access_api.document_db import MetadataDbClient

# Projects WITHOUT subprojects - these standalone names are valid
PROJECTS_WITHOUT_SUBPROJECTS = [
    "AIND Viral Genetic Tools",
    "AIBS WB AAV Toolbox",
    "Behavior and Motor Control",
    "Behavior Platform",
    "BG AAV Toolbox",
    "Brain Computer Interface",
    "BRAIN CONNECTS HIVE",
    "BRAIN CONNECTS TransNeuronal Tools",
    "Cell Type LUT",
    "Cognitive flexibility in patch foraging",
    "Costa Greene Adrenal",
    "CTY Genetic Tools",
    "Delphi",
    "DELTA",
    "Discovery-Brain Wide Circuit Dynamics",
    "Dynamic Routing",
    "Ephys Platform",
    "Force Foraging",
    "Genetic Perturbation Platform",
    "High and Low Control",
    "Information seeking in partially observable environments",
    "Kleinfeld U19",
    "Learning mFISH-V1omFISH",
    "Medulla",
    "MRI-Guided Electrophysiology",
    "MSMA Platform",
    "NBA Behavior and Motor Control",
    "Neurobiology of Action",
    "NP Ultra",
    "NP Ultra and Psychedelics",
    "OpenScope",
    "Ophys Platform - FIP, HSFP and indicator testing",
    "Ophys Platform - SLAP2",
    "PLACE",
    "Single-neuron computations within brain-wide circuits (SCBC)",
]

# Projects WITH subprojects - only the full "Project - Subproject" format is valid
PROJECTS_WITH_SUBPROJECTS = [
    "Discovery-Neuromodulator circuit dynamics during foraging - Subproject 1 Electrophysiological Recordings from NM Neurons During Behavior",
    "Discovery-Neuromodulator circuit dynamics during foraging - Subproject 2 Molecular Anatomy Cell Types",
    "Discovery-Neuromodulator circuit dynamics during foraging - Subproject 3 Fiber Photometry Recordings of NM Release During Behavior",
    "Neurobiology of Action - ASAP Motor Circuit Dysfunction in PD",
    "Thalamus in the middle - Project 1 Mesoscale thalamic circuits",
    "Thalamus in the middle - Project 2 Cell-type specific thalamocortical projectome",
    "Thalamus in the middle - Project 4 Frontal cortical dynamics and cognitive behaviors",
    "Thalamus in the middle - Project 5 Models of computation",
    "Thalamus in the middle - Project 6 Molecular Science Core",
    "XPG Core Imaging - Methods Development",
]

# Combined list of all valid project names
EXPECTED_PROJECT_NAMES = PROJECTS_WITHOUT_SUBPROJECTS + PROJECTS_WITH_SUBPROJECTS


def format_modality(modality):
    """Extract modality abbreviations."""
    if not modality:
        return ""
    if isinstance(modality, str):
        return modality
    if isinstance(modality, list):
        abbrevs = [m.get("abbreviation", "") for m in modality if isinstance(m, dict)]
        return ", ".join(filter(None, abbrevs))
    return ""


def format_investigators(investigators):
    """Extract investigator names."""
    if not investigators:
        return ""
    if isinstance(investigators, list):
        names = [inv.get("name", "") for inv in investigators if isinstance(inv, dict)]
        return ", ".join(filter(None, names))
    return ""


def main():
    parser = argparse.ArgumentParser(description="Generate spreadsheet of assets with incorrect project names")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of records")
    parser.add_argument("--output", type=str, default=None, help="Output CSV filename")
    args = parser.parse_args()

    if args.output is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output = f"incorrect_project_names_{args.limit or 'all'}_{timestamp}.csv"

    client = MetadataDbClient(host="api.allenneuraldynamics.org", database="metadata_index", collection="data_assets")

    filter_query = {
        "$and": [
            {"data_description.project_name": {"$nin": [None, *EXPECTED_PROJECT_NAMES]}},
            {"location": {"$not": {"$regex": "codeocean"}}},
        ]
    }

    projection = {
        "_id": 1,
        "name": 1,
        "location": 1,
        "created": 1,
        "data_description": 1,
        "session": 1,
    }

    results = list(
        client.retrieve_docdb_records(filter_query=filter_query, projection=projection, limit=args.limit or 20000)
    )

    df = pd.DataFrame(results)

    df["modality"] = df["data_description"].apply(lambda x: x.get("modality") if isinstance(x, dict) else None)
    df["investigators"] = df["data_description"].apply(
        lambda x: x.get("investigators") if isinstance(x, dict) else None
    )
    df["experimenter_full_name"] = df["session"].apply(
        lambda x: x.get("experimenter_full_name") if isinstance(x, dict) else None
    )
    df["subject_id"] = df["data_description"].apply(lambda x: x.get("subject_id") if isinstance(x, dict) else None)
    df["data_level"] = df["data_description"].apply(lambda x: x.get("data_level") if isinstance(x, dict) else None)
    df["project_name"] = df["data_description"].apply(lambda x: x.get("project_name") if isinstance(x, dict) else None)

    df["modality"] = df["modality"].apply(format_modality)
    df["investigators"] = df["investigators"].apply(format_investigators)
    df["experimenter_full_name"] = df["experimenter_full_name"].apply(
        lambda x: ", ".join(x) if isinstance(x, list) else ""
    )

    columns = [
        "_id",
        "name",
        "created",
        "location",
        "project_name",
        "modality",
        "investigators",
        "experimenter_full_name",
        "subject_id",
        "data_level",
    ]
    df = df[columns]
    df = df.sort_values("created", ascending=False)

    df.to_csv(args.output, index=False)
    print(f"Wrote {len(df)} records to {args.output}")


if __name__ == "__main__":
    main()
