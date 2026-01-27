# Asset 733a1052-683c-46d2-96ca-8f89bd270192 Upgrade Failure Analysis

## Summary

The asset **cannot upgrade** from session v1.1.2 to v2.2.3 due to missing channel data in fiber connections.

## Root Cause

The upgrader expects fiber connections in session v1 to have the following structure:

```python
{
    "patch_cord_name": "Patch Cord 0",
    "fiber_name": "Fiber 0",
    "patch_cord_output_power": "20",
    "output_power_unit": "microwatt",
    "channel": {                           # <--- THIS IS MISSING
        "channel_name": "...",
        "detector_name": "...",
        "light_source_name": "...",
        "intended_measurement": "...",
        # ... other channel fields
    }
}
```

But the actual data in this asset has:

```python
{
    "patch_cord_name": "Patch Cord 0",
    "fiber_name": "Fiber 0",
    "patch_cord_output_power": "20",
    "output_power_unit": "microwatt"
    # NO "channel" field at all!
}
```

## What Happens During Upgrade

1. The upgrader calls `_upgrade_fiber()` to convert fiber connections
2. For each fiber connection, it calls `_upgrade_fiber_connection_config()`
3. At line 251-254 of v1v2.py:
   ```python
   channel_data = fiber_connection.get("channel", {})
   
   if not channel_data or channel_data["channel_name"] == "disconnected":
       return None, []  # Returns nothing!
   ```
4. Since there's no `channel` field, the method returns `(None, [])` 
5. No `PatchCordConfig` objects are created
6. The stream has modality "Fiber photometry" 
7. The new schema **requires** at least one `PatchCordConfig` or `FiberAssemblyConfig` for fiber photometry streams
8. Validation fails with the error:
   > Missing one of required devices ['PatchCordConfig', 'FiberAssemblyConfig'] for modality Fiber photometry

## Metadata State

- **Session version:** 1.1.2
- **Created:** 2025-01-04
- **Asset name:** behavior_689727_2024-02-07_15-01-36
- **Modalities:** behavior-videos, behavior, fiber photometry (fib)
- **Fiber connections:** 4 (Patch Cord 0-3)
- **Light sources:** 4 LEDs (IR, 470nm, 415nm, 565nm)
- **Detectors:** 2 CMOS (Green, Red)

## Why This Happened

This asset's metadata was likely created with:
1. An older version of aind-data-schema that didn't require/support channel information in fiber connections, OR
2. A tool/script that didn't properly populate the channel data, OR
3. Manual metadata creation that missed the channel field

## Implications

All assets with this same metadata structure will fail to upgrade. This could be:
- A single isolated case
- A batch of assets from the same experiment/date
- All assets created by a particular tool/pipeline

## Potential Solutions

### Option 1: Fix the Upgrader
Modify `_upgrade_fiber_connection_config()` to handle missing channel data by:
- Creating default channels based on available detectors and light sources
- Making educated guesses about which light source/detector pairs form channels
- Logging warnings about assumptions made

### Option 2: Fix the Source Data
Update the metadata in DocDB to add the missing channel information:
- Would require knowing the correct channel mappings
- May not be feasible if the information is truly lost

### Option 3: Schema Exception
If this structure was valid in v1.1.2, update the upgrader to:
- Skip fiber photometry device creation for assets missing channel data
- Remove the "fib" modality from the stream if no valid fiber devices can be created
- Log a warning about incomplete upgrade

## Next Steps

1. Search for other assets with the same issue:
   - Query DocDB for assets with session.schema_version = "1.1.2"
   - Check if fiber_connections exist but lack channel data
   
2. Determine the scope:
   - Is this one asset or many?
   - Was this from a specific pipeline/time period?
   
3. Decide on fix strategy:
   - If isolated: manually fix the metadata
   - If widespread: update the upgrader to handle this case
