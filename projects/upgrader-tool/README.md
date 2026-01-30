# AIND Metadata Upgrader Tool

A Flask web application for testing whether AIND metadata assets can successfully upgrade from schema v1 to v2, with detailed field-by-field breakdowns for partial failures.

## Overview

This tool provides both a command-line interface and web UI for testing metadata upgrades. The key innovation is its **two-step upgrade approach** that can identify which specific metadata fields succeed or fail when a full asset upgrade fails.

## Core Upgrade Logic

### Two-Step Approach

The upgrade process (`upgrade.py::upgrade_asset_by_field`) works as follows:

1. **Step 1: Try Full Asset Upgrade**
   - Attempt to upgrade the entire asset with all metadata files
   - If successful, show all upgraded fields and exit
   
2. **Step 2: Individual Field Testing** (only if Step 1 fails)
   - Test each metadata field individually using `skip_metadata_validation=True`
   - Create minimal test dict: `{_id, name, created, field_to_test, subject}`
   - This allows fields to upgrade independently without full dependency validation
   - Clearly identify which fields succeed and which fail with their specific errors

### Key Insight: `skip_metadata_validation=True`

The critical parameter that makes field-by-field testing work is `skip_metadata_validation=True` when instantiating the `Upgrade` class. This:
- Bypasses full metadata structure validation
- Allows testing individual fields without all required dependencies
- Enables accurate identification of which specific fields have validation errors

Without this parameter, the upgrader requires all core files to be present and valid, making it impossible to isolate field-specific failures.

### Field Name Conversions

The tool automatically handles v1 to v2 field name changes:
- `session` → `acquisition`
- `rig` → `instrument`

These conversions are tracked in results with a `converted_to` field.

## Module Structure

### `upgrade.py`

Core upgrade logic module with the following functions:

- **`get_mongodb_client()`**: Returns MongoDB client for metadata index
- **`upgrade_asset_by_field(asset_identifier: str) -> dict`**: Main function that implements the two-step upgrade approach
  - Returns dict with:
    - `success`: Overall upgrade success (bool)
    - `partial_success`: Some fields succeeded, some failed (bool)
    - `field_results`: Dict of per-field results with original/upgraded data or errors
    - `successful_fields`: List of field names that upgraded
    - `failed_fields`: List of field names that failed
    - `overall_error` and `overall_traceback`: Full asset error info if applicable
- **`upgrade_asset(asset_identifier: str) -> dict`**: Simple full-asset upgrade without field breakdown
  - Used for basic upgrade testing
  - Returns dict with success status, original_data, and upgraded_data or error

### `upgrader_app.py`

Flask web application that provides the UI:

- **Backend Routes:**
  - `/`: Main page with search form
  - `/check`: API endpoint that calls `upgrade_asset_by_field()` and returns JSON results
  
- **Frontend Features:**
  - Collapsible tree view for JSON comparison (using `<details>` HTML elements)
  - Side-by-side display of original (v1) vs upgraded (v2) for each field
  - Success/failure indicators: `[SUCCESS]`, `[FAILED]` labels
  - Field conversion display: `session → acquisition`
  - Error messages and tracebacks for failed fields
  - Shareable URLs: Asset ID is automatically added to URL for easy sharing
  - Real-time URL updates when checking assets
  - "Copy Shareable URL" button that copies current browser URL
  
- **UI Behavior:**
  - "Check Upgrade" button is disabled until asset ID is entered
  - "Copy Shareable URL" button is disabled until a valid asset is found
  - Full asset comparison section is expanded by default
  - Fields not present in original asset are skipped entirely (not displayed)

## Web UI Features

### Collapsible JSON Comparison

- Each metadata field has a collapsible section
- Shows original v1 data and upgraded v2 data side-by-side
- Color-coded status indicators
- Full error messages and tracebacks for failures

### Shareable Links

- URL automatically updates with asset ID when checking an asset
- Can share direct link: `http://localhost:5001/?asset_id=<uuid>`
- Copy button for easy URL sharing
- URL persists in browser address bar for direct copying

## Testing

### Pytest Test Suite

Run the comprehensive test suite:

```bash
uv run pytest test_upgrade.py -v
```

The test suite (`test_upgrade.py`) validates:
- **`test_successful_asset`**: Full asset upgrade success
- **`test_partially_failing_asset`**: Partial upgrades (some fields succeed, some fail)
- **`test_field_results_structure`**: Correct result structure with original/upgraded/error fields
- **`test_field_conversion`**: Field name conversions are tracked correctly
- **`test_skip_missing_fields`**: Fields not in original asset are skipped

### Test Assets

- **Successful**: `single-plane-ophys_705363_2024-01-10_15-46-42`
- **Partial failure**: `behavior_746346_2025-03-12_17-21-50` 
  - `data_description`, `subject`, `rig`, `processing` succeed
  - `procedures`, `session` fail with validation errors

## Usage

### Command Line

```bash
# Test a specific asset with field breakdown
cd projects/upgrader-tool
uv run python -c "from upgrade import upgrade_asset_by_field; import json; result = upgrade_asset_by_field('behavior_746346_2025-03-12_17-21-50'); print(json.dumps(result, indent=2, default=str))"

# Or use the simple CLI
uv run python upgrade.py --name behavior_775743_2025-03-21_08-54-07

# By ID
uv run python upgrade.py --id <uuid>

# JSON output
uv run python upgrade.py --name <asset> --json
```

### Standalone Web App

```bash
cd projects/upgrader-tool
uv run python upgrader_app.py --port 5001
```

Then visit http://localhost:5001

### Via Tool Launcher

The app is integrated into the AIND tool launcher:

```bash
cd ../tool-launcher
uv run python launcher.py
```

Then visit http://localhost:8080/upgrader

## Dependencies

The app requires:
- `aind-data-access-api`: MongoDB DocDB client for fetching assets
- `aind-metadata-upgrader`: Core upgrade logic with schema v1→v2 mappers
- `flask`: Web framework
- `pytest`: Testing framework

Dependencies are managed via `pyproject.toml` and `uv`.

## Integration Notes for Other Applications

To integrate this functionality into another application:

1. **Import the upgrade logic:**
   ```python
   from upgrade import upgrade_asset_by_field
   ```

2. **Call for any asset:**
   ```python
   result = upgrade_asset_by_field("asset_name_or_id")
   ```

3. **Parse the results:**
   - Check `result["success"]` for overall status
   - Check `result["partial_success"]` to see if some fields worked
   - Iterate `result["field_results"]` for per-field details
   - Each field has `success` (bool), `original` (dict), `upgraded` (dict), and `error` (str) as applicable

4. **Display field-by-field comparison:**
   - Use the `upgrader_app.py::displayResults()` JavaScript function as a reference
   - Shows collapsible tree view with side-by-side JSON comparison
   - Handles field conversions and error display

5. **Key implementation details:**
   - Always use `copy.deepcopy()` of original asset data before any upgrade attempts
   - This ensures the "original" display shows raw v1 data, not modified Pydantic models
   - Use `json.loads(json.dumps(data, default=str))` for JSON serialization of Pydantic models

