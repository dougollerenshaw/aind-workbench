# PatchSeq Metadata Project

This project contains a modular system for managing metadata for PatchSeq experiments, specifically for generating procedures.json files for SmartSPIM subjects. The system processes data from AIND metadata services and Excel spreadsheets to create comprehensive procedure metadata.

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

### Core System
- `create_procedures.py` - Main CLI script for generating procedures.json files
- `__init__.py` - Package initialization for modular imports

### Modular Components  
- `excel_loader.py` - Excel file loading and specimen procedures extraction
- `metadata_service.py` - AIND metadata service API interactions
- `schema_conversion.py` - V1 to V2 schema conversion and validation
- `file_io.py` - Safe file I/O operations for procedures.json files
- `csv_tracking.py` - CSV export and progress tracking functionality
- `subject_utils.py` - Subject ID validation and utility functions

### Data Files
- `patchseq_subject_ids.csv` - Subject IDs extracted from SmartSPIM filenames
- `DT_HM_TissueClearingTracking_.xlsx` - Excel spreadsheet with specimen procedure data
- `viral_material_tracking.csv` - Generated CSV with viral injection tracking
- `specimen_procedure_tracking.csv` - Generated CSV with specimen procedure tracking

### Documentation & Examples
- `example_usage.ipynb` - Comprehensive notebook showing both CLI and programmatic usage
- `extract_patchseq_subjects.py` - Utility script to extract subject IDs from filenames
- `requirements.txt` - Python package dependencies
- `procedures/` - Output directory containing generated procedures.json files

## Usage

### 1. Command Line Interface (Recommended)

The main CLI script works exactly as before, but now with enhanced functionality:

```bash
# Process all subjects
python create_procedures.py

# Process specific subjects
python create_procedures.py --subjects 699461 699462

# Skip existing v2.0 files (don't overwrite)
python create_procedures.py --skip-existing

# Limit processing to first N subjects  
python create_procedures.py --limit 5

# Use custom Excel file
python create_procedures.py --excel /path/to/custom_file.xlsx
```

### 2. Programmatic Usage

Import and use individual modules for custom workflows:

```python
from excel_loader import load_specimen_procedures_excel
from metadata_service import fetch_procedures_metadata
from schema_conversion import convert_procedures_to_v2
from file_io import save_procedures_json

# Load Excel data
excel_data = load_specimen_procedures_excel("DT_HM_TissueClearingTracking_.xlsx")

# Process a single subject
success, data, message = fetch_procedures_metadata("699461")
if success:
    v2_data, coords_info, batch_info = convert_procedures_to_v2(data, excel_data)
    save_procedures_json("699461", v2_data, is_v1=False)
```

### 3. Extract Subject IDs (if needed)

If you need to regenerate the subject IDs CSV from SmartSPIM filenames:

```bash
python extract_patchseq_subjects.py
```

## Key Features

### Enhanced Data Coverage
- **94% improvement** in specimen procedures coverage (from 18 missing to 1)
- Processes Excel data from "Additional batch info" sheet
- Comprehensive viral material and injection coordinate tracking

### Robust Processing
- **V1 caching** - Never overwrites data from metadata service
- **V2 regeneration** - Always creates fresh v2 schema files (unless --skip-existing)
- **Error handling** - Graceful handling of missing data and API failures
- **Progress tracking** - Detailed CSV exports for analysis

### Modular Architecture  
- **Independent modules** - Use components separately for custom workflows
- **Clean CLI** - Backward compatible command-line interface
- **Comprehensive examples** - Jupyter notebook with usage patterns

## Output

After running `create_procedures.py`, you'll have:

```
procedures/
├── 699461/
│   ├── procedures_v1.json    # Cached data from metadata service
│   └── procedures.json       # V2 schema with Excel integration
├── 699462/
│   ├── procedures_v1.json
│   └── procedures.json
└── ...
```

**Generated CSV Files:**
- `viral_material_tracking.csv` - Comprehensive viral injection data
- `specimen_procedure_tracking.csv` - Specimen processing procedures

**Processing Summary:**
- ✅ **Success rate**: 32/32 subjects processed
- 📋 **Injection materials**: 99 tracked
- 🧪 **Specimen procedures**: 31/32 subjects (major improvement!)

## Recent Improvements

### Version 2.0 (July 2024)
- **Modular architecture** - Clean separation of concerns
- **Enhanced Excel processing** - "Additional batch info" sheet integration  
- **Improved data coverage** - 94% reduction in missing specimen procedures
- **Better error handling** - Graceful handling of missing coordinates
- **Comprehensive tracking** - Detailed CSV exports for analysis
- **Backward compatibility** - CLI interface unchanged

## Notes for AI Agents

When working with this project:
1. Always activate the `patchseq_metadata` conda environment first
2. Use the modular components for custom workflows
3. The CLI interface (`python create_procedures.py`) remains unchanged for backward compatibility
4. V1 files are cached and never overwritten; V2 files are regenerated unless `--skip-existing` is used
5. Excel data integration happens during V1→V2 conversion
6. Handle both 200 and 406 HTTP responses from the AIND metadata service
7. Check `example_usage.ipynb` for comprehensive usage examples
