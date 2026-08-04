"""M2 tests: the canonical seed dataset, idempotency, and the rules it must obey."""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import Database
from app.store import compute_acquisition_type
from scripts.seed import (
    CANONICAL_PROCEDURES,
    EXTRA_PROCEDURES,
    row_counts,
    seed_database,
)

# Fixed reference date so seeded datetimes are predictable in tests.
REFERENCE = datetime(2026, 8, 3, 17, 30, tzinfo=timezone.utc)
TODAY = datetime(2026, 8, 3, tzinfo=timezone.utc)

EXPECTED_PROCEDURES = len(CANONICAL_PROCEDURES) + len(EXTRA_PROCEDURES)


@pytest.fixture()
def db(tmp_path):
    database = Database(tmp_path / "seed.duckdb")
    yield database
    database.close()


@pytest.fixture()
def seeded(db):
    seed_database(db, reference=REFERENCE)
    return db


# ---------------------------------------------------------------------------
# Canonical vocabulary and lookups
# ---------------------------------------------------------------------------


def test_seed_row_counts(seeded):
    counts = row_counts(seeded)
    assert counts["procedure_types"] == 8
    assert counts["instruments"] == 3
    assert counts["mice"] == 3
    assert counts["projects"] == 2
    assert counts["users"] == 3
    # 3 compatible types per instrument, per DESIGN.md's seed table.
    assert counts["instrument_compatible_types"] == 9
    assert counts["scheduled_procedures"] == EXPECTED_PROCEDURES
    assert 15 <= counts["scheduled_procedures"] <= 25


def test_procedure_types_match_design_vocabulary(seeded):
    rows = seeded.conn.execute(
        "SELECT name, modality_name, modality_abbreviation, sort_order "
        "FROM procedure_types ORDER BY sort_order"
    ).fetchall()
    assert rows == [
        ("Acute extracellular electrophysiology (modular insertion)",
         "Extracellular electrophysiology", "ecephys", 1),
        ("Whole-brain 3D histology",
         "Selective plane illumination microscopy", "SPIM", 2),
        ("Cellular imaging", "Planar optical physiology", "pophys", 3),
        ("Fiber photometry (FIP)", "Fiber photometry", "fib", 4),
        ("Fiber photometry (HSFP)", "Fiber photometry", "fib", 5),
        ("Patch foraging behavior", "Behavior", "behavior", 6),
        ("Dynamic foraging behavior", "Behavior", "behavior", 7),
        ("Whole-brain axonal imaging",
         "Selective plane illumination microscopy", "SPIM", 8),
    ]


def test_instruments_match_design_seed_table(seeded):
    rows = seeded.conn.execute(
        "SELECT name, instrument_id, sipe_rig_name, active FROM instruments ORDER BY name"
    ).fetchall()
    assert rows == [
        ("Ephys-Rig-2", "EPHYS2", "EPHYS-02", True),
        ("SmartSPIM-1", "SmartSPIM1", "IMG-SPIM-01", True),
        ("VR-Foraging-Rig-A", "VRForaging1", "BEH-VR-01", True),
    ]


# Literal compatibility sets from DESIGN.md's instruments seed table —
# deliberately NOT read from scripts.seed, so drift in seed.py fails here.
DESIGN_COMPATIBILITY = {
    "VR-Foraging-Rig-A": [
        "Dynamic foraging behavior",
        "Fiber photometry (FIP)",
        "Patch foraging behavior",
    ],
    "SmartSPIM-1": [
        "Cellular imaging",
        "Whole-brain 3D histology",
        "Whole-brain axonal imaging",
    ],
    "Ephys-Rig-2": [
        "Acute extracellular electrophysiology (modular insertion)",
        "Fiber photometry (FIP)",
        "Patch foraging behavior",
    ],
}


