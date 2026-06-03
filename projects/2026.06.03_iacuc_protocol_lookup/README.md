# IACUC protocol lookup for a mouse — design notes

> **The function now lives in the shared package**, not in this folder. Import it as
> `from aind_workbench import get_iacuc_id_for_mouse` (see the
> [repo README](../../README.md#shared-utilities-aind_workbench)), and it's also exposed
> as a REST endpoint in [`projects/iacuc_lookup_api`](../iacuc_lookup_api). This folder
> is kept as the design/investigation record.

`get_iacuc_id_for_mouse(subject_id)` returns the **current IACUC protocol number** for a
mouse (e.g. `"2414"`), or `None` if none is recorded.

This replaces the earlier Dataverse-backfill plan (`../2026.03.25_*` / the
`2026.06.03_mouse_protocol_backfill` folder): the data's authoritative home is
LabTracks, surfaced through procedures metadata — no need to copy it into Dataverse
just to read it.

## Two-stage lookup

1. **Fast — AIND DocDB** (`metadata_index.data_assets`). Reads the procedures metadata
   already indexed there via the public read API. No credentials, ~sub-second.
2. **Fallback — `aind-metadata-service`** `GET /api/v2/procedures/{subject_id}`. Only
   when DocDB has no procedures doc (or no protocol) for the subject. Authoritative
   (pulls LabTracks live) but slow (~30 s) and needs the internal service host (VPN).

In both, the value lives at `procedures.subject_procedures[].iacuc_protocol` — a bare
number string. (LabTracks form; Dataverse uses `"2414-Westlake"`.)

## Movers

A mouse that changed protocols has surgeries with different `iacuc_protocol`s. The
function returns the **most recent** (by `start_date`) and logs a warning listing all
distinct protocols. Use `return_details=True` (or `--details`) to see the full history.

## Usage

As a library (after `uv pip install -e .` at the repo root):

```python
from aind_workbench import get_iacuc_id_for_mouse
protocol = get_iacuc_id_for_mouse("762287")                  # "2414"
info = get_iacuc_id_for_mouse("762287", return_details=True) # dict w/ source + history
```

CLI:

```bash
get-iacuc-id 762287            # -> 2414
get-iacuc-id 762287 --details  # JSON: protocol + source + history
get-iacuc-id 656374 --no-fallback   # DocDB only
```

## Verified behaviour (live, against real subjects)

| subject | result | notes |
|---|---|---|
| 632269 | `2109` | single protocol, from DocDB |
| 762287 | `2414` | mover (2109 → 2414); returns most recent, warns |
| 656374 | `None` | DocDB has procedures but `iacuc_protocol` is null → fallback territory |
| 823508 | `None`* | no procedures doc in DocDB → fallback territory |

\* Fallback to the metadata service couldn't be tested here (internal host not
resolving off-VPN), but the path is wired and fails gracefully.

## Notes / limitations

- DocDB reads need no auth; the metadata-service fallback needs network access to the
  internal host.
- "Current" = protocol on the most recent surgery. There is no authoritative per-mouse
  effective-date range in the source — protocol history is inferred from surgery dates.
- Dependency-light on purpose (just `requests`); the DocDB call mirrors
  `aind_data_access_api.document_db.MetadataDbClient` and could swap to it if preferred.
