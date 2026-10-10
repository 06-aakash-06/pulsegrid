"""Process liveness and explicit dependency readiness routes."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..constants import SERVICE_NAME
from ..schemas import DependencyReadiness, LivenessResponse, ReadinessResponse

health_router = APIRouter(prefix="/health", tags=["health"])


@health_router.get("/live", response_model=LivenessResponse)
async def live() -> LivenessResponse:
    """Report that the application process is responding."""
    return LivenessResponse(status="alive", service=SERVICE_NAME)


@health_router.get(
    "/ready",
    response_model=ReadinessResponse,
    status_code=503,
    responses={503: {"model": ReadinessResponse}},
)
async def ready() -> JSONResponse:
    """Report application state separately from its unconfigured database."""
    body = ReadinessResponse(
        status="not_ready",
        service=SERVICE_NAME,
        application="ready",
        dependencies={
            "database": DependencyReadiness(status="unconfigured", required=True)
        },
    )
    return JSONResponse(
        status_code=503,
        content=body.model_dump(mode="json"),
    )
