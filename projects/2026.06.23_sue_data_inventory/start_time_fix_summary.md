# Fix: missing `start_date_time` in video-compression DataProcess

## Summary

19 of the 24 assets in this issue fail the v1→v2 upgrade because of a malformed
video-compression `DataProcess` in `processing.processing_pipeline.data_processes`.
The upgrade raises:

```
1 validation error for DataProcess
start_date_time  Input should be a valid datetime [input_value=None]
```

This is the same defect tracked in
[aind-scientific-computing#599](https://github.com/AllenNeuralDynamics/aind-scientific-computing/issues/599)
and fixed for a different asset set by
[aind-data-migration-scripts#567](https://github.com/AllenNeuralDynamics/aind-data-migration-scripts/pull/567).
The asset sets do **not** overlap — these 19 were not covered by that run.

## The malformed process

Each affected record has a `DataProcess` with:

- `name`: `"Compression"`
- `code_url`: `https://github.com/AllenNeuralDynamics/aind-behavior-video-transformation`
- `notes`: `"Called compression library with gamma-encoding-fix-colorspace."`
- **missing**: `start_date_time` (null), `end_date_time`, `input_location`, `output_location`, `outputs`

It originates from a one-off video-compression run (for pose tracking) whose
metadata was never validated. Note: this entry sits **alongside a valid
`Compression` process** (the standard `aind-ephys-transformation` step), so it is
**not** always at index 0 — identify it by content, not list position.

## Minimal fix (verified)

Setting just `start_date_time` and `end_date_time` to a valid datetime is enough
for the upgrade to succeed. A follow-up migration script can be simpler by taking
this approach:

1. Select records by `{"name": {"$in": [...the 19 names...]}}`.
2. In `processing.processing_pipeline.data_processes`, find the process(es) where
   `start_date_time is None` (equivalently: `code_url` contains
   `aind-behavior-video-transformation`).
3. Set `start_date_time` and `end_date_time` to a real timestamp already present
   on the record (e.g. the adjacent valid process's time, or the acquisition time)
   and add a `notes` line indicating the time is approximate (the original
   compression run times were not recorded). This avoids deriving timestamps from
   S3 / external sources.
4. Write only the `processing` file. Read-only dry run first; keep before/after
   snapshots (see PR #567 for the established pattern).

If the downstream DF behavior+fiber analysis pipeline also needs `input_location`
/ `output_location`, those can be filled from path templates (see PR #567) without
changing the timestamp approach above.

> Longer term: these `DataProcess` fields are optional in metadata v2, so once
> assets are on v2 no imputation is needed — the imputation is only required while
> the analysis pipeline consumes v1.

## Affected assets (19)

```
behavior_714116_2024-08-28_12-11-55
behavior_714116_2024-08-29_11-46-43
behavior_716325_2024-05-29_10-33-32
behavior_716325_2024-05-30_11-33-46
behavior_716325_2024-05-31_10-31-14
behavior_716325_2024-06-01_09-25-37
behavior_717121_2024-06-11_10-23-31
behavior_717121_2024-06-15_10-00-58
behavior_717259_2024-06-28_11-17-19
behavior_717263_2024-07-24_10-40-05
behavior_722832_2024-09-13_11-55-58
behavior_724172_2024-10-01_11-20-11
behavior_724172_2024-10-03_11-02-53
behavior_739970_2024-10-15_10-04-12
behavior_739970_2024-10-16_12-15-24
behavior_739977_2024-10-24_12-58-26
behavior_751766_2025-02-13_11-31-21
behavior_751766_2025-02-14_11-37-11
behavior_751766_2025-02-15_12-08-11
```

(The remaining assets in this issue fail for unrelated reasons — `procedures.subject_id`
null and a `data_description` funder typo — and are tracked separately.)
