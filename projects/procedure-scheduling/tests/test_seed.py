"""M2 tests: the canonical seed dataset, idempotency, and the rules it must obey."""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scheduler_app.db import Database
from scheduler_app.store import compute_acquisition_type
from scripts.seed import (
    CANONICAL_PROCEDURES,
    EXTRA_PROCEDURES,
    row_counts,
    seed_database,
)
from tests.expected_times import LOCAL_TZ, expected_start

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
    assert counts["instruments"] == 4
    assert counts["mice"] == 3
    assert counts["projects"] == 2
    assert counts["users"] == 3
    # 2 + 2 + 3 + 3 across the four instruments (see DESIGN_COMPATIBILITY).
    assert counts["instrument_compatible_types"] == 10
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
        ("Dynamic-Foraging-Box-1", "DynamicForaging1", "BEH-DF-01", True),
        ("Ephys-Rig-2", "EPHYS2", "EPHYS-02", True),
        ("SmartSPIM-1", "SmartSPIM1", "IMG-SPIM-01", True),
        ("VR-Foraging-Rig-A", "VRForaging1", "BEH-VR-01", True),
    ]


# Literal compatibility sets — deliberately NOT read from scripts.seed, so
# drift in seed.py fails here. These reflect Doug's 2026-08-04 domain
# correction (one behavior task per rig; VR foraging IS patch foraging;
# Dynamic foraging lives on its own box), which supersedes DESIGN.md's seed
# table. See BUILD_NOTES.md "Domain correction".
DESIGN_COMPATIBILITY = {
    "VR-Foraging-Rig-A": [
        "Fiber photometry (FIP)",
        "Patch foraging behavior",
    ],
    "Dynamic-Foraging-Box-1": [
        "Dynamic foraging behavior",
        "Fiber photometry (FIP)",
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
    """SP-1: testmouse1, today+1 09:00->11:00 LOCAL, Dynamic foraging + FIP,
    contact Doug, experimenter Bruno.

    Per Doug's 2026-08-04 correction this row lives on
    Dynamic-Foraging-Box-1, not DESIGN.md's VR-Foraging-Rig-A (a VR rig
    doesn't run the dynamic foraging task); everything else is as documented.
    """
    start = expected_start(TODAY, 1, 9)   # 09:00 LOCAL on day+1
    row, active, experimenters = _resolved(
        seeded, "testmouse1", "Dynamic-Foraging-Box-1", start
    )

    assert row[3] == "BEH-DF-01"
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
    start = expected_start(TODAY, 2, 13)  # 13:00 LOCAL on day+2
    row, active, experimenters = _resolved(seeded, "testmouse2", "VR-Foraging-Rig-A", start)
    assert row[7] == start + timedelta(hours=1, minutes=30)
    assert row[8] == "Patch foraging behavior"
    assert row[5] == "Doug Ollerenshaw"
    assert active == ["Patch foraging behavior"]
    assert experimenters == ["Jane Kim"]


def test_sp3_matches_design_document(seeded):
    start = expected_start(TODAY, 4, 10)  # 10:00 LOCAL on day+4
    row, active, experimenters = _resolved(seeded, "testmouse3", "SmartSPIM-1", start)
    assert row[7] == start + timedelta(hours=6)
    assert row[4] == "Brain-wide connectivity"
    assert row[5] == "Jane Kim"
    assert row[8] == "Whole-brain 3D histology"
    assert active == ["Whole-brain 3D histology"]
    assert experimenters == ["Jane Kim"]


def test_sp4_matches_design_document(seeded):
    start = expected_start(TODAY, 8, 9)   # 09:00 LOCAL on day+8
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


def test_dynamic_foraging_box_exists_and_vr_rig_excludes_dynamic(seeded):
    """Doug's domain correction: Dynamic foraging moved off the VR rig onto
    its own box, and the VR rig offers exactly patch foraging + FIP."""
    def compat(instrument_name):
        return {
            r[0]
            for r in seeded.conn.execute(
                """
                SELECT pt.name FROM instruments i
                JOIN instrument_compatible_types ict ON ict.instrument_id = i.id
                JOIN procedure_types pt ON pt.id = ict.procedure_type_id
                WHERE i.name = ?
                """,
                [instrument_name],
            ).fetchall()
        }

    assert compat("Dynamic-Foraging-Box-1") == {
        "Dynamic foraging behavior", "Fiber photometry (FIP)",
    }
    assert compat("VR-Foraging-Rig-A") == {
        "Patch foraging behavior", "Fiber photometry (FIP)",
    }
    assert "Dynamic foraging behavior" not in compat("VR-Foraging-Rig-A")
    # And the dynamic box is actually used by seeded procedures.
    assert seeded.conn.execute(
        """
        SELECT count(*) FROM scheduled_procedures sp
        JOIN instruments i ON i.id = sp.instrument_id
        WHERE i.name = 'Dynamic-Foraging-Box-1'
        """
    ).fetchone()[0] > 0


def test_no_instrument_offers_two_behavior_tasks(seeded):
    """A behavior rig runs one behavior task, so no compatibility set may
    contain two Behavior-modality types."""
    offenders = seeded.conn.execute(
        """
        SELECT i.name, count(*) FROM instruments i
        JOIN instrument_compatible_types ict ON ict.instrument_id = i.id
        JOIN procedure_types pt ON pt.id = ict.procedure_type_id
        WHERE pt.modality_name = 'Behavior'
        GROUP BY i.name HAVING count(*) > 1
        """
    ).fetchall()
    assert offenders == []


def test_no_seeded_procedure_has_two_behavior_types(seeded):
    """Validation rule 4 holds across the whole seeded dataset."""
    offenders = seeded.conn.execute(
        """
        SELECT sp.id, count(*) FROM scheduled_procedures sp
        JOIN scheduled_procedure_active_types sat ON sat.scheduled_procedure_id = sp.id
        JOIN procedure_types pt ON pt.id = sat.procedure_type_id
        WHERE pt.modality_name = 'Behavior'
        GROUP BY sp.id HAVING count(*) > 1
        """
    ).fetchall()
    assert offenders == []


def test_every_seeded_procedure_is_in_local_working_hours_on_a_weekday(seeded):
    """ALL 18 rows — canonical included — must look like real sessions: inside
    the local working-hours window, on a weekday, not spanning midnight.

    No exemptions since Doug's 2026-08-04 ruling that documented clock times
    are rig-local (previously the four canonical rows landed at 02:00-06:00
    local because their times were read as UTC).
    """
    rows = seeded.conn.execute(
        "SELECT id, scheduled_start, scheduled_end FROM scheduled_procedures"
    ).fetchall()
    assert len(rows) == EXPECTED_PROCEDURES

    # Window bounds hardcoded (07:00-18:00 local), not read from seed.py.
    window_start, window_end = 7 * 60, 18 * 60
    for _, start_utc, end_utc in rows:
        start = start_utc.astimezone(LOCAL_TZ)
        end = end_utc.astimezone(LOCAL_TZ)
        assert start.weekday() < 5, f"{start} is a weekend"
        assert end.weekday() < 5, f"{end} is a weekend"
        assert window_start <= start.hour * 60 + start.minute <= window_end, (
            f"{start} starts outside working hours"
        )
        assert window_start <= end.hour * 60 + end.minute <= window_end, (
            f"{end} ends outside working hours"
        )
        assert start.date() == end.date(), f"{start} spans midnight"


def test_canonical_rows_keep_their_documented_clock_times_as_local(seeded):
    """SP-1..SP-4 keep DESIGN.md's documented clock values (09:00 / 13:00 /
    10:00 / 09:00) and durations, read as RIG-LOCAL time per Doug's
    2026-08-04 decision — so 09:00 means 9 a.m. at the rig, not 02:00 local.

    Expected instants are computed by tests/expected_times.py, an independent
    implementation of the documented rule.
    """
    expected = [
        ("SP-1", 1, 9, 0, 2.0),     # today+1, 09:00 local, 2 h
        ("SP-2", 2, 13, 0, 1.5),    # today+2, 13:00 local, 1.5 h
        ("SP-3", 4, 10, 0, 6.0),    # today+4, 10:00 local, 6 h
        ("SP-4", 8, 9, 0, 3.0),     # today+8, 09:00 local, 3 h
    ]
    for label, day_offset, hour, minute, hours in expected:
        start = expected_start(TODAY, day_offset, hour, minute)
        row = seeded.conn.execute(
            "SELECT scheduled_end FROM scheduled_procedures WHERE scheduled_start = ?",
            [start],
        ).fetchone()
        assert row is not None, (
            f"no {label} starting {start.isoformat()} "
            f"({hour:02d}:{minute:02d} local on day+{day_offset})"
        )
        assert row[0] == start + timedelta(hours=hours), label
        # The documented clock value is what a calendar reader sees locally.
        local_start = start.astimezone(LOCAL_TZ)
        assert (local_start.hour, local_start.minute) == (hour, minute), label


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
    # All four instruments are used, so the calendar has populated rows.
    used = seeded.conn.execute(
        "SELECT count(DISTINCT instrument_id) FROM scheduled_procedures"
    ).fetchone()[0]
    assert used == 4


def test_seed_uses_all_three_mice_and_both_projects(seeded):
    assert seeded.conn.execute(
        "SELECT count(DISTINCT mouse_id) FROM scheduled_procedures"
    ).fetchone()[0] == 3
    assert seeded.conn.execute(
        "SELECT count(DISTINCT project_id) FROM scheduled_procedures"
    ).fetchone()[0] == 2
