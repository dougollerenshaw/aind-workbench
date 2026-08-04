# Spec: Classify session assets for open-data migration

**Purpose.** Take the spreadsheet of session assets attached to Sue's capsule, look each
asset up in the AIND metadata DocDB (v2 first, falling back to v1), and write a `status`
column (plus diagnostic columns) that sorts every asset into one of a small, finite set of
**action buckets**. The downstream goal is to open one GitHub sub-issue per action bucket
under [aind-beh-ephys-analysis#7](https://github.com/AllenNeuralDynamics/aind-beh-ephys-analysis/issues/7),
where each sub-issue lists exactly the assets needing that action.

This document is meant to be handed to Claude Code working in
`dougollerenshaw/aind-workbench`. It describes *what* to build and *why*, with the gotchas
already discovered so they don't have to be rediscovered.

---

## 1. Input

- File: `session_assets_sources_-_Doug_Copy.xlsx` (note: **xlsx, not csv** — read with
  pandas + openpyxl).
- One sheet, named `in`. 491 data rows. Columns:
  - `Unnamed: 0` — original integer row index. Preserve it; don't treat it as data.
  - `id` — the **Code Ocean asset UUID** (e.g. `0438b3fa-3ddc-45ba-9c95-9ce2baf71b93`).
  - `name` — the data asset name (e.g. `behavior_744779_2024-11-14_13-13-37`).
  - `source-bucket` — bucket label from the capsule. **Unreliable — see §3.** Values seen:
    `aind-open-data` (188), blank/NaN (152), `aind-private-data-prod-o5171v` (68),
    `aind-scratch-data` (66), `aind-ephys-data` (17).
  - `external` — 0/1/NaN flag from the source export; not needed for classification but keep it.
- `id` is unique across rows; `name` is unique in this sheet too.

---

## 2. Output

1. **Enriched spreadsheet** `session_assets_status.xlsx` — the input with all original
   columns preserved plus the new columns in §6.
2. **Console/summary** — a count of assets per `status`.
3. **One list file per action bucket** (markdown or txt) under e.g. `out/`, each listing
   `name`, `id`, and current `location` for the assets in that bucket — formatted as a
   GitHub task list so it can be pasted straight into a sub-issue.

A local JSON response cache (keyed by asset `id`) so re-runs are cheap and don't hammer the API.

---

## 3. Facts already established (don't rediscover these)

These came out of manual spot-checking ~12 assets through the metadata service. They drive
the design:

1. **`source-bucket` cannot be trusted.** Assets labeled `aind-private-data-prod-o5171v`
   were found already sitting in `s3://aind-open-data/`. The only source of truth for "where
   does it live now" is the `location` field on the live DocDB record. So every asset —
   including the 188 already labeled `aind-open-data` — must be looked up.

2. **`name` is the primary join key, and it works in both physical layouts:**
   - Asset in a named data bucket → `location = s3://<bucket>/<name>` (name matches directly).
   - Asset still in the Code Ocean internal bucket → `location =
     s3://codeocean-s3datasetsbucket-1u41qdg42ur9/<id>` while `name` is still the human name.
     The exact `name` still matches the record, so name-matching catches these too. The `id`
     appears in the `location` path, which gives a useful **secondary** join (§5 step 2).

3. **There are two DocDB indices: v2 and v1.** Some assets — especially older
   `aind-ephys-data` ones — exist **only in v1**. Example: `ecephys_687697_2023-09-15_11-30-06`
   returns nothing from v2 but is present in v1 at `s3://aind-ephys-data/...` with valid
   `data_description` and `processing`. An asset in v1 but not v2 means *something blocked the
   v1→v2 upgrade* — that's its own action bucket, not a "missing" asset.

4. **Names can drift by a few seconds, and a given derived run may never have been
   registered.** Example: the sheet has
   `behavior_791691_2025-06-24_13-21-29_sorted_curated_2025-09-19_08-15-06` (note `13-21-29`),
   but DocDB only has `…_13-21-26…` records — the raw session and several *other* derived
   assets, mostly already in open-data — and **no** `sorted_curated_2025-09-19` run at all.
   So this asset is neither cleanly "found" nor cleanly "session missing": it's an orphaned /
   unregistered derived asset whose session exists under a slightly different timestamp. This
   is its own bucket (`NAME_MISMATCH`) so these can be reviewed by hand.

5. **The same `name` can have multiple records** (e.g. one in `aind-open-data` and a duplicate
   in the Code Ocean bucket). Rule: if **any** matched record has a `location` starting
   `s3://aind-open-data/`, the asset counts as already in open data.

6. **`data_description` and `processing` can be `null` even on open-data records.** That's
   fine — completeness only gates the *move* decision for assets that are **not yet** in
   open-data. Treat a key that is present-but-null the same as missing.

---

## 4. Data access API (verified against source)

Repo: https://github.com/AllenNeuralDynamics/aind-data-access-api

```bash
pip install "aind-data-access-api[docdb]"
```

```python
from aind_data_access_api.document_db import MetadataDbClient

HOST = "api.allenneuraldynamics.org"   # defaults: database="metadata_index", collection="data_assets"

client_v2 = MetadataDbClient(host=HOST, version="v2")
client_v1 = MetadataDbClient(host=HOST, version="v1")
```

- The **read** endpoints (`find` / `aggregate`, used by `retrieve_docdb_records` and
  `aggregate_docdb_records`) are **public and read-only — no AWS credentials required.** Only
  the write/register methods sign requests; we don't use those here.
- Useful methods on `MetadataDbClient`:
  - `retrieve_docdb_records(filter_query=..., projection=..., limit=0)` — paginated, returns
    `list[dict]`.
  - `aggregate_docdb_records(pipeline)` — for `$project`-with-`$cond` presence checks if you
    want to keep payloads tiny.
  - `fetch_records_by_filter_list(filter_key, filter_values, projection=...)` — batch `$in`
    lookup; ideal for matching many names at once.
- Record shape we rely on: top-level `_id`, `name`, `location`, `data_description`,
  `processing`. (`location` format is `s3://{bucket}/{name}` per the AIND docs.)

### 4.1 ⚠️ Verify the v1/v2 mapping BEFORE the full run

The library has **no special v2 logic** — `version` is just spliced into the REST path
(`/v2/metadata_index/data_assets`). The `version="v2"` / `version="v1"` mapping above is
*inferred*, so confirm it empirically first:

- `client_v2` query `{"name": "ecephys_687697_2023-09-15_11-30-06"}` → **expect 0 records**.
- `client_v1` same query → **expect exactly 1 record** at `s3://aind-ephys-data/…` with
  `data_description` and `processing` both present.
- Sanity the other direction: `client_v2` query
  `{"name": "behavior_744779_2024-11-14_13-13-37"}` → **expect 1 record** in `aind-open-data`.

If v2 returns the ecephys asset, the mapping is wrong — stop and figure out the real v2
endpoint before proceeding (it may be a different host/path).

---

## 5. Lookup procedure (per asset)

Given `(id, name)` from a row, attempt matches in this order and stop at the first that hits.
Record which method matched. Use `re.escape` on `id`/`name` for any regex.

1. **v2, exact name**: `retrieve_docdb_records(filter_query={"name": name}, version=v2)`.
2. **v2, id-in-location**: `{"location": {"$regex": re.escape(id) + "$"}}` (the id is the last
   path segment for Code Ocean-internal records). Catches name-drift where the id is stable.
3. **v1, exact name**.
4. **v1, id-in-location**.
5. **Prefix probe (name-mismatch detection)**: derive the session prefix from the name —
   for `behavior_`/`ecephys_` names this is the first three underscore tokens, e.g.
   `behavior_791691_2025-06-24`. Query v2 then v1 with `{"name": {"$regex": "^" + re.escape(prefix)}}`.
   - If candidates come back → `NAME_MISMATCH`, and store the candidate names/locations.
   - If still nothing → `NOT_FOUND`.

A match may return **multiple** records — keep them all. Derive:

- `found_in` ∈ {`v2`, `v1`, `none`} (which index produced the match; v2 wins if both).
- `in_open_data` = any matched `location` starts with `s3://aind-open-data/`.
- `has_data_description` = any matched record has non-null `data_description`.
- `has_processing` = any matched record has non-null `processing`.
- `n_records`, `match_method`, plus the representative `docdb_id` / `docdb_name` /
  `docdb_location` (prefer the open-data record if there is one, else the most complete).

Use a projection like `{"_id":1,"name":1,"location":1,"data_description":1,"processing":1}` to
limit payload, or an aggregation that projects booleans for presence if you'd rather keep it
tiny. Treat present-but-`null` as missing.

---

## 6. Classification (decision tree — first match wins)

| # | Condition | `status` | Action the sub-issue tracks |
|---|-----------|----------|------------------------------|
| 1 | found in v2 **and** `in_open_data` | `ALREADY_OPEN_DATA` | none (informational / done) |
| 2 | found in v2, not open, `has_data_description` **and** `has_processing` | `READY_TO_MOVE` | submit a request to move the asset to `aind-open-data` |
| 3 | found in v2, not open, missing dd and/or processing | `NEEDS_METADATA` | generate/repair `data_description` / `processing`, then move |
| 4 | found in v1 but **not** v2 | `V1_NOT_V2` | investigate why the v1→v2 upgrade is failing |
| 5 | no name/id match, but prefix candidates exist | `NAME_MISMATCH` | reconcile name/timestamp against the existing session; review candidates by hand |
| 6 | nothing found anywhere | `NOT_FOUND` | locate the data / create metadata from scratch |

**Edge case to decide explicitly (make it a config flag):** an asset that is `in_open_data`
but found **only in v1**. For the *move* goal it's done (`ALREADY_OPEN_DATA`), but it also has
the v1→v2 upgrade problem. Recommend: classify as `ALREADY_OPEN_DATA` for the primary status
but set a separate boolean column `v1_only=True` so these can also be swept into the
`V1_NOT_V2` investigation. Document whichever choice is made.

---

## 7. Columns to add to the output sheet

`status`, `found_in`, `match_method`, `in_open_data`, `has_data_description`,
`has_processing`, `n_records`, `docdb_id`, `docdb_name`, `docdb_location`, `v1_only`,
`candidate_matches` (semicolon-joined names for `NAME_MISMATCH`), `notes`, `api_version_used`,
`checked_at` (ISO timestamp). Keep all original columns unchanged.

---

## 8. Expected results for the assets already checked (use as a self-test)

The script should reproduce these classifications. Good smoke test before trusting the full run.

| name | id | expected status |
|------|----|-----------------|
| `behavior_744779_2024-11-14_13-13-37` | `f2029505-5cc9-4889-9bd6-5d80d4d6079a` | `ALREADY_OPEN_DATA` (sheet said private) |
| `behavior_758017_2025-02-04_11-57-33` | `75f7920a-17c9-4e0c-8259-aee69e0544b2` | `ALREADY_OPEN_DATA` (sheet said private) |
| `behavior_758017_2025-02-06_11-26-09_sorted_curated_2025-02-25_16-04-02` | `1c147ab8-4465-4684-bc58-448f9ba6a7aa` | `ALREADY_OPEN_DATA` (open-data + a CO duplicate) |
| `behavior_714116_2024-08-29_11-46-43_sorted-opto-bandpass_2024-08-30_19-45-29` | `17acbbc8-35e6-499d-b27f-1a21812f4070` | `READY_TO_MOVE` (in CO bucket, has dd+proc) |
| `ecephys_687697_2023-09-15_11-30-06` | `4699a15c-c8a7-47ab-b288-2a5768530d16` | `V1_NOT_V2` (only in v1; has dd+proc) |
| `behavior_791691_2025-06-24_13-21-29_sorted_curated_2025-09-19_08-15-06` | `0438b3fa-3ddc-45ba-9c95-9ce2baf71b93` | `NAME_MISMATCH` (only `13-21-26` siblings exist) |
| `260113_percentile_meshes` | `c712751d-f744-4fe8-9657-93a7084eab22` | `NOT_FOUND` |

(The three `ZS06x_..._nwb_...` assets are straightforward `ALREADY_OPEN_DATA`.)

---

## 9. Implementation notes / gotchas

- **xlsx** input: `pd.read_excel(path, sheet_name="in")`; write with
  `df.to_excel(out, sheet_name="in", index=False)` (openpyxl engine).
- **Batch then fall back**: do the exact-name match for all 491 names in chunks via
  `fetch_records_by_filter_list("name", names_chunk, projection=...)` against v2, then v1 for
  the misses. Only run the per-asset id-in-location and prefix probes for names that didn't
  match. 491 assets is small — the whole run should take a few minutes.
- **Cache**: persist raw responses to `out/docdb_cache.json` keyed by asset `id` so reruns and
  debugging don't re-query.
- **Retries**: wrap calls in a small retry-with-backoff; the API can occasionally time out.
- **null vs missing**: `data_description`/`processing` may be present and `null`; coerce both
  to "missing".
- **Don't write anything to DocDB.** This is a read-only classification pass. The actual
  bucket moves and metadata generation are separate processes triggered by the sub-issues.
- **Prefix derivation** for the name-mismatch probe is heuristic; for non-`behavior`/`ecephys`
  names (e.g. `260113_percentile_meshes`) there may be no sensible session prefix — in that
  case skip step 5 and let it fall through to `NOT_FOUND`.

---

## 10. Sub-issue plan (under #7)

After the sheet is classified, create one sub-issue per actionable status (everything except
`ALREADY_OPEN_DATA`). Suggested titles:

- `READY_TO_MOVE` → "Move assets with valid metadata to aind-open-data"
- `NEEDS_METADATA` → "Generate/repair metadata for assets not yet in open-data"
- `V1_NOT_V2` → "Investigate assets present in DocDB v1 but not v2 (upgrade failures)"
- `NAME_MISMATCH` → "Reconcile assets whose name/timestamp doesn't match a registered session"
- `NOT_FOUND` → "Locate / create metadata for assets absent from DocDB"

Each issue body: a GitHub task list of `- [ ] <name> (\`<id>\`) — <location or 'not found'>`.
The per-bucket list files from §2 are designed to drop straight in.