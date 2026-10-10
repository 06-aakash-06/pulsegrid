"""Strict request and response schemas for the frozen Doctor API."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)


_ID_PATTERN = re.compile(r"^[1-9][0-9]{0,18}$")
_UTC_TIME_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$"
)


def _bounded_id(value: str) -> str:
    if int(value) > 9223372036854775807:
        raise ValueError("ID is outside the supported range")
    return value


def _parse_utc_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise ValueError("time must be UTC RFC 3339 with Z or +00:00")
        return value.astimezone(timezone.utc)
    if not isinstance(value, str) or not _UTC_TIME_PATTERN.fullmatch(value):
        raise ValueError("time must be UTC RFC 3339 with Z or +00:00")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("time must be UTC")
    return parsed.astimezone(timezone.utc)


ID = Annotated[
    str,
    StringConstraints(strict=True, pattern=_ID_PATTERN.pattern),
    AfterValidator(_bounded_id),
]
Name = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=200),
]
Slug = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    ),
]
Time = Annotated[datetime, BeforeValidator(_parse_utc_time)]
Version = Annotated[StrictInt, Field(ge=1, le=9007199254740991)]
Revision = Annotated[StrictInt, Field(ge=0, le=9007199254740991)]
Role = Literal[
    "patient",
    "doctor",
    "receptionist",
    "pharmacist",
    "billing_staff",
    "emergency_staff",
    "hospital_admin",
    "ops",
]


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ErrorDetail(StrictSchema):
    code: str
    message: str
    request_id: UUID
    details: dict[str, Any] | None = None


class ErrorResponse(StrictSchema):
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


class SpecialtyInput(StrictSchema):
    slug: Slug
    name: Name


class EmptyCommand(StrictSchema):
    pass


class Specialty(StrictSchema):
    id: ID
    slug: Slug
    name: Name
    version: Version


class DoctorSpecialty(StrictSchema):
    id: ID
    name: Name


class DoctorProfile(StrictSchema):
    id: ID
    display_name: Name
    specialties: list[DoctorSpecialty]
    active: StrictBool
    version: Version


class DoctorSelf(StrictSchema):
    doctor: DoctorProfile
    staff_user_id: ID


class DoctorCreate(StrictSchema):
    staff_user_id: ID
    display_name: Name
    specialty_ids: list[ID] = Field(min_length=1, max_length=20)

    @field_validator("specialty_ids")
    @classmethod
    def distinct_specialties(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("specialty_ids must be distinct")
        return value


class DoctorPatch(StrictSchema):
    display_name: Name | None = None
    specialty_ids: list[ID] | None = Field(default=None, min_length=1, max_length=20)
    active: StrictBool | None = None

    @field_validator("specialty_ids")
    @classmethod
    def distinct_specialties(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and len(set(value)) != len(value):
            raise ValueError("specialty_ids must be distinct")
        return value

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> DoctorPatch:
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("patch fields cannot be null")
        return self


class DoctorSpecialtyBrief(StrictSchema):
    id: ID
    name: Name


class ScheduleIntervalInput(StrictSchema):
    starts_at: Time
    ends_at: Time

    @model_validator(mode="after")
    def increasing_interval(self) -> ScheduleIntervalInput:
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class ScheduleInput(StrictSchema):
    timezone: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=128)]
    slot_minutes: Annotated[StrictInt, Field(ge=5, le=120)]
    intervals: list[ScheduleIntervalInput] = Field(max_length=64)
    expected_revision: Revision


class ScheduleInterval(StrictSchema):
    starts_at: Time
    ends_at: Time


class ScheduleProposal(StrictSchema):
    id: ID
    doctor_id: ID
    revision: Version
    status: Literal["pending", "accepted", "rejected"]
    timezone: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=128)]
    slot_minutes: Annotated[StrictInt, Field(ge=5, le=120)]
    intervals: list[ScheduleInterval]
    conflicts: list[ID]
    version: Version


class ScheduleDecision(StrictSchema):
    proposal_id: ID
    doctor_id: ID
    revision: Version
    state: Literal["accepted", "rejected"]
    reason_code: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=128)] | None
    conflicting_appointment_ids: list[ID]
    version: Version

    @field_validator("conflicting_appointment_ids")
    @classmethod
    def distinct_conflicts(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("conflicting_appointment_ids must be distinct")
        return value


class StaffStatus(StrictSchema):
    user_id: ID
    active: StrictBool
    roles: list[Role]
    version: Version

    @field_validator("roles")
    @classmethod
    def distinct_roles(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("roles must be distinct")
        return value


class OperationalStatus(StrictSchema):
    doctor_id: ID
    bookable_slot_count: Annotated[StrictInt, Field(ge=0)]
    confirmed_booking_count: Annotated[StrictInt, Field(ge=0)]
    version: Version


class DoctorIdentity(StrictSchema):
    doctor_id: ID
    staff_user_id: ID
    active: StrictBool
    version: Version


class PrivateProposal(StrictSchema):
    proposal: ScheduleProposal
    staff_user_id: ID
    active: StrictBool
    doctor_version: Version


T = TypeVar("T")


class Page(StrictSchema, Generic[T]):
    items: list[T]
    next_cursor: str | None
