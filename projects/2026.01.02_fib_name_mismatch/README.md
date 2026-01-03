# FIB Modality Mismatch Search

## Overview

This script identifies processed/derived data assets that incorrectly have FIB (fiber photometry) modality listed, even though the corresponding raw data asset does not have FIB modality.

## Problem Description

During data processing, some derived/processed records were incorrectly assigned FIB modality even though:
- The corresponding raw session does not have FIB in its modality list
- This appears to be an error introduced during the processing pipeline

Since `data_description.data_level` is unreliable in many cases, this script identifies processed records by looking for "processed" in the session name rather than relying on the data level field.

## What the Script Does

1. Finds all processed sessions (identified by "processed" in the name) that have FIB modality
2. Extracts the corresponding raw session name from each processed session name
3. Checks whether the raw session has FIB modality
4. Flags all cases where processed has FIB but raw does not
5. Outputs results to both console and `fib_modality_issues.txt`

## Usage

### Setup

Install dependencies using UV:

```bash
uv sync
```

### Run

```bash
uv run python fib_mismatch_search.py
```

The script will:
- Query the metadata database for processed sessions with FIB
- Check each corresponding raw session
- Print results to console
- Save results to `fib_modality_issues.txt`

## Output

The output file contains:
- Subject ID
- Raw session name
- Number of problematic processed records
- List of all processed record names that need to be fixed

This information can be used to run a data migration script to remove FIB modality from the incorrectly flagged processed records.

