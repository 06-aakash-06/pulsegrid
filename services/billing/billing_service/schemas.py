"""Small response schemas shared by this service's routes."""

from __future__ import annotations

import re
from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

MAX_ID = 9_223_372_036_854_775_807
MAX_MINOR = 9_007_199_254_740_991
ID = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[1-9][0-9]{0,18}$", max_length=19),
    AfterValidator(lambda value: value if int(value) <= MAX_ID else _invalid_id()),
]
Minor = Annotated[int, Field(strict=True, ge=0, le=MAX_MINOR)]
PositiveMinor = Annotated[int, Field(strict=True, ge=1, le=MAX_MINOR)]
Quantity = Annotated[int, Field(strict=True, ge=1, le=1_000_000)]
Currency = Literal["INR"]
T = TypeVar("T")


def _invalid_id():
    raise ValueError("invalid ID")


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


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TariffCreate(StrictModel):
    charge_code: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    unit_amount_minor: Minor
    currency: Currency

    @field_validator("charge_code")
    @classmethod
    def validate_charge_code(cls, value: str) -> str:
        if value != "consultation" and not re.fullmatch(
            r"medicine:[1-9][0-9]{0,18}", value
        ):
            raise ValueError("charge_code must be consultation or medicine:<id>")
        if value.startswith("medicine:") and int(value[9:]) > MAX_ID:
            raise ValueError("invalid medicine ID")
        return value


class InvoiceCreate(StrictModel):
    appointment_id: ID
    currency: Currency


class ChargeImport(StrictModel):
    consultation_id: ID | None = None
    dispensing_ids: list[ID] = Field(max_length=50)

    @model_validator(mode="after")
    def validate_sources(self):
        if self.consultation_id is None and not self.dispensing_ids:
            raise ValueError("at least one charge source is required")
        if len(set(self.dispensing_ids)) != len(self.dispensing_ids):
            raise ValueError("dispensing_ids must be distinct")
        return self


class PaymentCreate(StrictModel):
    amount_minor: PositiveMinor
    currency: Currency
    simulated_outcome: Literal["success", "decline"]


class TariffResponse(StrictModel):
    id: ID
    charge_code: str
    revision: int = Field(strict=True, ge=1, le=MAX_MINOR)
    unit_amount_minor: Minor
    currency: Currency
    version: int = Field(strict=True, ge=1, le=MAX_MINOR)


class InvoiceItemResponse(StrictModel):
    id: ID
    charge_code: str
    source_service: Literal["records", "pharmacy"]
    source_item_id: ID
    quantity: Quantity
    unit_amount_minor: Minor
    tariff_revision: int = Field(strict=True, ge=1, le=MAX_MINOR)


class InvoiceResponse(StrictModel):
    id: ID
    journey_id: None
    appointment_id: ID
    patient_id: ID
    status: Literal["open", "paid"]
    items: list[InvoiceItemResponse]
    total_minor: Minor
    paid_minor: Minor
    balance_minor: Minor
    currency: Currency
    version: int = Field(strict=True, ge=1, le=MAX_MINOR)


class PaymentResponse(StrictModel):
    id: ID
    invoice_id: ID
    amount_minor: PositiveMinor
    currency: Currency
    status: Literal["success", "declined"]
    version: int = Field(strict=True, ge=1, le=MAX_MINOR)


class Page(StrictModel, Generic[T]):
    items: list[T]
    next_cursor: str | None


class AppointmentBillingContext(StrictModel):
    appointment_id: ID
    patient_id: ID
    state: Literal["confirmed", "cancelled"]
    version: int = Field(strict=True, ge=1, le=MAX_MINOR)


class ConsultationChargeContext(StrictModel):
    consultation_id: ID
    appointment_id: ID
    patient_id: ID
    status: Literal["draft", "finalized"]
    charge_code: Literal["consultation"]
    quantity: Literal[1]
    version: int = Field(strict=True, ge=1, le=MAX_MINOR)


class DispensingChargeItem(StrictModel):
    source_item_id: ID
    medicine_id: ID
    charge_code: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    quantity: Quantity


class DispensingChargeContext(StrictModel):
    dispensing_id: ID
    appointment_id: ID
    patient_id: ID
    items: list[DispensingChargeItem] = Field(max_length=50)
    version: int = Field(strict=True, ge=1, le=MAX_MINOR)
