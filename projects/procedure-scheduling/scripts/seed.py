#!/usr/bin/env python
"""Seed the prototype database with the canonical synthetic dataset.

The dataset here is the one defined in DESIGN.md "Seed data and worked
examples": the eight ``procedure_types`` with their aind-data-schema modality
mappings, four ``instruments`` with their compatibility sets, three ``mice``,
two ``projects``, three ``users``, the four explicit scheduled procedures
SP-1..SP-4, and a further set of procedures so the calendar looks populated
on first open.

ALL DATA HERE IS SYNTHETIC. Nothing is read from Dataverse, LIMS, or any
other live system, and the mouse ids are deliberately non-numeric
("testmouse1") so they can never be confused with real AIND subject ids.

Dates are relative to the day the script runs ("today" = run date), so a
freshly seeded database always has a schedule in the near future.

TIMES ARE RIG-LOCAL. Every clock time below is local wall-clock, converted to
UTC on the way into the database (storage is always UTC), and every row is
placed on a weekday inside working hours (see LOCAL_TZ / WORKING_DAY_* below).
This is Doug's 2026-08-04 decision and supersedes DESIGN.md, whose seed table
labels those times UTC — reading them as UTC rendered the documented 09:00
session at 02:00 Pacific.

Re-runnable: lookups are matched on their natural keys (name / subject_id /
email) and scheduled procedures on (mouse, instrument, scheduled_start), so
running this twice does not duplicate rows.

Usage:
    uv run python scripts/seed.py                 # seed (or top up) the default DB
    uv run python scripts/seed.py --reset         # wipe all tables, then seed
    uv run python scripts/seed.py --db-path X     # use a different DuckDB file
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

# Allow `uv run python scripts/seed.py` from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scheduler_app.db import DEFAULT_DB_PATH, TABLES, Database  # noqa: E402
from scheduler_app.store import (  # noqa: E402
    create_scheduled_procedure,
    ensure_instrument_compatibility,
    find_scheduled_procedure,
    get_or_create,
)

# ---------------------------------------------------------------------------
# Canonical vocabulary — DESIGN.md "Data model" seed values (sort_order 1-8 in
# the order listed there) with the modality mapping from DESIGN.md
# "Procedure type -> modality controlled vocabulary".
# ---------------------------------------------------------------------------

# (name, modality_name, modality_abbreviation, sort_order)
PROCEDURE_TYPES = [
    ("Acute extracellular electrophysiology (modular insertion)",
     "Extracellular electrophysiology", "ecephys", 1),
    ("Whole-brain 3D histology",
     "Selective plane illumination microscopy", "SPIM", 2),
    ("Cellular imaging",
     "Planar optical physiology", "pophys", 3),
    ("Fiber photometry (FIP)",
     "Fiber photometry", "fib", 4),
    ("Fiber photometry (HSFP)",
     "Fiber photometry", "fib", 5),
    ("Patch foraging behavior",
     "Behavior", "behavior", 6),
    ("Dynamic foraging behavior",
     "Behavior", "behavior", 7),
    ("Whole-brain axonal imaging",
     "Selective plane illumination microscopy", "SPIM", 8),
]

# Short aliases used below for legibility.
PT_EPHYS = "Acute extracellular electrophysiology (modular insertion)"
PT_HISTOLOGY = "Whole-brain 3D histology"
PT_CELLULAR = "Cellular imaging"
PT_FIP = "Fiber photometry (FIP)"
PT_PATCH = "Patch foraging behavior"
PT_DYNAMIC = "Dynamic foraging behavior"
PT_AXONAL = "Whole-brain axonal imaging"

# ---------------------------------------------------------------------------
# Instruments — DESIGN.md seed table (name, instrument_id, sipe_rig_name,
# compatible procedure types), as amended by Doug's domain correction below.
# ---------------------------------------------------------------------------

# NOTE (Doug's decision, 2026-08-04 — supersedes DESIGN.md's seed table):
# a behavior rig runs exactly ONE behavior task. VR foraging *is* the patch
# foraging paradigm (Bruno's Aind.Behavior.VrForaging), so VR-Foraging-Rig-A
# offers Patch foraging (+ FIP) only, and Dynamic foraging moves to its own
# box. See BUILD_NOTES.md "Domain correction".
INSTRUMENTS = [
    {
        "name": "VR-Foraging-Rig-A",
        "instrument_id": "VRForaging1",
        "sipe_rig_name": "BEH-VR-01",
        "compatible": [PT_PATCH, PT_FIP],
    },
    {
        "name": "Dynamic-Foraging-Box-1",
        "instrument_id": "DynamicForaging1",
        "sipe_rig_name": "BEH-DF-01",
        "compatible": [PT_DYNAMIC, PT_FIP],
    },
    {
        "name": "SmartSPIM-1",
        "instrument_id": "SmartSPIM1",
        "sipe_rig_name": "IMG-SPIM-01",
        "compatible": [PT_HISTOLOGY, PT_CELLULAR, PT_AXONAL],
    },
    {
        # A behavior task on an ephys rig is fine — that's still one behavior
        # task (Patch foraging), optionally alongside ephys/FIP.
        "name": "Ephys-Rig-2",
        "instrument_id": "EPHYS2",
        "sipe_rig_name": "EPHYS-02",
        "compatible": [PT_EPHYS, PT_PATCH, PT_FIP],
    },
]

INST_VR = "VR-Foraging-Rig-A"
INST_DF = "Dynamic-Foraging-Box-1"
INST_SPIM = "SmartSPIM-1"
INST_EPHYS = "Ephys-Rig-2"

# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

MICE = [
    ("testmouse1", "test-genotype"),
    ("testmouse2", "test-genotype"),
    ("testmouse3", "test-genotype"),
]

PROJECT_PF = "Cognitive flexibility in patch foraging"
PROJECT_BC = "Brain-wide connectivity"
PROJECTS = [PROJECT_PF, PROJECT_BC]

# ORCIDs are deliberately invalid placeholder values (all-zero prefix) so they
# cannot be mistaken for anyone's real ORCID; the field exists to show the
# aind-data-schema `Person` mapping.
USERS = [
    ("Doug Ollerenshaw", "doug.ollerenshaw@alleninstitute.org", "0000-0000-0000-0001"),
    ("Bruno Cruz", "bruno.cruz@alleninstitute.org", None),
    ("Jane Kim", "jane.kim@alleninstitute.org", "0000-0000-0000-0002"),
]

USR_DOUG = "doug.ollerenshaw@alleninstitute.org"
USR_BRUNO = "bruno.cruz@alleninstitute.org"
USR_JANE = "jane.kim@alleninstitute.org"

# The rig's local timezone (the machine's). All procedure times below are
# written as local wall-clock and converted to UTC on the way into the
# database. A calendar reader sees local time, so this is what keeps the
# seeded schedule looking like a real working week.
LOCAL_TZ = datetime.now().astimezone().tzinfo

# Working-hours window every seeded procedure must fit inside (local time).
# Keep in step with WORKING_HOURS in template.html.
WORKING_DAY_START = time(7, 0)
WORKING_DAY_END = time(18, 0)

# TIMEZONE RULE (Doug's decision, 2026-08-04 — supersedes DESIGN.md, whose
# seed table says "times UTC"): every clock time in this file is RIG-LOCAL
# wall-clock. SP-1's documented 09:00 means 9 a.m. at the rig, not 09:00 UTC
# (which renders as 02:00 in Pacific time — the 2 a.m. session from Doug's
# first browser pass). Times are converted to UTC on the way into the
# database, which remains UTC-only. See BUILD_NOTES.md "M12".

# Synthetic IACUC / ethics protocol numbers.
ETHICS_BEHAVIOR = "IACUC-2109"
ETHICS_IMAGING = "IACUC-2115"

# ---------------------------------------------------------------------------
# Scheduled procedures.
#
# The first four rows are SP-1..SP-4 exactly as tabulated in DESIGN.md; their
# day offsets come from that table read relative to the document's "today"
# (2026-08-03): 08-04 -> +1, 08-05 -> +2, 08-07 -> +4, 08-11 -> +8. The rest
# fill the next ~3 weeks so the calendar is populated, mixing single- and
# multi-platform sessions across all four instruments.
#
# Fields: day offset from today, start time, duration in hours, mouse
# subject_id, instrument name, project, contact, experimenters, active
# procedure types, and optional extras. Every `start` is LOCAL wall-clock and
# every row lands on the first weekday at/after its offset — see
# _weekday_local_start. Day offsets are therefore approximate on run dates
# where the offset falls on a weekend.
# ---------------------------------------------------------------------------

CANONICAL_PROCEDURES = [
    {   # SP-1 — DESIGN.md puts this on VR-Foraging-Rig-A, which is now
        # illegal (Dynamic foraging is not a VR-rig task); moved to the
        # dynamic-foraging box, everything else unchanged, so the canonical
        # multi-modality example survives. See BUILD_NOTES.md.
        "label": "SP-1",
        "day_offset": 1, "start": time(9, 0), "hours": 2,
        "mouse": "testmouse1", "instrument": INST_DF,
        "project": PROJECT_PF, "contact": USR_DOUG, "experimenters": [USR_BRUNO],
        "types": [PT_DYNAMIC, PT_FIP],
        "ethics_review_id": ETHICS_BEHAVIOR,
        "protocols": "Dynamic foraging task v2; FIP dual-fiber",
        "planned_config": {"stage": "stage_final", "fibers": ["DMS-left", "DMS-right"]},
    },
    {   # SP-2
        "label": "SP-2",
        "day_offset": 2, "start": time(13, 0), "hours": 1.5,
        "mouse": "testmouse2", "instrument": "VR-Foraging-Rig-A",
        "project": PROJECT_PF, "contact": USR_DOUG, "experimenters": [USR_JANE],
        "types": [PT_PATCH],
        "ethics_review_id": ETHICS_BEHAVIOR,
        "protocols": "Patch foraging task, VR corridor",
        "planned_config": {"stage": "stage_2"},
    },
    {   # SP-3
        "label": "SP-3",
        "day_offset": 4, "start": time(10, 0), "hours": 6,
        "mouse": "testmouse3", "instrument": "SmartSPIM-1",
        "project": PROJECT_BC, "contact": USR_JANE, "experimenters": [USR_JANE],
        "types": [PT_HISTOLOGY],
        "ethics_review_id": ETHICS_IMAGING,
        "protocols": "Whole-brain 3D histology, standard clearing",
    },
    {   # SP-4
        "label": "SP-4",
        "day_offset": 8, "start": time(9, 0), "hours": 3,
        "mouse": "testmouse1", "instrument": "Ephys-Rig-2",
        "project": PROJECT_PF, "contact": USR_DOUG, "experimenters": [USR_BRUNO],
        "types": [PT_EPHYS, PT_FIP],
        "ethics_review_id": ETHICS_BEHAVIOR,
        "protocols": "Modular probe insertion, 4 shanks; FIP dual-fiber",
        "planned_config": {"probe_count": 4, "fibers": ["DMS-left", "DMS-right"]},
    },
]

# Additional procedures (14) bringing the total to 18 across ~3 weeks.
# Times are LOCAL working hours (see _weekday_local_start) and weekday-
# nudged, so the calendar reads naturally for whoever opens it.
EXTRA_PROCEDURES = [
    {"day_offset": 1, "start": time(13, 30), "hours": 2,
     "mouse": "testmouse2", "instrument": "Ephys-Rig-2", "project": PROJECT_PF,
     "contact": USR_DOUG, "experimenters": [USR_BRUNO], "types": [PT_EPHYS],
     "ethics_review_id": ETHICS_BEHAVIOR,
     "protocols": "Modular probe insertion, 2 shanks"},

    {"day_offset": 2, "start": time(9, 0), "hours": 2,
     "mouse": "testmouse1", "instrument": INST_DF, "project": PROJECT_PF,
     "contact": USR_DOUG, "experimenters": [USR_BRUNO, USR_JANE],
     "types": [PT_DYNAMIC, PT_FIP], "ethics_review_id": ETHICS_BEHAVIOR,
     "protocols": "Dynamic foraging task v2; FIP dual-fiber",
     "planned_config": {"stage": "stage_final", "fibers": ["DMS-left", "DMS-right"]}},

    {"day_offset": 3, "start": time(9, 30), "hours": 2,
     "mouse": "testmouse2", "instrument": "VR-Foraging-Rig-A", "project": PROJECT_PF,
     "contact": USR_DOUG, "experimenters": [USR_JANE], "types": [PT_PATCH, PT_FIP],
     "ethics_review_id": ETHICS_BEHAVIOR,
     "protocols": "Patch foraging task; FIP single-fiber"},

    {"day_offset": 3, "start": time(12, 0), "hours": 5,
     "mouse": "testmouse3", "instrument": "SmartSPIM-1", "project": PROJECT_BC,
     "contact": USR_JANE, "experimenters": [USR_JANE], "types": [PT_AXONAL],
     "ethics_review_id": ETHICS_IMAGING,
     "protocols": "Whole-brain axonal imaging, 3 channels"},

    {"day_offset": 5, "start": time(9, 0), "hours": 2,
     "mouse": "testmouse1", "instrument": INST_DF, "project": PROJECT_PF,
     "contact": USR_DOUG, "experimenters": [USR_BRUNO], "types": [PT_DYNAMIC],
     "ethics_review_id": ETHICS_BEHAVIOR,
     "protocols": "Dynamic foraging task v2",
     "planned_config": {"stage": "stage_final"}},

    {"day_offset": 5, "start": time(13, 0), "hours": 3,
     "mouse": "testmouse2", "instrument": "Ephys-Rig-2", "project": PROJECT_PF,
     "contact": USR_DOUG, "experimenters": [USR_BRUNO], "types": [PT_EPHYS, PT_FIP],
     "ethics_review_id": ETHICS_BEHAVIOR,
     "protocols": "Modular probe insertion, 4 shanks; FIP dual-fiber",
     "planned_config": {"probe_count": 4, "fibers": ["DMS-left", "DMS-right"]}},

    {"day_offset": 6, "start": time(10, 0), "hours": 4,
     "mouse": "testmouse3", "instrument": "SmartSPIM-1", "project": PROJECT_BC,
     "contact": USR_JANE, "experimenters": [USR_JANE], "types": [PT_CELLULAR],
     "ethics_review_id": ETHICS_IMAGING,
     "protocols": "Cellular imaging survey"},

    {"day_offset": 9, "start": time(9, 0), "hours": 2,
     "mouse": "testmouse2", "instrument": "VR-Foraging-Rig-A", "project": PROJECT_PF,
     "contact": USR_DOUG, "experimenters": [USR_JANE], "types": [PT_PATCH],
     "ethics_review_id": ETHICS_BEHAVIOR,
     "protocols": "Patch foraging task, VR corridor",
     "planned_config": {"stage": "stage_3"}},

    {"day_offset": 9, "start": time(13, 0), "hours": 2,
     "mouse": "testmouse1", "instrument": INST_DF, "project": PROJECT_PF,
     "contact": USR_DOUG, "experimenters": [USR_BRUNO], "types": [PT_DYNAMIC, PT_FIP],
     "ethics_review_id": ETHICS_BEHAVIOR,
     "protocols": "Dynamic foraging task v2; FIP dual-fiber"},

    {"day_offset": 10, "start": time(10, 0), "hours": 6,
     "mouse": "testmouse3", "instrument": "SmartSPIM-1", "project": PROJECT_BC,
     "contact": USR_JANE, "experimenters": [USR_JANE, USR_DOUG],
     "types": [PT_HISTOLOGY], "ethics_review_id": ETHICS_IMAGING,
     "protocols": "Whole-brain 3D histology, standard clearing"},

    {"day_offset": 12, "start": time(9, 0), "hours": 2,
     "mouse": "testmouse1", "instrument": INST_DF, "project": PROJECT_PF,
     "contact": USR_DOUG, "experimenters": [USR_BRUNO], "types": [PT_DYNAMIC],
     "ethics_review_id": ETHICS_BEHAVIOR,
     "protocols": "Dynamic foraging task v2"},

    {"day_offset": 12, "start": time(13, 30), "hours": 3,
     "mouse": "testmouse2", "instrument": "Ephys-Rig-2", "project": PROJECT_PF,
     "contact": USR_DOUG, "experimenters": [USR_BRUNO], "types": [PT_EPHYS],
     "ethics_review_id": ETHICS_BEHAVIOR,
     "protocols": "Modular probe insertion, 4 shanks",
     "planned_config": {"probe_count": 4}},

    {"day_offset": 15, "start": time(9, 30), "hours": 2,
     "mouse": "testmouse2", "instrument": "VR-Foraging-Rig-A", "project": PROJECT_PF,
     "contact": USR_DOUG, "experimenters": [USR_JANE], "types": [PT_PATCH, PT_FIP],
     "ethics_review_id": ETHICS_BEHAVIOR,
     "protocols": "Patch foraging task; FIP single-fiber"},

    {"day_offset": 16, "start": time(10, 0), "hours": 5,
     "mouse": "testmouse3", "instrument": "SmartSPIM-1", "project": PROJECT_BC,
     "contact": USR_JANE, "experimenters": [USR_JANE], "types": [PT_AXONAL],
     "ethics_review_id": ETHICS_IMAGING,
     "protocols": "Whole-brain axonal imaging, 3 channels"},
]


def _today(reference: datetime | None = None) -> datetime:
    """Midnight UTC on the seeding reference date (default: today).

    Used only as the date anchor that day offsets are added to; the actual
    clock times are applied in the local timezone by
    :func:`_weekday_local_start`.
    """
    now = reference or datetime.now(timezone.utc)
    return now.astimezone(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def _weekday_local_start(today: datetime, day_offset: int, start: time) -> datetime:
    """Start time for EVERY seeded row: `start` read as rig-LOCAL wall-clock
    on the first weekday at/after ``today + day_offset``, returned as UTC.

    Two deliberate choices, both applied uniformly to the canonical SP-1..SP-4
    rows and the filler rows (see BUILD_NOTES.md "M12"):

    - **Local, not UTC.** A human reading the calendar sees local time, so
      DESIGN.md's documented 09:00 means 9 a.m. at the rig. Reading it as UTC
      rendered it at 02:00 Pacific — the 2 a.m. session from the first
      browser pass. The database still stores UTC.
    - **Weekends nudged forward.** Rig work happens on weekdays; a histology
      session appearing on a Saturday just because the seed script ran on a
      Tuesday makes the demo look wrong. This costs DESIGN.md's exact day
      offsets on some run dates (they become "first weekday at or after the
      offset"), which is a better trade than a weekend session.
    """
    day = today + timedelta(days=day_offset)
    while day.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
        day += timedelta(days=1)
    local_naive = datetime(
        day.year, day.month, day.day, start.hour, start.minute
    )
    return local_naive.replace(tzinfo=LOCAL_TZ).astimezone(timezone.utc)


def wipe(db: Database) -> None:
    """Delete every row from every table (for --reset)."""
    with db.write() as conn:
        for table in reversed(TABLES):
            conn.execute(f"DELETE FROM {table}")


def seed_database(db: Database, reference: datetime | None = None) -> dict[str, int]:
    """Seed (or top up) the database. Returns per-table row counts.

    Safe to re-run: every insert is guarded by a natural-key lookup.
    """
    if reference is not None:
        today = _today(reference)
    else:
        today = _today()

    # --- vocabulary -------------------------------------------------------
    type_ids: dict[str, str] = {}
    for name, modality_name, modality_abbr, sort_order in PROCEDURE_TYPES:
        type_ids[name] = get_or_create(
            db, "procedure_types", "name", name,
            {
                "modality_name": modality_name,
                "modality_abbreviation": modality_abbr,
                "sort_order": sort_order,
            },
        )

    # --- instruments + compatibility -------------------------------------
    instrument_ids: dict[str, str] = {}
    for inst in INSTRUMENTS:
        inst_id = get_or_create(
            db, "instruments", "name", inst["name"],
            {
                "instrument_id": inst["instrument_id"],
                "sipe_rig_name": inst["sipe_rig_name"],
                "active": True,
            },
        )
        instrument_ids[inst["name"]] = inst_id
        ensure_instrument_compatibility(
            db, inst_id, [type_ids[t] for t in inst["compatible"]]
        )

    # --- lookups ----------------------------------------------------------
    mouse_ids = {
        subject_id: get_or_create(
            db, "mice", "subject_id", subject_id, {"genotype": genotype}
        )
        for subject_id, genotype in MICE
    }
    project_ids = {
        name: get_or_create(db, "projects", "name", name, {})
        for name in PROJECTS
    }
    user_ids = {
        email: get_or_create(
            db, "users", "email", email, {"name": name, "orcid": orcid}
        )
        for name, email, orcid in USERS
    }

    # --- scheduled procedures --------------------------------------------
    # Slots already in the database from an EARLIER run. The same mouse in the
    # same slot means "this spec is already seeded", which is what makes
    # re-running a no-op.
    seeded_slots: dict[tuple[str, datetime], str] = {}
    for inst_id, existing_start, existing_mouse_id in db.conn.execute(
        "SELECT instrument_id, scheduled_start, mouse_id FROM scheduled_procedures"
    ).fetchall():
        seeded_slots[(inst_id, existing_start)] = existing_mouse_id

    # Slots filled during THIS run. A clash here is two different specs wanting
    # the same rig at the same instant — including the same mouse, which the
    # weekday nudge can produce when a canonical row's weekend offset lands on
    # a filler row's day — so the later spec shifts rather than being skipped.
    placed_slots: set[tuple[str, datetime]] = set()

    def add(spec: dict, start_dt: datetime) -> None:
        instrument_id = instrument_ids[spec["instrument"]]
        mouse_id = mouse_ids[spec["mouse"]]

        # Resolve the slot, shifting an hour at a time past anything already
        # taken. Bailing out as soon as a slot holds this mouse from a previous
        # run keeps re-runs idempotent; the scan is deterministic, so every run
        # resolves each spec the same way.
        while True:
            key = (instrument_id, start_dt)
            if seeded_slots.get(key) == mouse_id:
                return  # already seeded on an earlier run
            if key not in placed_slots and key not in seeded_slots:
                break
            start_dt += timedelta(hours=1)

        if find_scheduled_procedure(db, mouse_id, instrument_id, start_dt) is not None:
            return  # already seeded — re-run, nothing to do
        placed_slots.add((instrument_id, start_dt))

        create_scheduled_procedure(
            db,
            mouse_id=mouse_id,
            instrument_id=instrument_id,
            project_id=project_ids[spec["project"]],
            contact_user_id=user_ids[spec["contact"]],
            scheduled_start=start_dt,
            scheduled_end=start_dt + timedelta(hours=spec["hours"]),
            active_procedure_type_ids=[type_ids[t] for t in spec["types"]],
            experimenter_user_ids=[user_ids[e] for e in spec["experimenters"]],
            ethics_review_id=spec.get("ethics_review_id"),
            notes=spec.get("notes"),
            planned_config=spec.get("planned_config"),
            protocols=spec.get("protocols"),
        )

    for spec in CANONICAL_PROCEDURES:
        add(spec, _weekday_local_start(today, spec["day_offset"], spec["start"]))
    for spec in EXTRA_PROCEDURES:
        add(spec, _weekday_local_start(today, spec["day_offset"], spec["start"]))

    return row_counts(db)


def row_counts(db: Database) -> dict[str, int]:
    return {
        table: db.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in TABLES
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH),
                        help=f"DuckDB file to seed (default: {DEFAULT_DB_PATH})")
    parser.add_argument("--reset", action="store_true",
                        help="delete all existing rows before seeding")
    args = parser.parse_args()

    db = Database(args.db_path)
    try:
        if args.reset:
            wipe(db)
            print("Wiped all tables.")
        counts = seed_database(db)
    finally:
        db.close()

    print(f"Seeded {args.db_path}:")
    for table, count in counts.items():
        print(f"  {table:38s} {count:4d}")


if __name__ == "__main__":
    main()
