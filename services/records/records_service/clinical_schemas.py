"""Frozen Phase 2 clinical wire inputs and dependency snapshots."""

from datetime import datetime, timezone
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
)

from .authorization import valid_id


def identifier(value):
    if not valid_id(value):
        raise ValueError("Invalid ID")
    return value


def utc(value):
    if value.tzinfo is None or value.utcoffset().total_seconds() != 0:
        raise ValueError("UTC required")
    return value.astimezone(timezone.utc)


ID = Annotated[str, AfterValidator(identifier)]
Text = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
]
Reason = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]
Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
Version = Annotated[int, Field(strict=True, ge=1, le=9007199254740991)]
Quantity = Annotated[int, Field(strict=True, ge=1, le=1000000)]


def time_string(value):
    if (
        not isinstance(value, str)
        or "T" not in value
        or not value.endswith(("Z", "+00:00"))
    ):
        raise ValueError("UTC RFC 3339 string required")
    return value


Time = Annotated[datetime, BeforeValidator(time_string), AfterValidator(utc)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClinicalContent(Input):
    summary: Text
    assessment: Text
    plan: Text


class CreateConsultation(Input):
    appointment_id: ID
    clinical_content: ClinicalContent


class EditConsultation(Input):
    clinical_content: ClinicalContent


class PrescriptionItemInput(Input):
    medicine_id: ID
    quantity: Quantity
    dosage: Text
    instructions: Text


class Finalize(Input):
    prescription_items: list[PrescriptionItemInput] = Field(max_length=50)

    @classmethod
    def distinct(cls, items):
        if len({i.medicine_id for i in items}) != len(items):
            raise ValueError("Distinct medicines required")
        return items

    from pydantic import field_validator

    validate_items = field_validator("prescription_items")(distinct)


class Amendment(Input):
    content: ClinicalContent
    reason: Reason


class Revoke(Input):
    reason: Reason


class Grant(Input):
    patient_id: ID
    grantee_user_id: ID
    scope: Literal["records:read", "prescriptions:read"]
    expires_at: Time


class AppointmentContext(Input):
    appointment_id: ID
    patient_id: ID
    doctor_id: ID
    doctor_user_id: ID
    journey_id: None
    state: Literal["confirmed", "cancelled"]
    clinical_hold: Literal["none", "active", "finalized"]
    version: Version


class WorkflowContext(Input):
    appointment_id: ID
    patient_id: ID
    doctor_id: ID
    doctor_user_id: ID
    workflow: dict | None
    clinical_hold: Literal["none", "active", "finalized"]
    version: Version


class PatientStatus(Input):
    patient_id: ID
    active: bool = Field(strict=True)
    version: Version


class StaffStatus(Input):
    user_id: ID
    active: bool = Field(strict=True)
    roles: list[
        Literal[
            "patient",
            "doctor",
            "receptionist",
            "pharmacist",
            "billing_staff",
            "emergency_staff",
            "hospital_admin",
            "ops",
        ]
    ]
    version: Version


class Medicine(Input):
    id: ID
    active: bool = Field(strict=True)
    catalog_version: Version
    name: Name


class Medicines(Input):
    items: list[Medicine] = Field(min_length=1, max_length=50)


# Exact output views also describe the service-local OpenAPI document.


class Consultation(Input):
    id: ID
    appointment_id: ID
    patient_id: ID
    doctor_id: ID
    status: Literal["draft", "finalized"]
    clinical_content: ClinicalContent
    revision: Version
    version: Version


class RecordSummary(Input):
    id: ID
    consultation_id: ID
    patient_id: ID
    revision: Version
    created_at: Time
    version: Version


class MedicalRecord(Input):
    id: ID
    consultation_id: ID
    patient_id: ID
    content: ClinicalContent
    revision: Version
    supersedes_id: ID | None
    version: Version


class PrescriptionItem(PrescriptionItemInput):
    id: ID


class Prescription(Input):
    id: ID
    consultation_id: ID
    patient_id: ID
    journey_id: None
    revision: Version
    state: Literal["issued", "revoked"]
    items: list[PrescriptionItem]
    version: Version


class FinalizeResult(Input):
    consultation: Consultation
    record: MedicalRecord
    prescription: Prescription | None


class AccessGrant(Grant):
    id: ID
    version: Version


T = TypeVar("T")


class Page(Input, Generic[T]):
    items: list[T]
    next_cursor: str | None


class DispensingItem(Input):
    id: ID
    medicine_id: ID
    quantity: Quantity


class DispensingContext(Input):
    prescription_id: ID
    consultation_id: ID
    appointment_id: ID
    patient_id: ID
    journey_id: None
    revision: Version
    state: Literal["issued", "revoked"]
    items: list[DispensingItem]
    version: Version


class ChargeContext(Input):
    consultation_id: ID
    appointment_id: ID
    patient_id: ID
    status: Literal["draft", "finalized"]
    charge_code: Literal["consultation"]
    quantity: Literal[1]
    version: Version
