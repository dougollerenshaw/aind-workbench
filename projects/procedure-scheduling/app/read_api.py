"""Public read-only API (GET only), mounted under /session_schedule/api.

Two groups of endpoints (DESIGN.md "API"):

- The general read API: scheduled-procedures (with the full filter set) and
  the lookup tables, every response with lookups resolved to names.
- The rig-facing convenience endpoints, mirroring the Python client shape in
  Bruno's proposal (`get_planned_acquisitions`, `get_acquisition_record`,
  `get_next_acquisition_for_animal`). In every response the `id` is the
  persistent acquisition token (UUIDv7).

Writes live in a separate admin router (M4) so the public API stays
read-only.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request

from app import queries
from app.db import Database, utcnow
from app.schemas import (
    InstrumentOut,
    MouseOut,
    NextAcquisitionOut,
    PlannedAcquisitionOut,
    ProcedureTypeOut,
    ProjectOut,
    ScheduledProcedureDetail,
    ScheduledProcedureSummary,
    Status,
    UserOut,
)

router = APIRouter(prefix="/session_schedule/api")


def _db(request: Request) -> Database:
    return request.app.state.db


# ---------------------------------------------------------------------------
# Scheduled procedures
# ---------------------------------------------------------------------------


@router.get(
    "/scheduled-procedures",
    response_model=list[ScheduledProcedureSummary],
    tags=["read"],
    summary="List scheduled procedures (all filters optional and combinable)",
)
def list_scheduled_procedures(
    request: Request,
    mouse_id: str | None = Query(None, description="Mouse UUID"),
    subject_id: str | None = Query(None, description="Mouse subject_id, e.g. 'testmouse1'"),
    instrument_id: str | None = Query(None, description="Instrument UUID"),
    project_id: str | None = Query(None, description="Project UUID"),
    contact_user_id: str | None = Query(None, description="Scientific-contact user UUID"),
    procedure_type_id: str | None = Query(
        None, description="Procedure type UUID; matches any active type"
    ),
    status: Status | None = Query(None),
    start_after: datetime | None = Query(None, description="scheduled_start >= this (inclusive)"),
    start_before: datetime | None = Query(None, description="scheduled_start <= this (inclusive)"),
    end_after: datetime | None = Query(None, description="scheduled_end >= this (inclusive)"),
    end_before: datetime | None = Query(None, description="scheduled_end <= this (inclusive)"),
):
    return queries.fetch_scheduled_procedures(
        _db(request),
        mouse_id=mouse_id,
        subject_id=subject_id,
        instrument_id=instrument_id,
        project_id=project_id,
        contact_user_id=contact_user_id,
        procedure_type_id=procedure_type_id,
        status=status,
        start_after=start_after,
        start_before=start_before,
        end_after=end_after,
        end_before=end_before,
    )


@router.get(
    "/scheduled-procedures/{sp_id}",
    response_model=ScheduledProcedureDetail,
    tags=["read"],
    summary="One scheduled procedure, fully resolved",
)
def get_scheduled_procedure(request: Request, sp_id: str):
    record = queries.fetch_scheduled_procedure(_db(request), sp_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No scheduled procedure with id '{sp_id}'.")
    return record


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------


@router.get("/instruments", response_model=list[InstrumentOut], tags=["read"])
def list_instruments(
    request: Request,
    active: bool | None = Query(None),
    procedure_type_id: str | None = Query(
        None, description="Only instruments compatible with this procedure type"
    ),
):
    return queries.fetch_instruments(
        _db(request), active=active, procedure_type_id=procedure_type_id
    )


@router.get("/procedure-types", response_model=list[ProcedureTypeOut], tags=["read"])
def list_procedure_types(request: Request):
    return queries.fetch_procedure_types(_db(request))


@router.get("/mice", response_model=list[MouseOut], tags=["read"])
def list_mice(request: Request, subject_id: str | None = Query(None)):
    return queries.fetch_mice(_db(request), subject_id=subject_id)


@router.get("/projects", response_model=list[ProjectOut], tags=["read"])
def list_projects(request: Request):
    return queries.fetch_projects(_db(request))


@router.get("/users", response_model=list[UserOut], tags=["read"])
def list_users(request: Request):
    return queries.fetch_users(_db(request))


# ---------------------------------------------------------------------------
# Rig-facing convenience endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/rig/{rig_id}/planned-acquisitions",
    response_model=list[PlannedAcquisitionOut],
    tags=["rig-facing"],
    summary="Planned acquisitions for one rig (mirrors get_planned_acquisitions)",
)
def rig_planned_acquisitions(
    request: Request,
    rig_id: str,
    start: datetime | None = Query(None, description="Window start (inclusive)"),
    end: datetime | None = Query(None, description="Window end (exclusive)"),
):
    """``rig_id`` matches ``instruments.sipe_rig_name``, falling back to
    ``instruments.name``."""
    db = _db(request)
    instrument_id = queries.resolve_rig(db, rig_id)
    if instrument_id is None:
        raise HTTPException(status_code=404, detail=f"No instrument with rig id '{rig_id}'.")
    return queries.fetch_planned_acquisitions(db, instrument_id, start=start, end=end)


@router.get(
    "/acquisitions/{acquisition_id}",
    response_model=ScheduledProcedureDetail,
    tags=["rig-facing"],
    summary="One acquisition record by token (mirrors get_acquisition_record)",
)
def get_acquisition_record(request: Request, acquisition_id: str):
    """Same payload as ``/scheduled-procedures/{id}``; the path exists so the
    rig-side client shape from Bruno's proposal is drop-in."""
    record = queries.fetch_scheduled_procedure(_db(request), acquisition_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No acquisition with id '{acquisition_id}'.")
    return record


@router.get(
    "/animals/{animal_id}/next-acquisition",
    response_model=NextAcquisitionOut,
    tags=["rig-facing"],
    summary="Soonest upcoming scheduled procedure for an animal "
    "(mirrors get_next_acquisition_for_animal)",
)
def next_acquisition_for_animal(request: Request, animal_id: str):
    """'Next' means earliest upcoming ``scheduled_start`` (status
    'scheduled'), not most-recently-created. ``animal_id`` matches
    ``mice.subject_id``, falling back to the mouse UUID."""
    try:
        record = queries.fetch_next_acquisition(_db(request), animal_id, now=utcnow())
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No animal '{animal_id}'.")
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"No upcoming scheduled procedure for animal '{animal_id}'.",
        )
    return record
