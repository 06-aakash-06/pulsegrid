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
from .exceptions import DomainHTTPException
from .logging_config import get_service_logger
from .middleware import install_request_context
from .settings import Settings
from .authorization import AuthConfig, Verifier


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
            "Synthetic educational emergency request management for an "
            "educational prototype. This is not an emergency dispatch or "
            "medical triage system."
        ),
    )
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
    mount_admission(application,'emergency',error_response)
    install_request_context(application)

    @application.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exception: StarletteHTTPException
    ) -> JSONResponse:
        if isinstance(exception, DomainHTTPException):
            return error_response(
                request,
                exception.status_code,
                code=exception.code,
                message=exception.message,
                details=exception.details,
                headers=exception.headers,
            )
        return error_response(
            request,
            exception.status_code,
            headers=exception.headers,
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