@pytest.mark.parametrize("instrument_name", sorted(DESIGN_COMPATIBILITY))
def test_instrument_compatibility_sets(seeded, instrument_name):
    names = [
        r[0]
        for r in seeded.conn.execute(
            """
            SELECT pt.name
            FROM instruments i
            JOIN instrument_compatible_types ict ON ict.instrument_id = i.id
            JOIN procedure_types pt ON pt.id = ict.procedure_type_id
            WHERE i.name = ?
            """,
            [instrument_name],
        ).fetchall()
    ]
    assert sorted(names) == DESIGN_COMPATIBILITY[instrument_name]


def test_mice_projects_users(seeded):
    # Literal expected values from DESIGN.md's seed dataset — deliberately
    # NOT read from scripts.seed constants, so drift in seed.py fails here.
    mice = seeded.conn.execute(
        "SELECT subject_id, genotype FROM mice ORDER BY subject_id"
    ).fetchall()
    assert mice == [
        ("testmouse1", "test-genotype"),
        ("testmouse2", "test-genotype"),
        ("testmouse3", "test-genotype"),
    ]
    # Synthetic-data guardrail: never numeric AIND-looking subject ids.
    assert all(not s.isdigit() for s, _ in mice)

    projects = [
        r[0] for r in seeded.conn.execute("SELECT name FROM projects ORDER BY name").fetchall()
    ]
    assert projects == [
        "Brain-wide connectivity",
        "Cognitive flexibility in patch foraging",
    ]

    users = seeded.conn.execute(
        "SELECT name, email FROM users ORDER BY name"
    ).fetchall()
    assert users == [
        ("Bruno Cruz", "bruno.cruz@alleninstitute.org"),
        ("Doug Ollerenshaw", "doug.ollerenshaw@alleninstitute.org"),
        ("Jane Kim", "jane.kim@alleninstitute.org"),
    ]
    # Doug's ORCID placeholder round-trips; Bruno's is NULL (nullable case).
    orcids = dict(
        seeded.conn.execute("SELECT name, orcid FROM users").fetchall()
    )
    assert orcids["Doug Ollerenshaw"] == "0000-0000-0000-0001"
    assert orcids["Bruno Cruz"] is None


# ---------------------------------------------------------------------------
# The four explicit scheduled procedures (SP-1..SP-4)
# ---------------------------------------------------------------------------


def _resolved(db, subject_id, instrument_name, start):
    """Fetch one scheduled procedure fully resolved, by natural key."""
    row = db.conn.execute(
        """
        SELECT sp.id, m.subject_id, i.name, i.sipe_rig_name, p.name, u.name,
               sp.scheduled_start, sp.scheduled_end, sp.acquisition_type,
               sp.acquisition_name, sp.status, sp.ethics_review_id,
               sp.planned_config, sp.protocols
        FROM scheduled_procedures sp
        JOIN mice m ON m.id = sp.mouse_id
        JOIN instruments i ON i.id = sp.instrument_id
        JOIN projects p ON p.id = sp.project_id
        JOIN users u ON u.id = sp.contact_user_id
        WHERE m.subject_id = ? AND i.name = ? AND sp.scheduled_start = ?
        """,
        [subject_id, instrument_name, start],
    ).fetchone()
    assert row is not None, f"no procedure for {subject_id}/{instrument_name} at {start}"
    active = [
        r[0]
        for r in db.conn.execute(
            """
            SELECT pt.name FROM scheduled_procedure_active_types sat
            JOIN procedure_types pt ON pt.id = sat.procedure_type_id
            WHERE sat.scheduled_procedure_id = ? ORDER BY pt.sort_order
            """,
            [row[0]],
        ).fetchall()
    ]
    experimenters = [
        r[0]
        for r in db.conn.execute(
            """
            SELECT u.name FROM scheduled_procedure_experimenters se
            JOIN users u ON u.id = se.user_id
            WHERE se.scheduled_procedure_id = ? ORDER BY u.name
            """,
            [row[0]],
        ).fetchall()
    ]
    return row, active, experimenters


