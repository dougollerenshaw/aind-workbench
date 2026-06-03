# IACUC Lookup REST API

A tiny Flask app, mounted by the [`tool-launcher`](../tool-launcher) at
**`/iacuc_lookup`**, that returns the current IACUC protocol for a mouse as JSON.

It's a thin web wrapper around `aind_workbench.get_iacuc_id_for_mouse` (see the
[repo README](../../README.md#shared-utilities-aind_workbench)).

## Endpoint

```
GET /iacuc_lookup?subject_id=762287   ->  {"762287": "2414"}
GET /iacuc_lookup/762287              ->  {"762287": "2414"}
GET /iacuc_lookup?762287              ->  {"762287": "2414"}   (bare query string)
```

Response shape is `{subject_id: protocol_id}`. If no protocol is found the value is
`null`. Missing subject id returns HTTP 400.

Optional query params:

| param | effect |
|---|---|
| `details=true` | Return the richer blob: `{subject_id, iacuc_protocol, source, history}`. |
| `fallback=false` | DocDB only; skip the slow (~30 s) metadata-service fallback. |

Example:

```bash
curl "http://<vm-ip>/iacuc_lookup?subject_id=762287"
# {"762287": "2414"}

curl "http://<vm-ip>/iacuc_lookup?subject_id=762287&details=true"
# {"subject_id":"762287","iacuc_protocol":"2414","source":"docdb",
#  "history":[{"start_date":"2025-01-24","iacuc_protocol":"2414"},
#             {"start_date":"2024-10-30","iacuc_protocol":"2109"}]}
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
