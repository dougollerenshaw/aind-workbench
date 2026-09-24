"""Read-side queries: fetch rows with lookups resolved into plain dicts.

Every scheduled-procedure dict carries the *full* field set; the API layer
narrows it to the list shape via ``response_model`` filtering, so list and
detail payloads can never drift apart.

Filter semantics (DESIGN.md list filters): all optional and combinable;
``*_after`` bounds are inclusive (>=) and ``*_before`` bounds are inclusive
(<=). The rig planned-acquisitions window is start-inclusive, end-exclusive.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from scheduler_app.db import Database

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def iso_utc(dt: datetime) -> str:
    """ISO-8601 UTC with a 'Z' suffix, e.g. 2026-08-04T09:00:00Z."""
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def ensure_utc(dt: datetime) -> datetime:
    """Coerce a (possibly naive) datetime to tz-aware UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Scheduled procedures
# ---------------------------------------------------------------------------

_BASE_SELECT = """
SELECT sp.id,
       m.id, m.subject_id,
       i.id, i.name, i.sipe_rig_name,
       p.id, p.name,
       cu.id, cu.name,
       sp.acquisition_type, sp.acquisition_name,
       sp.scheduled_start, sp.scheduled_end, sp.status,
       sp.ethics_review_id, sp.notes, sp.planned_config, sp.protocols,
       sp.created_at, sp.updated_at
FROM scheduled_procedures sp
JOIN mice m ON m.id = sp.mouse_id
JOIN instruments i ON i.id = sp.instrument_id
JOIN projects p ON p.id = sp.project_id
JOIN users cu ON cu.id = sp.contact_user_id
"""


def _row_to_record(row: tuple) -> dict:
    return {
        "id": row[0],
        "mouse": {"id": row[1], "subject_id": row[2]},
        "instrument": {"id": row[3], "name": row[4], "sipe_rig_name": row[5]},
        "project": {"id": row[6], "name": row[7]},
        "contact": {"id": row[8], "name": row[9]},
        "experimenters": [],           # filled by _attach_relations
        "active_procedure_types": [],  # filled by _attach_relations
        "acquisition_type": row[10],
        "acquisition_name": row[11],
        "scheduled_start": iso_utc(row[12]),
        "scheduled_end": iso_utc(row[13]),
        "status": row[14],
        "ethics_review_id": row[15],
        "notes": row[16],
        "planned_config": json.loads(row[17]) if row[17] is not None else None,
        "protocols": row[18],
        "created_at": iso_utc(row[19]),
        "updated_at": iso_utc(row[20]),
    }


def _attach_relations(db: Database, records: list[dict]) -> None:
    """Fill active_procedure_types and experimenters for the given records."""
    if not records:
        return
    by_id = {r["id"]: r for r in records}
    ids = list(by_id)
    placeholders = ", ".join("?" for _ in ids)

    for sp_id, type_name in db.conn.execute(
        f"""
        SELECT sat.scheduled_procedure_id, pt.name
        FROM scheduled_procedure_active_types sat
        JOIN procedure_types pt ON pt.id = sat.procedure_type_id
        WHERE sat.scheduled_procedure_id IN ({placeholders})
        ORDER BY pt.name
        """,
        ids,
    ).fetchall():
        by_id[sp_id]["active_procedure_types"].append(type_name)

    for sp_id, user_id, user_name in db.conn.execute(
        f"""
        SELECT se.scheduled_procedure_id, u.id, u.name
        FROM scheduled_procedure_experimenters se
        JOIN users u ON u.id = se.user_id
        WHERE se.scheduled_procedure_id IN ({placeholders})
        ORDER BY u.name
        """,
        ids,
    ).fetchall():
        by_id[sp_id]["experimenters"].append({"id": user_id, "name": user_name})


