# MAPseq blackbox acquisition — implementation summary

A field-by-field record of the values in `mapseq_acquisition.py`, where they came from, and what's still open.

## Field-by-field source audit

### Authoritative

| Field | Value | Source |
|---|---|---|
| `subject_id` | `780345`, `780346` | Confirmed |
| `acquisition_start_time` (780345) | 2025-03-24 (date shipped to CSHL) | Polina Kosillo Teams chat, 2026-05-01 |
| `acquisition_start_time` (780346) | 2025-07-23 (date shipped to CSHL) | Polina Kosillo Teams chat, 2026-05-01 |
| `acquisition_end_time` (both) | 2025-10-30 (last reprocessing/redelivery date) | Polina Kosillo Teams chat, 2026-05-01 |
| `experimenters` | `["Cold Spring Harbor Laboratory (CSHL) MAPseq team"]` | Decided here |
| `specimen_id` (`*_map001`–`*_map039`) | 39 sections per subject | aind-data-schema PR #1763 (`examples/procedures_sectioning.py`, branch `1729-barseqmapseq-procedures`) |
| `Modality.MAPSEQ` | enum from `aind_data_schema_models.modalities` | Verified to exist on `aind-data-schema-models` main branch |
| `protocol_id` | `[]` (empty list) | No published MAPseq protocol URL |
| Time-of-day on `acquisition_start_time` / `acquisition_end_time` | `12:00:00` (`America/Los_Angeles`) | Exact times unknown; noon avoids timezone-edge day shifts |
| `notes` (Acquisition-level and ExternalDataStream-level) | "MAPseq was performed off-site at Cold Spring Harbor Laboratory. The acquisition_start_time represents the date the tissue was mailed to CSHL; the acquisition_end_time represents the date the final processed results were received." | Judgment call — clarifies that the dates are mailing/receipt dates, not the actual dates of the off-site procedures |

### Unconfirmed

| Field | Value | Why it's unconfirmed |
|---|---|---|
| `acquisition_type` | `"BarcodeSequencing"` | Copied from `barseq_acquisition.py`. MAPseq is barcode-based, so plausible, but unconfirmed as the canonical string for MAPseq. |
| `specimen_id` includes `*_spinal` (single entry) | `780345_spinal`, `780346_spinal` | From PR #1763. For 780345, three `Section` objects share `output_specimen_id="780345_spinal"`; we list the ID once. List-once vs list-three-times is unconfirmed. |
| `specimen_id` does NOT include slide chunks | e.g. `780345_map001_001`, `780345_map001_002`, ... | PR #1763's `examples/procedures_sectioning.py::generate_mapseq_slide_chunks()` creates per-section "chunks" (brain region pieces extracted from each section). These chunks are presumably what was actually mailed to CSHL and sequenced. We currently list only the parent section IDs. **This is the most important open question.** |

## Questions to ask (Dan first, fall back to Polina if needed)

1. **Sections vs. slide chunks for `specimen_id`** — PR #1763's `examples/procedures_sectioning.py` defines section-level specimens (e.g., `780345_map001`) via `generate_mapseq_slides_780345_first_batch()` / `_second_batch()`, AND chunk-level specimens (e.g., `780345_map001_001`) via `generate_mapseq_slide_chunks()`. The chunks are presumably what was actually mailed to CSHL and sequenced. Should the MAPseq acquisition's `specimen_id` list reference:
   - (a) section-level IDs only — what we have now, ~40 per subject
   - (b) chunk-level IDs — potentially several hundred per subject
   - (c) both?
2. **Spinal cord listing convention** — when a single `output_specimen_id` (e.g., `780345_spinal`) is shared across multiple `Section` objects, should that ID appear once or N-times in the acquisition `specimen_id` list?
3. **`acquisition_type` string** — is `"BarcodeSequencing"` the right value for MAPseq, the same as the BARseq example? Or is there a different canonical value for MAPseq?

## Source artifacts referenced

- **PR #1763** (Dan Birman, `aind-data-schema`): "BarMapSeq procedures" — open as of writing, base `dev`, head `1729-barseqmapseq-procedures`. Contains `examples/procedures_sectioning.py` which is the authoritative source for MAPseq specimen IDs and section counts.
- **PR #1781** (`aind-data-schema`): "Barseq blackbox acquisition" — merged into `dev` 2026-04-03. Adds the `ExternalDataStream` blackbox acquisition pattern this MAPseq script depends on.
- **`projects/barseq_blackbox_acquisition/barseq_acquisition.py`**: structural template that this MAPseq script parallels.
- **Polina Kosillo Teams chat, 2026-05-01**: shipping dates and the "last reprocessing date" convention for `acquisition_end`. Link: https://teams.microsoft.com/l/message/19:meeting_Y2NmYjk4YjktOWRlMS00YzAwLTgwMTItOTNjZmIzMjA3Zjg3@thread.v2/1777669568392?context=%7B%22contextType%22%3A%22chat%22%7D
