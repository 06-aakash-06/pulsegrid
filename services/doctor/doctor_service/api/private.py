"""Appointment-only Doctor identity and immutable proposal leaves."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import append_audit
from ..authorization import Principal, bearer
from ..database import get_database_session
from ..errors import ApiError
from ..repository import get_doctor, list_schedules, proposal_view
from ..schemas import DoctorIdentity, PrivateProposal
from ..wire import etag, parse_id, validate_query_keys

private_router = APIRouter(tags=["doctor-internal"])


def _service_principal(request: Request, scope: str) -> tuple[str, Principal]:
    caller = request.app.state.auth_verifier.service(
        bearer(request), scope
    )
    if caller != "appointment":
        raise ApiError(403, "forbidden")
    delegated = request.app.state.auth_verifier.user(
        bearer(request, "X-Delegated-Authorization")
    )
    return caller, delegated


def _allowed_identity(principal: Principal, staff_user_id: int) -> bool:
    return bool(
        {"patient", "receptionist", "hospital_admin"}.intersection(principal.roles)
        or ("doctor" in principal.roles and principal.user_id == str(staff_user_id))
    )


def _allowed_proposal(principal: Principal, staff_user_id: int) -> bool:
    return bool(
        "hospital_admin" in principal.roles
        or ("doctor" in principal.roles and principal.user_id == str(staff_user_id))
    )


@private_router.get(
    "/internal/v1/doctors/{doctor_id}/identity",
    response_model=DoctorIdentity,
)
async def doctor_identity(
    doctor_id: str,
    request: Request,
    session: AsyncSession = Depends(get_database_session),
) -> JSONResponse:
    validate_query_keys(request, set())
    doctor_id = parse_id(doctor_id)
    _, principal = _service_principal(request, "doctors:identity")
    row = await get_doctor(session, doctor_id)
    if row is None or not _allowed_identity(principal, row["staff_user_id"]):
        raise ApiError(404, "not_found")
    await append_audit(
        session,
        request,
        actor_user_id=principal.user_id,
        action="doctor.identity.read",
        resource_type="doctor",
        resource_id=doctor_id,
        resource_version=row["version"],
    )
    await session.commit()
    response = DoctorIdentity(
        doctor_id=doctor_id,
        staff_user_id=str(row["staff_user_id"]),
        active=row["active"],
        version=row["version"],
    )
    return JSONResponse(
        content=response.model_dump(mode="json"),
        headers={"ETag": etag(row["version"]), "Cache-Control": "no-store"},
    )


@private_router.get(
    "/internal/v1/doctors/{doctor_id}/schedule-proposals/{proposal_id}",
    response_model=PrivateProposal,
)
async def schedule_proposal(
    doctor_id: str,
    proposal_id: str,
    request: Request,
    session: AsyncSession = Depends(get_database_session),
) -> JSONResponse:
    validate_query_keys(request, set())
    doctor_id = parse_id(doctor_id)
    proposal_id = parse_id(proposal_id)
    _, principal = _service_principal(request, "schedules:read")
    doctor = await get_doctor(session, doctor_id)
    if doctor is None or not _allowed_proposal(principal, doctor["staff_user_id"]):
        raise ApiError(404, "not_found")
    proposals = await list_schedules(
        session,
        doctor_id=doctor_id,
        cursor=None,
        limit=1,
        proposal_id=proposal_id,
    )
    if not proposals:
        raise ApiError(404, "not_found")
    proposal = proposals[0]
    await append_audit(
        session,
        request,
        actor_user_id=principal.user_id,
        action="doctor.schedule_proposal.read",
        resource_type="schedule_proposal",
        resource_id=proposal_id,
        resource_version=proposal["version"],
    )
    await session.commit()
    response = PrivateProposal(
        proposal=proposal_view(proposal),
        staff_user_id=str(doctor["staff_user_id"]),
        active=doctor["active"],
        doctor_version=doctor["version"],
    )
    return JSONResponse(
        content=response.model_dump(mode="json"),
        headers={"ETag": etag(proposal["version"]), "Cache-Control": "no-store"},
    )
