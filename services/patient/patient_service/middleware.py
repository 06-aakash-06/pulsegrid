"""Request and trace context validation and response headers."""

from __future__ import annotations

import re
from time import perf_counter
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from .constants import SERVICE_NAME
from .errors import error_response

_OBSERVABILITY_EXCLUDED_PATHS = {
    "/metrics", "/health/live", "/health/ready",
    "/api/v1/health/live", "/api/v1/health/ready",
}

_TRACEPARENT = re.compile(
    r"^(?P<version>[0-9a-f]{2})-(?P<trace_id>[0-9a-f]{32})-"
    r"(?P<span_id>[0-9a-f]{16})-(?P<flags>[0-9a-f]{2})"
    r"(?:-(?P<extension>[0-9a-f]+(?:-[0-9a-f]+)*))?$"
)


def validate_traceparent(value: str | None) -> str | None:
    """Return a valid W3C traceparent value, or None when it is malformed."""
    if value is None:
        return None
    match = _TRACEPARENT.fullmatch(value)
    if match is None:
        return None
    if match.group("version") == "ff":
        return None
    if match.group("trace_id") == "0" * 32 or match.group("span_id") == "0" * 16:
        return None
    if match.group("version") == "00" and match.group("extension") is not None:
        return None
    return value


def _active_traceparent(fallback: str | None) -> str | None:
    """Use this request's server span as the parent for service-owned work."""
    try:
        from opentelemetry import trace

        context = trace.get_current_span().get_span_context()
        if context.is_valid:
            return (
                f"00-{context.trace_id:032x}-{context.span_id:016x}-"
                f"{int(context.trace_flags):02x}"
            )
    except ImportError:
        pass
    return fallback


def _parse_or_generate_uuid(value: str | None) -> tuple[UUID, bool]:
    if value is None:
        return uuid4(), False
    try:
        return UUID(value), False
    except (ValueError, AttributeError):
        return uuid4(), True


def install_request_context(app: FastAPI) -> None:
    """Install request/correlation ID handling and safe request completion logs."""

    @app.middleware("http")
    async def request_context_middleware(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id, invalid_request_id = _parse_or_generate_uuid(
            request.headers.get("X-Request-ID")
        )
        correlation_id, invalid_correlation_id = _parse_or_generate_uuid(
            request.headers.get("X-Correlation-ID")
        )
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id
        request.state.traceparent = _active_traceparent(
            validate_traceparent(request.headers.get("traceparent"))
        )

        response_headers = {
            "X-Request-ID": str(request_id),
            "X-Correlation-ID": str(correlation_id),
        }
        if invalid_request_id or invalid_correlation_id:
            invalid_header = "X-Request-ID" if invalid_request_id else "X-Correlation-ID"
            return error_response(
                request,
                400,
                code="invalid_request_id" if invalid_request_id else "invalid_correlation_id",
                message=f"{invalid_header} must be a UUID.",
                headers=response_headers,
            )

        start = perf_counter()
        response = await call_next(request)
        response.headers.update(response_headers)
        matched_route = request.scope.get("route")
        route_template = getattr(matched_route, "path", "<unmatched>")
        if request.url.path not in _OBSERVABILITY_EXCLUDED_PATHS:
            request.app.state.logger.info(
                "http_request_completed",
                extra={
                    "service": SERVICE_NAME,
                    "request_id": str(request_id),
                    "correlation_id": str(correlation_id),
                    "traceparent": request.state.traceparent,
                    "method": request.method,
                    "path": route_template,
                    "status_code": response.status_code,
                    "duration_ms": round((perf_counter() - start) * 1000, 3),
                },
            )
        return response
