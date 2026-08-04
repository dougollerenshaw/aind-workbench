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
