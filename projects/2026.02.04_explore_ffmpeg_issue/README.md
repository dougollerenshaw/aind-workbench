# AIND Video Metadata Fix - Issue #457

Scripts to identify and process behavior videos affected by the ffmpeg metadata issue described in [GitHub Issue #457](https://github.com/AllenNeuralDynamics/aind-scientific-computing/issues/457).

## Problem Summary

Videos processed with `aind-behavior-video-transformation` version < 0.2.1 (before Dec 1, 2025) have mismatched pixel scaling and metadata. This causes videos to appear oversaturated in most players and analysis software like Lightning Pose.

**Fix:** Galen created a [Code Ocean capsule](https://codeocean.allenneuraldynamics.org/capsule/3921827/tree) that corrects the metadata without re-encoding.

## Affected Scope

- **~4,410 data assets** with aind-behavior-video-transformation version < 0.2.1
- Primarily from the "Cognitive flexibility in patch foraging" project
- All .mp4 files within these assets need metadata correction

## Workflow

### Step 1: Identify Affected Assets and Files

Run the identification script to cross-reference DocDB metadata with S3 file inventories:

```bash
uv run identify_affected_files.py \
  --private-bucket-json /allen/aind/scratch/jon.young/temp_video_file_lists/video_files_in_private_bucket.json \
  --open-bucket-json /allen/aind/scratch/jon.young/temp_video_file_lists/video_files_in_open_bucket.json \
  --output affected_files.json
```

This will:
1. Query DocDB for assets with aind-behavior-video-transformation < 0.2.1
2. Load Jon's S3 file inventories
3. Find all .mp4 files within affected asset locations
4. Output summary statistics and detailed file list

**Output files:**
- `affected_files.json` - Full details of affected assets and files
- `affected_files_asset_ids.txt` - List of asset IDs (one per line)

### Step 2: Generate Processing Commands

Generate a list or commands for batch processing:

```bash
# Generate CSV list of assets
uv run generate_codeocean_commands.py \
  --input affected_files.json \
  --csv-output assets_to_process.csv

# Or generate bash commands (template)
uv run generate_codeocean_commands.py \
  --input affected_files.json \
  --output batch_process.sh \
  --capsule-id 3921827
```

### Step 3: Process Through Galen's Capsule

Use Galen's Code Ocean capsule to fix the metadata:
- Capsule URL: https://codeocean.allenneuraldynamics.org/capsule/3921827/tree
- The capsule processes all .mp4 files and corrects the metadata
- No re-encoding - just metadata changes (very fast, ~$0.003/hr of video)

## Key Queries

### MongoDB: Count affected assets by version
```javascript
[
  {
    "$match": {
      "processing.processing_pipeline.data_processes": {
        "$elemMatch": {
          "code_url": {"$regex": "aind-behavior-video-transformation", "$options": "i"},
          "software_version": {"$lt": "0.2.1"}
        }
      }
    }
  },
  {
    "$unwind": "$processing.processing_pipeline.data_processes"
  },
  {
    "$match": {
      "processing.processing_pipeline.data_processes.code_url": {"$regex": "aind-behavior-video-transformation", "$options": "i"},
      "processing.processing_pipeline.data_processes.software_version": {"$lt": "0.2.1"}
    }
  },
  {
    "$group": {
      "_id": "$processing.processing_pipeline.data_processes.software_version",
      "count": {"$sum": 1}
    }
  },
  {
    "$sort": {"_id": 1}
  }
]
```

### MongoDB: Get all affected assets with locations
```javascript
[
  {
    "$match": {
      "processing.processing_pipeline.data_processes": {
        "$elemMatch": {
          "code_url": {"$regex": "aind-behavior-video-transformation", "$options": "i"},
          "software_version": {"$lt": "0.2.1"}
        }
      }
    }
  },
  {
    "$project": {
      "_id": 1,
      "name": 1,
      "location": 1
    }
  }
]
```

## Version Distribution

Based on DocDB analysis:

| Version | Count | Status |
|---------|-------|--------|
| 0.1.0   | 19    | Affected (questionable metadata) |
| 0.1.3   | 619   | Affected (reliable metadata) |
| 0.1.6   | 2,473 | Affected (reliable metadata) |
| 0.1.7   | 1,192 | Affected (questionable metadata) |
| 0.2.0   | 107   | Affected (reliable metadata) |
| **Total** | **4,410** | **All need fix** |
| 0.2.1   | 630   | Fixed (started Dec 2, 2025) |
| 0.2.2   | 353   | Fixed |

## Important Notes

1. **Version 0.2.1+ is the fix**: All versions before 0.2.1 are affected
2. **Date cutoff is Dec 1, 2025**: This is when version 0.2.1 was deployed
3. **Metadata correction, not re-encoding**: The fix only updates container metadata, preserving the original encoded video
4. **Some players still won't work**: Even with corrected metadata, some players (like VLC) may still misinterpret full-range videos
5. **OpenCV/Lightning Pose will work**: The corrected metadata allows proper interpretation by OpenCV-based tools

## Files in This Package

- `identify_affected_files.py` - Main script to identify affected files
- `generate_codeocean_commands.py` - Generate batch processing commands
- `pyproject.toml` - Project dependencies (UV)
- `README.md` - This file

## Setup

This project uses UV for dependency management. To set up:

```bash
# Install dependencies
uv sync

# Run scripts with UV
uv run identify_affected_files.py --help
```

## Contact

For questions about this issue:
- GitHub: https://github.com/AllenNeuralDynamics/aind-scientific-computing/issues/457
- Galen Lynch (@galenlynch) - Created the fix capsule
- Rachel Lee (@rachelstephlee) - Project coordination
- Jon Young (@jtyoung84) - S3 file inventory

## References

- Original issue: https://github.com/AllenNeuralDynamics/aind-scientific-computing/issues/457
- Root cause: https://github.com/AllenNeuralDynamics/aind-behavior-video-transformation/issues/32
- Fix capsule: https://codeocean.allenneuraldynamics.org/capsule/3921827/tree
- Fix PR: https://github.com/AllenNeuralDynamics/aind-behavior-video-transformation/pull/33