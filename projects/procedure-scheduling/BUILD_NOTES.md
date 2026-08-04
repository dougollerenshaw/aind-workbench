# Build notes — procedure-scheduling prototype

Running log of decisions and deviations, kept per milestone. Final summary
(what was built, how to run on the VM) will be completed at M7.

## M1 — Schema + store

Built: `pyproject.toml` (uv-managed, Python >= 3.11), `app/db.py` (full
DESIGN.md schema in DuckDB + single app-level connection with serialized
writes), `tests/test_db.py` (10 tests, all passing).

Decisions / deviations:

- **No native DuckDB `FOREIGN KEY` constraints.** DuckDB implements `UPDATE`
  as `DELETE` + `INSERT`, so a row referenced by a declared FK (e.g. a
  `scheduled_procedures` row referenced by its `scheduled_procedure_active_types`
  join rows) cannot be updated in place — which would break the M4 admin
  `PUT` endpoint for legitimate edits. Relationships are documented in the
  DDL comments and referential integrity is enforced in the application
  layer (the write API resolves every lookup anyway, per DESIGN.md).
- **DB-level `CHECK` backstops** added for `scheduled_end > scheduled_start`
  and the `status` enum. These are safety nets only; the M4 API still
  validates first and returns clear 4xx errors per DESIGN.md.
- **`pytz` added as an explicit dependency**: the duckdb Python client
  requires it to return `TIMESTAMPTZ` columns as tz-aware Python datetimes.
- **UUIDv7 source is `uuid-utils`** (stdlib `uuid.uuid7` needs Python >= 3.14).
  `scheduled_procedures.id` uses UUIDv7; other PKs use uuid4.
- Project is laid out as an `app/` package (`app/db.py`, later `app/main.py`
  for `uvicorn app.main:app`) rather than a single top-level `app.py`, since
  a module and package with the same name can't coexist. A convenience
  entry point satisfying "`uv run python app.py`-style startup" will be
  addressed in M3/M7 (e.g. `run.sh` / CLI wrapper) and documented in the
  README.

## M2 — Seed data

Built: `app/store.py` (shared write logic: the DESIGN.md validation rules and
the computed `acquisition_type`, so the seed script and the M4 admin API
behave identically), `scripts/seed.py` (canonical synthetic dataset,
re-runnable, `--reset` / `--db-path` flags), `tests/test_seed.py`,
`tests/test_store.py`.

Row counts after seeding: procedure_types 8, instruments 3,
instrument_compatible_types 9, mice 3, projects 2, users 3,
scheduled_procedures 18, scheduled_procedure_active_types 25,
scheduled_procedure_experimenters 20.

Decisions / deviations:

- **Procedure type name: full vocabulary name wins.** DESIGN.md's vocabulary
  and modality-mapping tables name the type
  `"Acute extracellular electrophysiology (modular insertion)"`, while the
  instruments seed table and Example 1 abbreviate it to
  `"Acute extracellular electrophysiology"`. The seed uses the full
  vocabulary name, so SP-4's computed `acquisition_type` is
  `"Acute extracellular electrophysiology (modular insertion) + Fiber photometry (FIP)"`
  rather than the abbreviated string shown in Example 1. Same for the
  compatibility-error message. This is a doc inconsistency, not a schema
  choice — flag it to Bruno if the shorter label is preferred.
- **Dates are offsets from the run date.** DESIGN.md's SP-1..SP-4 dates are
  read relative to the document's "today" (2026-08-03): 08-04 -> +1 day,
  08-05 -> +2, 08-07 -> +4, 08-11 -> +8, with the exact UTC times and
  durations from the table. The four canonical rows keep those exact offsets
  even if one lands on a weekend; the 14 filler rows are nudged forward off
  Sat/Sun so the calendar reads naturally.
- **18 procedures total** (4 canonical + 14 filler) spanning ~15 days across
  all three instruments, all three mice, and both projects. 7 are
  multi-platform (including Dynamic foraging + FIP) to exercise the
  multiselect. (The M2 commit message says 6 — miscount, correct number is 7.)
