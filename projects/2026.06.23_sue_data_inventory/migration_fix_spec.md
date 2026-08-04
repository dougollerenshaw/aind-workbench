# Migration spec: fix 33 v1 assets so they upgrade to v2

These are the 24 assets in
[aind-beh-ephys-analysis#12](https://github.com/AllenNeuralDynamics/aind-beh-ephys-analysis/issues/12)
that exist in DocDB v1 but fail the v1→v2 upgrade, **plus 9 additional `ecephys`
records** with the identical `NINMH` funder defect found by a v1-vs-v2 diff (not
attached to the capsule — see "Additional records" below). Three independent v1
metadata defects cause the failures; an asset may have more than one. Applying the
fixes below makes **all 33** upgrade cleanly (verified by running each repaired
record through `aind_metadata_upgrader.upgrade.Upgrade`).

One migration can fix everything by touching `processing`, `procedures`, and
`data_description` as needed per record. The callback should be conditional and
idempotent (only act when the bad value is present), so it applies the right
subset of fixes to each record regardless of which defects it has.

## Fix 1 — `processing`: null `start_date_time` (19 assets)

A malformed video-compression `DataProcess` (from an unvalidated one-off run) is
missing its timestamps. Same defect as
[aind-scientific-computing#599](https://github.com/AllenNeuralDynamics/aind-scientific-computing/issues/599)
/ [migration PR #567](https://github.com/AllenNeuralDynamics/aind-data-migration-scripts/pull/567)
(different, non-overlapping asset set). Identify it by content, not list index —
it sits next to a valid `aind-ephys-transformation` compression:

- `name == "Compression"`, `code_url` contains `aind-behavior-video-transformation`,
  `start_date_time is None`.

**Fix:** for every `data_process` in `processing.processing_pipeline.data_processes`
with `start_date_time is None`, set `start_date_time` and `end_date_time` to a real
timestamp already on the record (e.g. the adjacent valid process's `end_date_time`).
Add a `notes` line marking the time as approximate. (These fields are optional in
v2; the imputation is only needed while the analysis pipeline consumes v1.)

## Fix 2 — `procedures`: null `subject_id` (9 assets)

`procedures.subject_id` is `null`, but `subject.subject_id` is present and matches
the subject in the asset name.

**Fix:** if `procedures.subject_id is None`, set it to `str(record["subject"]["subject_id"])`.

> Note: some records also have a null `subject_procedures[].Surgery.start_date`.
> The upgrader tolerates this (no exception), so it does **not** need fixing.

## Fix 3 — `data_description`: invalid funder `"NINMH"` (5 assets)

One `funding_source` entry has `funder` as the bare string `"NINMH"` (typo for
NIMH; the grant number `1R01MH134833` confirms NIMH). The upgrader rejects it
with `Unsupported funder type: NINMH`.

**Fix:** replace that entry's `funder` (string) with the structured object:

```json
{
  "abbreviation": "NIMH",
  "name": "National Institute of Mental Health",
  "registry": {"abbreviation": "ROR", "name": "Research Organization Registry"},
  "registry_identifier": "04xeg9z08"
}
```

Leave the entry's `fundee` and `grant_number` unchanged. (Match by
`isinstance(funder, str)`.)

## Per-asset fix matrix

| asset | proc | subj_id | funder |
|---|:--:|:--:|:--:|
| behavior_714116_2024-08-28_12-11-55 | ✓ | | |
| behavior_714116_2024-08-29_11-46-43 | ✓ | | |
| behavior_716325_2024-05-29_10-33-32 | ✓ | ✓ | |
| behavior_716325_2024-05-29_10-33-32_sorted-opto_2024-09-11_22-32-12 | | ✓ | |
| behavior_716325_2024-05-30_11-33-46 | ✓ | ✓ | |
| behavior_716325_2024-05-30_11-33-46_sorted-opto_2024-06-04_17-00-28 | | ✓ | |
| behavior_716325_2024-05-31_10-31-14 | ✓ | ✓ | |
| behavior_716325_2024-05-31_10-31-14_sorted_curated_2024-07-16_06-10-19 | | ✓ | |
| behavior_716325_2024-05-31_10-31-14_sorted-opto-ZS_2024-06-05_03-54-32 | | ✓ | |
| behavior_716325_2024-06-01_09-25-37 | ✓ | ✓ | |
| behavior_716325_2024-06-01_09-25-37_sorted-opto-bandpass_2024-09-10_13-10-02 | | ✓ | |
| behavior_717121_2024-06-11_10-23-31 | ✓ | | |
| behavior_717121_2024-06-15_10-00-58 | ✓ | | |
| behavior_717259_2024-06-28_11-17-19 | ✓ | | |
| behavior_717263_2024-07-24_10-40-05 | ✓ | | |
| behavior_722832_2024-09-13_11-55-58 | ✓ | | ✓ |
| behavior_724172_2024-10-01_11-20-11 | ✓ | | ✓ |
| behavior_724172_2024-10-03_11-02-53 | ✓ | | ✓ |
| behavior_739970_2024-10-15_10-04-12 | ✓ | | |
| behavior_739970_2024-10-16_12-15-24 | ✓ | | ✓ |
| behavior_739977_2024-10-24_12-58-26 | ✓ | | ✓ |
| behavior_751766_2025-02-13_11-31-21 | ✓ | | |
| behavior_751766_2025-02-14_11-37-11 | ✓ | | |
| behavior_751766_2025-02-15_12-08-11 | ✓ | | |

Totals (issue #12 set): processing 19, subject_id 9, funder 5.

## Additional records (same NINMH rule, not in issue #12)

A v1-vs-v2 diff for the same defect signatures surfaced **9 more `ecephys`
records** carrying the identical `NINMH` funder typo. They are absent from v2 and
upgrade cleanly with **Fix 3 alone** (funder only — no processing/subject_id
defects). They are not attached to the capsule; include them in the same
migration since the rule is identical (note this in the PR description rather than
in issue #12).

| asset | proc | subj_id | funder |
|---|:--:|:--:|:--:|
| ecephys_730694_2024-10-29_12-39-55 | | | ✓ |
| ecephys_732855_2024-09-30_11-05-37 | | | ✓ |
| ecephys_732857_2024-10-17_11-42-22 | | | ✓ |
| ecephys_732857_2024-10-18_11-10-23 | | | ✓ |
| ecephys_734219_2024-09-15_10-23-58 | | | ✓ |
| ecephys_734219_2024-09-19_10-57-59 | | | ✓ |
| ecephys_737846_2024-10-22_13-44-57 | | | ✓ |
| ecephys_737846_2024-10-23_13-31-57 | | | ✓ |
| ecephys_737846_2024-10-24_10-46-24 | | | ✓ |

Grand totals (all 33): processing 19, subject_id 9, funder 14.

## Out of scope (do not include)

Two other populations share a signature but are **not** fixable with these rules
(deeper, heterogeneous blockers); they belong to the general upgrade effort:

- 9 `ecephys` records with the misspelled funder `"Allen Insitute for Neural
  Dynamics"` — also blocked by a null `craniotomy_type` enum. See
  `allen_institute_typo_records.md`.
- ~2115 records missing `procedures.subject_id` — only ~8% upgrade after these
  fixes; the rest fail for unrelated reasons.

The query method used to find all of the above is in `find_similar_broken.py`.

## Implementation notes

- Query: `{"name": {"$in": [...all 33 names...]}}`; migrate files `["processing",
  "procedures", "data_description"]`.
- Identify the malformed processing entry by content (`start_date_time is None`),
  not list index — see Fix 1.
- Make each fix idempotent and conditional (only act when the bad value is
  present), so the callback applies the right subset per record and is safe to
  re-run.
- Dry run with before/after snapshots first; the `name`/`data name` mismatch
  warnings during upgrade are benign.
