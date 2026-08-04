"""M1 tests: schema creation, UUIDv7 token properties, basic insert/read."""

import json
import threading
import time
from datetime import datetime, timedelta, timezone

import duckdb
import pytest

from app.db import (
    TABLES,
    Database,
    create_schema,
    list_tables,
    new_uuid,
    new_uuid7,
    utcnow,
)


@pytest.fixture()
def db(tmp_path):
    database = Database(tmp_path / "test.duckdb")
    yield database
    database.close()


# ---------------------------------------------------------------------------
# Schema creation
# ---------------------------------------------------------------------------


def test_all_tables_created(db):
    assert set(list_tables(db.conn)) == set(TABLES)


def test_schema_creation_is_idempotent(tmp_path):
    """Creating the schema twice (same connection and reopen) is safe and
    does not drop existing data."""
    path = tmp_path / "idem.duckdb"

    db = Database(path)
    # Re-run on the same live connection.
    create_schema(db.conn)
    assert set(list_tables(db.conn)) == set(TABLES)

    # Insert a row, close, and reopen — Database.__init__ runs
    # create_schema again on the existing file.
    with db.write() as conn:
        conn.execute(
            "INSERT INTO projects (id, name) VALUES (?, ?)",
            [new_uuid(), "Brain-wide connectivity"],
        )
    db.close()

    db2 = Database(path)
    assert set(list_tables(db2.conn)) == set(TABLES)
    count, = db2.conn.execute("SELECT count(*) FROM projects").fetchone()
    assert count == 1, "re-creating the schema must not drop existing rows"
    db2.close()


# ---------------------------------------------------------------------------
# UUIDv7 acquisition token
# ---------------------------------------------------------------------------


def test_uuid7_is_valid_uuid_version_7():
    token = new_uuid7()
    # Standard 8-4-4-4-12 layout; version nibble is '7'.
    parts = token.split("-")
    assert [len(p) for p in parts] == [8, 4, 4, 4, 12]
    assert parts[2][0] == "7"


def test_uuid7_tokens_are_time_sortable():
    """Tokens minted later sort later as plain strings (UUIDv7 property)."""
    tokens = []
    for _ in range(20):
        tokens.append(new_uuid7())
        time.sleep(0.003)  # exceed the UUIDv7 millisecond timestamp resolution
    assert len(set(tokens)) == len(tokens)
    assert tokens == sorted(tokens)


def test_scheduled_procedure_rows_sort_by_id_in_creation_order(db):
    """Rows ordered by id alone come back in creation order."""
    mouse_id, instrument_id, project_id, user_id = _insert_lookups(db)
    created_order = []
    for i in range(5):
        sp_id = new_uuid7()
        created_order.append(sp_id)
        _insert_scheduled_procedure(
            db, sp_id, mouse_id, instrument_id, project_id, user_id,
            start_offset_hours=i,
        )
        time.sleep(0.003)
    ids = [
        r[0]
        for r in db.conn.execute(
            "SELECT id FROM scheduled_procedures ORDER BY id"
        ).fetchall()
    ]
    assert ids == created_order


# ---------------------------------------------------------------------------
# Insert / read across all tables (including join tables)
# ---------------------------------------------------------------------------


def _insert_lookups(db):
    """Insert one row into each lookup table; return their ids."""
    mouse_id, instrument_id, project_id, user_id = (new_uuid() for _ in range(4))
    with db.write() as conn:
        conn.execute(
            "INSERT INTO mice (id, subject_id, genotype) VALUES (?, ?, ?)",
            [mouse_id, "testmouse1", "test-genotype"],
        )
        conn.execute(
            "INSERT INTO instruments (id, name, instrument_id, sipe_rig_name, location, active) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [instrument_id, "Ephys-Rig-2", "EPHYS2", "EPHYS-02", "Room 123", True],
        )
        conn.execute(
            "INSERT INTO projects (id, name) VALUES (?, ?)",
            [project_id, "Cognitive flexibility in patch foraging"],
        )
        conn.execute(
            "INSERT INTO users (id, name, email, orcid) VALUES (?, ?, ?, ?)",
            [user_id, "Doug Ollerenshaw", "doug.ollerenshaw@alleninstitute.org",
             "0000-0000-0000-0001"],
        )
    return mouse_id, instrument_id, project_id, user_id