- **Idempotency key** for scheduled procedures is
  `(mouse_id, instrument_id, scheduled_start)`. Lookups are matched on their
  natural keys (`name` / `subject_id` / `email`). Re-running the seed changes
  nothing — verified by test, including that no new UUIDv7 tokens are minted.
  A deterministic hour-shift avoids double-booking one instrument at the same
  instant, and recognizes its own previous output on a re-run.
- **Values DESIGN.md doesn't specify** were synthesized: emails for Bruno
  Cruz and Jane Kim (only Doug's is given), placeholder ORCIDs for two users
  (deliberately invalid all-zero-prefix values so they can't be mistaken for
  real ORCIDs; one user has NULL to exercise the nullable case), and
  `ethics_review_id` / `protocols` / `planned_config` values so those fields
  are visible in the demo. `instruments.location` is left NULL — DESIGN.md's
  seed table doesn't give locations.
- **New validation rule not in DESIGN.md:** a scheduled procedure must have at
  least one active procedure type (error code `no_active_procedure_types`).
  Without it `acquisition_type` would be the empty string. Noting it since
  it's an addition; trivially removable.
- The compatibility-error message lists compatible types in `sort_order`;
  DESIGN.md's example lists them in the order they appear in that doc's seed
  table. Content is the same, order differs.

## M3 — Read API

Built: `app/schemas.py` (Pydantic v2 response models), `app/queries.py`
(read-side SQL with lookups resolved), `app/read_api.py` (the public GET
router under `/session_schedule/api`), `app/main.py` (`create_app` factory),
top-level `app.py` (CLI entry point), `tests/test_read_api.py` (29 tests).

Entry points (resolves the M1 carry-forward): both documented forms work.
`uv run python app.py [--host 0.0.0.0] [--port 8000] [--db-path ...]` — the
top-level `app.py` script coexists with the `app/` package because packages
win import precedence, so `from app.main import create_app` inside it
resolves to the package (verified by smoke test). `uv run uvicorn
app.main:app` also works: `app.main` exposes `app` as a lazy module attribute
(PEP 562 `__getattr__`) so importing the module — e.g. from tests — doesn't
create/seed the default database as a side effect.

Decisions / deviations:

- **Auto-seed on first run:** `create_app()` seeds the database if
  `procedure_types` is empty (acceptance criterion 2: populated calendar on
  first run, no separate seed step needed). Disable with
  `create_app(seed_if_empty=False)`; `scripts/seed.py` remains the explicit
  path.
- **Detail payload** (`/scheduled-procedures/{id}`, `/acquisitions/{id}`)
  includes `ethics_review_id`, `created_at`, `updated_at` in addition to
  Example 2's documented `protocols`/`notes`/`planned_config` — DESIGN.md says
  "fully resolved", and hiding audit fields helps no one. The *list* payload
  matches Example 2's shape exactly (enforced by `response_model` filtering;
  both come from the same query so they cannot drift).
- **`/api/instruments` additionally returns `compatible_procedure_types`**
  (list of `{id, name}`) — the M5 form needs the instrument -> compatible-set
  mapping to constrain its checkboxes, and "responses resolve lookups" covers
  it.
- **Filter semantics:** `*_after` is inclusive (>=), `*_before` inclusive
  (<=); the rig `planned-acquisitions` window is start-inclusive,
  end-exclusive. Naive datetimes in query params are treated as UTC.
- **`next-acquisition` semantics:** only `status = 'scheduled'` rows with
  `scheduled_start` strictly in the future qualify; 404 when the animal is
  unknown *or* has nothing upcoming (distinct messages). `animal_id` matches
  `mice.subject_id` first, falling back to the mouse UUID.
- `planned_config` is returned as parsed JSON (an object), not a string,
  matching Example 1's payload.