def fetch_scheduled_procedures(
    db: Database,
    *,
    sp_id: str | None = None,
    mouse_id: str | None = None,
    subject_id: str | None = None,
    instrument_id: str | None = None,
    project_id: str | None = None,
    contact_user_id: str | None = None,
    procedure_type_id: str | None = None,
    status: str | None = None,
    start_after: datetime | None = None,
    start_before: datetime | None = None,
    end_after: datetime | None = None,
    end_before: datetime | None = None,
) -> list[dict]:
    """Scheduled procedures, fully resolved, ordered by scheduled_start."""
    clauses: list[str] = []
    params: list = []

    def add(clause: str, value) -> None:
        clauses.append(clause)
        params.append(value)

    if sp_id is not None:
        add("sp.id = ?", sp_id)
    if mouse_id is not None:
        add("sp.mouse_id = ?", mouse_id)
    if subject_id is not None:
        add("m.subject_id = ?", subject_id)
    if instrument_id is not None:
        add("sp.instrument_id = ?", instrument_id)
    if project_id is not None:
        add("sp.project_id = ?", project_id)
    if contact_user_id is not None:
        add("sp.contact_user_id = ?", contact_user_id)
    if procedure_type_id is not None:
        add(
            "EXISTS (SELECT 1 FROM scheduled_procedure_active_types sat "
            "WHERE sat.scheduled_procedure_id = sp.id "
            "AND sat.procedure_type_id = ?)",
            procedure_type_id,
        )
    if status is not None:
        add("sp.status = ?", status)
    if start_after is not None:
        add("sp.scheduled_start >= ?", ensure_utc(start_after))
    if start_before is not None:
        add("sp.scheduled_start <= ?", ensure_utc(start_before))
    if end_after is not None:
        add("sp.scheduled_end >= ?", ensure_utc(end_after))
    if end_before is not None:
        add("sp.scheduled_end <= ?", ensure_utc(end_before))

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = db.conn.execute(
        f"{_BASE_SELECT} {where} ORDER BY sp.scheduled_start, sp.id", params
    ).fetchall()
    records = [_row_to_record(r) for r in rows]
    _attach_relations(db, records)
    return records


def fetch_scheduled_procedure(db: Database, sp_id: str) -> dict | None:
    records = fetch_scheduled_procedures(db, sp_id=sp_id)
    return records[0] if records else None


# ---------------------------------------------------------------------------
# Rig-facing convenience queries
# ---------------------------------------------------------------------------


def resolve_rig(db: Database, rig_id: str) -> str | None:
    """Instrument id for a rig identity: sipe_rig_name, falling back to name."""
    row = db.conn.execute(
        "SELECT id FROM instruments WHERE sipe_rig_name = ?", [rig_id]
    ).fetchone()
    if row is None:
        row = db.conn.execute(
            "SELECT id FROM instruments WHERE name = ?", [rig_id]
        ).fetchone()
    return row[0] if row else None