def test_sp1_matches_design_document(seeded):
    """SP-1: testmouse1 on VR-Foraging-Rig-A, today+1 09:00->11:00,
    Dynamic foraging + FIP, contact Doug, experimenter Bruno."""
    start = TODAY + timedelta(days=1, hours=9)
    row, active, experimenters = _resolved(seeded, "testmouse1", "VR-Foraging-Rig-A", start)

    assert row[3] == "BEH-VR-01"
    assert row[4] == "Cognitive flexibility in patch foraging"
    assert row[5] == "Doug Ollerenshaw"
    assert row[6] == start
    assert row[7] == start + timedelta(hours=2)
    assert row[8] == "Dynamic foraging behavior + Fiber photometry (FIP)"
    assert row[9] is None, "acquisition_name is NULL for purely-scheduled rows"
    assert row[10] == "scheduled"
    assert row[11] == "IACUC-2109"
    assert json.loads(row[12])["fibers"] == ["DMS-left", "DMS-right"]
    assert active == ["Fiber photometry (FIP)", "Dynamic foraging behavior"]
    assert experimenters == ["Bruno Cruz"]
    # The id token is a UUIDv7.
    assert row[0].split("-")[2][0] == "7"


def test_sp2_matches_design_document(seeded):
    start = TODAY + timedelta(days=2, hours=13)
    row, active, experimenters = _resolved(seeded, "testmouse2", "VR-Foraging-Rig-A", start)
    assert row[7] == start + timedelta(hours=1, minutes=30)
    assert row[8] == "Patch foraging behavior"
    assert row[5] == "Doug Ollerenshaw"
    assert active == ["Patch foraging behavior"]
    assert experimenters == ["Jane Kim"]


def test_sp3_matches_design_document(seeded):
    start = TODAY + timedelta(days=4, hours=10)
    row, active, experimenters = _resolved(seeded, "testmouse3", "SmartSPIM-1", start)
    assert row[7] == start + timedelta(hours=6)
    assert row[4] == "Brain-wide connectivity"
    assert row[5] == "Jane Kim"
    assert row[8] == "Whole-brain 3D histology"
    assert active == ["Whole-brain 3D histology"]
    assert experimenters == ["Jane Kim"]


def test_sp4_matches_design_document(seeded):
    start = TODAY + timedelta(days=8, hours=9)
    row, active, experimenters = _resolved(seeded, "testmouse1", "Ephys-Rig-2", start)
    assert row[7] == start + timedelta(hours=3)
    assert row[5] == "Doug Ollerenshaw"
    assert row[8] == (
        "Acute extracellular electrophysiology (modular insertion) "
        "+ Fiber photometry (FIP)"
    )
    assert sorted(active) == [
        "Acute extracellular electrophysiology (modular insertion)",
        "Fiber photometry (FIP)",
    ]
    assert experimenters == ["Bruno Cruz"]


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_reseeding_does_not_duplicate_rows(db):
    first = seed_database(db, reference=REFERENCE)
    ids_before = {
        r[0] for r in db.conn.execute("SELECT id FROM scheduled_procedures").fetchall()
    }

    second = seed_database(db, reference=REFERENCE)
    third = seed_database(db, reference=REFERENCE)

    assert first == second == third
    ids_after = {
        r[0] for r in db.conn.execute("SELECT id FROM scheduled_procedures").fetchall()
    }
    assert ids_after == ids_before, "re-seeding must not mint new tokens"


def test_reseeding_preserves_natural_key_uniqueness(seeded):
    seed_database(seeded, reference=REFERENCE)
    dupes = seeded.conn.execute(
        """
        SELECT mouse_id, instrument_id, scheduled_start, count(*) AS n
        FROM scheduled_procedures
        GROUP BY 1, 2, 3 HAVING count(*) > 1
        """
    ).fetchall()
    assert dupes == []


