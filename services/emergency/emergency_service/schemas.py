"""Small response schemas shared by this service's routes."""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from .authorization import valid_id


def validate_wire_id(value: str) -> str:
    if not valid_id(value):
        raise ValueError("invalid ID")
    return value


EmergencyState = Literal[
    "submitted", "triaged", "claimed", "processing", "resolved", "cancelled"
]
ReportedUrgency = Literal["unspecified", "urgent"]
TransitionState = Literal["processing", "resolved", "cancelled"]
WireId = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[1-9][0-9]{0,18}$", max_length=19),
    AfterValidator(validate_wire_id),
]
Description = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=4000),
]
Reason = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=500),
]
SyntheticContact = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=256),
]


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmergencyRequestCreate(StrictRequest):
    patient_id: WireId
    description: Description
    reported_urgency: ReportedUrgency
    synthetic_contact: SyntheticContact | None = None


class PriorityUpdate(StrictRequest):
    assigned_priority: Annotated[int, Field(strict=True, ge=1, le=5)]
    reason: Reason


class ClaimCommand(StrictRequest):
    pass


class ReleaseCommand(StrictRequest):
    reason: Reason


class TransitionCommand(StrictRequest):
    state: TransitionState
    reason: Reason


class EmergencyRequestView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: WireId
    state: EmergencyState
    reported_urgency: ReportedUrgency
    assigned_priority: int | None
    created_at: str
    updated_at: str
    version: Annotated[int, Field(strict=True, ge=1)]


class EmergencyStaffRequestView(EmergencyRequestView):
    patient_id: WireId
    description: str
    synthetic_contact: str | None
    claimed_by_user_id: WireId | None
    claim_expires_at: str | None


class EmergencyRequestPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[EmergencyStaffRequestView | EmergencyRequestView]
    next_cursor: str | None


class EmergencyHistoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: WireId
    previous_state: EmergencyState | None
    new_state: EmergencyState
    priority: int | None
    occurred_at: str


class EmergencyStaffHistoryEntry(EmergencyHistoryEntry):
    actor_user_id: WireId | None
    reason: str


class EmergencyHistoryPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[EmergencyStaffHistoryEntry | EmergencyHistoryEntry]
    next_cursor: str | None


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    request_id: UUID
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ErrorDetail


class LivenessResponse(BaseModel):
    status: Literal["alive"]
    service: str


class DependencyReadiness(BaseModel):
    status: Literal["unconfigured", "available", "unavailable"]
    required: bool


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    service: str
    application: Literal["ready"]
    dependencies: dict[str, DependencyReadiness] = Field(min_length=1)
