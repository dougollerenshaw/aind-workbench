# Build notes — procedure-scheduling prototype

## Summary (read this first)

**Status: complete and deployed.** Milestones M1–M7 (the specified build)
plus M8–M13 (tool-launcher integration and Doug's review rounds) are built and
verified; the full pytest suite (150 tests, including headless-browser smoke
tests) is green, plus 11 launcher tests,
and each milestone passed an independent verification pass. Nothing is
blocked. **If you read one more thing, read "Spec corrections found while
building" immediately below — the places where DESIGN.md's assumptions didn't
survive contact with a running system.**

**What was built** — the prototype specified in `DESIGN.md`:

- DuckDB store with all nine tables (string-UUID PKs; the
  `scheduled_procedures.id` acquisition token is a time-sortable UUIDv7),
  idempotent schema creation, single app-level connection with serialized
  writes (`app/db.py`).
- Canonical synthetic seed dataset, idempotent/re-runnable
  (`scripts/seed.py`); the app also auto-seeds an empty DB on startup.
- Read-only public API under `/session_schedule/api/...` with the full
  combinable filter set and resolved lookups, plus the three rig-facing
  endpoints (`app/read_api.py`).
- Admin write API under `/session_schedule/api/admin/...` enforcing both
  validation rules and recomputing `acquisition_type`/`updated_at`
  server-side (`app/admin_api.py`, shared rules in `app/store.py`).
- Calendar SPA at `/session_schedule/` — a hand-rolled grid (M13): day or
  week blocks stacked vertically, instrument sub-rows inside each block,
  color-by-platform legend, filters, detail panel, add/edit modal constrained
  to instrument compatibility (`template.html`). No external assets.
- Parquet export of every table for the Dataverse backfill
  (`scripts/export_parquet.py`).
- README with setup, CLI options, VM remote-access, and the Dataverse
  mapping; OpenAPI docs at `/docs` with tagged sections.

**Run it (deployed, primary):** the scheduler is mounted in the AIND tool
launcher (`projects/tool-launcher/`, M8) — on the VM it lives at
`http://10.128.142.221:8080/session_schedule/` (docs at
`.../session_schedule/docs`) alongside the other tools.

**Run it standalone (dev):**

```bash
cd projects/procedure-scheduling
uv sync
uv run python app.py            # binds 0.0.0.0:8000, auto-seeds if empty
# UI:   http://<vm_ip>:8000/session_schedule/   (hostname -I for the IP)
# Docs: http://<vm_ip>:8000/session_schedule/docs
uv run pytest                   # full test suite
uv run python scripts/seed.py --reset          # fresh demo data (optional)
uv run python scripts/export_parquet.py        # Parquet -> data/parquet/
```

**DuckDB is single-writer:** stop the app (and the tool launcher, if it has
the scheduler's DB open) before running `scripts/seed.py` or
`scripts/export_parquet.py` against the same file, or DuckDB fails with
`IOException: Could not set lock`.

**Deferred (per DESIGN.md, intentionally not built):** auto Acquisition-log
generation, cancellation/reschedule-reason capture, PowerPlatform
notifications, SmartSPIM sub-workflows, auth. No Dataverse/network
integration of any kind — local DuckDB + synthetic data only. Also
deferred: the `run.sh` convenience script and optional systemd unit
mentioned in DESIGN.md's Deployment section — the M1 notes said the entry
point question would settle it, but the scripts themselves were never
built; the tool launcher (M8) is now the actual deployment vehicle, run
under tmux per its README, so they're redundant unless someone wants the
scheduler to survive reboots independently of the launcher.

## Spec corrections found while building

`DESIGN.md` was treated as a frozen input spec and never edited, so these are
the places where its assumptions didn't survive contact with a running
system — for Doug to fold back into the doc. The first is an internal
inconsistency in the doc; the next two are domain corrections Doug made once
he could see real behavior (2026-08-04); the fourth is a structural limit of
the chosen library that only showed up in a browser (2026-08-05). The
prototype implements the corrected behavior in all four cases. This is the
prototype doing its job: turning "is this what you're looking for?" into
answers that a document alone wasn't producing.

1. **Procedure-type name inconsistency (documentation).** The vocabulary and
   modality tables call it `Acute extracellular electrophysiology (modular
   insertion)`, while the instruments seed table and Example 1 abbreviate it
   to `Acute extracellular electrophysiology`. The prototype uses the full
   vocabulary name, so SP-4's computed `acquisition_type` is longer than
   Example 1 shows. Pick one spelling. (Details: M2 notes.)
2. **A behavior rig runs exactly ONE behavior task.** The seed table gives
   `VR-Foraging-Rig-A` both Patch foraging *and* Dynamic foraging, and SP-1
   schedules dynamic foraging on it. VR foraging **is** the patch-foraging
   paradigm (`Aind.Behavior.VrForaging`). Corrected: the VR rig offers Patch
   foraging + FIP; a fourth instrument `Dynamic-Foraging-Box-1`
   (`DynamicForaging1` / `BEH-DF-01`) carries Dynamic foraging + FIP; SP-1
   moves there unchanged; and a **fourth validation rule** rejects more than
   one Behavior-modality type per procedure (`multiple_behavior_types`).
   DESIGN.md lists three validation rules and three instruments; it needs
   four of each. (Details: M10 notes.)
3. **Times in the seed table are rig-local, not UTC.** The table is labelled
   "times UTC"; read that way, SP-1's documented 09:00 renders at 02:00
   Pacific — a 2 a.m. session. The documented clock values are rig-local
   wall-clock (storage stays UTC). The line saying "times UTC" should change.
   Related: the prototype also nudges seeded rows off weekends, so day
   offsets are "first weekday at or after the offset". (Details: M12 notes.)
4. **The stated frontend stack can't express the wanted layout.** DESIGN.md
   specifies "vanilla JS + FullCalendar from CDN" with a resource-timeline
   view. FullCalendar's timeline has exactly ONE resource axis and one time
   axis, so it structurally cannot nest dates ABOVE instruments — the layout
   Doug's mockup asks for (day block -> instrument sub-rows, repeated down the
   page). Every variant was a compromise on that intent, so FullCalendar was
   dropped for a hand-rolled grid (Doug's 2026-08-05 decision). The tech-stack
   line should change. Bonus: the page now has zero external asset requests,
   so it needs no internet access in the viewer's browser. (Details: M13
   notes.)

**Notable deviations from DESIGN.md** (each detailed in its milestone
section below): no native DuckDB FK constraints (app-enforced; DuckDB's
DELETE+INSERT updates would break edits); the full vocabulary name is used
for the ephys procedure type (DESIGN.md is self-inconsistent there); seed
dates are offsets from the run date; detail payloads include
audit fields; `/api/instruments` returns the compatible-type set; write
models reject (not ignore) server-computed fields; PUT is full-replace;
Parquet files are written by DuckDB's native writer and verified with
pyarrow; the SPA's subject filter is a client-side substring match; the
date-range filter bounds `scheduled_start` only.

---

Running log of decisions and deviations, kept per milestone, follows.

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
  choice — reconcile the doc to one spelling if the shorter label is preferred.
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

Decisions / deviations:

- **Deviation from the letter of DESIGN.md/CLAUDE.md ("pyarrow for Parquet
  export"): DuckDB writes, pyarrow verifies.** The files are written with
  DuckDB's native Parquet writer (`COPY <table> TO ... (FORMAT PARQUET)`)
  instead of a hand-rolled DuckDB->Arrow conversion; pyarrow is the reader
  that proves the output (acceptance criterion 9: counts match for all nine
  tables, plus column names, values, referential integrity of the exported
  join tables, and re-export overwriting in place). CLAUDE.md explicitly
  allows either as long as pyarrow can read the result, which the tests
  demonstrate.
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

## M7 — Docs + polish

Built: `README.md` (what/why, uv setup, run + CLI options, seeding, Parquet
export, "Remote access from your Mac (VM running the app)" mirroring the
query_tool README style with the actual 0.0.0.0:8000 defaults, the port-80
options from DESIGN.md, the Dataverse mapping table + practical notes, and
test instructions). OpenAPI polish: the three router groups are tagged and
described ("Public read API", "Rig-facing (read-only)", "Admin (write)") so
`/docs` reads as a guided tour for the Dataverse team. This summary section
added at the top of BUILD_NOTES.

Small follow-ups from the M6 review folded in: the Parquet
writer-vs-reader decision is now under a labeled deviation bullet in the M6
section, and the SPA's bootstrap error handler renders via `textContent`
(the last interpolating `innerHTML`).

## M8 — Tool-launcher integration

The scheduler is now mounted in the AIND tool launcher
(`projects/tool-launcher/launcher.py`, a werkzeug `DispatcherMiddleware`
serving every internal tool on port 8080), reachable at
`http://10.128.142.221:8080/session_schedule/`. Changes on both sides:

Scheduler side (this project):

- **Package renamed `app/` -> `scheduler_app/`.** The launcher imports
  fiber-schematic-viewer's Flask app as `from app import app`; with this
  project on the same sys.path, a package named `app` (or our top-level
  `app.py`) colliding with that module would be a landmine. `scheduler_app`
  is unambiguous. The user-facing entry points are unchanged
  (`uv run python app.py`; uvicorn form is now
  `uv run uvicorn scheduler_app.main:app`). Historical references to
  `app/...` paths in the milestone notes below should be read as
  `scheduler_app/...`.
- **OpenAPI docs moved under the prefix:** `/session_schedule/docs`,
  `/session_schedule/redoc`, `/session_schedule/openapi.json` (previously
  `/docs` etc.). The launcher forwards only `/session_schedule/*` to this
  app, so everything the app serves must live under that prefix; standalone
  behavior is identical. The root `/` redirect remains for standalone
  convenience. README, template link, and tests updated.

Launcher side (`projects/tool-launcher/` — write scope explicitly widened
to this folder for M8):

- Added runtime deps to its pyproject: `a2wsgi` (ASGI->WSGI bridge),
  `fastapi`, `pydantic`, `duckdb`, `uuid-utils`, `pytz` (what
  `scheduler_app` imports at runtime; deliberately NOT `pyarrow`/`uvicorn`,
  which only the export script / standalone CLI use). `uv.lock` updated.
- `launcher.py`: the procedure-scheduling dir is **appended** (not
  inserted at the front) to sys.path, with a comment — its top-level
  `app.py` must never shadow the fiber viewer's `app` module. The FastAPI
  app is built with an absolute DB path
  (`projects/procedure-scheduling/data/procedure_scheduling.duckdb`) so the
  launcher's cwd doesn't matter, wrapped in `a2wsgi.ASGIMiddleware`, and
  mounted at `/session_schedule`.
- **Prefix shim:** `DispatcherMiddleware` strips the mount prefix into
  `SCRIPT_NAME`, but the scheduler's routes are defined WITH the
  `/session_schedule` prefix (it also runs standalone). A tiny WSGI shim
  re-prepends the prefix to `PATH_INFO` (and empties `SCRIPT_NAME`) before
  calling the wrapped app.
- **Lazy creation:** the werkzeug reloader (`use_reloader=True`) imports
  `launcher.py` in BOTH the watcher process and the serving child; opening
  DuckDB at import time in both would fail (single-writer file lock). The
  scheduler app is therefore created on the first request, which only ever
  happens in the serving child. Schema creation stays idempotent and
  auto-seed only fires on an empty DB, so reloads are safe.
- Landing page `<li>` and the startup print list gained the scheduler
  entry.

Operational note (also in the README): the launcher holds the scheduler's
DuckDB open once it has served a scheduler request — stop it before running
`scripts/seed.py` / `scripts/export_parquet.py` on the default DB.

## M9 — First-browser-pass fixes (modal CSS bug + duration input)

**Bug (blocking): the add/edit modal was permanently open.** Root cause:
the stylesheet declared `#modal-backdrop { display: flex; ... }`. Any
author `display` rule beats the UA stylesheet's `[hidden] { display: none }`,
so the `hidden` attribute (set in the markup and toggled by
`openModal`/`closeModal`) had no effect — the modal was visible from page
load and Cancel/Create appeared to do nothing. Fix: the rule is now
`#modal-backdrop:not([hidden]) { ... }`, so the flex layout only applies
when the element is shown. A stylesheet audit confirmed the backdrop was
the only element toggled via `.hidden` that also had an author `display`
rule (`#detail-panel` has none). A static regression test now parses the
CSS and asserts every `.hidden`-toggled id either has no author `display`
rule or guards it with `[hidden]`, and that the specific
`:not([hidden])` fix is present.

**Lesson learned:** this is exactly the class of bug server-side tests
structurally cannot catch — every DOM/wiring assertion passed while the
rendered page was unusable. It took Doug's first real browser pass to see
it. Anything beyond static page-contract checks needs an actual browser
(even one manual pass, or Playwright if this outlives the prototype).

**Feature (Doug's request): duration instead of explicit end time.** (see
also M10 below) The
form now takes Scheduled start (datetime-local, as before) + Duration in
hours (numeric, step 0.25, min 0.25, default 2). The client computes
`scheduled_end = start + duration` before POST/PUT — the API contract is
unchanged (the server still receives and validates `scheduled_start` +
`scheduled_end`; no server changes). Edit mode derives the duration field
from the record's `end - start`. A live hint under the fields shows the
computed end time in local time.

## M10 — Domain correction: one behavior task per rig

**A domain error in the spec.** DESIGN.md's seed table and its
SP-1 example encode a mistake: they put **both** behavior tasks (Patch
foraging *and* Dynamic foraging) on `VR-Foraging-Rig-A`. Per Doug's
2026-08-04 ruling, a behavior rig runs exactly **one** behavior task, VR
foraging **is** the patch-foraging paradigm (Bruno's
`Aind.Behavior.VrForaging`), and no procedure ever runs two behavior tasks
simultaneously. The prototype now **deliberately diverges from DESIGN.md**
on the following points; DESIGN.md itself was left untouched (it's the
frozen input spec) and these are the amendments it needs:

1. **`VR-Foraging-Rig-A` compatible set** — was Patch foraging + Dynamic
   foraging + FIP; **now Patch foraging behavior + Fiber photometry (FIP)**.
   Dynamic foraging removed.
2. **New instrument added: `Dynamic-Foraging-Box-1`**
   (`instrument_id` = `DynamicForaging1`, `sipe_rig_name` = `BEH-DF-01`),
   compatible with **Dynamic foraging behavior + Fiber photometry (FIP)** —
   so dynamic foraging still appears in the demo, on a rig that can actually
   run it. DESIGN.md's seed table lists only three instruments; the
   prototype now seeds four.
3. **`SmartSPIM-1` and `Ephys-Rig-2` unchanged.** Ephys-Rig-2 keeps Patch
   foraging behavior — a behavior task on an ephys rig is fine, that's still
   *one* behavior task (optionally alongside ephys and/or FIP).
4. **SP-1 relocated.** DESIGN.md's SP-1 is "Dynamic foraging + FIP on
   VR-Foraging-Rig-A", which is now illegal. It moved to
   `Dynamic-Foraging-Box-1`; mouse, project, contact, experimenter, times,
   active types, and computed `acquisition_type` are all unchanged, so the
   canonical multi-modality example survives. Consequently the documented
   rig-facing example for SP-1 is served under `BEH-DF-01`, not `BEH-VR-01`.
   No other seed row needed moving except four filler dynamic-foraging rows,
   which moved to the same box; every remaining row was re-checked against
   the new sets and the new rule.
5. **New validation rule (an addition beyond DESIGN.md's three):** at most
   **one** active procedure type whose `modality_name` is `"Behavior"` per
   scheduled procedure. Rejected with the standard error shape and code
   `multiple_behavior_types`, naming the conflicting types. It lives in
   `scheduler_app/store.py`'s shared validate path, so seed and API enforce
   it identically. Keyed on `procedure_types.modality_name` (not hardcoded
   task names) so it generalizes to any behavior task added later.
   Cross-modality combos (behavior + FIP, ephys + FIP) remain allowed.

Supporting changes: `/api/instruments` now includes `modality_name` in each
`compatible_procedure_types` entry, and the form disables + visually mutes
the other Behavior-modality checkboxes once one is checked (server remains
the authority; the UI is guidance).

Seeded dataset after the correction: 4 instruments / 10 compatibility rows /
18 procedures — Dynamic-Foraging-Box-1 5, SmartSPIM-1 5, VR-Foraging-Rig-A 4,
Ephys-Rig-2 4; zero rows with two behavior tasks.

## M11 — Calendar usability (default day view, realistic seeded times)

Doug's browser pass: the default `resourceTimelineWeek` rendered a week at
hour resolution — 168 columns — so "now" sat far off-screen to the right,
with no current-time line and a seeded event at 2 a.m.

- **Default view is now `resourceTimelineDay`**, opening on today
  (`initialDate: new Date()`): instruments as rows, one day across the page
  at hour resolution, limited to a working-hours window so it fits with no
  horizontal scrolling. `nowIndicator` draws the live current-time line and
  `scrollTime` starts an hour before now.
- **`WORKING_HOURS = { start: '06:00:00', end: '20:00:00' }`** — a single
  named constant at the top of the calendar section of `template.html`,
  trivially adjustable.
- **Out-of-window events are reported, never silently hidden.** Verified
  behavior: FullCalendar does **not** render events lying entirely outside
  `slotMinTime..slotMaxTime`. Rather than widen the window to swallow every
  edge case, the page (a) applies the window to the **day view only**, so
  Week and Month always show every event, (b) counts events on the displayed
  day that fall outside the window and says so in a notice under the
  calendar, and (c) offers a **"Show full 24 h"** checkbox that drops the
  window entirely. Nothing is unreachable.
- **Week and month now use day-resolution columns** (`slotDuration:
  { days: 1 }`) — 7 and ~30 columns that fit on screen, instead of 168 hour
  columns. Local time-of-day moved into the event label (`eventContent`) so
  the day-columns still say when a procedure runs, and today's column is
  highlighted via `.fc-day-today`. The three existing view buttons are
  unchanged; no list/agenda view was added.
- **Seeded times are now working-hours-constrained.** The 14 filler rows are
  written as **local** wall-clock times inside `WORKING_DAY_START..
  WORKING_DAY_END` (07:00–18:00) on weekdays, then converted to UTC for
  storage (the DB is always UTC). This is the real fix for the 2 a.m.
  session: the browser renders local time, so a filler row written at 09:00
  *UTC* appeared at 02:00 Pacific. One row (SmartSPIM, 5 h) moved from 14:00
  to 12:00 so it ends inside the window. The existing weekday nudge is kept.

**RESOLVED (M12) — see the M12 section below.** M11 left the canonical rows'
times read as UTC pending Doug's call; on 2026-08-04 he ruled that documented
clock values are **rig-local**, which is now the single behavior. All 18
seeded rows land inside local working hours.

## M12 — Timezone rule: documented clock times are rig-local

**Doug's decision, 2026-08-04:** the clock values in DESIGN.md's seed table
are **rig-local wall-clock**, not UTC. SP-1's documented 09:00 means 9 a.m. at
the rig. Reading them as UTC put the flagship example at 02:00 Pacific — the
2 a.m. session from the first browser pass.

What changed:

- `scripts/seed.py` has **one** start-time helper (`_weekday_local_start`)
  used by canonical and filler rows alike: local wall-clock -> UTC for
  storage. The M11 `CANONICAL_TIMES_ARE_UTC` switch was **removed** rather
  than flipped — a lingering boolean with two supported timezone meanings is
  exactly the confusion that produced this bug.
- **Canonical rows are now weekday-nudged too.** SP-3 (day+4) landed on a
  Saturday whenever the seed ran on a Tuesday or Wednesday; a Saturday
  histology session makes the demo look wrong. The cost is that DESIGN.md's
  exact day offsets become "the first weekday at or after the offset" on some
  run dates — a better trade than a weekend session, and the documented clock
  times and durations are preserved exactly.
- **Slot-collision fix (found by this change):** nudging a canonical row can
  drop it onto a filler row's slot for the same mouse and rig — SP-3 and a
  filler both wanted SmartSPIM-1 at 10:00 on the same Monday when seeding from
  a Tuesday — and the natural-key dedupe silently skipped one, yielding 17
  rows instead of 18. Seeding now distinguishes "slot already in the database
  from an earlier run" (skip, keeping re-runs idempotent) from "two specs want
  one slot in this run" (shift an hour). Verified: exactly 18 rows, all inside
  weekday working hours, idempotent on re-run, from **all seven** reference
  weekdays.

**Known cosmetic artifact:** because the shifter moves a colliding row by an
hour rather than out of the way entirely, weekday nudging can leave two
sessions *overlapping* on one instrument (e.g. SmartSPIM-1 10:00–16:00 and
11:00–15:00 on the same Monday). This is deliberate: DESIGN.md defines no
non-overlap rule, a scheduler should be able to represent a genuine
double-booking, and FullCalendar stacks the bars legibly within the
instrument's row. If Doug wants the seed to avoid it, the fix is to push the
later row to the next weekday rather than the next hour.

### Timezone audit (M12 task 1)

Every place a conversion happens, and whether it agrees with "documented
clock values are rig-local":

| Place | Behavior | Consistent? |
|---|---|---|
| `scripts/seed.py` | local wall-clock -> UTC on write | ✔ the rule |
| DuckDB storage / API responses | UTC always, ISO-8601 with `Z` | ✔ unambiguous |
| SPA add/edit form | `datetime-local` (local) -> `toISOString()` (UTC) | ✔ |
| SPA calendar rendering | renders UTC instants in viewer-local time | ✔ |
| SPA date-range filter | **was** a bug — see below | ✔ now fixed |
| Admin write API, naive datetime | treated as **UTC** | ⚠ see below |

- **Fixed here — SPA date-range filter.** The From/To inputs are local
  calendar dates, but the page sent `${date}T00:00:00Z` / `T23:59:59Z`, i.e.
  UTC-midnight bounds. In Pacific that shifted the window seven hours: a "To"
  date silently excluded every procedure after 16:59 local. Now converts local
  midnight / end-of-day to UTC instants (`localDayStart` / `localDayEnd`),
  covered by a test.
- **Remaining ambiguity, deliberately left — naive datetimes on the write
  API.** `ensure_utc()` treats a datetime with no offset as UTC, so
  `POST {"scheduled_start": "2026-09-01T09:00:00"}` means 09:00 **UTC**, which
  in Pacific stores 02:00 local — the opposite of the seed's convention for
  the same-looking string. It is not a bug for any current caller (the SPA
  always sends explicit `Z`), and treating naive input as server-local would
  make the API's meaning depend on the host's timezone, which is worse for an
  API. **Recommendation for the real system: reject naive datetimes outright**
  (require an explicit offset) rather than guessing. Flagged rather than
  silently changed.

## M13 — Calendar rebuild: hand-rolled grid, FullCalendar dropped

**Deviation from DESIGN.md's tech stack, deliberately** (see spec correction 4
above). DESIGN.md says "vanilla JS + FullCalendar from CDN"; the FullCalendar
part is gone as of Doug's 2026-08-05 decision. Reason: his mockup nests dates
ABOVE instruments — a day header, then one sub-row per rig, then the next day
below — and FullCalendar's timeline has exactly one resource axis, so it
cannot express that. M11/M12 were successive compromises on the same intent;
this replaces the library rather than the intent. The rest of the stated stack
(vanilla JS, no build toolchain, no bundler) is unchanged and now more
literally true.

What the grid does:

- **Vertical stack of blocks.** Day view: one block per day (`Wednesday
  August 5`, today badged and tinted), each containing one sub-row per
  instrument. Week view: the same machinery with one block per week.
- **One shared horizontal scroll container.** Every block lives inside a
  single `#grid-scroll`, so blocks scroll together by construction and there
  is exactly one scrollbar — no per-block scrollbars to get out of sync. It
  scrolls vertically too (blocks stack inside it), which is what lets the
  hour axis stick to the top and the instrument labels stick to the left in
  the same box.
- **Day view horizontal focus:** hour columns are sized so `FOCUS_START_HOUR`
  (8) to `FOCUS_END_HOUR` (18) exactly fill the visible lane width, with the
  full 24 h rendered and the initial `scrollLeft` at 8am. Nothing is hidden —
  early/late hours are off-viewport and scroll into view. (Contrast M11,
  where FullCalendar's `slotMinTime` genuinely *dropped* out-of-window
  events; that whole notice/24h-toggle mechanism is now unnecessary and gone.)
- **Week view:** 7 day columns sized to fit the viewport exactly, so a full
  week never scrolls horizontally. Bars sit in their day's column labelled
  with the local start time; several procedures on one rig and day share the
  column side by side.
- **Bars** are positioned by start time and sized by duration (day view),
  colored by primary active platform from the existing `sort_order` palette,
  and labelled `subject_id · acquisition_type` (day) or `time subject_id`
  (week), truncated with ellipsis. Non-`scheduled` statuses are dimmed and
  cancelled ones struck through. Click still opens the unchanged detail panel.
- **Now-indicator:** one continuous line across today's block, repositioned
  every minute.
- **Today at top on load** (`scrollToToday`), with `WINDOW_DAYS_BEFORE = 14`
  rendered above it, so scrolling up really does reveal past days, and
  `WINDOW_DAYS_AFTER = 45` below.
- **Empty blocks show by default** (gaps read as real calendar gaps) with a
  "Hide empty days" checkbox, since most days have few sessions across four
  rigs.
- **Instrument filter removes sub-rows** rather than leaving them empty —
  Doug's primary interaction.

**Month view dropped.** In this model a month block would be ~30 day columns
of instrument sub-rows: either cramped to unreadability or horizontally
scrolling, which is the problem week view was fixed to avoid. Day and week are
what Doug asked for, so the third button is gone rather than shipping
something broken. The stacked-block machinery would take a month view cheaply
if it's ever wanted (one more `blockRange()` branch).

**No external assets.** Verified: the served page contains no `src`/`href` to
another host, no `@import`, no remote `url()`, and every `href` is a
same-origin path. The page therefore works with no internet access in the
viewer's browser — which removes a real demo risk (the CDN bundle was a
single point of failure on a locked-down or offline machine) and is enforced
by a test.

**What was preserved unchanged:** all five filters including the M12
local-day-bounds fix, the legend, the detail side panel, the add/edit modal
(M9 hidden-attribute CSS fix, duration field, M10 behavior-type exclusivity),
and the server-computed-fields discipline in the write body.

**Verification honesty.** This is a from-scratch layout, so the static tests
prove the wiring exists and is internally consistent — not that it looks
right. Pixel geometry (column widths, sticky offsets, bar placement,
scroll-together behavior) can only really be confirmed in a browser, and that
pass is Doug's. Specific things worth his eye are listed in the M13 report.

## M14 — Blank calendar: root cause, and why 133 tests couldn't see it

**The headline lesson.** 133 static tests were green while the calendar
rendered a completely blank box in a real browser. Assertions on HTML *text*
cannot see a rendered page: they confirm that code exists, never that it
works. This is the **third** UI bug found by a human looking at the screen
(modal stuck open, filter timezone bounds, blank grid) and the first that made
the page unusable. Browser-level smoke tests now exist precisely because this
class of failure is invisible to everything else in the suite:
`tests/test_browser_smoke.py` drives real headless Firefox and asserts on DOM
state, so a blank page fails the suite.

### The bug the reproduction actually found

Instrumented the page (error handlers + progress markers via `dump()`), served
it through a proxy so the absolute API paths resolved, and ran headless
Firefox. The page rendered fine against a freshly seeded DB *and* against the
live database — so the blank state did not reproduce that way. What did
reproduce, instantly, when the new browser test drove the app under **uvicorn**:

```
IndexError: tuple index out of range
  scheduler_app/queries.py:314  in fetch_instruments
    "sipe_rig_name": r[3],
```

**Root cause: a single DuckDB connection shared across threads.** The whole app
used one `DuckDBPyConnection`. A `DuckDBPyConnection` is not safe for
concurrent use — simultaneous `execute`/`fetchall` calls interleave on the same
result state and hand back rows of the wrong width. FastAPI runs sync endpoint
functions in a threadpool, and the calendar fires **five** lookup requests at
once on load, so those five raced on one connection: rows came back short,
`r[3]` blew up, the endpoint 500'd, and the page's `Promise.all` rejected —
leaving every lookup array empty. That produces *exactly* the reported
symptoms: blank grid with no legend, and "No instruments match the current
filter" once a view button forces a re-render.

Fixed in `scheduler_app/db.py`: `Database.conn` now returns a **per-thread
cursor** (`self._conn.cursor()`, cached in `threading.local()`), so each thread
has its own result state. Writes still go through `write()` on the base
connection under the lock. M1's design serialized *writes* only — reads were
assumed safe to share, which is where this hid for 13 milestones.

**Honest caveat on attribution.** Through the tool launcher this bug is
*masked*: werkzeug's dev server runs `threaded=False`, so requests are
serialized and never race (verified: 30 concurrent bootstrap requests against
live :8080 all returned 200, before and after the fix). It reproduces
deterministically under uvicorn, i.e. standalone `uv run python app.py`. So
this is certainly a real bug with the right symptoms, but I could not prove it
is the one Doug hit on :8080, and I could not reproduce his blank page in
headless Firefox against his data. The hardening below is what makes the next
occurrence self-diagnosing instead of mysterious.

### Two more real bugs the browser found

Both were invisible to static tests and are now covered by browser assertions:

- **Day headers were invisible.** `.day-header` had `position: sticky;
  left: 0`, but sticky on a *full-width* box does nothing — the box never
  leaves the scrollport, so the text just sat at its far-left edge, ~1000px
  off-screen once the day view scrolled to 8am. Every block therefore showed
  an empty grey band where "Wednesday, August 5" belonged. Fixed by making the
  band static and its **label** the narrow sticky child.
- **Week view scrolled horizontally by ~15px.** Lane widths are measured from
  `clientWidth`, then rendering makes the content tall enough to add a
  vertical scrollbar, which *shrinks* `clientWidth` after the fact. Fixed with
  `overflow-y: scroll` (not `auto`) so the scrollbar is always reserved and
  the measurement stays valid.

### Bootstrap hardening (a failure must be loud, and must not blank the page)

- The five lookup fetches now settle **independently** (`Promise.allSettled`)
  instead of one all-or-nothing `Promise.all` destructure. Whatever arrives is
  used; the page renders what it can.
- Failures appear in a **loud red banner** at the top of the grid area naming
  each failed dependency and its error, e.g. *"Could not load: instruments
  (/session_schedule/api/instruments -> HTTP 503)."* Verified by simulating a
  503: the banner appears and the rest of the page still renders.
- `window.error` / `unhandledrejection` handlers also raise the banner, so
  nothing fails silently. Previously the only report went to the small grey
  status line at the bottom of the grid — which a view-button click then
  overwrote, which is why Doug never saw an error.
- Every read retries once after 500 ms, so a single transient hiccup (the
  launcher serves requests one at a time, so a burst can queue) no longer
  costs a whole dependency.
- The status line and per-block note distinguish "instruments failed to load"
  from "no instruments match the filter".

### The new test modules

- **`tests/test_browser_smoke.py`** (9 tests) — starts the app on an ephemeral
  port against a temp seeded DB, serves the real `template.html` through a
  proxy with two observation-only scripts injected (an error recorder in
  `<head>`, a DOM probe at the end of `<body>`), and drives headless Firefox,
  reading the probe's JSON off stdout via `dump()`. Asserts: zero JS
  errors/rejections, no failure banner, 8 legend chips, day blocks and
  instrument sub-rows and event bars all > 0 with real pixel width, a 24-hour
  axis scrolled to the focus hour, today marked with a now-line, sticky labels
  actually on screen, and a 7-column week view with no horizontal overflow.
  No clicking is required for the day view. Skips with a clear reason if no
  Firefox binary exists, so `uv run pytest` still works without one. ~15 s.
- **`tests/test_concurrency.py`** (4 tests) — the fast Python-level regression
  for the root cause: the five bootstrap endpoints fired together repeatedly,
  instrument payload shape checked under load, mixed endpoints hammered, and a
  store-level check that concurrent queries of different row widths never
  interleave. **Verified these fail on the buggy version**: reverting
  `Database.conn` to the shared connection turns all four red (and the browser
  tests error out with the page never rendering); restoring the fix turns them
  green.

## M15 — Calendar refinements: off-hours/weekend shading, Sunday-first week

Three requests from Doug, all in `template.html`:

- **Day view tints the off-hours columns** (before 8am, after 6pm) with a light
  `rgba(92,100,112,0.10)` band. The hours stay fully real and scrollable — the
  tint is background only, drawn *under* the rows (`.col-shade` at `z-index: 0`,
  `.instrument-row` at `z-index: 1`, `pointer-events: none`), so bars,
  gridlines, the now-line and text keep their normal contrast and a procedure
  scheduled at 2am does not look disabled. Verified in a browser: bar opacity
  stays `1` with no filter.
- **Week view tints the Saturday and Sunday columns**, same treatment.
- **Week view is Sunday-first** (Sun → Sat).

The shaded ranges are **derived, never hardcoded twice**:
`shadedRanges()` builds the day-view bands from `FOCUS_START_HOUR` /
`FOCUS_END_HOUR`, so the tint and the focus lane cannot disagree, and the
weekend columns come from `WEEKEND_DAYS` mapped through `WEEK_STARTS_ON`. A
static test asserts there is no second literal 8 or 18 in that function.

Sunday-first touched everything that encoded the old Monday assumption, all now
driven by one constant `WEEK_STARTS_ON = 0`:

- `startOfWeek()` — `(getDay() - WEEK_STARTS_ON + 7) % 7`, replacing the
  Monday-biased `(getDay() + 6) % 7`.
- The axis labels (generated from `startOfWeek`, so they follow automatically).
- The block label, which now names the whole span —
  *"Week of Sun, Aug 2 – Sat, Aug 8"* — so a Sunday-first week is unambiguous
  rather than just "Week of August 2".
- "This week" (`isCurrent`), bar day-column placement, and the week now-line
  offset, all of which route through `startOfWeek`.

Tests: the browser smoke module grew from 9 to 13 tests and asserts the
**rendered** result, not the CSS text — that each off-hours/weekend axis cell
carries the `shaded` class *and* a non-transparent computed background, that
in-hours/weekday cells have neither, that two tint bands with real width are
drawn per block under the rows, that bars are not dimmed, and that the week
axis is exactly `[Sun, Mon, Tue, Wed, Thu, Fri, Sat]` with tinting on columns
0 and 6 only. The static suite's Monday-first assertions were replaced with
Sunday-first ones.

## M17 — Incident: a broken working tree took down four unrelated tools

**What happened (2026-08-10).** An in-progress round of work in this project was
left uncommitted and unimportable: `scheduler_app/read_api.py` referenced a
`SubjectLookupOut` response model whose definition was never written (the edit
that would have added it to `schemas.py` never landed). `projects/tool-launcher/
launcher.py` imported `scheduler_app` **at module scope**, so the NameError
raised at startup killed the launcher process. Doug's live service at :8080 was
down — and not just the scheduler: **query_tool, fiber_schematic_viewer,
upgrader and iacuc_lookup went with it**, four tools with no connection to this
project. A second fault appeared in the same log: werkzeug's reloader watches
every `.py` in each mounted project, so editing a test file here
(`tests/test_browser_smoke.py`) restart-looped his live service.

That work is parked as a git stash and is **not** being resumed — it is
deliberately left alone.

**The rule this leaves behind, and it is the important part:** the launcher
imports this project *from the live working tree*, so any moment the tree is
unimportable is a production outage for every tool on that launcher. Never end
an edit — let alone a session — with the tree in a non-importable state. After
touching `scheduler_app/*.py`, check immediately:

```bash
uv run python -c "from scheduler_app.main import create_app"
```

**What was added here (M17):**

- `tests/test_imports.py` — walks every module under `scheduler_app` and
  imports it, plus the launcher's exact mount import, the standalone `app.py`
  entry, and the scripts. A missing symbol now fails in pytest in ~1.5 s
  instead of in Doug's browser. 133+ tests had passed with the tree in a state
  that could not be imported at all, because nothing had ever tried.

The launcher-side hardening (fail-soft mount, scoped reloader) lives in
`projects/tool-launcher/` and is documented in its README: the scheduler mount
now defers *and guards* its import, serving a plain-text 503 at
`/session_schedule/` while the other four tools keep working, retrying after 30
seconds so a fixed tree recovers without a restart.

**Note on the calendar:** the calendar prototype is preserved at git tag
`calendar-prototype-v1` (commit 307ea6f) should anyone want it back.

### Re-seeding the live database (Doug runs this when ready)

**This supersedes the sequences in the M10/M11 notes — one run covers all of
M10 + M11 + M12.** Seeding is idempotent, so a plain re-run will NOT pick up
these changes; `--reset` is required. It needs the launcher stopped, because
DuckDB is single-writer.

What the re-seed brings in that the live database does not have yet:

- M10: the fourth instrument `Dynamic-Foraging-Box-1`, the corrected
  compatibility sets (VR rig loses Dynamic foraging), SP-1's relocation.
- M11/M12: every procedure on a weekday inside local working hours
  (07:00–18:00), with documented clock times read as rig-local.

**`--reset` wipes every table, discarding any procedures created through the
UI.** Everything in `template.html` (the M9 modal fix and duration input, the
M11 day-view calendar, the M12 filter fix) is read per request and is already
live — no restart and no re-seed needed for those.

```bash
# 1. stop the launcher (in its tmux session: Ctrl-C, or)
pkill -f "launcher.py"

# 2. reset + re-seed the scheduler's database  (WIPES existing rows)
cd ~/code/aind-workbench/projects/procedure-scheduling
uv run python scripts/seed.py --reset

# 3. restart the launcher
cd ../tool-launcher
uv run python launcher.py          # or inside tmux: tmux new -s tools
```

Then reload `http://10.128.142.221:8080/session_schedule/`. Expect: four
instrument rows including Dynamic-Foraging-Box-1, one working day across the
page with the current-time line, and every seeded session between 07:00 and
18:00 on a weekday — no 2 a.m. or Saturday sessions.
