# Metadata Mapper Analysis: Root Cause Identified

## The Two Mappers

### Old Mapper (dev branch) - Kenta's Setup
- **Repository:** [aind-metadata-mapper/dev/src/aind_metadata_mapper/fip](https://github.com/AllenNeuralDynamics/aind-metadata-mapper/tree/dev/src/aind_metadata_mapper/fip)
- **Target Schema:** aind-data-schema v1.4 (session v1.0.1, v1.1.2)
- **Status:** Currently in production, Kenta still using
- **Problem:** Creates fiber connections WITHOUT channel data

### New Mapper (release-v1.0.0) - Bruno's Refactor
- **Repository:** [aind-metadata-mapper/release-v1.0.0/src/aind_metadata_mapper/fip](https://github.com/AllenNeuralDynamics/aind-metadata-mapper/tree/release-v1.0.0/src/aind_metadata_mapper/fip)
- **Target Schema:** aind-data-schema v2.0 (session v2.x)
- **Status:** Ready for production when Bruno's code is deployed
- **Feature:** Properly creates Channel objects with full configuration

## Key Differences

### Old Mapper - Missing Channel Data

```python
# old_mapper_session.py line 231-233
fiber_connections=[
    FiberConnectionConfig(**fc) for fc in fiber_data.fiber_configs
]
```

The `fiber_configs` come from `data_streams[0]["fiber_connections"]` in the JobSettings, which contains ONLY:
- `patch_cord_name`
- `fiber_name`
- `patch_cord_output_power`
- `output_power_unit`

**NO channel field!**

### New Mapper - Proper Channel Creation

```python
# new_mapper.py line 505-554
def _create_channel(
    self,
    fiber_idx: int,
    channel_type: str,
    led_config: Optional[LightEmittingDiodeConfig],
    intended_measurement: Optional[str],
    camera_name: str,
    emission_wavelength: int,
    exposure_time_ms: float,
) -> Channel:
    return Channel(
        channel_name=f"Fiber_{fiber_idx}_{channel_type}",
        intended_measurement=intended_measurement,
        detector=DetectorConfig(
            device_name=camera_name,
            exposure_time=exposure_time_ms,
            exposure_time_unit=TimeUnit.MS,
            trigger_type=TriggerType.INTERNAL,
            compression=FIP_CAMERA_COMPRESSION,
        ),
        light_sources=[led_config] if led_config else [],
        excitation_filters=[],
        emission_filters=[],
        emission_wavelength=emission_wavelength,
        emission_wavelength_unit=SizeUnit.NM,
    )
```

Creates proper Channel objects for each fiber with:
- Green channel (470nm LED → Green camera)
- Isosbestic channel (415nm LED → Green camera)
- Red channel (565nm LED → Red camera)

## Answers to Key Questions

### Q: Why do ALL 4-fiber assets have missing channel data?
**A:** They all came from the old mapper on the dev branch, which was designed for schema v1.4 before channels were required in fiber connections.

### Q: Why do 7+ fiber assets have proper channel data?
**A:** These likely came from a different source (possibly hand-created or from a different pipeline) that was aware of the channel requirement.

### Q: When did this start?
**A:** November 2024 - when Kenta's pipeline started creating assets with the old mapper.

### Q: Why is it still happening?
**A:** Kenta is still using the old data collection code and old mapper. The issue will continue until he switches to Bruno's refactored code with the new mapper.

## Resolution Options

### Option 1: Update the Upgrader (Recommended for immediate relief)
**Pros:**
- Fixes all 175 existing broken assets
- Allows them to upgrade to schema v2.x
- No changes needed to Kenta's workflow

**Cons:**
- Requires making assumptions about channel mappings
- Doesn't prevent future issues if Kenta continues using old mapper

**Implementation:**
Modify `aind-metadata-upgrader/session/v1v2.py` to handle missing channel data:
```python
def _upgrade_fiber_connection_config(self, stream: Dict, fiber_connection: Dict) -> tuple:
    channel_data = fiber_connection.get("channel", {})
    
    # NEW: If no channel data, create default channels based on available devices
    if not channel_data or channel_data.get("channel_name") == "disconnected":
        # For 4-fiber FIP setup: create default channel mappings
        # Extract fiber index from patch cord name (e.g., "Patch Cord 0" -> 0)
        # Map to standard FIP configuration:
        #   - Green channel: 470nm LED -> Green detector
        #   - Iso channel: 415nm LED -> Green detector  
        #   - Red channel: 565nm LED -> Red detector
        return self._create_default_fip_channel(stream, fiber_connection)
    
    # Original code continues...
```

### Option 2: Create New v2 Mapper for Old Code (Not recommended)
**Pros:**
- Would create proper v2 metadata from old data collection code

**Cons:**
- Effort for code that will be retired soon
- Technical debt
- Doesn't fix existing 175 assets

### Option 3: Wait for Bruno's Code + Backfill (Partial solution)
**Pros:**
- Future assets will be correct
- Clean forward path

**Cons:**
- Doesn't help existing 175 assets
- Leaves technical debt in the system

### Option 4: Fix Old Mapper to Add Channels (Interim solution)
**Pros:**
- Future assets from Kenta would be correct
- Relatively simple change

**Cons:**
- Still doesn't fix existing 175 assets
- Effort for deprecated code
- Would need to add channel logic to old mapper

## Recommended Strategy

### Phase 1: Immediate (This Week)
1. **Update the upgrader** to handle missing channel data
   - Create sensible defaults for 4-fiber FIP configurations
   - Log warnings about assumptions
   - Allows existing 175 assets to upgrade

### Phase 2: Short-term (This Month)
2. **Coordinate with Kenta** on timeline for switching to Bruno's code
   - If it's soon (< 2 months): just wait
   - If it's longer: consider updating old mapper as interim fix

### Phase 3: Long-term (Next Quarter)
3. **Retire old mapper** once Bruno's code is in production
4. **Add validation** at metadata creation to prevent this in future
5. **Document** the 4-fiber configuration standard for FIP

## The 4-Fiber Pattern Explained

The 100% correlation between 4 fibers and missing channels makes perfect sense now:

**Kenta's setup:**
- 4 patch cords / 4 fibers (standard FIP configuration)
- 4 LEDs (IR, 470nm, 415nm, 565nm)
- 2 CMOS detectors (Green, Red)
- Old mapper → Creates fiber connections without channels

**Other setups (7+ fibers):**
- Different configuration / different labs
- Possibly different mapper or hand-created metadata
- Properly included channel data from the start

## Next Steps

1. **Decision:** Which resolution option to pursue?
2. **Timeline:** When will Kenta switch to Bruno's code?
3. **Implementation:** Update upgrader vs. update old mapper vs. both?
4. **Testing:** Validate the chosen approach with sample assets
5. **Deployment:** Roll out the fix to production

## Code References

### Files to Modify (Option 1 - Update Upgrader)
- `aind-metadata-upgrader/src/aind_metadata_upgrader/session/v1v2.py`
  - Method: `_upgrade_fiber_connection_config` (line 245)
  - Add logic to create default channels when missing

### Files to Modify (Option 4 - Fix Old Mapper)
- `aind-metadata-mapper/src/aind_metadata_mapper/fip/session.py` (dev branch)
  - Add channel creation logic similar to new mapper
  - Update fiber_configs to include channel data
