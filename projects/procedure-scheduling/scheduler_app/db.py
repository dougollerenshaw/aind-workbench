"""DuckDB store for the procedure-scheduling prototype.

Implements the schema from DESIGN.md "Data model":

- ``procedure_types``   — shared vocabulary of acquisition platforms/procedure
  types, with the aind-data-schema modality mapping (name + abbreviation).
- ``instruments``       — rigs/instruments, carrying the aind-data-schema
  ``instrument_id`` and the SIPE rig name used by rig-facing lookups.
- ``instrument_compatible_types``          — join: instrument <-> procedure_type
  ("Compatible Acquisition Platforms").
- ``mice``, ``projects``, ``users``        — minimal lookup tables.
- ``scheduled_procedures``                 — the main table; its ``id`` is a
  time-sortable UUIDv7, the persistent acquisition token.
- ``scheduled_procedure_active_types``     — join: scheduled_procedure <->
  procedure_type ("Active Acquisition Platforms").
- ``scheduled_procedure_experimenters``    — join: scheduled_procedure <-> user.

Conventions:

- All primary keys are string UUIDs (they map onto Dataverse GUIDs).
  ``scheduled_procedures.id`` specifically is a UUIDv7 so rows sort by
  creation time on the id alone.
- Datetimes are timezone-aware (``TIMESTAMPTZ``); the app always writes UTC.
- Foreign-key relationships are documented in the DDL comments and enforced
  in the application layer rather than as native DuckDB FOREIGN KEY
  constraints. DuckDB implements UPDATE as DELETE + INSERT, so a row that is
  referenced by a declared FK (e.g. a scheduled procedure referenced by its
  join-table rows) cannot be updated in place — which would break legitimate
  edits from the admin API. See BUILD_NOTES.md.

DuckDB is single-writer, so the app shares one connection and serializes all
writes through ``Database.write()``.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from uuid import uuid4

import duckdb
import uuid_utils

# Default on-disk location: <project>/data/procedure_scheduling.duckdb
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "procedure_scheduling.duckdb"

STATUS_VALUES = ("scheduled", "completed", "cancelled", "rescheduled")

# Every table in the schema, in dependency order (lookups first).
TABLES = [
    "procedure_types",
    "instruments",
    "instrument_compatible_types",
    "mice",
    "projects",
    "users",
    "scheduled_procedures",
    "scheduled_procedure_active_types",
    "scheduled_procedure_experimenters",
]

SCHEMA_SQL = """
-- Vocabulary of acquisition platforms / procedure types, with the
-- aind-data-schema modality each one maps onto.
CREATE TABLE IF NOT EXISTS procedure_types (
    id                    VARCHAR PRIMARY KEY,          -- UUID string
    name                  VARCHAR NOT NULL UNIQUE,      -- AIND-internal label, e.g. "Dynamic foraging behavior"
    modality_name         VARCHAR NOT NULL,             -- aind-data-schema modality name, e.g. "Behavior"
    modality_abbreviation VARCHAR NOT NULL,             -- aind-data-schema modality abbreviation, e.g. "behavior"
    sort_order            INTEGER NOT NULL              -- stable display/color ordering
);

CREATE TABLE IF NOT EXISTS instruments (
    id            VARCHAR PRIMARY KEY,                  -- UUID string
    name          VARCHAR NOT NULL UNIQUE,              -- display name, e.g. "VR-Foraging-Rig-A"
    instrument_id VARCHAR,                              -- aind-data-schema instrument_id, e.g. "EPHYS2"
    sipe_rig_name VARCHAR,                              -- SIPE env-var rig/computer name (rig-facing "rig_id")
    location      VARCHAR,                              -- optional room/rig location
    active        BOOLEAN NOT NULL DEFAULT TRUE         -- soft-hide retired instruments
);

-- Join: "Compatible Acquisition Platforms" per instrument.
CREATE TABLE IF NOT EXISTS instrument_compatible_types (
    instrument_id     VARCHAR NOT NULL,                 -- FK -> instruments.id (application-enforced)
    procedure_type_id VARCHAR NOT NULL,                 -- FK -> procedure_types.id (application-enforced)
    PRIMARY KEY (instrument_id, procedure_type_id)
);

CREATE TABLE IF NOT EXISTS mice (
    id         VARCHAR PRIMARY KEY,                     -- UUID string
    subject_id VARCHAR NOT NULL UNIQUE,                 -- AIND subject id (aind-data-schema aligned)
    genotype   VARCHAR                                  -- optional
);

