"""Write-side store logic: validation, computed fields, and inserts.

This module is the single place where the DESIGN.md validation rules and the
computed ``acquisition_type`` live, so the seed script (M2) and the admin
write API (M4) behave identically.

Validation rules (DESIGN.md "Validation rules"):

1. ``scheduled_end`` must be strictly after ``scheduled_start``.
2. Every active procedure type on a scheduled procedure must be in the
   instrument's compatible set.
3. ``acquisition_type`` is always recomputed server-side from the active
   type names; it is never client-supplied.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Iterable, Sequence

from app.db import Database, new_uuid, new_uuid7, utcnow

ACQUISITION_TYPE_SEPARATOR = " + "


class ValidationError(Exception):
    """A rejected write. ``code``/``detail`` shape the API error response."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


# ---------------------------------------------------------------------------
# Computed fields
# ---------------------------------------------------------------------------


def compute_acquisition_type(type_names: Iterable[str]) -> str:
    """Active procedure type names, sorted alphabetically, joined with " + ".

    Rule 3: this is the only way ``acquisition_type`` is ever produced.
    """
    return ACQUISITION_TYPE_SEPARATOR.join(sorted(type_names))


# ---------------------------------------------------------------------------
# Small read helpers used by validation
# ---------------------------------------------------------------------------