# ---------------------------------------------------------------------------
# Rules every seeded row must satisfy
# ---------------------------------------------------------------------------


def test_all_seeded_procedures_respect_instrument_compatibility(seeded):
    violations = seeded.conn.execute(
        """
        SELECT sp.id, pt.name, i.name
        FROM scheduled_procedures sp
        JOIN scheduled_procedure_active_types sat ON sat.scheduled_procedure_id = sp.id
        JOIN procedure_types pt ON pt.id = sat.procedure_type_id
        JOIN instruments i ON i.id = sp.instrument_id
        WHERE NOT EXISTS (
            SELECT 1 FROM instrument_compatible_types ict
            WHERE ict.instrument_id = sp.instrument_id
              AND ict.procedure_type_id = sat.procedure_type_id
        )
        """
    ).fetchall()
    assert violations == []


def test_all_seeded_procedures_have_end_after_start(seeded):
    bad = seeded.conn.execute(
        "SELECT id FROM scheduled_procedures WHERE scheduled_end <= scheduled_start"
    ).fetchall()
    assert bad == []


def test_every_procedure_has_at_least_one_active_type(seeded):
    orphans = seeded.conn.execute(
        """
        SELECT sp.id FROM scheduled_procedures sp
        WHERE NOT EXISTS (
            SELECT 1 FROM scheduled_procedure_active_types sat
            WHERE sat.scheduled_procedure_id = sp.id
        )
        """
    ).fetchall()
    assert orphans == []


def test_acquisition_type_equals_sorted_join_of_active_types(seeded):
    rows = seeded.conn.execute(
        """
        SELECT sp.id, sp.acquisition_type, list(pt.name)
        FROM scheduled_procedures sp
        JOIN scheduled_procedure_active_types sat ON sat.scheduled_procedure_id = sp.id
        JOIN procedure_types pt ON pt.id = sat.procedure_type_id
        GROUP BY sp.id, sp.acquisition_type
        """
    ).fetchall()
    assert len(rows) == EXPECTED_PROCEDURES
    for sp_id, acquisition_type, names in rows:
        assert acquisition_type == compute_acquisition_type(names), sp_id
        # Alphabetical order, " + "-joined.
        assert acquisition_type == " + ".join(sorted(names))


def test_multi_platform_procedures_exist(seeded):
    """The multiselect is exercised: some sessions run two platforms."""
    multi = seeded.conn.execute(
        """
        SELECT count(*) FROM (
            SELECT scheduled_procedure_id
            FROM scheduled_procedure_active_types
            GROUP BY scheduled_procedure_id HAVING count(*) > 1
        )
        """
    ).fetchone()[0]
    assert multi >= 4
    assert seeded.conn.execute(
        "SELECT count(*) FROM scheduled_procedures "
        "WHERE acquisition_type = 'Dynamic foraging behavior + Fiber photometry (FIP)'"
    ).fetchone()[0] >= 1


def test_procedures_span_the_next_two_to_three_weeks(seeded):
    lo, hi = seeded.conn.execute(
        "SELECT min(scheduled_start), max(scheduled_start) FROM scheduled_procedures"
    ).fetchone()
    assert lo >= TODAY
    span_days = (hi - lo).days
    assert 14 <= span_days <= 25, f"schedule spans {span_days} days"
    # All three instruments are used, so the calendar has populated rows.
    used = seeded.conn.execute(
        "SELECT count(DISTINCT instrument_id) FROM scheduled_procedures"
    ).fetchone()[0]
    assert used == 3


def test_seed_uses_all_three_mice_and_both_projects(seeded):
    assert seeded.conn.execute(
        "SELECT count(DISTINCT mouse_id) FROM scheduled_procedures"
    ).fetchone()[0] == 3
    assert seeded.conn.execute(
        "SELECT count(DISTINCT project_id) FROM scheduled_procedures"
    ).fetchone()[0] == 2
