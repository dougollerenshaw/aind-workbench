"""Tests for the shared write logic in app/store.py.

These cover the pieces the seed script (M2) and the admin write API (M4)
both depend on: the computed ``acquisition_type`` and the two validation
rules from DESIGN.md.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scheduler_app.db import Database
from scheduler_app.store import (
    ValidationError,
    compute_acquisition_type,
    create_scheduled_procedure,
)
from scripts.seed import seed_database

REFERENCE = datetime(2026, 8, 3, 17, 30, tzinfo=timezone.utc)


@pytest.fixture()
def db(tmp_path):
    database = Database(tmp_path / "store.duckdb")
    seed_database(database, reference=REFERENCE)
    yield database
    database.close()


def _id(db, table, column, value):
    return db.conn.execute(
        f"SELECT id FROM {table} WHERE {column} = ?", [value]
    ).fetchone()[0]


# ---------------------------------------------------------------------------
# acquisition_type (rule 3)
# ---------------------------------------------------------------------------


def test_compute_acquisition_type_sorts_and_joins():
    assert compute_acquisition_type(["Fiber photometry (FIP)", "Dynamic foraging behavior"]) == (
        "Dynamic foraging behavior + Fiber photometry (FIP)"
    )
    assert compute_acquisition_type(["Patch foraging behavior"]) == "Patch foraging behavior"
    assert compute_acquisition_type([]) == ""


def test_create_computes_acquisition_type_regardless_of_input_order(db):
    start = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
    fip = _id(db, "procedure_types", "name", "Fiber photometry (FIP)")
    dynamic = _id(db, "procedure_types", "name", "Dynamic foraging behavior")

    sp_id = create_scheduled_procedure(
        db,
        mouse_id=_id(db, "mice", "subject_id", "testmouse1"),
        instrument_id=_id(db, "instruments", "name", "VR-Foraging-Rig-A"),
        project_id=_id(db, "projects", "name", "Cognitive flexibility in patch foraging"),
        contact_user_id=_id(db, "users", "email", "doug.ollerenshaw@alleninstitute.org"),
        scheduled_start=start,
        scheduled_end=start + timedelta(hours=2),
        # Deliberately reverse-alphabetical input order.
        active_procedure_type_ids=[fip, dynamic],
    )
    acquisition_type, = db.conn.execute(
        "SELECT acquisition_type FROM scheduled_procedures WHERE id = ?", [sp_id]
    ).fetchone()
    assert acquisition_type == "Dynamic foraging behavior + Fiber photometry (FIP)"


# ---------------------------------------------------------------------------
# Rule 1: end > start
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("end_offset_hours", [0, -1])
def test_end_not_after_start_is_rejected(db, end_offset_hours):
    start = datetime(2026, 9, 2, 9, 0, tzinfo=timezone.utc)
    with pytest.raises(ValidationError) as exc:
        create_scheduled_procedure(
            db,
            mouse_id=_id(db, "mice", "subject_id", "testmouse1"),
            instrument_id=_id(db, "instruments", "name", "VR-Foraging-Rig-A"),
            project_id=_id(db, "projects", "name", "Cognitive flexibility in patch foraging"),
            contact_user_id=_id(db, "users", "email", "doug.ollerenshaw@alleninstitute.org"),
            scheduled_start=start,
            scheduled_end=start + timedelta(hours=end_offset_hours),
            active_procedure_type_ids=[
                _id(db, "procedure_types", "name", "Dynamic foraging behavior")
            ],
        )
    assert exc.value.code == "invalid_time_range"


# ---------------------------------------------------------------------------
# Rule 2: active types must be compatible with the instrument
# ---------------------------------------------------------------------------


def test_incompatible_procedure_type_is_rejected(db):
    """DESIGN.md's worked failure case: histology on Ephys-Rig-2."""
    start = datetime(2026, 9, 3, 9, 0, tzinfo=timezone.utc)
    with pytest.raises(ValidationError) as exc:
        create_scheduled_procedure(
            db,
            mouse_id=_id(db, "mice", "subject_id", "testmouse2"),
            instrument_id=_id(db, "instruments", "name", "Ephys-Rig-2"),
            project_id=_id(db, "projects", "name", "Cognitive flexibility in patch foraging"),
            contact_user_id=_id(db, "users", "email", "doug.ollerenshaw@alleninstitute.org"),
            scheduled_start=start,
            scheduled_end=start + timedelta(hours=2),
            active_procedure_type_ids=[
                _id(db, "procedure_types", "name", "Whole-brain 3D histology")
            ],
        )
    assert exc.value.code == "incompatible_procedure_type"
    assert "'Whole-brain 3D histology' is not compatible with instrument 'Ephys-Rig-2'" in (
        exc.value.detail
    )
    assert "Compatible types:" in exc.value.detail
    # Nothing was written.
    assert db.conn.execute(
        "SELECT count(*) FROM scheduled_procedures WHERE scheduled_start = ?", [start]
    ).fetchone()[0] == 0


def test_compatible_procedure_type_succeeds(db):
    start = datetime(2026, 9, 3, 9, 0, tzinfo=timezone.utc)
    sp_id = create_scheduled_procedure(
        db,
        mouse_id=_id(db, "mice", "subject_id", "testmouse2"),
        instrument_id=_id(db, "instruments", "name", "Ephys-Rig-2"),
        project_id=_id(db, "projects", "name", "Cognitive flexibility in patch foraging"),
        contact_user_id=_id(db, "users", "email", "doug.ollerenshaw@alleninstitute.org"),
        scheduled_start=start,
        scheduled_end=start + timedelta(hours=2),
        active_procedure_type_ids=[
            _id(db, "procedure_types", "name",
                "Acute extracellular electrophysiology (modular insertion)"),
            _id(db, "procedure_types", "name", "Fiber photometry (FIP)"),
        ],
        experimenter_user_ids=[_id(db, "users", "email", "bruno.cruz@alleninstitute.org")],
        planned_config={"probe_count": 4},
    )
    assert sp_id
    assert db.conn.execute(
        "SELECT count(*) FROM scheduled_procedure_active_types "
        "WHERE scheduled_procedure_id = ?", [sp_id]
    ).fetchone()[0] == 2
    assert db.conn.execute(
        "SELECT count(*) FROM scheduled_procedure_experimenters "
        "WHERE scheduled_procedure_id = ?", [sp_id]
    ).fetchone()[0] == 1


def test_unknown_reference_is_rejected(db):
    start = datetime(2026, 9, 4, 9, 0, tzinfo=timezone.utc)
    with pytest.raises(ValidationError) as exc:
        create_scheduled_procedure(
            db,
            mouse_id="not-a-real-mouse-id",
            instrument_id=_id(db, "instruments", "name", "Ephys-Rig-2"),
            project_id=_id(db, "projects", "name", "Cognitive flexibility in patch foraging"),
            contact_user_id=_id(db, "users", "email", "doug.ollerenshaw@alleninstitute.org"),
            scheduled_start=start,
            scheduled_end=start + timedelta(hours=1),
            active_procedure_type_ids=[
                _id(db, "procedure_types", "name", "Patch foraging behavior")
            ],
        )
    assert exc.value.code == "unknown_reference"
