"""Admin write API, namespaced under /session_schedule/api/admin.

Kept separate from the public data API so the "read-only API" contract is
honored: everything outside ``/api/admin/`` is GET-only. No auth — this is
an internal-network prototype; the namespace makes the write side obvious.

All writes go through the shared logic in ``scheduler_app/store.py``, which enforces
DESIGN.md's validation rules and recomputes ``acquisition_type`` and
``updated_at`` server-side. A rejected write returns the documented error
shape::

    HTTP 422
    {"error": "incompatible_procedure_type", "detail": "..."}
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from scheduler_app import queries, store
from scheduler_app.db import Database
from scheduler_app.queries import ensure_utc
from scheduler_app.schemas import (
    CompatibilityCreate,
    InstrumentCreate,
    InstrumentOut,
    MouseCreate,
    MouseOut,
    ProjectCreate,
    ProjectOut,
    ScheduledProcedureDetail,
    ScheduledProcedureWrite,
    UserCreate,
    UserOut,
)

router = APIRouter(prefix="/session_schedule/api/admin", tags=["Admin (write)"])


def _db(request: Request) -> Database:
    return request.app.state.db


def _write_kwargs(body: ScheduledProcedureWrite) -> dict:
    return dict(
        mouse_id=body.mouse_id,
        instrument_id=body.instrument_id,
        project_id=body.project_id,
        contact_user_id=body.contact_user_id,
        scheduled_start=ensure_utc(body.scheduled_start),
        scheduled_end=ensure_utc(body.scheduled_end),
        active_procedure_type_ids=body.active_procedure_type_ids,
        experimenter_user_ids=body.experimenter_user_ids,
        status=body.status,
        acquisition_name=body.acquisition_name,
        ethics_review_id=body.ethics_review_id,
        notes=body.notes,
        planned_config=body.planned_config,
        protocols=body.protocols,
    )


# ---------------------------------------------------------------------------
# Scheduled procedures
# ---------------------------------------------------------------------------


@router.post(
    "/scheduled-procedures",
    response_model=ScheduledProcedureDetail,
    status_code=201,
    summary="Schedule a procedure (mints the persistent acquisition token)",
)
def create_scheduled_procedure(request: Request, body: ScheduledProcedureWrite):
    db = _db(request)
    sp_id = store.create_scheduled_procedure(db, **_write_kwargs(body))
    return queries.fetch_scheduled_procedure(db, sp_id)


@router.put(
    "/scheduled-procedures/{sp_id}",
    response_model=ScheduledProcedureDetail,
    summary="Update a scheduled procedure (full replace; id and created_at immutable)",
)
def update_scheduled_procedure(request: Request, sp_id: str, body: ScheduledProcedureWrite):
    db = _db(request)
    found = store.update_scheduled_procedure(db, sp_id, **_write_kwargs(body))
    if not found:
        raise HTTPException(status_code=404, detail=f"No scheduled procedure with id '{sp_id}'.")
    return queries.fetch_scheduled_procedure(db, sp_id)


@router.delete(
    "/scheduled-procedures/{sp_id}",
    status_code=204,
    summary="Delete a scheduled procedure (join rows included)",
)
def delete_scheduled_procedure(request: Request, sp_id: str):
    if not store.delete_scheduled_procedure(_db(request), sp_id):
        raise HTTPException(status_code=404, detail=f"No scheduled procedure with id '{sp_id}'.")
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Minimal lookup creation (so the demo can be populated through the UI)
# ---------------------------------------------------------------------------


@router.post("/instruments", response_model=InstrumentOut, status_code=201)
def create_instrument(request: Request, body: InstrumentCreate):
    db = _db(request)
    row_id = store.create_instrument(
        db,
        name=body.name,
        instrument_id=body.instrument_id,
        sipe_rig_name=body.sipe_rig_name,
        location=body.location,
        active=body.active,
        compatible_procedure_type_ids=body.compatible_procedure_type_ids,
    )
    return next(i for i in queries.fetch_instruments(db) if i["id"] == row_id)


@router.post("/mice", response_model=MouseOut, status_code=201)
def create_mouse(request: Request, body: MouseCreate):
    db = _db(request)
    row_id = store.create_mouse(db, subject_id=body.subject_id, genotype=body.genotype)
    return {"id": row_id, "subject_id": body.subject_id, "genotype": body.genotype}


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(request: Request, body: ProjectCreate):
    row_id = store.create_project(_db(request), name=body.name)
    return {"id": row_id, "name": body.name}


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(request: Request, body: UserCreate):
    row_id = store.create_user(
        _db(request), name=body.name, email=body.email, orcid=body.orcid
    )
    return {"id": row_id, "name": body.name, "email": body.email, "orcid": body.orcid}


@router.post(
    "/instrument-compatibility",
    response_model=CompatibilityCreate,
    status_code=201,
    summary="Declare a procedure type compatible with an instrument (idempotent)",
)
def add_instrument_compatibility(request: Request, body: CompatibilityCreate):
    store.add_instrument_compatibility(
        _db(request),
        instrument_id=body.instrument_id,
        procedure_type_id=body.procedure_type_id,
    )
    return body
