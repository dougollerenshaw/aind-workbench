# Action Plan: Fix the Fiber Photometry Upgrade Issue

## Problem Summary
- **175 assets** with 4-fiber FIP configuration cannot upgrade to schema v2
- Root cause: Old metadata mapper (dev branch) doesn't create channel data
- Created by: Kenta's legacy FIP data acquisition code
- Still active: Yes, will continue until Kenta switches to Bruno's refactored code

## Critical Decision Point

**How soon will Kenta retire the old FIP acquisition code?**

### If Retiring Soon (< 1 month)
→ **Just fix the upgrader** (Option 1 below)
- Minimal effort, fixes all existing assets
- No new broken assets will be created soon

### If Retiring Later (> 1 month)  
→ **Fix both upgrader AND old mapper** (Options 1 + 4)
- Prevents new broken assets
- Fixes existing assets
- Cleaner transition

## Recommended Solutions

### Option 1: Fix the Upgrader (HIGH PRIORITY)

**File:** `aind-metadata-upgrader/src/aind_metadata_upgrader/session/v1v2.py`

**Changes needed:**

```python
def _upgrade_fiber_connection_config(self, stream: Dict, fiber_connection: Dict) -> tuple:
    """Convert a single fiber connection config, return Channel, PatchCordConfig, Connection"""
    
    patch_cord_name = fiber_connection.get("patch_cord_name", "unknown")
    fiber_name = fiber_connection.get("fiber_name", "unknown")
    channel_data = fiber_connection.get("channel", {})
    
    # NEW: Handle missing channel data for legacy 4-fiber FIP assets
    if not channel_data or channel_data.get("channel_name") == "disconnected":
        # Check if this looks like a 4-fiber FIP setup
        if self._is_four_fiber_fip_setup(stream):
            return self._create_default_fip_channel_from_fiber(
                stream, patch_cord_name, fiber_name
            )
        else:
            # Not a 4-fiber FIP setup, keep original behavior
            return None, []
    
    # Original code continues...
```

**New helper methods needed:**

```python
def _is_four_fiber_fip_setup(self, stream: Dict) -> bool:
    """Check if this is a 4-fiber FIP setup based on devices"""
    fiber_connections = stream.get("fiber_connections", [])
    light_sources = stream.get("light_sources", [])
    detectors = stream.get("detectors", [])
    
    # 4 fiber connections, 4 LEDs (including IR), 2 detectors (Green/Red CMOS)
    return (
        len(fiber_connections) == 4 and
        len([ls for ls in light_sources if ls.get("device_type") == "Light emitting diode"]) == 4 and
        len(detectors) == 2
    )

def _create_default_fip_channel_from_fiber(
    self, 
    stream: Dict, 
    patch_cord_name: str, 
    fiber_name: str
) -> tuple:
    """Create default channel for legacy 4-fiber FIP setup"""
    
    # Extract fiber index from name (e.g., "Fiber 0" -> 0)
    fiber_idx = int(fiber_name.split()[-1])
    
    # Standard 4-fiber FIP mapping:
    # Fiber has 3 channels: Green (470nm), Iso (415nm), Red (565nm)
    # For upgrader purposes, create the primary channel (Green)
    
    light_sources = stream.get("light_sources", [])
    detectors = stream.get("detectors", [])
    
    # Find the 470nm LED (primary channel)
    green_led = next((ls for ls in light_sources 
                      if "470" in str(ls.get("name", ""))), None)
    
    # Find Green CMOS detector
    green_detector = next((d for d in detectors
                          if "Green" in str(d.get("name", ""))), None)
    
    if not green_led or not green_detector:
        logging.warning(
            f"Could not create default channel for {patch_cord_name}: "
            f"missing expected devices"
        )
        return None, []
    
    # Create channel
    channel = Channel(
        channel_name=f"Fiber_{fiber_idx}_Green",
        intended_measurement="dF/F",
        detector=self._upgrade_detector_config(green_detector),
        light_sources=[self._upgrade_light_source_config(green_led)],
        emission_wavelength=520,
        emission_wavelength_unit="nanometer",
    )
    
    # Create PatchCordConfig
    patch_cord_config = PatchCordConfig(
        device_name=patch_cord_name,
        channels=[channel],
    ).model_dump()
    
    # Create connections
    connections = [
        Connection(
            source_device=green_led["name"],
            target_device=patch_cord_name,
        ).model_dump(),
        Connection(
            source_device=patch_cord_name,
            target_device=fiber_name,
            send_and_receive=True,
        ).model_dump(),
        Connection(
            source_device=patch_cord_name,
            target_device=green_detector["name"],
        ).model_dump(),
    ]
    
    logging.info(
        f"Created default FIP channel for {patch_cord_name} "
        f"(legacy 4-fiber asset without channel data)"
    )
    
    return patch_cord_config, connections
```

