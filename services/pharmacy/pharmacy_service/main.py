"""FastAPI application factory and default ASGI application."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api.health import health_router
from .api.router import api_router
from .constants import SERVICE_NAME, SERVICE_VERSION
from .errors import error_response
from .logging_config import get_service_logger
from .middleware import install_request_context
from .settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an independently configurable service application."""
    resolved_settings = settings or Settings.from_env()
    application = FastAPI(
        title=f"PulseGrid {SERVICE_NAME.title()} Service",
        version=SERVICE_VERSION,
        description=(
            "Synthetic educational prototype scaffold. Business operations and "
            "database adapters are not implemented."
        ),
    )
    application.state.settings = resolved_settings
    application.state.logger = get_service_logger(
        SERVICE_NAME, resolved_settings.log_level
    )
    application.include_router(health_router)
    application.include_router(api_router)
    install_request_context(application)

    @application.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exception: StarletteHTTPException
    ) -> JSONResponse:
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
