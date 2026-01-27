# Critical Finding: Fiber Photometry Upgrader Issue

## Executive Summary

Asset `733a1052-683c-46d2-96ca-8f89bd270192` cannot upgrade due to missing fiber connection channel data. This is **NOT an isolated issue** - it affects ~91% of fiber photometry assets with v1 session schemas.

## The Smoking Gun

**100% correlation between 4 fiber connections and missing channel data:**

| # Fiber Connections | Total Assets | Missing Channel Data | % Missing |
|---------------------|--------------|----------------------|-----------|
| **4**               | **175**      | **175**              | **100%**  |
| 7                   | 15           | 0                    | 0%        |
| 12                  | 2            | 0                    | 0%        |
| 17                  | 1            | 0                    | 0%        |

## Implications

There is clearly a **specific tool or pipeline** that:
1. Creates fiber photometry metadata with exactly 4 fiber connections
2. Does NOT populate the required `channel` field in fiber connections
3. Has been producing broken metadata from November 2024 through January 2026

## Timeline

- **First occurrence:** November 21, 2024
- **Latest occurrence:** January 21, 2026
- **Still active:** Yes, the issue is ongoing

## Affected Versions

- Session v1.0.1: 125 assets affected
- Session v1.1.2: 50 assets affected

## Why the Upgrade Fails

The upgrader (v1v2.py) expects:

```python
fiber_connection = {
    "patch_cord_name": "...",
    "fiber_name": "...",
    "channel": {  # <-- MISSING
        "channel_name": "...",
        "detector_name": "...",
        "light_source_name": "..."
    }
}
```

Without the `channel` field, the upgrader cannot create `PatchCordConfig` objects. Since the stream has fiber photometry modality, the v2 schema validation fails.

## Root Cause Hypothesis

A tool/pipeline used for 4-fiber experiments:
- Likely a specific behavioral fiber photometry setup
- Creates sessions with 4 LEDs + 2 detectors + 4 fibers
- Was updated/created around November 2024
- Never properly implemented the channel mapping

In contrast, the 7+ fiber connection tool properly includes channel data.

## Recommended Immediate Actions

### 1. Identify the Tool
- Find which tool/pipeline creates metadata with exactly 4 fiber connections
- Check its code/configuration for fiber connection generation
- Look for the missing channel population logic

### 2. Fix the Tool
- Update the tool to properly populate channel data
- Add validation to prevent incomplete metadata
- Consider backfilling existing assets if possible

### 3. Update the Upgrader (Temporary Workaround)
If fixing 175 assets is not feasible, the upgrader could:
- Detect missing channel data
- Create default channels based on available detectors/light sources
- Log warnings about assumptions made
- Allow the upgrade to proceed with best-effort conversion

### 4. Prevent Future Occurrences
- Add schema validation at metadata creation time
- Update documentation for fiber photometry metadata requirements
- Test metadata creation tools against the upgrader

## Questions to Answer

1. **What is the tool that creates 4-fiber metadata?**
   - Check the pipeline that generated these 175 assets
   - Look for "behavior_" fiber photometry sessions

2. **Can we backfill the channel data?**
   - Do we have the original experimental configuration?
   - Can we infer channel mappings from the data itself?

3. **Should we fix the tool or the upgrader?**
   - Tool fix: prevents future issues, but leaves 175 assets broken
   - Upgrader fix: handles existing assets, but doesn't fix the root cause
   - **Best approach: do both**

## Files Generated

- `affected_assets.csv` - All 193 assets with fiber connections (175 problematic)
- `FINDINGS.md` - Detailed technical analysis
- `README.md` - Investigation documentation
- `investigate_asset.py` - Script to test specific assets
- `find_affected_assets.py` - Script that found the scope
- `analyze_patterns.py` - Script that revealed the pattern
