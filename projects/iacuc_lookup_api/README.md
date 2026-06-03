# IACUC Lookup REST API

A tiny Flask app, mounted by the [`tool-launcher`](../tool-launcher) at
**`/iacuc_lookup`**, that returns the current IACUC protocol for a mouse as JSON.

It's a thin web wrapper around `aind_workbench.get_iacuc_id_for_mouse` (see the
[repo README](../../README.md#shared-utilities-aind_workbench)).

## Endpoint

```
GET /iacuc_lookup?subject_id=762287    (or /iacuc_lookup/762287, or ?762287)
->
{
  "subject_id":       "762287",
  "ethics_review_id": "2414",                      # protocol number (null if none)
  "source":           "docdb",                      # "docdb" | "metadata_service" | null
  "date_queried":     "2026-05-07T09:10:57.441Z"
}
```

`date_queried` is provenance for spotting **stale** IDs:
- `source: docdb` → the `_created` date of the DocDB procedures record the value came
  from (the freshest record asserting that protocol).
- `source: metadata_service` → the current time, since that path queries LabTracks live.

If no protocol is found, `ethics_review_id`/`source`/`date_queried` are `null`. A request
with no subject id returns the HTML form (browser) — programmatic callers always pass one.

Optional query params:

| param | effect |
|---|---|
| `details=true` | Adds a `history` array: every distinct `{start_date, ethics_review_id}`. |
| `fallback=false` | DocDB only; skip the slow (~30 s) metadata-service fallback. |

Example:

```bash
curl "http://<vm-ip>/iacuc_lookup?subject_id=762287"
# {"subject_id":"762287","ethics_review_id":"2414","source":"docdb","date_queried":"2026-05-07T09:10:57.441Z"}
```

## Running

Via the launcher (mounted with the other tools):

```bash
cd ../tool-launcher
uv run launcher.py            # serves http://0.0.0.0:8080/iacuc_lookup?subject_id=...
```

Standalone (for local testing):

```bash
uv run --with flask --with requests iacuc_app.py --port 8090
```

## Notes

- The lookup hits DocDB (no creds) first; the metadata-service fallback needs network
  access to the internal host (VPN). A web request that falls back can take ~30 s.
- `aind_workbench` is imported from the repo root (the app adds it to `sys.path`), so
  it works whether or not the package is `pip install`-ed.
