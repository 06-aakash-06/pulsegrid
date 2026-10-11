"""FastAPI application factory and default ASGI application."""

from __future__ import annotations

from contextlib import asynccontextmanager
import asyncio
import os
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
        tasks=[]
        try:
            if application.state.phase3_enabled:
                from sqlalchemy import text
                async with database.session_factory() as session:
                    revision=(await session.execute(text('SELECT version_num FROM alembic_version'))).scalar_one()
                if revision!='0009_phase3_registration_history':raise RuntimeError('Phase 3 schema not reviewed at current head')
                from .integration_workers import worker_loop
                tasks=[asyncio.create_task(worker_loop(application))]
            yield
        finally:
            for task in tasks:task.cancel()
            if tasks:await asyncio.gather(*tasks,return_exceptions=True)
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
    enabled_value=os.environ.get('PULSEGRID_APPOINTMENT_PHASE3_ENABLED','false')
    if enabled_value not in ('true','false'):raise ValueError('Phase 3 activation must be true or false')
    application.state.phase3_enabled=enabled_value=='true'
    from .features.journey.snapshots import SnapshotClient
    application.state.snapshot_client=SnapshotClient()
    register_extensions(application, phase3_core, enabled=('waitlist','checkin','queue','journey') if application.state.phase3_enabled else ())
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
                "offer_unavailable", "version_conflict", "source_changed",
                "journey_not_ready", "doctor_busy", "not_queue_head", "queue_changed",
                "checkin_window_closed", "checkin_window_open",
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
