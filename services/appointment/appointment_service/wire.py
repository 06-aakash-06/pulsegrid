"""Strict frozen Phase 2 input and dependency schemas."""
from datetime import datetime, timedelta
from typing import Annotated, Literal
from pydantic import BeforeValidator, BaseModel, ConfigDict, Field, AfterValidator, StrictInt, field_validator, model_validator
from .authorization import valid_id


def id_value(v):
    if not valid_id(v):
        raise ValueError('Invalid ID')
    return v


def utc_value(v):
    if v.tzinfo is None or v.utcoffset()!=timedelta(0):
        raise ValueError('UTC required')
    return v


ID = Annotated[str, AfterValidator(id_value)]
Version = Annotated[StrictInt, Field(ge=1, le=9007199254740991)]
def time_input(v):
    import re
    if isinstance(v,str) and not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)',v):
        raise ValueError('RFC 3339 UTC required')
    if not isinstance(v,(str,datetime)):
        raise ValueError('Time string required')
    return v


Time = Annotated[datetime, BeforeValidator(time_input), AfterValidator(utc_value)]


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Book(Input):
    patient_id: ID
    slot_id: ID
    expected_schedule_revision: Version


class Move(Input):
    target_slot_id: ID
    expected_schedule_revision: Version


class Cancel(Input):
    reason: Annotated[str, Field(min_length=1,max_length=500)]

    @field_validator('reason')
    @classmethod
    def trimmed(cls,v):
        v=v.strip()
        if not v:
            raise ValueError('Empty reason')
        return v


class Decide(Input):
    doctor_id: ID
    proposal_id: ID
    expected_accepted_revision: Annotated[StrictInt,Field(ge=0,le=9007199254740991)]


class Hold(Input):
    consultation_id: ID


class Identity(Input):
    doctor_id: ID
    staff_user_id: ID
    active: bool = Field(strict=True)
    version: Version


class PatientStatus(Input):
    patient_id: ID
    active: bool = Field(strict=True)
    version: Version


class Interval(Input):
    starts_at: Time
    ends_at: Time

    @model_validator(mode='after')
    def interval(self):
        if self.ends_at<=self.starts_at:
            raise ValueError('Invalid interval')
        return self


class Proposal(Input):
    id: ID
    doctor_id: ID
    revision: Version
    status: Literal['pending','accepted','rejected']
    timezone: str
    slot_minutes: Annotated[StrictInt,Field(ge=5,le=120)]
    intervals: list[Interval] = Field(max_length=64)
    conflicts: list[ID]
    version: Version


class ProposalContext(Input):
    proposal: Proposal
    staff_user_id: ID
    active: bool = Field(strict=True)
    doctor_version: Version


class SlotView(Input):
    id: ID
    doctor_id: ID
    starts_at: Time
    ends_at: Time
    state: Literal['bookable','retired']
    revision: Version


class AvailabilityView(Input):
    slots: list[SlotView]
    accepted_revision: Annotated[StrictInt,Field(ge=0)]
    observed_at: Time


class AppointmentView(Input):
    id: ID
    journey_id: ID | None
    patient_id: ID
    doctor_id: ID
    slot_id: ID
    starts_at: Time
    ends_at: Time
    state: Literal['confirmed','cancelled']
    version: Version


class AppointmentPage(Input):
    items: list[AppointmentView]
    next_cursor: str|None


class DecisionView(Input):
    proposal_id: ID
    doctor_id: ID
    revision: Version
    state: Literal['accepted','rejected']
    reason_code: str|None
    conflicting_appointment_ids: list[ID]
    version: Version


class ConsultationContextView(Input):
    appointment_id: ID
    patient_id: ID
    doctor_id: ID
    doctor_user_id: ID
    journey_id: None
    state: Literal['confirmed','cancelled']
    clinical_hold: Literal['none','active','finalized']
    version: Version


class BillingContextView(Input):
    appointment_id: ID
    patient_id: ID
    state: Literal['confirmed','cancelled']
    version: Version


class OperationalStatusView(Input):
    doctor_id: ID
    bookable_slot_count: Annotated[StrictInt,Field(ge=0)]
    confirmed_booking_count: Annotated[StrictInt,Field(ge=0)]
    version: Version
