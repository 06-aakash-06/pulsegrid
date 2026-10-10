"""Authenticated emergency request lifecycle API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..authorization import (
    Principal,
    assert_current_role,
    authenticated_user,
    require_current_role,
    validate_patient_reference,
    valid_id,
)
from ..commands import (
    claim_request,
    command_response,
    create_request,
    get_request,
    idempotency_key_valid,
    list_history,
    list_requests,
    release_request,
    transition_request,
    update_priority,
    validate_patient_filter,
)
from ..database import get_database_session
from ..exceptions import DomainHTTPException
from ..schemas import (
    ClaimCommand,
    EmergencyHistoryPage,
    EmergencyRequestCreate,
    EmergencyRequestPage,
    EmergencyRequestView,
    EmergencyStaffRequestView,
    PriorityUpdate,
    ReleaseCommand,
    TransitionCommand,
    EmergencyState,
    WireId,
)
from ..constants import API_PREFIX

api_router = APIRouter(prefix=API_PREFIX)


async def _authorize_read(request: Request, principal: Principal) -> bool:
    if "emergency_staff" in principal.roles:
        await assert_current_role(request, principal, "emergency_staff")
        return True
    if "patient" in principal.roles:
        await assert_current_role(request, principal, "patient")
        return False
    raise HTTPException(403)


def _validate_query_keys(request: Request, allowed: set[str]) -> None:
    keys = request.query_params.keys()
    if any(key not in allowed for key in keys):
        raise DomainHTTPException(422, "validation_error", "Unknown query parameter.")
    if any(len(request.query_params.getlist(key)) != 1 for key in set(keys)):
        raise DomainHTTPException(422, "validation_error", "Repeated query parameter.")


def _patient_scope(principal: Principal) -> str:
    if principal.patient_id is None or not valid_id(principal.patient_id):
        raise HTTPException(403)
    return principal.patient_id


def _validate_idempotency_key(value: str) -> None:
    if not idempotency_key_valid(value):
        raise DomainHTTPException(
            400,
            "bad_request",
            "Idempotency-Key must contain 16 to 128 printable ASCII characters.",
        )


@api_router.post(
    "",
    status_code=201,
    response_model=EmergencyRequestView,
    responses={201: {"model": EmergencyRequestView}},
)
async def submit_request(
    request: Request,
    body: EmergencyRequestCreate,
    principal: Annotated[Principal, Depends(require_current_role("patient"))],
    session: Annotated[AsyncSession, Depends(get_database_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
):
    _validate_idempotency_key(idempotency_key)
    patient_id = _patient_scope(principal)
    if body.patient_id != patient_id:
        raise HTTPException(403)
    await validate_patient_reference(request, principal, patient_id)
    outcome = await create_request(
        session,
        request,
        body,
        principal_user_id=principal.user_id,
        worker_id=request.app.state.settings.id_worker_id,
    )
    return command_response(outcome)


@api_router.get("", response_model=EmergencyRequestPage)
async def get_requests(
    request: Request,
    principal: Annotated[Principal, Depends(authenticated_user)],
    session: Annotated[AsyncSession, Depends(get_database_session)],
    patient_id: str | None = None,
    state: EmergencyState | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    _validate_query_keys(request, {"patient_id", "state", "cursor", "limit"})
    staff = await _authorize_read(request, principal)
    patient_scope = None if staff else _patient_scope(principal)
    validate_patient_filter(patient_id)
    if not staff and patient_id is not None and patient_id != patient_scope:
        raise DomainHTTPException(404, "not_found", "Emergency request was not found.")
    body = await list_requests(
        session,
        request,
        principal_user_id=principal.user_id,
        patient_scope=patient_scope,
        staff=staff,
        patient_filter=patient_id,
        state_filter=state,
        cursor=cursor,
        limit=limit,
        worker_id=request.app.state.settings.id_worker_id,
    )
    return JSONResponse(
        content=body,
        headers={"Cache-Control": "no-store"},
    )


@api_router.get("/{request_id}/history", response_model=EmergencyHistoryPage)
async def get_request_history(
    request: Request,
    request_id: WireId,
    principal: Annotated[Principal, Depends(authenticated_user)],
    session: Annotated[AsyncSession, Depends(get_database_session)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    _validate_query_keys(request, {"cursor", "limit"})
    staff = await _authorize_read(request, principal)
    patient_scope = None if staff else _patient_scope(principal)
    body = await list_history(
        session,
        request,
        request_id,
        principal_user_id=principal.user_id,
        patient_scope=patient_scope,
        staff=staff,
        cursor=cursor,
        limit=limit,
        worker_id=request.app.state.settings.id_worker_id,
    )
    return JSONResponse(content=body, headers={"Cache-Control": "no-store"})


@api_router.get(
    "/{request_id}",
    response_model=EmergencyStaffRequestView | EmergencyRequestView,
)
async def get_request_detail(
    request: Request,
    request_id: WireId,
    principal: Annotated[Principal, Depends(authenticated_user)],
    session: Annotated[AsyncSession, Depends(get_database_session)],
):
    staff = await _authorize_read(request, principal)
    patient_scope = None if staff else _patient_scope(principal)
    body, etag = await get_request(
        session,
        request,
        request_id,
        principal_user_id=principal.user_id,
        patient_scope=patient_scope,
        staff=staff,
        worker_id=request.app.state.settings.id_worker_id,
    )
    return JSONResponse(
        content=body,
        headers={"ETag": etag, "Cache-Control": "no-store"},
    )


@api_router.patch(
    "/{request_id}/priority", response_model=EmergencyStaffRequestView
)
async def assign_priority(
    request: Request,
    request_id: WireId,
    body: PriorityUpdate,
    principal: Annotated[Principal, Depends(require_current_role("emergency_staff"))],
    session: Annotated[AsyncSession, Depends(get_database_session)],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
):
    outcome = await update_priority(
        session,
        request,
        request_id,
        body,
        principal_user_id=principal.user_id,
        worker_id=request.app.state.settings.id_worker_id,
        if_match=if_match,
    )
    return command_response(outcome)


@api_router.post(
    "/{request_id}/claim", response_model=EmergencyStaffRequestView
)
async def claim_emergency_request(
    request: Request,
    request_id: WireId,
    body: ClaimCommand,
    principal: Annotated[Principal, Depends(require_current_role("emergency_staff"))],
    session: Annotated[AsyncSession, Depends(get_database_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
):
    _validate_idempotency_key(idempotency_key)
    outcome = await claim_request(
        session,
        request,
        request_id,
        principal_user_id=principal.user_id,
        worker_id=request.app.state.settings.id_worker_id,
        if_match=if_match,
        idempotency_key=idempotency_key,
    )
    return command_response(outcome)


@api_router.post(
    "/{request_id}/release", response_model=EmergencyStaffRequestView
)
async def release_emergency_request(
    request: Request,
    request_id: WireId,
    body: ReleaseCommand,
    principal: Annotated[Principal, Depends(require_current_role("emergency_staff"))],
    session: Annotated[AsyncSession, Depends(get_database_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
):
    _validate_idempotency_key(idempotency_key)
    outcome = await release_request(
        session,
        request,
        request_id,
        body.reason,
        principal_user_id=principal.user_id,
        worker_id=request.app.state.settings.id_worker_id,
        if_match=if_match,
        idempotency_key=idempotency_key,
    )
    return command_response(outcome)


@api_router.post(
    "/{request_id}/transitions",
    response_model=EmergencyStaffRequestView | EmergencyRequestView,
)
async def transition_emergency_request(
    request: Request,
    request_id: WireId,
    body: TransitionCommand,
    principal: Annotated[Principal, Depends(authenticated_user)],
    session: Annotated[AsyncSession, Depends(get_database_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
):
    _validate_idempotency_key(idempotency_key)
    if body.state in {"processing", "resolved"} or "emergency_staff" in principal.roles:
        await assert_current_role(request, principal, "emergency_staff")
        staff_actor = True
    elif body.state == "cancelled" and "patient" in principal.roles:
        await assert_current_role(request, principal, "patient")
        staff_actor = False
    else:
        raise HTTPException(403)
    patient_id = _patient_scope(principal) if not staff_actor else None
    outcome = await transition_request(
        session,
        request,
        request_id,
        body,
        principal_user_id=principal.user_id,
        patient_id=patient_id,
        worker_id=request.app.state.settings.id_worker_id,
        staff_actor=staff_actor,
        if_match=if_match,
        idempotency_key=idempotency_key,
    )
    return command_response(outcome)
