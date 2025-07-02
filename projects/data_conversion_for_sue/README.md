# Sue's Behavioral Neuroscience Data Conversion

This project contains scripts for converting and organizing behavioral neuroscience data for Sue Su's project.

## Metadata Management

The metadata workflow consists of two main scripts plus a convenient wrapper:

### 1. `get_procedures_and_subject_metadata.py`

Fetches subject and procedures metadata from the AIND metadata service for each unique subject in the asset inventory. Saves metadata to both:
- Subject-specific folders (legacy format): `metadata/<subject_id>/`
- Experiment-specific folders (new format): `metadata/<subject_id>_<date>_<time>/`

```bash
python get_procedures_and_subject_metadata.py [--output-dir DIR] [--force-overwrite]
```

### 2. `make_data_descriptions.py`

Creates AIND data schema 2.0 compliant `data_description.json` files for each experimental session, containing administrative information about the data asset.

```bash
python make_data_descriptions.py [--output-dir DIR] [--force-overwrite]
```

### 3. `generate_all_metadata.py` (Wrapper Script)

Runs both scripts in sequence for a complete metadata update:

```bash
python generate_all_metadata.py [--output-dir DIR] [--force-overwrite]
```

## Directory Structure

Each experiment will have its own folder in the `metadata/` directory, with a consistent naming convention:

```
metadata/
└── subject_YYYY-MM-DD_HH-MM-SS/
    ├── subject.json
    ├── procedures.json
    └── data_description.json
```

## Requirements

- Python 3.8+
- pandas
- numpy
- requests
- pyyaml
- aind_data_schema (for data description schema)

## Source of Truth

The `asset_inventory.csv` file serves as the source of truth for which experiments exist and is used to drive the naming of experiment folders.

## Configuration

The `config.yaml` file contains mappings for subject IDs and ORCID identifiers.

## Utilities

Shared functionality is factored into the `metadata_utils.py` module.
