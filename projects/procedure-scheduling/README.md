# Procedure Scheduling Prototype

A working prototype of an acquisition/procedure scheduling system for AIND,
built to break the logjam on
[aind-scientific-computing#624](https://github.com/AllenNeuralDynamics/aind-scientific-computing/issues/624).
It is a **conversation-starter and stopgap**, not the production system. The
point is to break a talking-past-each-other loop in issues and design docs by
putting something concrete in front of people and asking "is this what you're
looking for?" — the answers come much faster from a running system than from
another round of documents. The long-term home for this is Microsoft
Dataverse, and the schema here deliberately mirrors Bruno's proposed Dataverse
tables so the data can be backfilled later with a direct field-by-field
mapping (see "How this maps to Dataverse" below).

What it does: schedule a procedure (mouse, instrument, project, contact,
experimenters, time window, active platforms) and get back a **persistent
acquisition token** — a time-sortable UUIDv7 minted at scheduling time,
before the acquisition exists — intended to be the through-line identifier
from plan to raw data to every derived asset. Around that: a read-only
filterable REST API, rig-facing convenience endpoints, an admin write API, a
calendar UI (hand-rolled: day/week blocks with instrument sub-rows), and
Parquet exports of every table. Entirely self-contained: local DuckDB file +
synthetic seed data, no auth, no external services, **no external asset
requests from the page**, and **no contact with production Dataverse or any
live system**.

See `DESIGN.md` for the full design and `BUILD_NOTES.md` for build decisions
and deviations.

## Deployed access (primary)

The scheduler is mounted in the **AIND tool launcher**
(`projects/tool-launcher/`), which serves all the internal tools on one
port. On the VM it is reachable at:

- UI: **http://10.128.142.221:8080/session_schedule/**
- API: `http://10.128.142.221:8080/session_schedule/api/...`
- Interactive API docs: `http://10.128.142.221:8080/session_schedule/docs`

The launcher's landing page (`http://10.128.142.221:8080/`) links to it
alongside the other tools. See `projects/tool-launcher/README.md` for how the
launcher itself is run (tmux on the VM). The app's code is identical in both
modes — every route already lives under the `/session_schedule` prefix, so
the launcher just forwards that prefix here.

## Standalone mode (development)

1. Install dependencies from `pyproject.toml` (creates `.venv`):
```bash
cd projects/procedure-scheduling
uv sync
```

2. Run the app:
```bash
uv run python app.py
```

3. Open your browser to: `http://localhost:8000/session_schedule/`

The interactive API docs (OpenAPI) are at
`http://localhost:8000/session_schedule/docs`.

On first run the database is created at `data/procedure_scheduling.duckdb`
and auto-seeded with the synthetic demo dataset, so the calendar is
populated immediately.

> **DuckDB is single-writer.** Only one process can have the database file
> open. Stop the standalone app *and* the tool launcher before running
> `scripts/seed.py` or `scripts/export_parquet.py` against the same file,
> otherwise DuckDB fails with `IOException: Could not set lock`.

### Command-line options
```bash
uv run python app.py --host 0.0.0.0 --port 8000 --db-path data/procedure_scheduling.duckdb
```

- `--host`: Host address to bind to (default: `0.0.0.0`)
- `--port`: Port to bind to (default: `8000`)
- `--db-path`: DuckDB file to use (default: `data/procedure_scheduling.duckdb`)

Equivalent alternative (same defaults via uvicorn directly):
```bash
uv run uvicorn scheduler_app.main:app --host 0.0.0.0 --port 8000
```

(The application package is `scheduler_app` rather than `app` so it can
never collide with other tools' `app` modules when mounted in the shared
tool launcher.)

## Seeding

The app auto-seeds an empty database on startup, so no separate step is
needed. To seed explicitly (e.g. after experimenting, or into another file)
— with the app/launcher stopped, per the single-writer note above:

```bash
uv run python scripts/seed.py            # top up the default DB (idempotent)
uv run python scripts/seed.py --reset    # wipe all tables, then seed fresh
uv run python scripts/seed.py --db-path some/other.duckdb
```

The seed dataset is the canonical one from `DESIGN.md`: 8 procedure types
(with their aind-data-schema modality mappings), 3 instruments with
compatibility sets, 3 synthetic mice (`testmouse1..3` — deliberately
non-numeric so they can never be mistaken for real AIND subject ids),
2 projects, 3 users, and 18 scheduled procedures spread over the next
~3 weeks relative to the day you seed. Re-running the script never
duplicates rows.

## Parquet export

Export every table to Parquet (one file per table) for portability and the
eventual Dataverse backfill (again with the app/launcher stopped):

```bash
uv run python scripts/export_parquet.py                      # -> data/parquet/
uv run python scripts/export_parquet.py --db-path X --out-dir Y
```

The files are plain Parquet readable with pyarrow/pandas. `TIMESTAMPTZ`
columns export as UTC-zoned timestamps; the `planned_config` JSON column
exports as a JSON string.

## Remote access from your Mac (standalone mode on a VM)

For the deployed launcher, just use the URLs under "Deployed access" above.
To reach a *standalone* dev instance running on a VM:

1. On the VM, run the app bound to all interfaces (default):
```bash
cd projects/procedure-scheduling
uv run python app.py
```
(Internally this uses `host=0.0.0.0` and `port=8000`.)

2. Find the VM's IP on the VPN network:
```bash
hostname -I
```
Pick the VPN-reachable address (often `10.x.x.x`).

3. From your Mac, open: `http://<VM_IP>:8000/session_schedule/`
   (API docs at `http://<VM_IP>:8000/session_schedule/docs`.)

4. If the page does not load, check:
- VM firewall allows inbound TCP 8000.
- VPN routing allows direct access to the VM IP.
- No other process is using port 8000.

### Custom host/port (optional)
```bash
uv run python app.py --port 8081
```
Then browse to `http://<VM_IP>:8081/session_schedule/`.

### Serving on bare port 80 (optional)

The default stays 8000 so no root is required. To get
`http://<VM_IP>/session_schedule/` on port 80, either:

- run on port 80 with the privilege to bind low ports — `sudo uv run python
  app.py --port 80`, or grant the capability once with
  `sudo setcap 'cap_net_bind_service=+ep' $(readlink -f .venv/bin/python)`
  and then run `uv run python app.py --port 80` unprivileged; or
- put a minimal nginx/caddy reverse proxy in front, forwarding
  `/session_schedule` to `127.0.0.1:8000`.

## How this maps to Dataverse

Field names and table structure intentionally mirror Bruno's proposed
Dataverse tables, so `scripts/export_parquet.py` output is the import
payload when Dataverse is ready — existing prototype rows carry over rather
than being re-entered.

| Prototype | Microsoft Dataverse (proposed / existing) |
|---|---|
| `procedure_types` | Procedure Types (vocab) |
| `instruments` + `instrument_compatible_types` | Instruments table w/ Compatible Acquisition Platforms multiselect; `sipe_rig_name` is the rig identity |
| `scheduled_procedures` | Scheduled Procedures / Schedule Acquisitions table (new) |
| `scheduled_procedure_active_types` | Active Acquisition Platforms multiselect |
| `acquisition_type` | Acquisition Type (computed concatenation) |
| `mice` | **existing** `aibs_dim_mices` (don't recreate — reference it) |
| `projects`, `users` | existing Dataverse lookups (Project, Users) |
| `planned_config` (behavior rows) | association to the existing `aibs_fact_mouse_proposed_behavior_sessionses` row(s) |

Practical notes for whoever does the real migration:

- Dataverse is a **star schema** with `aibs_`-prefixed `dim_`/`fact_` tables
  and **GUID** primary keys; relationships are set with the
  `field@odata.bind = /table(guid)` syntax, not by writing a foreign-key
  column directly. Our string-UUID keys map onto those GUIDs (the
  `scheduled_procedures.id` UUIDv7 is a standard 128-bit UUID).
- `mice` already exists as `aibs_dim_mices` — the real scheduled-procedures
  table should look up mice there rather than importing ours.
- Standard audit columns (`createdon`, `modifiedon`) are added by Dataverse
  automatically; our `created_at`/`updated_at` are the analogues.

This prototype never touches production Dataverse: the mapping above is
reference material for a **human-run, one-way** backfill later. See the
guardrails section of `DESIGN.md`.

## Running tests

```bash
uv run pytest
```

The suite (100+ tests) covers the schema, seed dataset, every API filter,
both validation rules, `acquisition_type` computation, the admin write
round-trips, the SPA page contract, and the Parquet round-trip.
