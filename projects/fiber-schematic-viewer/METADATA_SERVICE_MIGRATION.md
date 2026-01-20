# Metadata Service Migration

## Summary

Successfully migrated the Fiber Schematic Viewer from using DocDB (aind-data-access-api) to using the AIND Metadata Service (aind-metadata-service-client).

## Why?

- **More comprehensive**: Metadata service pulls from source systems (surgical records, LabTracks, etc.) before data upload
- **DocDB limitation**: Only has data AFTER experiments are uploaded
- **Result**: Subject 775741 now shows 2 fibers (was only showing 1 from DocDB)

## Changes Made

### 1. Updated Dependencies

**fiber-schematic-viewer/pyproject.toml:**
- Removed: `aind-data-access-api`
- Added: `aind-metadata-service-client`

**tool-launcher/pyproject.toml:**
- Added: `aind-metadata-service-client` (keeps aind-data-access-api for query_tool)

### 2. Simplified Function

**app.py - get_procedures_for_subject():**
- **Before**: 3-stage fallback (DocDB V1 → DocDB V2 → metadata service stub)
- **After**: Single call to metadata service

Key implementation details:
- Uses internal host: `http://aind-metadata-service`
- Handles validation errors gracefully (400 with valid data in response body)
- Query time: ~30-40 seconds per subject

### 3. Test Results

**Subject 804434:**
- Metadata Service: 2 fibers ✓
- DocDB V2: 2 fibers ✓
- **Result: MATCH**

**Subject 775741:**
- Metadata Service: 2 fibers ✓
- DocDB V2: 1 fiber (missing Fiber_0)
- **Result: Metadata service is more complete**

Fibers found for 775741:
- Fiber_1: AP=-3.05, ML=-0.60, DV=0.00, Target=Ventral tegmental area
- Fiber_0: AP=1.00, ML=-1.50, DV=0.00, Target=Nucleus accumbens

## Trade-offs

**Pros:**
- More comprehensive data from source systems
- Simpler codebase (one query instead of three)
- No need to wait for data upload

**Cons:**
- Slower (~30-40s vs ~1-2s for DocDB)
- Some subjects may have schema validation warnings (handled gracefully)

## Next Steps

None required. The migration is complete and tested.
