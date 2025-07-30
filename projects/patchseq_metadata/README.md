# PatchSeq Metadata Project

This project contains scripts and tools for managing metadata for PatchSeq experiments, specifically for generating procedures.json files for SmartSPIM subjects.

## Environment Setup

This project uses a dedicated Anaconda environment called `patchseq_metadata`. 

**Before running any scripts, activate the environment:**

```bash
conda activate patchseq_metadata
```

If the environment doesn't exist yet, create it:

```bash
conda create -n patchseq_metadata python=3.12
conda activate patchseq_metadata
pip install -r requirements.txt
```

## Project Structure

- `patchseq_subject_ids.csv` - CSV file containing subject IDs extracted from SmartSPIM filenames
- `create_procedures.py` - Main script to fetch procedures metadata and create procedures.json files
- `extract_patchseq_subjects.py` - Script to extract subject IDs from SmartSPIM filenames
- `requirements.txt` - Python package dependencies

## Usage

### 1. Extract Subject IDs (if needed)

If you need to regenerate the subject IDs CSV from SmartSPIM filenames:

```bash
python extract_patchseq_subjects.py
```

This creates `patchseq_subject_ids.csv` with all subject IDs.

### 2. Create Procedures JSON Files

To fetch procedures metadata and create procedures.json files for all subjects:

```bash
python create_procedures.py
```

This script will:
- Read subject IDs from `patchseq_subject_ids.csv`
- Fetch procedures metadata from the AIND metadata service for each subject
- Create a folder for each subject containing `procedures.json`
- Provide a summary of successful and failed requests

## Output

After running `create_procedures.py`, you'll have:
```
692912/
  procedures.json
716946/
  procedures.json
716947/
  procedures.json
...
```

## Notes for AI Agents

When working with this project:
1. Always activate the `patchseq_metadata` conda environment first
2. Update `requirements.txt` whenever adding new package dependencies
3. Keep scripts simple and compact with clear function separation
4. Follow the pattern of: read CSV → process subjects → fetch metadata → save JSON files
5. Handle both 200 and 406 HTTP responses from the AIND metadata service