def procedure_type_names(db: Database, procedure_type_ids: Sequence[str]) -> dict[str, str]:
    """Map procedure_type id -> name for the given ids."""
    if not procedure_type_ids:
        return {}
    placeholders = ", ".join("?" for _ in procedure_type_ids)
    rows = db.conn.execute(
        f"SELECT id, name FROM procedure_types WHERE id IN ({placeholders})",
        list(procedure_type_ids),
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def compatible_type_ids(db: Database, instrument_id: str) -> set[str]:
    """The instrument's compatible procedure type ids."""
    rows = db.conn.execute(
        "SELECT procedure_type_id FROM instrument_compatible_types WHERE instrument_id = ?",
        [instrument_id],
    ).fetchall()
    return {r[0] for r in rows}


def compatible_type_names(db: Database, instrument_id: str) -> list[str]:
    """The instrument's compatible procedure type names, in display order."""
    rows = db.conn.execute(
        """
        SELECT pt.name
        FROM instrument_compatible_types ict
        JOIN procedure_types pt ON pt.id = ict.procedure_type_id
        WHERE ict.instrument_id = ?
        ORDER BY pt.sort_order
        """,
        [instrument_id],
    ).fetchall()
    return [r[0] for r in rows]


def _require_row(db: Database, table: str, row_id: str, label: str) -> tuple:
    row = db.conn.execute(f"SELECT * FROM {table} WHERE id = ?", [row_id]).fetchone()
    if row is None:
        raise ValidationError("unknown_reference", f"Unknown {label} id '{row_id}'.")
    return row


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_scheduled_procedure(
    db: Database,
    *,
    mouse_id: str,
    instrument_id: str,
    project_id: str,
    contact_user_id: str,
    scheduled_start: datetime,
    scheduled_end: datetime,
    active_procedure_type_ids: Sequence[str],
    experimenter_user_ids: Sequence[str] = (),
) -> str:
    """Apply the DESIGN.md validation rules; return the computed
    ``acquisition_type``. Raises :class:`ValidationError` on rejection.
    """
    # Referential checks (the prototype enforces FKs in the app layer).
    _require_row(db, "mice", mouse_id, "mouse")
    instrument = _require_row(db, "instruments", instrument_id, "instrument")
    _require_row(db, "projects", project_id, "project")
    _require_row(db, "users", contact_user_id, "contact user")
    for user_id in experimenter_user_ids:
        _require_row(db, "users", user_id, "experimenter user")

    # Rule 1: end strictly after start.
    if scheduled_end <= scheduled_start:
        raise ValidationError(
            "invalid_time_range",
            f"scheduled_end ({scheduled_end.isoformat()}) must be strictly after "
            f"scheduled_start ({scheduled_start.isoformat()}).",
        )

    if not active_procedure_type_ids:
        raise ValidationError(
            "no_active_procedure_types",
            "At least one active procedure type is required.",
        )

    names = procedure_type_names(db, active_procedure_type_ids)
    missing = [pid for pid in active_procedure_type_ids if pid not in names]
    if missing:
        raise ValidationError(
            "unknown_reference",
            f"Unknown procedure type id(s): {', '.join(missing)}.",
        )

    # Rule 2: active types must be a subset of the instrument's compatible set.
    instrument_name = instrument[1]
    compatible = compatible_type_ids(db, instrument_id)
    for pid in active_procedure_type_ids:
        if pid not in compatible:
            raise ValidationError(
                "incompatible_procedure_type",
                f"'{names[pid]}' is not compatible with instrument "
                f"'{instrument_name}'. Compatible types: "
                f"{', '.join(compatible_type_names(db, instrument_id))}.",
            )

    # Rule 3: always computed here, never taken from the caller. Dedupe the
    # ids exactly like the join-row inserts do, so a repeated id in the
    # request can never make acquisition_type disagree with the join table.
    return compute_acquisition_type(
        names[pid] for pid in dict.fromkeys(active_procedure_type_ids)
    )


def _encode_planned_config(value: Any) -> str | None:
    """Encode planned_config for the JSON column; reject invalid JSON strings."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValidationError(
                "invalid_planned_config",
                f"planned_config is not valid JSON: {exc}.",
            )
        return value
    return json.dumps(value)


# ---------------------------------------------------------------------------
# Insert
# ---------------------------------------------------------------------------


def create_scheduled_procedure(
    db: Database,
    *,
    mouse_id: str,
    instrument_id: str,
    project_id: str,
    contact_user_id: str,
    scheduled_start: datetime,
    scheduled_end: datetime,
    active_procedure_type_ids: Sequence[str],
    experimenter_user_ids: Sequence[str] = (),
    status: str = "scheduled",
    acquisition_name: str | None = None,
    ethics_review_id: str | None = None,
    notes: str | None = None,
    planned_config: Any = None,
    protocols: str | None = None,
) -> str:
    """Validate and insert a scheduled procedure plus its join rows.

    Returns the new UUIDv7 id — the persistent acquisition token, minted here
    at scheduling time.
    """
    acquisition_type = validate_scheduled_procedure(
        db,
        mouse_id=mouse_id,
        instrument_id=instrument_id,
        project_id=project_id,
        contact_user_id=contact_user_id,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        active_procedure_type_ids=active_procedure_type_ids,
        experimenter_user_ids=experimenter_user_ids,
    )

    sp_id = new_uuid7()
    now = utcnow()
    config_json = _encode_planned_config(planned_config)

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
                sp_id, mouse_id, instrument_id, project_id, contact_user_id,
                scheduled_start, scheduled_end, acquisition_type,
                acquisition_name, status, ethics_review_id, notes,
                config_json, protocols, now, now,
            ],
        )
        for pid in dict.fromkeys(active_procedure_type_ids):
            conn.execute(
                "INSERT INTO scheduled_procedure_active_types "
                "(scheduled_procedure_id, procedure_type_id) VALUES (?, ?)",
                [sp_id, pid],
            )
        for user_id in dict.fromkeys(experimenter_user_ids):
            conn.execute(
                "INSERT INTO scheduled_procedure_experimenters "
                "(scheduled_procedure_id, user_id) VALUES (?, ?)",
                [sp_id, user_id],
            )
    return sp_id


# ---------------------------------------------------------------------------
# Update / delete (admin API)
# ---------------------------------------------------------------------------


def update_scheduled_procedure(
    db: Database,
    sp_id: str,
    *,
    mouse_id: str,
    instrument_id: str,
    project_id: str,
    contact_user_id: str,
    scheduled_start: datetime,
    scheduled_end: datetime,
    active_procedure_type_ids: Sequence[str],
    experimenter_user_ids: Sequence[str] = (),
    status: str = "scheduled",
    acquisition_name: str | None = None,
    ethics_review_id: str | None = None,
    notes: str | None = None,
    planned_config: Any = None,
    protocols: str | None = None,
) -> bool:
    """Full-replace update of a scheduled procedure.

    The ``id`` (the acquisition token) and ``created_at`` are immutable;
    ``acquisition_type`` and ``updated_at`` are recomputed server-side. The
    row update and the replacement of both join tables happen in one
    transaction, so a failed write leaves the record untouched.

    Returns False if no such procedure exists.
    """
    exists = db.conn.execute(
        "SELECT 1 FROM scheduled_procedures WHERE id = ?", [sp_id]
    ).fetchone()
    if exists is None:
        return False

    acquisition_type = validate_scheduled_procedure(
        db,
        mouse_id=mouse_id,
        instrument_id=instrument_id,
        project_id=project_id,
        contact_user_id=contact_user_id,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        active_procedure_type_ids=active_procedure_type_ids,
        experimenter_user_ids=experimenter_user_ids,
    )
    config_json = _encode_planned_config(planned_config)
    now = utcnow()

    with db.write() as conn:
        conn.execute(
            """
            UPDATE scheduled_procedures SET
                mouse_id = ?, instrument_id = ?, project_id = ?,
                contact_user_id = ?, scheduled_start = ?, scheduled_end = ?,
                acquisition_type = ?, acquisition_name = ?, status = ?,
                ethics_review_id = ?, notes = ?, planned_config = ?,
                protocols = ?, updated_at = ?
            WHERE id = ?
            """,
            [
                mouse_id, instrument_id, project_id, contact_user_id,
                scheduled_start, scheduled_end, acquisition_type,
                acquisition_name, status, ethics_review_id, notes,
                config_json, protocols, now, sp_id,
            ],
        )
        conn.execute(
            "DELETE FROM scheduled_procedure_active_types WHERE scheduled_procedure_id = ?",
            [sp_id],
        )
        for pid in dict.fromkeys(active_procedure_type_ids):
            conn.execute(
                "INSERT INTO scheduled_procedure_active_types "
                "(scheduled_procedure_id, procedure_type_id) VALUES (?, ?)",
                [sp_id, pid],
            )
        conn.execute(
            "DELETE FROM scheduled_procedure_experimenters WHERE scheduled_procedure_id = ?",
            [sp_id],
        )
        for user_id in dict.fromkeys(experimenter_user_ids):
            conn.execute(
                "INSERT INTO scheduled_procedure_experimenters "
                "(scheduled_procedure_id, user_id) VALUES (?, ?)",
                [sp_id, user_id],
            )
    return True


def delete_scheduled_procedure(db: Database, sp_id: str) -> bool:
    """Delete a scheduled procedure and its join rows (one transaction).

    Returns False if no such procedure exists.
    """
    exists = db.conn.execute(
        "SELECT 1 FROM scheduled_procedures WHERE id = ?", [sp_id]
    ).fetchone()
    if exists is None:
        return False
    with db.write() as conn:
        conn.execute(
            "DELETE FROM scheduled_procedure_active_types WHERE scheduled_procedure_id = ?",
            [sp_id],
        )
        conn.execute(
            "DELETE FROM scheduled_procedure_experimenters WHERE scheduled_procedure_id = ?",
            [sp_id],
        )
        conn.execute("DELETE FROM scheduled_procedures WHERE id = ?", [sp_id])
    return True


# ---------------------------------------------------------------------------
# Admin lookup creation (minimal, so the demo can be populated via the UI)
# ---------------------------------------------------------------------------


def _reject_duplicate(db: Database, table: str, column: str, value: str) -> None:
    if db.conn.execute(
        f"SELECT 1 FROM {table} WHERE {column} = ?", [value]
    ).fetchone():
        raise ValidationError(
            "already_exists", f"A {table} row with {column} '{value}' already exists."
        )


def create_instrument(
    db: Database,
    *,
    name: str,
    instrument_id: str | None = None,
    sipe_rig_name: str | None = None,
    location: str | None = None,
    active: bool = True,
    compatible_procedure_type_ids: Sequence[str] = (),
) -> str:
    _reject_duplicate(db, "instruments", "name", name)
    names = procedure_type_names(db, compatible_procedure_type_ids)
    missing = [p for p in compatible_procedure_type_ids if p not in names]
    if missing:
        raise ValidationError(
            "unknown_reference", f"Unknown procedure type id(s): {', '.join(missing)}."
        )
    row_id = new_uuid()
    with db.write() as conn:
        conn.execute(
            "INSERT INTO instruments (id, name, instrument_id, sipe_rig_name, location, active) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [row_id, name, instrument_id, sipe_rig_name, location, active],
        )
        for pid in dict.fromkeys(compatible_procedure_type_ids):
            conn.execute(
                "INSERT INTO instrument_compatible_types "
                "(instrument_id, procedure_type_id) VALUES (?, ?)",
                [row_id, pid],
            )
    return row_id


def create_mouse(db: Database, *, subject_id: str, genotype: str | None = None) -> str:
    _reject_duplicate(db, "mice", "subject_id", subject_id)
    row_id = new_uuid()
    with db.write() as conn:
        conn.execute(
            "INSERT INTO mice (id, subject_id, genotype) VALUES (?, ?, ?)",
            [row_id, subject_id, genotype],
        )
    return row_id


def create_project(db: Database, *, name: str) -> str:
    _reject_duplicate(db, "projects", "name", name)
    row_id = new_uuid()
    with db.write() as conn:
        conn.execute("INSERT INTO projects (id, name) VALUES (?, ?)", [row_id, name])
    return row_id


def create_user(
    db: Database, *, name: str, email: str, orcid: str | None = None
) -> str:
    _reject_duplicate(db, "users", "email", email)
    row_id = new_uuid()
    with db.write() as conn:
        conn.execute(
            "INSERT INTO users (id, name, email, orcid) VALUES (?, ?, ?, ?)",
            [row_id, name, email, orcid],
        )
    return row_id


def add_instrument_compatibility(
    db: Database, *, instrument_id: str, procedure_type_id: str
) -> None:
    """Declare a procedure type compatible with an instrument (idempotent)."""
    _require_row(db, "instruments", instrument_id, "instrument")
    _require_row(db, "procedure_types", procedure_type_id, "procedure type")
    ensure_instrument_compatibility(db, instrument_id, [procedure_type_id])


# ---------------------------------------------------------------------------
# Idempotent lookup upserts (used by the seed script)
# ---------------------------------------------------------------------------


def get_or_create(
    db: Database,
    table: str,
    natural_key: str,
    natural_value: str,
    columns: dict[str, Any],
) -> str:
    """Return the id of the row whose ``natural_key`` equals ``natural_value``,
    inserting it (with a fresh uuid4 id) if absent.

    Existing rows are left untouched, which is what makes re-running the seed
    script safe.
    """
    existing = db.conn.execute(
        f"SELECT id FROM {table} WHERE {natural_key} = ?", [natural_value]
    ).fetchone()
    if existing is not None:
        return existing[0]

    row_id = new_uuid()
    values = {"id": row_id, natural_key: natural_value, **columns}
    cols = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    with db.write() as conn:
        conn.execute(
            f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
            list(values.values()),
        )
    return row_id


def ensure_instrument_compatibility(
    db: Database, instrument_id: str, procedure_type_ids: Iterable[str]
) -> None:
    """Add any missing instrument<->procedure_type compatibility rows."""
    existing = compatible_type_ids(db, instrument_id)
    missing = [pid for pid in procedure_type_ids if pid not in existing]
    if not missing:
        return
    with db.write() as conn:
        for pid in missing:
            conn.execute(
                "INSERT INTO instrument_compatible_types "
                "(instrument_id, procedure_type_id) VALUES (?, ?)",
                [instrument_id, pid],
            )


def find_scheduled_procedure(
    db: Database, mouse_id: str, instrument_id: str, scheduled_start: datetime
) -> str | None:
    """Look up a scheduled procedure by its natural key.

    (mouse, instrument, start) is treated as the seed script's natural key:
    the same mouse cannot be on the same rig at the same instant twice. Used
    only to make seeding re-runnable — the real primary key is the UUIDv7 id.
    """
    row = db.conn.execute(
        "SELECT id FROM scheduled_procedures "
        "WHERE mouse_id = ? AND instrument_id = ? AND scheduled_start = ?",
        [mouse_id, instrument_id, scheduled_start],
    ).fetchone()
    return row[0] if row else None