def _insert_scheduled_procedure(
    db, sp_id, mouse_id, instrument_id, project_id, user_id,
    start_offset_hours=0, planned_config=None,
):
    start = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc) + timedelta(
        hours=start_offset_hours
    )
    now = utcnow()
    with db.write() as conn:
        conn.execute(
            """
            INSERT INTO scheduled_procedures (
                id, mouse_id, instrument_id, project_id, contact_user_id,
                scheduled_start, scheduled_end, acquisition_type,
                acquisition_name, status, ethics_review_id, notes,
                planned_config, protocols, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                sp_id, mouse_id, instrument_id, project_id, user_id,
                start, start + timedelta(hours=2),
                "Acute extracellular electrophysiology + Fiber photometry (FIP)",
                None, "scheduled", "IACUC-2109", "First ephys session.",
                planned_config, "Modular probe insertion, 4 shanks",
                now, now,
            ],
        )
    return start


def test_insert_and_read_across_tables(db):
    mouse_id, instrument_id, project_id, user_id = _insert_lookups(db)

    # Procedure types + instrument compatibility join.
    pt_ephys, pt_fip = new_uuid(), new_uuid()
    with db.write() as conn:
        conn.execute(
            "INSERT INTO procedure_types (id, name, modality_name, modality_abbreviation, sort_order) "
            "VALUES (?, ?, ?, ?, ?), (?, ?, ?, ?, ?)",
            [
                pt_ephys, "Acute extracellular electrophysiology (modular insertion)",
                "Extracellular electrophysiology", "ecephys", 1,
                pt_fip, "Fiber photometry (FIP)", "Fiber photometry", "fib", 4,
            ],
        )
        conn.execute(
            "INSERT INTO instrument_compatible_types (instrument_id, procedure_type_id) "
            "VALUES (?, ?), (?, ?)",
            [instrument_id, pt_ephys, instrument_id, pt_fip],
        )

    # Scheduled procedure with tz-aware datetimes and JSON planned_config.
    sp_id = new_uuid7()
    planned_config = json.dumps({"probe_count": 4, "fibers": ["DMS-left", "DMS-right"]})
    start = _insert_scheduled_procedure(
        db, sp_id, mouse_id, instrument_id, project_id, user_id,
        planned_config=planned_config,
    )

    # Join tables for the scheduled procedure.
    with db.write() as conn:
        conn.execute(
            "INSERT INTO scheduled_procedure_active_types (scheduled_procedure_id, procedure_type_id) "
            "VALUES (?, ?), (?, ?)",
            [sp_id, pt_ephys, sp_id, pt_fip],
        )
        conn.execute(
            "INSERT INTO scheduled_procedure_experimenters (scheduled_procedure_id, user_id) "
            "VALUES (?, ?)",
            [sp_id, user_id],
        )

    # Read back through joins and verify values.
    row = db.conn.execute(
        """
        SELECT sp.id, m.subject_id, i.name, i.instrument_id, i.sipe_rig_name,
               p.name, u.name, u.orcid, sp.scheduled_start, sp.scheduled_end,
               sp.acquisition_type, sp.status, sp.ethics_review_id,
               sp.planned_config
        FROM scheduled_procedures sp
        JOIN mice m ON m.id = sp.mouse_id
        JOIN instruments i ON i.id = sp.instrument_id
        JOIN projects p ON p.id = sp.project_id
        JOIN users u ON u.id = sp.contact_user_id
        WHERE sp.id = ?
        """,
        [sp_id],
    ).fetchone()

    assert row[0] == sp_id
    assert row[1] == "testmouse1"
    assert row[2] == "Ephys-Rig-2"
    assert row[3] == "EPHYS2"
    assert row[4] == "EPHYS-02"
    assert row[5] == "Cognitive flexibility in patch foraging"
    assert row[6] == "Doug Ollerenshaw"
    assert row[7] == "0000-0000-0000-0001"
    # Datetimes come back timezone-aware and equal to what was stored.
    assert row[8].tzinfo is not None
    assert row[8] == start
    assert row[9] == start + timedelta(hours=2)
    assert row[10] == "Acute extracellular electrophysiology + Fiber photometry (FIP)"
    assert row[11] == "scheduled"
    assert row[12] == "IACUC-2109"
    assert json.loads(row[13]) == {"probe_count": 4, "fibers": ["DMS-left", "DMS-right"]}

    # Join tables round-trip.
    active = db.conn.execute(
        """
        SELECT pt.name, pt.modality_name, pt.modality_abbreviation
        FROM scheduled_procedure_active_types sat
        JOIN procedure_types pt ON pt.id = sat.procedure_type_id
        WHERE sat.scheduled_procedure_id = ?
        ORDER BY pt.sort_order
        """,
        [sp_id],
    ).fetchall()
    assert active == [
        ("Acute extracellular electrophysiology (modular insertion)",
         "Extracellular electrophysiology", "ecephys"),
        ("Fiber photometry (FIP)", "Fiber photometry", "fib"),
    ]

    experimenters = db.conn.execute(
        """
        SELECT u.name FROM scheduled_procedure_experimenters se
        JOIN users u ON u.id = se.user_id
        WHERE se.scheduled_procedure_id = ?
        """,
        [sp_id],
    ).fetchall()
    assert experimenters == [("Doug Ollerenshaw",)]

    compatible = db.conn.execute(
        "SELECT count(*) FROM instrument_compatible_types WHERE instrument_id = ?",
        [instrument_id],
    ).fetchone()[0]
    assert compatible == 2


def test_end_before_start_rejected_by_schema_backstop(db):
    """The DB-level CHECK backstops validation rule 1 (end > start)."""
    mouse_id, instrument_id, project_id, user_id = _insert_lookups(db)
    start = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)
    now = utcnow()
    with pytest.raises(duckdb.ConstraintException):
        with db.write() as conn:
            conn.execute(
                """
                INSERT INTO scheduled_procedures (
                    id, mouse_id, instrument_id, project_id, contact_user_id,
                    scheduled_start, scheduled_end, acquisition_type,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [new_uuid7(), mouse_id, instrument_id, project_id, user_id,
                 start, start, "Patch foraging behavior", now, now],
            )


def test_invalid_status_rejected(db):
    mouse_id, instrument_id, project_id, user_id = _insert_lookups(db)
    start = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)
    now = utcnow()
    with pytest.raises(duckdb.ConstraintException):
        with db.write() as conn:
            conn.execute(
                """
                INSERT INTO scheduled_procedures (
                    id, mouse_id, instrument_id, project_id, contact_user_id,
                    scheduled_start, scheduled_end, acquisition_type, status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [new_uuid7(), mouse_id, instrument_id, project_id, user_id,
                 start, start + timedelta(hours=1), "Patch foraging behavior",
                 "not-a-status", now, now],
            )


def test_write_lock_serializes_concurrent_writers(db):
    """Many threads writing through Database.write() all land their rows."""
    n_threads, n_rows = 4, 25
    errors = []

    def writer(worker):
        try:
            for i in range(n_rows):
                with db.write() as conn:
                    conn.execute(
                        "INSERT INTO projects (id, name) VALUES (?, ?)",
                        [new_uuid(), f"project-{worker}-{i}"],
                    )
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(w,)) for w in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    count, = db.conn.execute("SELECT count(*) FROM projects").fetchone()
    assert count == n_threads * n_rows


def test_write_rolls_back_on_error(db):
    with pytest.raises(RuntimeError):
        with db.write() as conn:
            conn.execute(
                "INSERT INTO projects (id, name) VALUES (?, ?)",
                [new_uuid(), "doomed project"],
            )
            raise RuntimeError("boom")
    count, = db.conn.execute("SELECT count(*) FROM projects").fetchone()
    assert count == 0
