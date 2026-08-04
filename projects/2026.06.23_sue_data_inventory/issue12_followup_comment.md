The other two failure modes in this set (beyond the `start_date_time` issue above) are:

**`procedures.subject_id` is null (9 assets).** The top-level `subject_id` was never set, but `subject.subject_id` is present and matches the subject in the asset name.
Fix: set `procedures.subject_id = str(record["subject"]["subject_id"])`.

**`data_description` funder `"NINMH"` (5 assets).** One `funding_source` entry has `funder` as the bare string `"NINMH"` (typo for NIMH; grant `1R01MH134833` confirms NIMH), which the upgrader rejects (`Unsupported funder type: NINMH`).
Fix: replace that entry's `funder` string with the structured object:
```json
{
  "abbreviation": "NIMH",
  "name": "National Institute of Mental Health",
  "registry": {"abbreviation": "ROR", "name": "Research Organization Registry"},
  "registry_identifier": "04xeg9z08"
}
```

All three fixes (start_date_time + the two above) can go in one migration touching `processing`, `procedures`, and `data_description`. Applying them makes all 24 assets upgrade cleanly (verified). Full spec — including the per-asset fix matrix and identification rules — is in `migration_fix_spec.md`.