**Testing:**
```bash
cd /path/to/aind-metadata-upgrader
# Add the changes above
# Run tests on known broken asset
python -m pytest tests/ -k test_session_upgrade
# Test on asset 733a1052-683c-46d2-96ca-8f89bd270192
```

### Option 4: Fix the Old Mapper (If needed for ongoing use)

**File:** `aind-metadata-mapper/src/aind_metadata_mapper/fip/session.py` (dev branch)

**Changes needed:**

Instead of just passing through fiber_configs, create channel data:

```python
def _create_fiber_connections_with_channels(
    self, 
    fiber_configs: List[dict],
    light_sources: List[dict],
    detectors: List[dict]
) -> List[dict]:
    """Add channel information to fiber connections"""
    
    connections_with_channels = []
    
    for fc in fiber_configs:
        # Extract fiber index
        fiber_idx = int(fc["fiber_name"].split()[-1])
        
        # Find devices (similar to new mapper logic)
        green_led = next((ls for ls in light_sources if "470" in ls.get("name", "")), None)
        green_detector = next((d for d in detectors if "Green" in d.get("name", "")), None)
        
        if green_led and green_detector:
            # Add channel data
            fc["channel"] = {
                "channel_name": f"Fiber_{fiber_idx}_Green",
                "detector_name": green_detector["name"],
                "light_source_name": green_led["name"],
                "intended_measurement": "dF/F",
                "emission_wavelength": 520,
                "emission_wavelength_unit": "nanometer",
            }
        
        connections_with_channels.append(fc)
    
    return connections_with_channels
```

Then update the session creation:
```python
# Before: line 231
fiber_connections=[
    FiberConnectionConfig(**fc) for fc in fiber_data.fiber_configs
],

# After:
fiber_connections=[
    FiberConnectionConfig(**fc) for fc in self._create_fiber_connections_with_channels(
        fiber_data.fiber_configs,
        fiber_data.light_source_configs,
        fiber_data.detector_configs
    )
],
```

## Implementation Timeline

### Week 1
1. **Discuss with Kenta**: When will he switch to Bruno's code?
2. **Review options**: Choose between upgrader-only vs. both fixes
3. **Start implementation**: Begin coding the chosen solution

### Week 2
4. **Testing**: Test on the 175 affected assets
5. **PR & Review**: Submit changes for review
6. **Documentation**: Update docs about the fix

### Week 3
7. **Deployment**: Deploy to production
8. **Validation**: Confirm assets can now upgrade
9. **Monitoring**: Watch for any edge cases

## Success Criteria

- [ ] All 175 identified assets can successfully upgrade to schema v2
- [ ] New assets from Kenta's pipeline either:
  - [ ] Stop being created (switched to Bruno's code), OR
  - [ ] Include proper channel data (old mapper fixed)
- [ ] No regression in upgrade success rate for other asset types
- [ ] Clear documentation of the fix and reasoning

## Testing Checklist

Test assets:
- [ ] `733a1052-683c-46d2-96ca-8f89bd270192` (original failing asset)
- [ ] 5-10 other assets from the affected_assets.csv (session v1.0.1)
- [ ] 5-10 other assets from the affected_assets.csv (session v1.1.2)
- [ ] 1-2 assets with 7+ fibers (should still work)
- [ ] Recent asset from after the fix (should work)

## Communication Plan

**Notify:**
- Kenta (FIP acquisition code owner)
- Bruno (new FIP code developer)
- Metadata team (upgrader owners)
- Data engineering (deployment)

**Key messages:**
- Why 175 assets were failing to upgrade
- What fix was chosen and why
- Timeline for deployment
- Any action needed from stakeholders
