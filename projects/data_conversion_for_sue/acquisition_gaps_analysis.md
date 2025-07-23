# Acquisition.json vs Session Template Comparison

## Overview
Comparing our generated `acquisition.json` files with Sue's `session_template.json` to identify missing fields and data that should be integrated.

---

## Top-Level Fields

| Field | session_template.json | acquisition.json | Status | Notes |
|-------|----------------------|------------------|--------|-------|
| `active_mouse_platform` | `false` | ❌ Missing | Need to add | Boolean field |
| `iacuc_protocol` | `"MO19M432"` | `"ethics_review_id": null` | ✅ Map | Rename and populate |
| `rig_id` | `"hopkins_295F_nlyx"` | `"instrument_id": "hopkins_ephys"` | ✅ Update | Use more specific rig ID |
| `session_type` | `"Uncoupled Without Baiting"` | `"acquisition_type": "Behavioral foraging"` | ✅ Update | Use more specific type |
| `mouse_platform_name` | `"mouse_tube_foraging_hopkins"` | `"Unknown"` | ✅ Update | Use actual platform name |
| `headframe_registration` | `null` | ❌ Missing | Need to add | |
| `reward_delivery` | `null` | ❌ Missing | Need to add | |

---

## Stimulus Epoch Fields

### Currently Empty/Null in acquisition.json
| Field | session_template.json | acquisition.json | Status |
|-------|----------------------|------------------|--------|
| `code` | Has software array | `null` | ✅ Populate |
| `active_devices` | `["Stimulus Speaker"]` | `[]` | ✅ Populate |
| `configurations` | Has speaker_config | `[]` | ✅ Populate |
| `notes` | Detailed go cue info | `null` | ✅ Populate |

### Missing Fields Entirely
| Field | session_template.json | acquisition.json |
|-------|----------------------|------------------|
| `light_source_config` | `[]` | ❌ Missing |
| `script` | `null` | ❌ Missing |
| `session_number` | `null` | ❌ Missing |
| `software` | GitHub repo info | ❌ Missing |
| `speaker_config` | Volume/name config | ❌ Missing |
| `stimulus_device_names` | `["Stimulus Speaker"]` | ❌ Missing |
| `stimulus_parameters` | Detailed audio params | ❌ Missing |

---

## Software/Code Information (Major Gap)

### session_template.json has:
```json
"software": [
  {
    "name": "dynamic-foraging-task",
    "parameters": {},
    "url": "hhttps://github.com/JeremiahYCohenLab/sueBehavior.git",
    "version": null
  }
]
```

### acquisition.json has:
```json
"code": null
```

**Action**: Map software info to `code` field in stimulus epoch.

---

## Performance Metrics - output_parameters

### session_template.json has rich data:
```json
"output_parameters": {
  "meta": {
    "box": "hopkins_295F_nlyx",
    "session_run_time_in_min": 120
  },
  "performance": {
    "foraging_efficiency": 0.7421219466716389,
    "foraging_efficiency_with_actual_random_seed": 0.7743190661478598
  },
  "task_parameters": {
    "BlockBeta": "15",
    "BlockMax": "35",
    "BlockMin": "20",
    "DelayBeta": "0.0",
    "DelayMax": "1.0",
    "DelayMin": "1.0",
    "ITIBeta": "3.0",
    "ITIMax": "15.0",
    "ITIMin": "2.0",
    "LeftValue_volume": "3.00",
    "RightValue_volume": "3.00",
    "Task": "Uncoupled Without Baiting",
    "reward_probability": "0.1, 0.5, 0.9"
  },
  "water": {
    "water_after_session": 0.75,
    "water_day_total": 1.578,
    "water_in_session_foraging": 0.796,
    "water_in_session_manual": 0.032,
    "water_in_session_total": 0.828
  }
}
```

### acquisition.json has:
```json
"output_parameters": {}
```

**Action**: Populate with task parameters, performance metrics, and water data.

---

## Speaker/Audio Configuration

### session_template.json has:
```json
"speaker_config": {
  "name": "Stimulus Speaker",
  "volume": "60",
  "volume_unit": "decibels"
},
"stimulus_parameters": [
  {
    "amplitude_modulation_frequency": 7500,
    "frequency_unit": "hertz",
    "sample_frequency": "96000",
    "stimulus_name": "auditory go cue",
    "stimulus_type": "Auditory Stimulation"
  },
  {
    "amplitude_modulation_frequency": 15000,
    "frequency_unit": "hertz", 
    "sample_frequency": "96000",
    "stimulus_name": "auditory no go cue",
    "stimulus_type": "Auditory Stimulation"
  }
]
```

### acquisition.json has:
```json
"active_devices": [],
"configurations": []
```

**Action**: Add speaker configurations and stimulus parameters.

---

## Implementation Priority

### High Priority (Core Missing Data)
1. ✅ **ethics_review_id**: Map from `iacuc_protocol`
2. ✅ **instrument_id**: Use specific rig ID
3. ✅ **acquisition_type**: Use specific session type
4. ✅ **task_parameters**: Add to output_parameters
5. ✅ **software/code**: Add GitHub repo info

### Medium Priority (Device Configurations)
6. ✅ **speaker_config**: Add to stimulus epoch configurations
7. ✅ **active_devices**: Add "Stimulus Speaker"
8. ✅ **stimulus_parameters**: Add audio cue details

### Lower Priority (Nice to Have)
9. ✅ **performance metrics**: Foraging efficiency, water breakdown
10. ✅ **mouse_platform_name**: Use actual platform name
11. ❌ **Additional fields**: active_mouse_platform, headframe_registration, etc.

---

## Notes
- Sue's template is schema v1.0.1, ours is v2.0.34
- Some field names changed between versions (iacuc_protocol → ethics_review_id)
- Need to determine which v1.0.1 fields are deprecated vs renamed in v2.0.34
