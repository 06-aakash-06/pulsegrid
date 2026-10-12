"""FastAPI application factory and default ASGI application."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api.clinical import private_router
from .api.clinical import router as clinical_router
from .api.health import health_router
from .api.router import api_router
from .authorization import AuthConfig, Verifier
from .constants import API_PREFIX, SERVICE_NAME, SERVICE_VERSION
from .database import Database
from .domain_client import DomainClient
from .errors import error_response
from .logging_config import get_service_logger
from .middleware import install_request_context
from .settings import Settings


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
            from .admission import close as close_admission
            await close_admission(application)
            await database.close()

    application = FastAPI(
        lifespan=lifespan,
        title=f"PulseGrid {SERVICE_NAME.title()} Service",
        version=SERVICE_VERSION,
        description=(
            "Synthetic educational prototype. Secure Phase 2 clinical records."
        ),
    )
    application.state.domain_client = DomainClient()
    application.state.auth_config = auth_config
    application.state.auth_verifier = Verifier(auth_config)
    application.state.database = database
    application.state.settings = resolved_settings
    application.state.logger = get_service_logger(
        SERVICE_NAME, resolved_settings.log_level
    )
    from .phase4_metrics import mount as mount_metrics
    mount_metrics(application)
    application.include_router(health_router)
    application.include_router(
        health_router, prefix=API_PREFIX, include_in_schema=False
    )
    application.include_router(api_router)
    application.include_router(clinical_router)
    application.include_router(private_router)
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
            expose_headers=["ETag", "X-Request-ID", "X-Correlation-ID", "Retry-After"],
        )
    from .admission import mount as mount_admission
    mount_admission(application,'records',error_response)
    install_request_context(application)

    @application.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exception: StarletteHTTPException
    ) -> JSONResponse:
        return error_response(
            request,
            exception.status_code,
            headers=exception.headers,
            code=exception.detail
            if isinstance(exception.detail, str)
            and exception.detail
            in {
                "consultation_exists",
                "appointment_unavailable",
                "finalized",
                "superseded",
                "invalid_reference",
            }
            else None,
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
