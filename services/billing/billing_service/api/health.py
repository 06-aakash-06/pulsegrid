"""Process liveness and bounded PostgreSQL readiness checks."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from ..constants import SERVICE_NAME
from ..schemas import DependencyReadiness, LivenessResponse, ReadinessResponse

health_router = APIRouter(prefix="/health", tags=["health"])


@health_router.get("/live", response_model=LivenessResponse)
async def live() -> LivenessResponse:
    return LivenessResponse(status="alive", service=SERVICE_NAME)


@health_router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
async def ready(request: Request) -> JSONResponse:
    status = await request.app.state.database.readiness()
    ready = status == "available"
    body = ReadinessResponse(
        status="ready" if ready else "not_ready",
        service=SERVICE_NAME,
        application="ready",
        dependencies={"database": DependencyReadiness(status=status, required=True)},
    )
    return JSONResponse(
        status_code=200 if ready else 503, content=body.model_dump(mode="json")
    )
