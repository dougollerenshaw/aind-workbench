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
  all three instruments, all three mice, and both projects. 6 are
  multi-platform (including Dynamic foraging + FIP) to exercise the
  multiselect.
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
