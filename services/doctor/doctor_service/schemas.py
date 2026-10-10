"""Small response schemas shared by this service's routes."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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
    status: Literal["unconfigured"]
    required: bool


class ReadinessResponse(BaseModel):
    status: Literal["not_ready"]
    service: str
    application: Literal["ready"]
    dependencies: dict[str, DependencyReadiness] = Field(min_length=1)
