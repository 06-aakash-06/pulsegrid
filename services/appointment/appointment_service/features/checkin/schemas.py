"""Feature-local wire schemas for the frozen check-in contract."""

from datetime import date
from typing import Annotated, Literal

from pydantic import Field, StrictInt, StrictStr, field_validator

from ...wire import ID, Input, Time, Version
from ... import phase3_core as core


class EmptyBody(Input):
    pass


class TokenBody(Input):
    # Shape/length checks happen after resource authorization so malformed,
    # expired, revoked and unknown secrets share the same safe token_invalid path.
    token: StrictStr


class StaffCheckinBody(Input):
    reason: Annotated[str, Field(min_length=1, max_length=500)]

    @field_validator("reason")
    @classmethod
    def trimmed_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Reason must not be blank")
        return value


class TokenIssue(Input):
    link_id: ID
    appointment_id: ID
    expires_at: Time
    token: StrictStr
    landing_path: StrictStr
    version: Version


class QueueEntry(Input):
    id: ID
    appointment_id: ID
    doctor_id: ID
    local_date: date
    token_number: Annotated[StrictInt, Field(ge=1, le=9007199254740991)]
    state: Literal["waiting", "in_consultation", "completed", "cancelled", "no_show"]
    position: Annotated[StrictInt, Field(ge=1)] | None
    version: Version


class CheckinResult(Input):
    workflow: core.Workflow
    queue_entry: QueueEntry


class PatientStatus(Input):
    patient_id: ID
    active: bool = Field(strict=True)
    version: Version


class DoctorIdentity(Input):
    doctor_id: ID
    staff_user_id: ID
    active: bool = Field(strict=True)
    version: Version