- Datetimes serialize as ISO-8601 UTC with a `Z` suffix to match the
  examples byte-for-byte (Pydantic's default would emit `+00:00`), so the
  models declare those fields as strings.

## M4 — Admin write API + validation

Built: `app/admin_api.py` (POST/PUT/DELETE for scheduled procedures plus
minimal creates for instruments, mice, projects, users, and
instrument-compatibility, all under `/session_schedule/api/admin`),
write request models in `app/schemas.py`, update/delete and lookup-create
functions in `app/store.py`, the `ValidationError -> 422 {"error", "detail"}`
handler in `app/main.py`, `tests/test_admin_api.py` (23 tests).

Decisions / deviations:

- **PUT is full-replace**, not a partial patch: the body has the same shape
  as POST; optional fields omitted from the body reset to null. That matches
  what a form submit sends and keeps semantics standard. `id` (the token) and
  `created_at` are immutable; `acquisition_type` and `updated_at` are always
  recomputed server-side.
- **Server-computed fields are rejected, not ignored:** the write models use
  Pydantic `extra="forbid"`, so a client-sent `acquisition_type` (or `id`,
  `created_at`, `updated_at`, or any unknown field) fails with 422 instead of
  being silently dropped. Rule 3 made visible.
- **Atomicity:** PUT updates the row and replaces both join tables inside one
  transaction; DELETE removes join rows and the row in one transaction. A
  failed PUT (e.g. incompatible type) leaves the record byte-identical —
  tested.
- **Error shape:** rejected writes return the documented
  `{"error": <code>, "detail": <message>}` with HTTP 422 (Example 1's failure
  case). Codes: `incompatible_procedure_type`, `invalid_time_range`,
  `unknown_reference`, `no_active_procedure_types`, `already_exists`,
  `invalid_planned_config`. Body-shape violations (unknown/missing fields)
  return FastAPI's standard 422 instead — two 422 flavors, both documented
  in /docs.
- **Duplicate natural keys** (instrument name, mouse subject_id, project
  name, user email) are rejected with `already_exists` (422). The
  `instrument-compatibility` endpoint is idempotent — re-declaring an existing
  pair is a no-op 201.
- DELETE returns 204 with an empty body.
- The M3 read-only OpenAPI guard test was updated to assert the actual
  contract: non-GET methods exist **only** under `/api/admin/`; the public
  data API additionally returns 405 for POST/PUT/DELETE (tested).
- **Status semantics for creates:** the admin API accepts an optional
  `status` (default `scheduled`) and allows past-dated rows — needed to
  record completed/cancelled history, and used by the verifier-advisory
  tests (status filter narrows positively; `next-acquisition` skips past and
  cancelled rows).
- Mouse ids in write bodies are the UUID primary keys, not subject_ids —
  DESIGN.md Example 1 shows `"mouse_id": "testmouse2"`, but the doc's own
  convention note says the short placeholders stand in for real UUIDs, and
  the mice seed table uses the subject_id as its placeholder id.
- **Post-verification fix (AC7 invariant):** `acquisition_type` was computed
  from the raw `active_procedure_type_ids` list while the join-row inserts
  deduped, so a repeated id in a request body could persist an inflated
  value like `"X + X"` alongside a single join row. Fixed by deduping
  (`dict.fromkeys`) in `validate_scheduled_procedure` before computing;
  regression tests cover both POST and PUT with duplicated ids.

### Advisories for the UI (recorded before building M5)

- Because the write models are `extra="forbid"`, an edit form that GETs a
  record and PUTs it back **verbatim will 422** on `id` / `created_at` /
  `updated_at` / `acquisition_type` / the resolved lookup objects. The SPA
  edit path must construct the write body explicitly (only
  `ScheduledProcedureWrite` fields), never echo the read payload.
- Naive (timezone-less) datetimes sent to the write API are interpreted as
  UTC. The SPA always sends explicit UTC (`Date.toISOString()`), so users
  type local time in the form and the API stores UTC.

## M5 — Calendar SPA

Built: `template.html` (single-file vanilla-JS SPA, house style — no build
toolchain), served at `GET /session_schedule/` by `app/main.py`;
`tests/test_spa.py` (7 server-side tests; an earlier revision of this note
said 8 — miscount).

What the page does:

- FullCalendar **resource-timeline** (day/week/month) with instruments as
  rows and events spanning scheduled_start -> scheduled_end. The Scheduler
  bundle loads from CDN (`fullcalendar-scheduler@6.1.15`) under
  `schedulerLicenseKey: 'GPL-My-Project-Is-Open-Source'` (this repo is open
  source). No fallback view was needed — resource-timeline worked directly.
- Events colored by **primary active procedure type** = the active type with
  the lowest `sort_order`, mapped to a fixed 8-color palette indexed by
  `sort_order` (stable across loads). Legend chips map color -> platform.
- Filters: platform (procedure_type_id), instrument (instrument_id), and
  date range (start_after/start_before) are passed to the API; the
  subject_id text filter is a client-side **substring** match on the fetched
  records (friendlier than the API's exact-match `subject_id` param).
- **Date-range filter semantics:** the From/To inputs constrain
  `scheduled_start` only (`start_after`/`start_before`). A multi-day
  procedure that *starts before* the From bound but overlaps the window will
  not be listed. This matches DESIGN.md's filter set (which bounds start and
  end independently, with no "overlaps" filter); with the seed's <= 6-hour
  sessions it's invisible in practice, but worth knowing for long
  procedures.
- **Post-review hardening (M5 verifier notes):** the detail panel renders
  every value via `textContent` (a tiny `{code}`/`{pre}` wrapper for the
  token and planned_config) — previously notes/planned_config beginning with
  `<` could inject markup via `innerHTML`. Read-path fetch failures
  (event-click detail, filter refetches) now surface an alert instead of
  failing silently. Tests strengthened: the submit body's actual `const
  body = {...}` block is parsed and asserted free of server-computed fields
  and record spreads, and the detail renderer is asserted innerHTML-free.
- Event click -> side panel with token id, subject, instrument (+ SIPE rig
  name), project, contact, experimenters, active platforms,
  acquisition_type, acquisition_name, schedule, ethics_review_id, protocols,
  notes, and pretty-printed planned_config.
- **Add procedure** modal per DESIGN.md; the active-type checkboxes are
  rebuilt from the selected instrument's `compatible_procedure_types`
  (server still validates). Server 422s are surfaced verbatim in the form
  (e.g. the `incompatible_procedure_type` message). An **Edit** button on the
  detail panel reuses the modal with PUT — DESIGN.md's "Add / edit" line —
  constructing the write body field-by-field per the extra="forbid" advisory
  above; `acquisition_name`/`ethics_review_id` are preserved (not editable in
  the form).
- Times: users enter local time (`datetime-local`); the page converts to UTC
  with `toISOString()` on submit and renders event times in the viewer's
  locale.
- `/` redirects to `/session_schedule/`; the page route is excluded from the
  OpenAPI schema.

Testing note: the page is browser-rendered JS, so automated tests assert the
server-side contract (200 HTML, calendar mount, CDN + license key +
resourceTimeline present, every API path referenced, filter/legend/panel/
form elements present, no server-computed fields echoed in the write path,
redirects). The create round-trip was smoke-tested live over HTTP with the
exact body shape the form submits (including JS millisecond `toISOString()`
datetimes) — 201, token minted, event visible in the list API. Browser
click-through is left for Doug's demo pass.

## M6 — Parquet export

Built: `scripts/export_parquet.py` (one Parquet file per table into
`data/parquet/`, `--db-path` / `--out-dir` flags), `tests/test_export.py`
(7 tests).

- Uses DuckDB's native Parquet writer (`COPY <table> TO ... (FORMAT
  PARQUET)`) — simplest correct path; pyarrow reads the output, which the
  round-trip tests prove (acceptance criterion 9: counts match for all nine
  tables, plus column names, values, referential integrity of the exported
  join tables, and re-export overwriting in place).
- Column names in the files are exactly the DuckDB schema names, i.e. the
  left column of DESIGN.md's Dataverse-mapping table — backfill is a direct
  field mapping.
- Representation notes for whoever does the backfill: `TIMESTAMPTZ` columns
  export as UTC-zoned Parquet timestamps (tz preserved); the
  `planned_config` JSON column exports as a JSON **string** (Parquet has no
  JSON type) — parse on import if needed.
- `pyarrow` is a direct dependency and is what the tests use to verify the
  files; the writer itself is DuckDB's, avoiding a hand-rolled
  DuckDB->Arrow conversion step.
- Exports land in `data/parquet/`, which is gitignored along with the DB
  file (synthetic, regenerated on demand).
