# Metadata Upgrader Investigation: Asset 733a1052-683c-46d2-96ca-8f89bd270192

## Problem Statement

Asset `733a1052-683c-46d2-96ca-8f89bd270192` fails to upgrade from session schema v1.1.2 to v2.2.3 with the error:

> Missing one of required devices ['PatchCordConfig', 'FiberAssemblyConfig'] for modality Fiber photometry

## Investigation Summary

### Root Cause

The asset's session metadata has fiber connections that are missing the required `channel` field. The upgrader expects:

```python
{
    "patch_cord_name": "Patch Cord 0",
    "fiber_name": "Fiber 0", 
    "channel": {  # <-- THIS IS MISSING
        "channel_name": "...",
        "detector_name": "...",
        "light_source_name": "...",
        # ...
    }
}
```

But the actual data only contains:

```python
{
    "patch_cord_name": "Patch Cord 0",
    "fiber_name": "Fiber 0",
    "patch_cord_output_power": "20",
    "output_power_unit": "microwatt"
}
```

Without channel data, the upgrader cannot create the required `PatchCordConfig` objects for fiber photometry streams.

### Scope of the Issue

**This is a systemic problem affecting ~91% of fiber photometry assets with v1 session schemas:**

- Sampled 1000 assets with v1 session schemas
- 193 assets have fiber connections
- **175 assets (91%) are missing channel data**
- Affects both session v1.0.1 (125 assets) and v1.1.2 (50 assets)
- All affected assets have **ALL** their fiber connections missing channel data

See `affected_assets.csv` for the complete list.

## Files

- **`investigate_asset.py`** - Script to fetch and attempt to upgrade a specific asset
- **`analyze_session_data.py`** - Detailed analysis of session data structure
- **`find_affected_assets.py`** - Query DocDB to find all assets with this issue
- **`FINDINGS.md`** - Detailed technical analysis of the upgrade failure
- **`affected_assets.csv`** - List of all affected assets from the sample
- **`733a1052-683c-46d2-96ca-8f89bd270192_original.json`** - Original metadata from the problematic asset
- **`session_full.json`** - Full session metadata for analysis
- **`stream_0.json`** - Detailed stream data showing the missing channel fields

## Quick Start

```bash
# Check if a specific asset will have upgrade issues
uv run python check_asset.py <asset_id>

# Example
uv run python check_asset.py 733a1052-683c-46d2-96ca-8f89bd270192
```

## Deep Dive Scripts

```bash
# Investigate the specific asset in detail
uv run python investigate_asset.py

# Analyze the session structure
uv run python analyze_session_data.py

# Find all affected assets (slow - queries 1000 assets)
uv run python find_affected_assets.py

# Analyze patterns in affected assets
uv run python analyze_patterns.py
```

## Technical Details

The upgrade failure occurs in `aind_metadata_upgrader/session/v1v2.py`:

1. `_upgrade_fiber()` iterates over fiber connections
2. For each connection, calls `_upgrade_fiber_connection_config()`
3. At line 251-254:
   ```python
   channel_data = fiber_connection.get("channel", {})
   if not channel_data or channel_data["channel_name"] == "disconnected":
       return None, []  # Returns nothing!
   ```
4. No `PatchCordConfig` is created
5. Stream validation fails because fiber photometry requires these configs

## Recommended Actions

### Short-term
1. Document this as a known limitation
2. Provide a list of affected assets to stakeholders
3. Consider whether these assets need to be re-ingested with correct metadata

### Long-term 
1. **Fix the upgrader** to handle missing channel data by:
   - Creating default channels based on available detectors/light sources
   - Making educated guesses about device pairings
   - Logging warnings about assumptions
   
2. **Update metadata validation** to prevent this in the future:
   - Ensure fiber connections always have channel data when created
   - Add validation to catch this at ingestion time

3. **Investigate the source**:
   - Which tool/pipeline created these incomplete fiber connections?
   - Was this ever valid in any version of the schema?
   - Fix the tool to prevent future occurrences

## Questions for Follow-up

1. What created these assets? Was it a specific pipeline/tool?
2. Is the fiber photometry data itself valid, just the metadata incomplete?
3. Can we retroactively populate the channel information, or is it lost?
4. Should we prioritize fixing the upgrader vs. fixing/re-ingesting the data?
5. Are there other similar metadata quality issues we should investigate?
