#!/usr/bin/env python3
"""Generate spreadsheet of assets with null project names."""

import argparse
from datetime import datetime

import pandas as pd
from aind_data_access_api.document_db import MetadataDbClient


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
    parser = argparse.ArgumentParser(description="Generate spreadsheet of assets with null project names")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of records")
    parser.add_argument("--output", type=str, default=None, help="Output CSV filename")
    args = parser.parse_args()

    if args.output is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output = f"null_project_names_{args.limit or 'all'}_{timestamp}.csv"

    client = MetadataDbClient(host="api.allenneuraldynamics.org", database="metadata_index", collection="data_assets")

    filter_query = {
        "$and": [
            {"$or": [{"data_description.project_name": None}, {"data_description": None}]},
            {"location": {"$not": {"$regex": "codeocean"}}},
        ]
    }

    projection = {
        "_id": 1,
        "name": 1,
        "location": 1,
        "created": 1,
        "data_description.modality": 1,
        "data_description.data_level": 1,
        "data_description.subject_id": 1,
        "data_description.project_name": 1,
        "data_description.investigators": 1,
        "session.experimenter_full_name": 1,
    }

    results = list(
        client.retrieve_docdb_records(filter_query=filter_query, projection=projection, limit=args.limit or 20000)
    )

    df = pd.DataFrame(results)

    # Extract nested fields
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

    # Format modality, investigators, and experimenter
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