def fetch_planned_acquisitions(
    db: Database,
    instrument_id: str,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[dict]:
    """Planned acquisitions on one instrument (start inclusive, end exclusive)."""
    clauses = ["sp.instrument_id = ?"]
    params: list = [instrument_id]
    if start is not None:
        clauses.append("sp.scheduled_start >= ?")
        params.append(ensure_utc(start))
    if end is not None:
        clauses.append("sp.scheduled_start < ?")
        params.append(ensure_utc(end))
    rows = db.conn.execute(
        f"""
        SELECT sp.id, m.subject_id, sp.acquisition_type,
               sp.scheduled_start, sp.scheduled_end
        FROM scheduled_procedures sp
        JOIN mice m ON m.id = sp.mouse_id
        WHERE {" AND ".join(clauses)}
        ORDER BY sp.scheduled_start, sp.id
        """,
        params,
    ).fetchall()
    return [
        {
            "id": r[0],
            "subject_id": r[1],
            "acquisition_type": r[2],
            "scheduled_start": iso_utc(r[3]),
            "scheduled_end": iso_utc(r[4]),
        }
        for r in rows
    ]


def fetch_next_acquisition(
    db: Database, animal_id: str, now: datetime
) -> dict | None:
    """The soonest FUTURE scheduled procedure (status 'scheduled') for a mouse.

    ``animal_id`` matches ``mice.subject_id``, falling back to the mouse's
    UUID primary key. Returns None if the animal has no upcoming procedure;
    raises KeyError if the animal itself is unknown.
    """
    mouse = db.conn.execute(
        "SELECT id FROM mice WHERE subject_id = ?", [animal_id]
    ).fetchone()
    if mouse is None:
        mouse = db.conn.execute(
            "SELECT id FROM mice WHERE id = ?", [animal_id]
        ).fetchone()
    if mouse is None:
        raise KeyError(animal_id)

    row = db.conn.execute(
        """
        SELECT sp.id, m.subject_id, i.name, sp.acquisition_type, sp.scheduled_start
        FROM scheduled_procedures sp
        JOIN mice m ON m.id = sp.mouse_id
        JOIN instruments i ON i.id = sp.instrument_id
        WHERE sp.mouse_id = ? AND sp.status = 'scheduled' AND sp.scheduled_start > ?
        ORDER BY sp.scheduled_start, sp.id
        LIMIT 1
        """,
        [mouse[0], ensure_utc(now)],
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "subject_id": row[1],
        "instrument": row[2],
        "acquisition_type": row[3],
        "scheduled_start": iso_utc(row[4]),
    }


# ---------------------------------------------------------------------------
# Lookup endpoints
# ---------------------------------------------------------------------------


def fetch_instruments(
    db: Database,
    *,
    active: bool | None = None,
    procedure_type_id: str | None = None,
) -> list[dict]:
    clauses: list[str] = []
    params: list = []
    if active is not None:
        clauses.append("i.active = ?")
        params.append(active)
    if procedure_type_id is not None:
        clauses.append(
            "EXISTS (SELECT 1 FROM instrument_compatible_types ict "
            "WHERE ict.instrument_id = i.id AND ict.procedure_type_id = ?)"
        )
        params.append(procedure_type_id)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = db.conn.execute(
        f"""
        SELECT i.id, i.name, i.instrument_id, i.sipe_rig_name, i.location, i.active
        FROM instruments i {where} ORDER BY i.name
        """,
        params,
    ).fetchall()
    records = {
        r[0]: {
            "id": r[0],
            "name": r[1],
            "instrument_id": r[2],
            "sipe_rig_name": r[3],
            "location": r[4],
            "active": r[5],
            "compatible_procedure_types": [],
        }
        for r in rows
    }
    if records:
        placeholders = ", ".join("?" for _ in records)
        for inst_id, pt_id, pt_name, pt_modality in db.conn.execute(
            f"""
            SELECT ict.instrument_id, pt.id, pt.name, pt.modality_name
            FROM instrument_compatible_types ict
            JOIN procedure_types pt ON pt.id = ict.procedure_type_id
            WHERE ict.instrument_id IN ({placeholders})
            ORDER BY pt.sort_order
            """,
            list(records),
        ).fetchall():
            records[inst_id]["compatible_procedure_types"].append(
                # modality_name is included so the form can enforce the
                # one-behavior-task-per-procedure rule client-side.
                {"id": pt_id, "name": pt_name, "modality_name": pt_modality}
            )
    return list(records.values())


def fetch_procedure_types(db: Database) -> list[dict]:
    rows = db.conn.execute(
        "SELECT id, name, modality_name, modality_abbreviation, sort_order "
        "FROM procedure_types ORDER BY sort_order"
    ).fetchall()
    return [
        {
            "id": r[0],
            "name": r[1],
            "modality_name": r[2],
            "modality_abbreviation": r[3],
            "sort_order": r[4],
        }
        for r in rows
    ]


def fetch_mice(db: Database, subject_id: str | None = None) -> list[dict]:
    clauses, params = "", []
    if subject_id is not None:
        clauses = "WHERE subject_id = ?"
        params = [subject_id]
    rows = db.conn.execute(
        f"SELECT id, subject_id, genotype FROM mice {clauses} ORDER BY subject_id",
        params,
    ).fetchall()
    return [{"id": r[0], "subject_id": r[1], "genotype": r[2]} for r in rows]


def fetch_projects(db: Database) -> list[dict]:
    rows = db.conn.execute("SELECT id, name FROM projects ORDER BY name").fetchall()
    return [{"id": r[0], "name": r[1]} for r in rows]


def fetch_users(db: Database) -> list[dict]:
    rows = db.conn.execute(
        "SELECT id, name, email, orcid FROM users ORDER BY name"
    ).fetchall()
    return [{"id": r[0], "name": r[1], "email": r[2], "orcid": r[3]} for r in rows]
