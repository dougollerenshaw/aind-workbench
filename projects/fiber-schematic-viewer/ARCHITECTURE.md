# Fiber Schematic Viewer Architecture

## Overview

Simple Flask app that generates fiber implant schematics by querying the AIND Metadata Service and caching results locally.

## Data Flow

```
User Request → Cache Check → [Cache Hit? → Return Cached Data]
                           → [Cache Miss? → Query Metadata Service → Cache Result → Return]
```

## Components

### 1. Cache Layer (`get_cached_procedures`, `save_to_cache`)
- File-based cache at `.cache/procedures/`
- One JSON file per subject: `<subject_id>.json`
- Never expires (must manually delete to refresh)
- ~10KB per subject

### 2. Metadata Service Client (`get_procedures_for_subject`)
- Queries `http://aind-metadata-service` (internal service)
- Returns procedures data from source systems (surgical records, LabTracks, etc.)
- ~30-40 seconds per query
- Handles validation errors gracefully (some procedures have schema warnings but valid data)

### 3. Fiber Extractor (`extract_fiber_implants`)
- Parses procedures JSON to extract fiber implant coordinates
- Handles V2 schema format from metadata service
- Extracts: name, AP/ML/DV coordinates, angles, targeted structure

### 4. Schematic Generator (`create_schematic`)
- Matplotlib-based visualization
- Top-down view of mouse skull
- Bregma/Lambda reference points
- Color-coded fibers with legend

### 5. Flask Routes
- `/` - Main UI (serves index.html)
- `/generate` (POST) - Generate schematic for subject_id

## Dependencies

**Core:**
- `flask` - Web framework
- `aind-metadata-service-client` - AIND metadata API client

**Visualization:**
- `matplotlib` - Schematic generation
- `numpy` - Coordinate calculations

**Standard Library:**
- `json`, `time`, `pathlib` - Cache management
- `base64` - Image encoding

## Configuration

**Runtime Config** (`app.py --help`):
- `--host`, `--port`, `--debug` - Flask server settings
- `--cache-dir` - Cache directory location

**Visual Config** (`config.py`):
- Colors, sizes, fonts, dimensions
- All schematic visual parameters

## Performance

- **First query:** ~30-40s (metadata service)
- **Cached query:** < 0.1s (disk read)
- **Cache size:** ~10KB per subject
- **Cache persistence:** Indefinite (never expires)

## Why Metadata Service (Not DocDB)?

- **More comprehensive:** Has data from source systems before upload
- **Authoritative:** Direct from surgical records, LabTracks, etc.
- **Complete:** Example: Subject 775741 has 2 fibers in metadata service vs 1 in DocDB
- **Trade-off:** Slower query time (mitigated by caching)

## Code Stats

- **Total lines:** ~645
- **Functions:** 
  - 3 cache functions
  - 1 metadata query function
  - 1 schematic generator class
- **Routes:** 2 (index, generate)
