"""Pydantic (v2) response models for the read API.

Shapes follow DESIGN.md "Example 2 — what the GET endpoints return"
field-for-field. Datetimes are serialized as ISO-8601 UTC strings with a
"Z" suffix (e.g. "2026-08-04T09:00:00Z"), matching the examples.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Status = Literal["scheduled", "completed", "cancelled", "rescheduled"]


# ---------------------------------------------------------------------------
# Resolved lookup references embedded in scheduled-procedure payloads
# ---------------------------------------------------------------------------


class MouseRef(BaseModel):
    id: str
    subject_id: str


class InstrumentRef(BaseModel):
    id: str
    name: str
    sipe_rig_name: str | None


class ProjectRef(BaseModel):
    id: str
    name: str


class UserRef(BaseModel):
    id: str
    name: str


class ProcedureTypeRef(BaseModel):
    id: str
    name: str


# ---------------------------------------------------------------------------
# Scheduled procedures
# ---------------------------------------------------------------------------


class ScheduledProcedureSummary(BaseModel):
    """List-item shape (DESIGN.md Example 2, first payload)."""

    id: str = Field(
        description="The persistent acquisition token: a time-sortable UUIDv7 "
        "minted at scheduling, immutable, carried into acquisition and all "
        "downstream steps."
    )
    mouse: MouseRef
    instrument: InstrumentRef
    project: ProjectRef
    contact: UserRef
    experimenters: list[UserRef]
    active_procedure_types: list[str]
    acquisition_type: str = Field(
        description="Server-computed: active procedure type names, sorted "
        "alphabetically, joined with ' + '."
    )
    acquisition_name: str | None = Field(
        description="Secondary human-readable dated AIND session name; NULL "
        "until acquisition begins. Not the linking key — the id token is."
    )
    scheduled_start: str = Field(description="ISO-8601 UTC, e.g. 2026-08-04T09:00:00Z")
    scheduled_end: str = Field(description="ISO-8601 UTC")
    status: Status


class ScheduledProcedureDetail(ScheduledProcedureSummary):
    """Single-record shape: the summary plus every remaining field."""

    ethics_review_id: str | None
    notes: str | None
    planned_config: Any = Field(
        description="Platform-specific planned settings (free-form JSON)."
    )
    protocols: str | None
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Lookup endpoints
# ---------------------------------------------------------------------------


class ProcedureTypeOut(BaseModel):
    id: str
    name: str
    modality_name: str
    modality_abbreviation: str
    sort_order: int


class InstrumentOut(BaseModel):
    id: str
    name: str
    instrument_id: str | None = Field(
        description="The aind-data-schema instrument_id, e.g. 'EPHYS2'."
    )
    sipe_rig_name: str | None
    location: str | None
    active: bool
    compatible_procedure_types: list[ProcedureTypeRef] = Field(
        description="The instrument's 'Compatible Acquisition Platforms'."
    )


class MouseOut(BaseModel):
    id: str
    subject_id: str
    genotype: str | None


class ProjectOut(BaseModel):
    id: str
    name: str


class UserOut(BaseModel):
    id: str
    name: str
    email: str
    orcid: str | None


# ---------------------------------------------------------------------------
# Rig-facing convenience endpoints
# ---------------------------------------------------------------------------


class PlannedAcquisitionOut(BaseModel):
    """One planned acquisition, as a rig would fetch it."""

    id: str = Field(description="The persistent acquisition token (UUIDv7).")
    subject_id: str
    acquisition_type: str
    scheduled_start: str
    scheduled_end: str


class NextAcquisitionOut(BaseModel):
    """The soonest upcoming scheduled procedure for an animal."""

    id: str = Field(description="The persistent acquisition token (UUIDv7).")
    subject_id: str
    instrument: str = Field(description="Instrument display name.")
    acquisition_type: str
    scheduled_start: str
