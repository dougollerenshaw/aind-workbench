# Fiber Photometry Metadata Upgrader Issue - Executive Report

**Date:** January 27, 2026  
**Investigated Asset:** `733a1052-683c-46d2-96ca-8f89bd270192`  
**Issue:** Asset fails to upgrade from session v1.x to v2.x  

---

## Problem

175 fiber photometry assets cannot upgrade their metadata to the latest schema version. The upgrade fails with:

> Missing one of required devices ['PatchCordConfig', 'FiberAssemblyConfig'] for modality Fiber photometry

## Root Cause

A tool/pipeline that creates fiber photometry metadata with exactly **4 fiber connections** does not populate the required `channel` field within each fiber connection. This missing data prevents the upgrader from creating the required device configurations in the new schema.

## Scope

**Sample Size:** 1,000 assets with v1 session schemas  
**Assets with fiber connections:** 193  
**Assets affected by this bug:** 175 (91%)

### Critical Pattern Discovered

| # Fiber Connections | Total Assets | Affected | % Affected |
|---------------------|--------------|----------|------------|
| **4**               | **175**      | **175**  | **100%**   |
| 7+                  | 18           | 0        | 0%         |

**All assets with exactly 4 fiber connections have this issue.**  
**All assets with 7+ fiber connections work correctly.**

## Timeline

- **First affected asset:** November 21, 2024
- **Latest affected asset:** January 21, 2026
- **Status:** Issue is ongoing

## Impact

### Immediate
- 175 assets cannot be upgraded to the latest metadata schema
- These assets may be incompatible with new tools that require v2 schema
- Potential data processing pipeline failures

### Long-term
- If unaddressed, more assets will be created with this defect
- Growing technical debt in metadata quality
- Possible data loss if assets need to be re-ingested

## Recommendations

### 1. Identify the Tool (High Priority)
- Find which tool/pipeline creates metadata with exactly 4 fiber connections
- This is likely a specific behavioral fiber photometry setup/rig
- Search for assets with pattern: `behavior_*` + 4 fiber connections

### 2. Fix the Tool (High Priority)
- Update the tool to populate the `channel` field in fiber connections
- The channel must include:
  - `channel_name`
  - `detector_name` 
  - `light_source_name`
  - Other required channel properties
- Add validation to prevent incomplete metadata at creation time

### 3. Update the Upgrader (Medium Priority)
Modify the upgrader to handle missing channel data:
- Create default channels based on available detectors and light sources
- Make educated guesses about device pairings
- Log warnings about assumptions made
- Allow upgrade to proceed with best-effort conversion

### 4. Backfill Existing Assets (Low Priority)
If the correct channel mappings can be determined:
- Update the 175 affected assets in DocDB
- Add the missing channel information
- Re-run upgrades

## Next Steps

1. **Immediate:** Identify the tool that creates 4-fiber metadata
2. **This Week:** Fix the tool to prevent new broken assets
3. **This Month:** Decide on strategy for existing 175 assets (fix upgrader vs. backfill data)
4. **Ongoing:** Monitor for similar metadata quality issues

## Tools Provided

A diagnostic toolkit has been created in `/projects/2026.01.27_explore_upgrader/`:

- `check_asset.py` - Quick check if an asset will fail to upgrade
- `find_affected_assets.py` - Scan DocDB for all affected assets
- `analyze_patterns.py` - Analyze patterns in affected assets
- `affected_assets.csv` - List of all 175 affected assets

## Questions?

See `README.md`, `FINDINGS.md`, and `SUMMARY.md` for detailed technical analysis.

---

**Prepared by:** AI Assistant (Claude)  
**Investigation Date:** January 27, 2026  
**Contact:** Doug Ollerenshaw
