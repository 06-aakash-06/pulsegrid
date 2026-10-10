"""Small response schemas shared by this service's routes."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    StringConstraints,
    model_validator,
)


def _valid_id(value: str) -> str:
    if not value.isascii() or not value.isdigit() or value.startswith("0"):
        raise ValueError("invalid identifier")
    if len(value) > 19 or int(value) > 9223372036854775807:
        raise ValueError("invalid identifier")
    return value


def _valid_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError("invalid date") from None
    if parsed.isoformat() != value:
        raise ValueError("invalid date")
    return value


ID = Annotated[
    StrictStr,
    StringConstraints(pattern=r"^[1-9][0-9]{0,18}$", max_length=19),
    AfterValidator(_valid_id),
]
Name = Annotated[
    StrictStr, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
SKU = Annotated[
    StrictStr, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
]
BatchCode = Annotated[
    StrictStr, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
]
Reason = Annotated[
    StrictStr, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]
DateString = Annotated[
    StrictStr,
    StringConstraints(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"),
    AfterValidator(_valid_date),
]
Quantity = Annotated[StrictInt, Field(ge=1, le=1_000_000)]
Version = Annotated[StrictInt, Field(ge=1, le=9_007_199_254_740_991)]


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class MedicineCreate(StrictRequest):
    sku: SKU
    name: Name


class MedicinePatch(StrictRequest):
    name: Name | None = None
    active: StrictBool | None = None

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("at least one field is required")
        if self.name is None and "name" in self.model_fields_set:
            raise ValueError("name cannot be null")
        if self.active is None and "active" in self.model_fields_set:
            raise ValueError("active cannot be null")
        return self


class StockAdjustment(StrictRequest):
    medicine_id: ID
    batch_code: BatchCode
    expires_on: DateString
    delta: Annotated[StrictInt, Field(ge=-1_000_000, le=1_000_000)]
    reason: Reason
    expected_batch_version: Annotated[
        StrictInt, Field(ge=0, le=9_007_199_254_740_991)
    ]

    @model_validator(mode="after")
    def require_nonzero_delta(self):
        if self.delta == 0:
            raise ValueError("delta must be nonzero")
        return self


class ReservationItemInput(StrictRequest):
    prescription_item_id: ID
    quantity: Quantity


class ReservationCreate(StrictRequest):
    prescription_id: ID
    items: list[ReservationItemInput] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def require_distinct_items(self):
        ids = [item.prescription_item_id for item in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("prescription_item_id values must be distinct")
        return self


class EmptyCommand(StrictRequest):
    pass


class MedicineValidation(StrictRequest):
    medicine_ids: list[ID] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def require_distinct_medicines(self):
        if len(set(self.medicine_ids)) != len(self.medicine_ids):
            raise ValueError("medicine_ids must be distinct")
        return self


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