CREATE TABLE IF NOT EXISTS projects (
    id   VARCHAR PRIMARY KEY,                           -- UUID string
    name VARCHAR NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS users (
    id    VARCHAR PRIMARY KEY,                          -- UUID string
    name  VARCHAR NOT NULL,                             -- feeds acquisition `experimenters` (name strings)
    email VARCHAR NOT NULL UNIQUE,
    orcid VARCHAR                                       -- optional; maps user -> aind-data-schema Person
);

-- Main table. `id` is the persistent acquisition token: a UUIDv7 minted at
-- scheduling time, immutable, carried into acquisition and downstream steps.
CREATE TABLE IF NOT EXISTS scheduled_procedures (
    id               VARCHAR PRIMARY KEY,               -- UUIDv7 string (time-sortable)
    mouse_id         VARCHAR NOT NULL,                  -- FK -> mice.id (application-enforced)
    instrument_id    VARCHAR NOT NULL,                  -- FK -> instruments.id (application-enforced)
    project_id       VARCHAR NOT NULL,                  -- FK -> projects.id (application-enforced)
    contact_user_id  VARCHAR NOT NULL,                  -- FK -> users.id (scientific contact)
    scheduled_start  TIMESTAMPTZ NOT NULL,
    scheduled_end    TIMESTAMPTZ NOT NULL,
    acquisition_type VARCHAR NOT NULL,                  -- server-computed: sorted active type names, " + "-joined
    acquisition_name VARCHAR,                           -- secondary human-readable dated name; NULL until acquisition
    status           VARCHAR NOT NULL DEFAULT 'scheduled'
        CHECK (status IN ('scheduled', 'completed', 'cancelled', 'rescheduled')),
    ethics_review_id VARCHAR,                           -- IACUC / ethics protocol number
    notes            VARCHAR,                           -- free-form notes
    planned_config   JSON,                              -- platform-specific planned settings (free-form)
    protocols        VARCHAR,                           -- which protocol(s) should run, human-readable
    created_at       TIMESTAMPTZ NOT NULL,
    updated_at       TIMESTAMPTZ NOT NULL,
    CHECK (scheduled_end > scheduled_start)             -- backstop; the API validates before writing
);

-- Join: "Active Acquisition Platforms" for the session.
CREATE TABLE IF NOT EXISTS scheduled_procedure_active_types (
    scheduled_procedure_id VARCHAR NOT NULL,            -- FK -> scheduled_procedures.id (application-enforced)
    procedure_type_id      VARCHAR NOT NULL,            -- FK -> procedure_types.id (application-enforced)
    PRIMARY KEY (scheduled_procedure_id, procedure_type_id)
);

-- Join: experimenter(s) assigned to the session (in addition to the contact).
CREATE TABLE IF NOT EXISTS scheduled_procedure_experimenters (
    scheduled_procedure_id VARCHAR NOT NULL,            -- FK -> scheduled_procedures.id (application-enforced)
    user_id                VARCHAR NOT NULL,            -- FK -> users.id (application-enforced)
    PRIMARY KEY (scheduled_procedure_id, user_id)
);
"""


def new_uuid() -> str:
    """A random UUID (v4) string — for lookup-table primary keys."""
    return str(uuid4())


def new_uuid7() -> str:
    """A time-sortable UUIDv7 string — for scheduled_procedures.id.

    Uses the ``uuid-utils`` library (stdlib ``uuid.uuid7`` requires
    Python >= 3.14).
    """
    return str(uuid_utils.uuid7())


def utcnow() -> datetime:
    """Current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def create_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create all tables if they do not exist. Idempotent — safe to re-run."""
    conn.execute(SCHEMA_SQL)


def list_tables(conn: duckdb.DuckDBPyConnection) -> list[str]:
    """Names of the tables present in the main schema."""
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'main' ORDER BY table_name"
    ).fetchall()
    return [r[0] for r in rows]


class Database:
    """A single app-level DuckDB connection with serialized writes.

    DuckDB is single-writer, so the whole app shares one connection and all
    writes go through the :meth:`write` context manager, which holds a lock
    and wraps the work in a transaction.
    """

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(self.db_path))
        self._write_lock = threading.Lock()
        create_schema(self._conn)

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        """The shared connection (fine for reads; use write() for writes)."""
        return self._conn

    @contextmanager
    def write(self) -> Iterator[duckdb.DuckDBPyConnection]:
        """Serialize a write: take the lock and run inside a transaction."""
        with self._write_lock:
            self._conn.begin()
            try:
                yield self._conn
            except BaseException:
                self._conn.rollback()
                raise
            else:
                self._conn.commit()

    def close(self) -> None:
        self._conn.close()


# ---------------------------------------------------------------------------
# App-level singleton (the FastAPI app and scripts share one Database).
# ---------------------------------------------------------------------------

_db: Database | None = None
_db_lock = threading.Lock()


def get_db(db_path: str | Path | None = None) -> Database:
    """Return the shared Database, creating it on first call.

    ``db_path`` is honored only on first creation; later calls return the
    existing instance.
    """
    global _db
    with _db_lock:
        if _db is None:
            _db = Database(db_path if db_path is not None else DEFAULT_DB_PATH)
        return _db


def close_db() -> None:
    """Close and forget the shared Database (used by tests/shutdown)."""
    global _db
    with _db_lock:
        if _db is not None:
            _db.close()
            _db = None
