# Build brief — Procedure Scheduling prototype

You are building a prototype from scratch, largely unsupervised. **`DESIGN.md` in this folder is the source of truth** for the schema, API, validation rules, and UI. Read it fully before writing code. This brief tells you *how to work*, the build order, and the acceptance criteria you must verify before you stop.

## Where this lives

This is a self-contained project folder inside the `aind-workbench` monorepo: `projects/procedure-scheduling/`. It follows the same conventions as the sibling projects `projects/query_tool/` and `projects/tool-launcher/`:

- Managed with **`uv`**: a `pyproject.toml` and a committed `uv.lock`.
- Runnable with `uv run python app.py` (or `uv run uvicorn ...`).
- A `README.md` that includes a **"Remote access from the VM"** section, mirroring the style of `projects/query_tool/README.md` (bind `0.0.0.0`, find VM IP with `hostname -I`, browse from the Mac, firewall/port notes).
- CLI options for `--host` (default `0.0.0.0`) and `--port` (default `8000`).
- Keep the UI in a `template.html` (or a small `static/` + `templates/` set) — no JS build toolchain.

Do not modify anything outside `projects/procedure-scheduling/`.

## Goal (why this exists)

Break a logjam on [aind-scientific-computing#624](https://github.com/AllenNeuralDynamics/aind-scientific-computing/issues/624). This is a working, demo-able reference implementation of a procedure-scheduling system so stakeholders can react to something real, and so the schema can be backfilled into Dataverse later. It is a prototype: correctness and clarity over polish, but it must actually run end-to-end and look presentable in a demo.

## Tech stack (follow DESIGN.md)

- Python 3.11+, **FastAPI + uvicorn** (preferred — the auto-generated `/docs` OpenAPI page is a real asset when showing the API to the Dataverse team). If you have a strong reason to use Flask to match the house style, note it in the README, but default to FastAPI.
- **DuckDB** as the store; **pyarrow** for Parquet export.
- **Pydantic v2** for request/response models and validation.
- Frontend: vanilla JS + **FullCalendar** from CDN (resource-timeline plugin under its GPLv3 license key, since this repo is open source). No bundler.
- Tests: **pytest** + FastAPI `TestClient` (httpx).

Keep dependencies minimal. No auth libraries, no database server, no external services, no message queues. One process.

## Build order

Work in milestones. After each, run the checks for that milestone before moving on. Commit at each milestone boundary with a clear message.

**M1 — Schema + store.** Implement all tables from DESIGN.md in DuckDB (with the join tables), including the aind-data-schema alignment fields (the `procedure_types` modality mapping, `instruments.instrument_id`, `users.orcid`, `scheduled_procedures.ethics_review_id`) per DESIGN.md's "aind-data-schema alignment" section. String UUID PKs; the `scheduled_procedures` token id is a **UUIDv7** (time-sortable — use a `uuid7` library or `uuid-utils`, since stdlib `uuid.uuid7` only exists in Python ≥3.14). ISO-8601 tz-aware datetimes. Write a `db.py` that creates the schema idempotently and opens a single app-level connection (serialize writes; DuckDB is single-writer).

**M2 — Seed data.** `scripts/seed.py` populates the database from the **canonical seed dataset defined in DESIGN.md ("Seed data and worked examples")** — the same eight `procedure_types`, the three named `instruments` with their compatibility sets, the listed `mice`, `projects`, `users`, and at least the four explicit `scheduled_procedures` (SP-1…SP-4). Then extend to ~15–25 procedures spread across the next 2–3 weeks so the calendar looks alive on first open. Keep some procedures multi-platform (e.g. Dynamic Foraging + FIP) to exercise the multiselect. The worked examples in DESIGN.md are the ground truth for exact field values and the shape of API responses — match them. Seeding must be idempotent or safely re-runnable.

**M3 — Read API.** All GET endpoints from DESIGN.md with the full filter set. Responses resolve lookups (return names alongside IDs). This is the "read-only API with filters for all fields" deliverable.

**M4 — Admin write API + validation.** POST/PUT/DELETE under `/session_schedule/api/admin/...` for the form. Enforce: `scheduled_end > scheduled_start`; every active procedure type ⊆ the instrument's compatible set (reject with a clear 4xx + message); recompute `acquisition_type` and `updated_at` on every write.

**M5 — Calendar SPA.** Served at `GET /session_schedule/`. FullCalendar view with instruments as rows, events spanning start→end, colored by primary active platform with a legend. Client-side filters for platform, instrument, and date range, plus a subject_id text filter. Event click → detail panel. "Add procedure" modal form that constrains active-type choices to the selected instrument's compatible set and submits to the admin API.

**M6 — Parquet export.** `scripts/export_parquet.py` writes each table to `data/parquet/<table>.parquet`. Field names must match DESIGN.md's Dataverse-mapping table so backfill is a direct mapping.

**M7 — Docs + polish.** README with setup (uv), run instructions, CLI options, the VM remote-access section, and a short "How this maps to Dataverse" section lifted from DESIGN.md. Make sure `/docs` (OpenAPI) is reachable and clean.

## Acceptance criteria — verify before you stop

Write these as automated tests where possible (`tests/`), run them, and confirm they pass. Also do the manual curl/smoke checks.

1. `uv sync` succeeds from a clean checkout; `uv run python app.py` starts and serves `http://localhost:8000/session_schedule/`.
2. `/session_schedule/` renders a populated calendar from seed data (no empty state on first run).
3. `GET /session_schedule/api/scheduled-procedures` returns seeded rows with resolved lookup names, in the JSON shape shown in DESIGN.md "Example 2". Spot-check that SP-1's response matches the documented payload (resolved mouse/instrument/project/contact/experimenters, `active_procedure_types`, and computed `acquisition_type`). Also verify the rig-facing endpoints and `next-acquisition` return the documented shapes.
4. Every filter works and is combinable: filter by instrument, by project, by procedure type, by status, and by each date bound; verify result counts change correctly.
5. Compatibility validation: a POST that puts an active procedure type on an instrument that doesn't list it as compatible is **rejected** with a clear message; a compatible one succeeds.
6. `scheduled_end <= scheduled_start` is rejected.
7. `acquisition_type` is server-computed and equals the sorted concatenation of active type names; it is never taken from client input.
8. The Add-procedure form round-trips: create via the UI, then see the new event on the calendar and via the API.
9. `scripts/export_parquet.py` produces a Parquet file per table; re-reading them with pyarrow yields the same row counts as DuckDB.
10. `pytest` passes with no failures. Include tests for: each filter, both validation rules, acquisition_type computation, and the Parquet round-trip.
11. README's VM remote-access instructions are present and accurate for the actual `--host/--port` defaults.

Do not mark the build done until 1–11 all hold. If something can't be satisfied, leave it clearly noted in a `BUILD_NOTES.md` with what's blocked and why — don't paper over it.

## Guardrails

- **NEVER touch production Dataverse or any live system.** Read the "Guardrails: the prototype never touches production Dataverse" section of DESIGN.md and follow it exactly. This prototype is entirely self-contained: local DuckDB + synthetic seed data only. Do not connect to `*.crm.dynamics.com` or the Dataverse OData API; do not use Azure AD/MSAL, KeePass, the `svc_sipe` account, `clabe`, `dataverse-client`, or `DataversePicker`; do not read, write, or delete any existing Dataverse/LIMS table (`aibs_dim_mices`, `aibs_fact_mouse_proposed_behavior_sessionses`, "Behavior Training", etc.); do not make outbound network calls for data. The Dataverse details in DESIGN.md are reference-only for schema shaping and a future human-run backfill — they are NOT an instruction to integrate. All writes happen only against the local DuckDB store.
- Stay in scope. Deferred items in DESIGN.md (auto Acquisition-log generation, cancellation-reason capture, PowerPlatform notifications, dedicated SmartSPIM sub-tables, auth) are **out** — don't build them. If you think one is essential, note it in `BUILD_NOTES.md` instead of building it.
- Keep it one process, no auth, minimal deps.
- Don't invent fields not in DESIGN.md without noting them in `BUILD_NOTES.md`.
- Prefer clarity over cleverness; this code will be read by the Dataverse team as a reference.
- Commit at each milestone. Leave the repo in a runnable state.

## When done

Write a short `BUILD_NOTES.md` summarizing: what was built, anything deferred or blocked, any deviations from DESIGN.md and why, and the exact commands to run it on the VM. Assume Doug will read this first thing in the morning and want to `uv run` it and demo it.