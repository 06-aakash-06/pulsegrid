"""Safe, consistent HTTP error response helpers."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from fastapi import Request
from fastapi.responses import JSONResponse

from .schemas import ErrorResponse


_STATUS_ERRORS: dict[int, tuple[str, str]] = {
    400: ("bad_request", "The request could not be processed."),
    401: ("unauthorized", "Authentication is required or invalid."),
    403: ("forbidden", "The request is not permitted."),
    404: ("not_found", "The requested resource was not found."),
    405: ("method_not_allowed", "The request method is not allowed."),
    409: ("conflict", "The request conflicts with the current resource state."),
    410: ("gone", "The requested resource is no longer available."),
    412: ("version_conflict", "The resource version has changed."),
    422: ("validation_error", "The request did not pass validation."),
    428: ("precondition_required", "A required request precondition is missing."),
    429: ("rate_limited", "Too many requests."),
    503: ("dependency_unavailable", "A required dependency is unavailable."),
    504: ("dependency_timeout", "A required dependency did not respond in time."),
}


def error_response(
    request: Request,
    status_code: int,
    code: str | None = None,
    message: str | None = None,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    default_code, default_message = _STATUS_ERRORS.get(
        status_code, ("http_error", "The request could not be completed.")
    )
    request_id = getattr(request.state, "request_id", uuid4())
    body = ErrorResponse(
        error={
            "code": code or default_code,
            "message": message or default_message,
            "request_id": request_id,
            "details": details,
        }
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json", exclude_none=True),
        headers=headers,
    )
