"""FastAPI application factory and default ASGI application."""

from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api.health import health_router
from .api.router import api_router
from .constants import API_PREFIX, SERVICE_NAME, SERVICE_VERSION
from .database import Database
from .errors import error_response
from .logging_config import get_service_logger
from .middleware import install_request_context
from .settings import Settings
from .authorization import AuthConfig, Verifier
from .dependencies import DomainClient


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an independently configurable service application."""
    resolved_settings = settings or Settings.from_env()
    database = Database(resolved_settings)
    auth_config = AuthConfig.from_env(resolved_settings.environment)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        await database.start()
        try:
            yield
        finally:
            await database.close()

    application = FastAPI(
        lifespan=lifespan,
        title=f"PulseGrid {SERVICE_NAME.title()} Service",
        version=SERVICE_VERSION,
        description=(
            "Synthetic educational prototype. "
            "Phase 2.3 appointment operations use PostgreSQL constraints."
        ),
    )
    application.state.auth_config = auth_config
    application.state.auth_verifier = Verifier(auth_config)
    application.state.database = database
    application.state.domain_client = DomainClient()
    application.state.settings = resolved_settings
    application.state.logger = get_service_logger(
        SERVICE_NAME, resolved_settings.log_level
    )
    application.include_router(health_router)
    application.include_router(
        health_router, prefix=API_PREFIX, include_in_schema=False
    )
    from . import phase3_core
    from .extensions import register_extensions
    register_extensions(application, phase3_core)
    application.include_router(api_router)
    if auth_config.origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(auth_config.origins),
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "X-CSRF-Token",
                "Idempotency-Key",
                "X-Anonymous-Command-ID",
                "X-Request-ID",
                "X-Correlation-ID",
                "traceparent",
                "If-Match",
            ],
            expose_headers=["ETag", "X-Request-ID", "X-Correlation-ID"],
        )
    install_request_context(application)

    @application.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exception: StarletteHTTPException
    ) -> JSONResponse:
        return error_response(
            request,
            exception.status_code,
            headers=exception.headers or (
                {"Retry-After": "1"} if exception.status_code == 503 else None
            ),
            code=exception.detail if isinstance(exception.detail, str) and exception.detail in {
                "slot_occupied", "patient_overlap", "schedule_changed", "revision_gap",
                "clinical_hold", "cancelled", "appointment_unavailable", "invalid_reference",
                "workflow_locked", "invalid_transition",
                "already_waiting", "already_booked", "slot_available", "waitlist_pending",
            } else None,
        )

    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exception: RequestValidationError
    ) -> JSONResponse:
        fields = []
        for error in exception.errors():
            location = [
                str(part)
                for part in error.get("loc", ())
                if part not in {"body", "query", "path", "header"}
            ]
            fields.append({"location": ".".join(location), "code": error["type"]})
        return error_response(
            request,
            422,
            details={"fields": fields},
        )

    @application.exception_handler(SQLAlchemyError)
    async def database_exception_handler(
        request: Request, _exception: SQLAlchemyError
    ) -> JSONResponse:
        return error_response(request, 503)

    @application.exception_handler(Exception)
    async def unexpected_exception_handler(
        request: Request, _exception: Exception
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        application.state.logger.error(
            "unhandled_exception",
            extra={"service": SERVICE_NAME, "request_id": str(request_id or "")},
        )
        return error_response(
            request,
            500,
            code="internal_error",
            message="An unexpected error occurred.",
        )

    return application


app = create_app()
