"""Public Doctor profile, specialty, and schedule proposal endpoints."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import append_audit
from ..authorization import (
    Principal,
    authenticated_user,
    require_current_role,
    require_current_roles,
)
from ..constants import API_PREFIX
from ..commands import execute_idempotent
from ..database import get_database_session
from ..dependencies import DependencyTimeout, DependencyUnavailable, RemoteResponse
from ..errors import ApiError
from ..events import append_outbox
from ..idempotency import (
    fingerprint,
    outcome_response,
    replay_if_present,
)
from ..ids import new_id
from ..repository import (
    DOCTOR_SELECT,
    doctor_profile,
    get_doctor,
    list_doctors,
    list_schedules,
    list_specialties,
    proposal_view,
    specialty_view,
)
from ..schedules import validate_schedule
from ..schemas import (
    DoctorCreate,
    DoctorPatch,
    DoctorProfile,
    DoctorSelf,
    EmptyCommand,
    OperationalStatus,
    Page,
    ScheduleDecision,
    ScheduleInput,
    ScheduleProposal,
    Specialty,
    SpecialtyInput,
    StaffStatus,
)
from ..wire import (
    decode_cursor,
    encode_cursor,
    etag,
    idempotency_key,
    limit_value,
    normalized_search,
    parse_id,
    parse_if_match,
    validate_query_keys,
    filter_digest,
)

doctor_router = APIRouter(prefix=API_PREFIX)


def _json(model: Any, value: Any, *, status_code: int = 200, headers=None) -> JSONResponse:
    result = model.model_validate(value)
    return JSONResponse(
        status_code=status_code,
        content=result.model_dump(mode="json"),
        headers=headers or {},
    )


async def _preflight_replay(
    session: AsyncSession,
    principal: Principal,
    *,
    route_key: str,
    key: str,
    body: dict[str, Any],
    if_match: str | None,
) -> JSONResponse | None:
    replay = await replay_if_present(
        session,
        scope="user:" + principal.user_id,
        route_key=route_key,
        key=key,
        request_hash=fingerprint(body, if_match),
        lock=False,
    )
    if replay is not None:
        return outcome_response(replay)
    await session.commit()
    return None


async def _validate_specialties(
    session: AsyncSession, specialty_ids: list[str]
) -> None:
    if not 1 <= len(specialty_ids) <= 20 or len(set(specialty_ids)) != len(specialty_ids):
        raise ApiError(422, "validation_error")
    bind_names = [f"specialty_{index}" for index in range(len(specialty_ids))]
    params = {name: int(value) for name, value in zip(bind_names, specialty_ids)}
    placeholders = ",".join(f":{name}" for name in bind_names)
    rows = (
        await session.execute(
            text(f"SELECT id FROM specialties WHERE id IN ({placeholders})"), params
        )
    ).scalars().all()
    if {str(value) for value in rows} != set(specialty_ids):
        raise ApiError(422, "invalid_reference")


async def _replace_specialties(
    session: AsyncSession, doctor_id: str, specialty_ids: list[str]
) -> None:
    await _validate_specialties(session, specialty_ids)
    await session.execute(
        text("DELETE FROM doctor_specialties WHERE doctor_id=:doctor_id"),
        {"doctor_id": int(doctor_id)},
    )
    for specialty_id in specialty_ids:
        await session.execute(
            text(
                "INSERT INTO doctor_specialties(doctor_id,specialty_id) "
                "VALUES (:doctor_id,:specialty_id)"
            ),
            {"doctor_id": int(doctor_id), "specialty_id": int(specialty_id)},
        )


async def _doctor_for_user(session: AsyncSession, user_id: str) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(DOCTOR_SELECT + " WHERE d.staff_user_id=:user_id"),
            {"user_id": int(user_id)},
        )
    ).mappings().first()
    return dict(row) if row is not None else None


async def _authorized_doctor(
    session: AsyncSession, doctor_id: str, principal: Principal
) -> dict[str, Any]:
    row = await get_doctor(session, doctor_id)
    if row is None:
        raise ApiError(404, "not_found")
    if (
        principal.authorized_role == "doctor"
        and str(row["staff_user_id"]) != principal.user_id
    ):
        raise ApiError(404, "not_found")
    return row


def _page_cursor(rows: list[dict[str, Any]], limit: int, filter_hash: str) -> str | None:
    if len(rows) <= limit:
        return None
    last = rows[limit - 1]
    return encode_cursor(last["created_at"], str(last["id"]), filter_hash)


def _body(model: Any) -> dict[str, Any]:
    value = model.model_dump(mode="json", exclude_unset=True)
    if "specialty_ids" in value:
        value["specialty_ids"] = sorted(value["specialty_ids"], key=int)
    return value


async def _staff_status(request: Request, principal: Principal, user_id: str) -> StaffStatus:
    try:
        raw = await request.app.state.dependencies.staff_status(
            request, principal, user_id
        )
        status = StaffStatus.model_validate(raw)
    except RemoteResponse as error:
        if error.status_code == 404:
            raise ApiError(422, "invalid_reference") from None
        if error.status_code == 403:
            raise ApiError(403, "forbidden") from None
        raise ApiError(503, "dependency_unavailable") from None
    except DependencyTimeout:
        raise ApiError(504, "dependency_timeout") from None
    except DependencyUnavailable:
        raise ApiError(503, "dependency_unavailable") from None
    except ValidationError:
        raise ApiError(503, "dependency_unavailable") from None
    if status.user_id != user_id:
        raise ApiError(503, "dependency_unavailable")
    return status


async def _operational_status(
    request: Request, principal: Principal, doctor_id: str
) -> OperationalStatus:
    try:
        raw = await request.app.state.dependencies.operational_status(
            request, principal, doctor_id
        )
        status = OperationalStatus.model_validate(raw)
    except RemoteResponse as error:
        if error.status_code == 403:
            raise ApiError(403, "forbidden") from None
        raise ApiError(503, "dependency_unavailable") from None
    except DependencyTimeout:
        raise ApiError(504, "dependency_timeout") from None
    except DependencyUnavailable:
        raise ApiError(503, "dependency_unavailable") from None
    except ValidationError:
        raise ApiError(503, "dependency_unavailable") from None
    if status.doctor_id != doctor_id:
        raise ApiError(503, "dependency_unavailable")
    return status


async def _schedule_decision(
    request: Request, principal: Principal, proposal_id: str
) -> ScheduleDecision:
    try:
        raw = await request.app.state.dependencies.schedule_decision(
            request, principal, proposal_id
        )
        return ScheduleDecision.model_validate(raw)
    except RemoteResponse as error:
        if error.status_code == 404:
            raise ApiError(409, "decision_pending") from None
        if error.status_code == 403:
            raise ApiError(403, "forbidden") from None
        raise ApiError(503, "dependency_unavailable") from None
    except DependencyTimeout:
        raise ApiError(504, "dependency_timeout") from None
    except DependencyUnavailable:
        raise ApiError(503, "dependency_unavailable") from None
    except ValidationError:
        raise ApiError(503, "dependency_unavailable") from None


@doctor_router.get("/specialties", response_model=Page[Specialty])
async def get_specialties(
    request: Request,
    principal: Principal = Depends(authenticated_user),
    session: AsyncSession = Depends(get_database_session),
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> JSONResponse:
    del principal
    validate_query_keys(request, {"cursor", "limit"})
    limit_value(limit)
    digest = filter_digest({"resource": "doctor_specialties"})
    position = decode_cursor(cursor, digest)
    rows = await list_specialties(session, cursor=position, limit=limit + 1)
    next_cursor = _page_cursor(rows, limit, digest)
    page = {
        "items": [specialty_view(row) for row in rows[:limit]],
        "next_cursor": next_cursor,
    }
    return _json(Page[Specialty], page)


@doctor_router.post("/specialties", status_code=201, response_model=Specialty)
async def create_specialty(
    body: SpecialtyInput,
    request: Request,
    principal: Principal = Depends(require_current_role("hospital_admin")),
    session: AsyncSession = Depends(get_database_session),
    key_header: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    validate_query_keys(request, set())
    key = idempotency_key(key_header)
    request_body = _body(body)

    async def operation():
        specialty_id = str(new_id())
        await session.execute(
            text(
                """INSERT INTO specialties(id,slug,name,version)
                   VALUES (:id,:slug,:name,1)"""
            ),
            {"id": int(specialty_id), **request_body},
        )
        row = (
            await session.execute(
                text("SELECT id,slug,name,version FROM specialties WHERE id=:id"),
                {"id": int(specialty_id)},
            )
        ).mappings().one()
        result = specialty_view(dict(row))
        await append_audit(
            session,
            request,
            actor_user_id=principal.user_id,
            action="doctor.specialty.created",
            resource_type="specialty",
            resource_id=specialty_id,
            resource_version=1,
        )
        await append_outbox(
            session,
            request,
            event_type="doctor.specialty.created.v1",
            aggregate_type="doctor_specialty",
            aggregate_id=specialty_id,
            aggregate_version=1,
            payload={"resource_id": specialty_id, "version": 1},
        )
        return 201, result, etag(1)

    return await execute_idempotent(
        session,
        request,
        principal,
        route_key=request.url.path,
        key=key,
        body=request_body,
        if_match=None,
        operation=operation,
    )


@doctor_router.get("/me", response_model=DoctorSelf)
async def get_me(
    request: Request,
    principal: Principal = Depends(require_current_role("doctor")),
    session: AsyncSession = Depends(get_database_session),
) -> JSONResponse:
    validate_query_keys(request, set())
    row = await _doctor_for_user(session, principal.user_id)
    if row is None:
        raise ApiError(404, "not_found")
    await append_audit(
        session,
        request,
        actor_user_id=principal.user_id,
        action="doctor.self.read",
        resource_type="doctor",
        resource_id=str(row["id"]),
        resource_version=row["version"],
    )
    await session.commit()
    result = DoctorSelf(doctor=doctor_profile(row), staff_user_id=principal.user_id)
    return JSONResponse(
        content=result.model_dump(mode="json"),
        headers={"ETag": etag(row["version"]), "Cache-Control": "no-store"},
    )


@doctor_router.get("", response_model=Page[DoctorProfile])
async def search_doctors(
    request: Request,
    principal: Principal = Depends(authenticated_user),
    session: AsyncSession = Depends(get_database_session),
    specialty_id: str | None = None,
    active: bool = True,
    q: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> JSONResponse:
    del principal
    validate_query_keys(
        request, {"specialty_id", "active", "q", "cursor", "limit"}
    )
    specialty_id = parse_id(specialty_id) if specialty_id is not None else None
    query = normalized_search(q)
    limit_value(limit)
    if specialty_id is not None:
        exists = await session.scalar(
            text("SELECT id FROM specialties WHERE id=:id"),
            {"id": int(specialty_id)},
        )
        if exists is None:
            raise ApiError(422, "invalid_reference")
    digest = filter_digest(
        {"active": active, "q": query, "specialty_id": specialty_id}
    )
    position = decode_cursor(cursor, digest)
    rows = await list_doctors(
        session,
        active=active,
        specialty_id=specialty_id,
        query=query,
        cursor=position,
        limit=limit + 1,
    )
    page = {
        "items": [doctor_profile(row) for row in rows[:limit]],
        "next_cursor": _page_cursor(rows, limit, digest),
    }
    return _json(Page[DoctorProfile], page)


@doctor_router.get("/{doctor_id}", response_model=DoctorProfile)
async def get_doctor_profile(
    doctor_id: str,
    request: Request,
    principal: Principal = Depends(authenticated_user),
    session: AsyncSession = Depends(get_database_session),
) -> JSONResponse:
    del principal
    validate_query_keys(request, set())
    doctor_id = parse_id(doctor_id)
    row = await get_doctor(session, doctor_id)
    if row is None:
        raise ApiError(404, "not_found")
    return _json(
        DoctorProfile,
        doctor_profile(row),
        headers={"ETag": etag(row["version"])},
    )


@doctor_router.post("", status_code=201, response_model=DoctorProfile)
async def create_doctor(
    body: DoctorCreate,
    request: Request,
    principal: Principal = Depends(require_current_role("hospital_admin")),
    session: AsyncSession = Depends(get_database_session),
    key_header: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    validate_query_keys(request, set())
    key = idempotency_key(key_header)
    request_body = _body(body)
    replay = await _preflight_replay(
        session,
        principal,
        route_key=request.url.path,
        key=key,
        body=request_body,
        if_match=None,
    )
    if replay is not None:
        return replay
    await _validate_specialties(session, body.specialty_ids)
    await session.commit()
    staff = await _staff_status(request, principal, body.staff_user_id)
    if not staff.active or "doctor" not in staff.roles:
        raise ApiError(422, "invalid_reference")

    async def operation():
        doctor_id = str(new_id())
        await session.execute(
            text(
                """INSERT INTO doctors(id,staff_user_id,display_name,active,
                                       profile_version,version)
                   VALUES (:id,:staff_user_id,:display_name,true,1,1)"""
            ),
            {
                "id": int(doctor_id),
                "staff_user_id": int(body.staff_user_id),
                "display_name": body.display_name,
            },
        )
        await _replace_specialties(session, doctor_id, body.specialty_ids)
        row = await get_doctor(session, doctor_id)
        assert row is not None
        result = doctor_profile(row)
        await append_audit(
            session,
            request,
            actor_user_id=principal.user_id,
            action="doctor.profile.created",
            resource_type="doctor",
            resource_id=doctor_id,
            resource_version=1,
            details={"active": True, "specialty_count": len(body.specialty_ids)},
        )
        await append_outbox(
            session,
            request,
            event_type="doctor.profile.updated.v1",
            aggregate_type="doctor",
            aggregate_id=doctor_id,
            aggregate_version=1,
            payload={
                "doctor_id": doctor_id,
                "staff_user_id": body.staff_user_id,
                "profile_version": 1,
                "active": True,
            },
        )
        return 201, result, etag(1)

    return await execute_idempotent(
        session,
        request,
        principal,
        route_key=request.url.path,
        key=key,
        body=request_body,
        if_match=None,
        operation=operation,
    )


@doctor_router.patch("/{doctor_id}", response_model=DoctorProfile)
async def patch_doctor(
    doctor_id: str,
    body: DoctorPatch,
    request: Request,
    if_match_header: str | None = Header(default=None, alias="If-Match"),
    principal: Principal = Depends(
        require_current_roles("hospital_admin", "doctor")
    ),
    session: AsyncSession = Depends(get_database_session),
) -> JSONResponse:
    validate_query_keys(request, set())
    doctor_id = parse_id(doctor_id)
    expected_version = parse_if_match(if_match_header)
    patch_fields = body.model_fields_set
    if principal.authorized_role == "doctor" and patch_fields - {"display_name"}:
        raise ApiError(403, "forbidden")
    row = await get_doctor(session, doctor_id)
    if row is None:
        raise ApiError(404, "not_found")
    if (
        principal.authorized_role == "doctor"
        and str(row["staff_user_id"]) != principal.user_id
    ):
        raise ApiError(404, "not_found")
    if row["version"] != expected_version:
        raise ApiError(412, "version_conflict")

    requested_active = body.active if "active" in patch_fields else None
    active_change = requested_active is not None and requested_active != row["active"]
    if active_change and requested_active is False:
        latest = (
            await session.execute(
                text(
                    "SELECT id,status FROM schedule_versions "
                    "WHERE doctor_id=:doctor_id ORDER BY revision DESC LIMIT 1"
                ),
                {"doctor_id": int(doctor_id)},
            )
        ).mappings().first()
        interval_count = 0
        if latest is not None:
            interval_count = await session.scalar(
                text(
                    "SELECT count(*) FROM schedule_intervals "
                    "WHERE schedule_version_id=:proposal_id"
                ),
                {"proposal_id": latest["id"]},
            )
        if latest is None or latest["status"] != "accepted" or interval_count:
            raise ApiError(409, "schedule_not_closed")
        await session.commit()
        operational = await _operational_status(request, principal, doctor_id)
        if operational.bookable_slot_count or operational.confirmed_booking_count:
            raise ApiError(409, "schedule_not_closed")
    elif active_change and requested_active is True:
        await session.commit()
        staff = await _staff_status(request, principal, str(row["staff_user_id"]))
        if not staff.active or "doctor" not in staff.roles:
            raise ApiError(422, "invalid_reference")
    else:
        await session.commit()

    async with session.begin():
        current = await get_doctor(session, doctor_id, for_update=True)
        if current is None:
            raise ApiError(404, "not_found")
        if (
            principal.authorized_role == "doctor"
            and str(current["staff_user_id"]) != principal.user_id
        ):
            raise ApiError(404, "not_found")
        if current["version"] != expected_version:
            raise ApiError(412, "version_conflict")

        specialty_ids = body.specialty_ids if "specialty_ids" in patch_fields else None
        if specialty_ids is not None:
            await _validate_specialties(session, specialty_ids)
            existing = (
                await session.execute(
                    text(
                        "SELECT specialty_id FROM doctor_specialties "
                        "WHERE doctor_id=:doctor_id ORDER BY specialty_id"
                    ),
                    {"doctor_id": int(doctor_id)},
                )
            ).scalars().all()
            if sorted((str(value) for value in existing), key=int) != sorted(
                specialty_ids, key=int
            ):
                await _replace_specialties(session, doctor_id, specialty_ids)
                changed = True
            else:
                changed = False
        else:
            changed = False

        updates: dict[str, Any] = {}
        if "display_name" in patch_fields and body.display_name != current["display_name"]:
            updates["display_name"] = body.display_name
        if active_change:
            updates["active"] = requested_active
        if updates or changed:
            assignments = [f"{column}=:{column}" for column in updates]
            params = {**updates, "doctor_id": int(doctor_id)}
            assignments.extend(
                [
                    "version=version+1",
                    "updated_at=CURRENT_TIMESTAMP",
                ]
            )
            if updates or changed:
                assignments.append("profile_version=profile_version+1")
            await session.execute(
                text(
                    "UPDATE doctors SET " + ",".join(assignments) + " "
                    "WHERE id=:doctor_id"
                ),
                params,
            )
            current = await get_doctor(session, doctor_id)
            assert current is not None
            result = doctor_profile(current)
            active_now = current["active"]
            await append_audit(
                session,
                request,
                actor_user_id=principal.user_id,
                action=(
                    "doctor.profile.deactivated"
                    if "active" in updates and not active_now
                    else "doctor.profile.reactivated"
                    if "active" in updates and active_now
                    else "doctor.profile.updated"
                ),
                resource_type="doctor",
                resource_id=doctor_id,
                resource_version=current["version"],
                details={
                    "active": active_now,
                    "specialty_count": len(current["specialties"]),
                },
            )
            await append_outbox(
                session,
                request,
                event_type="doctor.profile.updated.v1",
                aggregate_type="doctor",
                aggregate_id=doctor_id,
                aggregate_version=current["version"],
                payload={
                    "doctor_id": doctor_id,
                    "staff_user_id": str(current["staff_user_id"]),
                    "profile_version": current["profile_version"],
                    "active": active_now,
                },
            )
        else:
            result = doctor_profile(current)
        version = result["version"]
    return _json(DoctorProfile, result, headers={"ETag": etag(version)})


@doctor_router.post(
    "/{doctor_id}/schedules", status_code=202, response_model=ScheduleProposal
)
async def propose_schedule(
    doctor_id: str,
    body: ScheduleInput,
    request: Request,
    if_match_header: str | None = Header(default=None, alias="If-Match"),
    principal: Principal = Depends(
        require_current_roles("hospital_admin", "doctor")
    ),
    session: AsyncSession = Depends(get_database_session),
    key_header: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    validate_query_keys(request, set())
    doctor_id = parse_id(doctor_id)
    expected_version = parse_if_match(if_match_header)
    key = idempotency_key(key_header)
    row = await _authorized_doctor(session, doctor_id, principal)
    request_body = _body(body)
    replay = await _preflight_replay(
        session,
        principal,
        route_key=request.url.path,
        key=key,
        body=request_body,
        if_match=if_match_header,
    )
    if replay is not None:
        return replay
    validate_schedule(body)
    async def operation():
        doctor = await get_doctor(session, doctor_id, for_update=True)
        if doctor is None:
            raise ApiError(404, "not_found")
        if (
            principal.authorized_role == "doctor"
            and str(doctor["staff_user_id"]) != principal.user_id
        ):
            raise ApiError(404, "not_found")
        if doctor["version"] != expected_version:
            raise ApiError(412, "version_conflict")
        if not doctor["active"]:
            raise ApiError(409, "conflict")
        latest = (
            await session.execute(
                text(
                    "SELECT revision,status FROM schedule_versions "
                    "WHERE doctor_id=:doctor_id ORDER BY revision DESC LIMIT 1"
                ),
                {"doctor_id": int(doctor_id)},
            )
        ).mappings().first()
        latest_revision = latest["revision"] if latest is not None else 0
        if latest is not None and latest["status"] == "pending":
            raise ApiError(409, "proposal_pending")
        if body.expected_revision != latest_revision:
            raise ApiError(409, "revision_conflict")
        revision = latest_revision + 1
        proposal_id = str(new_id())
        intervals = [
            {
                "starts_at": item.starts_at.astimezone(timezone.utc),
                "ends_at": item.ends_at.astimezone(timezone.utc),
            }
            for item in body.intervals
        ]
        effective_from = intervals[0]["starts_at"] if intervals else datetime.now(timezone.utc)
        await session.execute(
            text(
                """INSERT INTO schedule_versions
                     (id,doctor_id,revision,timezone,slot_minutes,effective_from,status,version)
                   VALUES (:id,:doctor_id,:revision,:timezone,:slot_minutes,
                           :effective_from,'pending',1)"""
            ),
            {
                "id": int(proposal_id),
                "doctor_id": int(doctor_id),
                "revision": revision,
                "timezone": body.timezone,
                "slot_minutes": body.slot_minutes,
                "effective_from": effective_from,
            },
        )
        for interval in intervals:
            await session.execute(
                text(
                    """INSERT INTO schedule_intervals
                         (id,schedule_version_id,starts_at,ends_at)
                       VALUES (:id,:schedule_version_id,:starts_at,:ends_at)"""
                ),
                {
                    "id": new_id(),
                    "schedule_version_id": int(proposal_id),
                    **interval,
                },
            )
        await session.execute(
            text(
                "UPDATE doctors SET version=version+1,updated_at=CURRENT_TIMESTAMP "
                "WHERE id=:doctor_id"
            ),
            {"doctor_id": int(doctor_id)},
        )
        proposals = await list_schedules(
            session,
            doctor_id=doctor_id,
            cursor=None,
            limit=1,
            proposal_id=proposal_id,
        )
        proposal = proposals[0]
        await append_audit(
            session,
            request,
            actor_user_id=principal.user_id,
            action="doctor.schedule.proposed",
            resource_type="schedule_proposal",
            resource_id=proposal_id,
            resource_version=proposal["version"],
            details={"revision": revision},
        )
        await append_outbox(
            session,
            request,
            event_type="doctor.schedule.proposed.v1",
            aggregate_type="doctor_schedule",
            aggregate_id=doctor_id,
            aggregate_version=revision,
            payload={
                "proposal_id": proposal_id,
                "doctor_id": doctor_id,
                "revision": revision,
                "previous_revision": latest_revision,
                "timezone": body.timezone,
                "slot_minutes": body.slot_minutes,
                "intervals": [
                    {
                        "starts_at": item["starts_at"].isoformat().replace("+00:00", "Z"),
                        "ends_at": item["ends_at"].isoformat().replace("+00:00", "Z"),
                    }
                    for item in intervals
                ],
            },
        )
        output = ScheduleProposal.model_validate(proposal_view(proposal)).model_dump(
            mode="json"
        )
        return 202, output, etag(proposal["version"])

    return await execute_idempotent(
        session,
        request,
        principal,
        route_key=request.url.path,
        key=key,
        body=request_body,
        if_match=if_match_header,
        operation=operation,
        no_store=True,
    )


@doctor_router.get(
    "/{doctor_id}/schedules", response_model=Page[ScheduleProposal]
)
async def get_schedules(
    doctor_id: str,
    request: Request,
    principal: Principal = Depends(
        require_current_roles("hospital_admin", "receptionist", "doctor")
    ),
    session: AsyncSession = Depends(get_database_session),
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> JSONResponse:
    validate_query_keys(request, {"cursor", "limit"})
    doctor_id = parse_id(doctor_id)
    limit_value(limit)
    doctor = await _authorized_doctor(session, doctor_id, principal)
    digest = filter_digest(
        {
            "resource": "doctor_schedules",
            "doctor_id": doctor_id,
            "role": principal.authorized_role,
            "user_id": principal.user_id,
        }
    )
    position = decode_cursor(cursor, digest)
    rows = await list_schedules(
        session, doctor_id=doctor_id, cursor=position, limit=limit + 1
    )
    await append_audit(
        session,
        request,
        actor_user_id=principal.user_id,
        action="doctor.schedule.read",
        resource_type="doctor",
        resource_id=doctor_id,
        resource_version=doctor["version"],
        details={"role": principal.authorized_role},
    )
    await session.commit()
    page = {
        "items": [
            ScheduleProposal.model_validate(proposal_view(row)).model_dump(mode="json")
            for row in rows[:limit]
        ],
        "next_cursor": _page_cursor(rows, limit, digest),
    }
    return JSONResponse(
        content=Page[ScheduleProposal].model_validate(page).model_dump(mode="json"),
        headers={"Cache-Control": "no-store"},
    )


@doctor_router.get(
    "/{doctor_id}/schedules/{proposal_id}", response_model=ScheduleProposal
)
async def get_schedule(
    doctor_id: str,
    proposal_id: str,
    request: Request,
    principal: Principal = Depends(
        require_current_roles("hospital_admin", "receptionist", "doctor")
    ),
    session: AsyncSession = Depends(get_database_session),
) -> JSONResponse:
    validate_query_keys(request, set())
    doctor_id = parse_id(doctor_id)
    proposal_id = parse_id(proposal_id)
    doctor = await _authorized_doctor(session, doctor_id, principal)
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
        action="doctor.schedule.read",
        resource_type="schedule_proposal",
        resource_id=proposal_id,
        resource_version=proposal["version"],
        details={"role": principal.authorized_role},
    )
    await session.commit()
    return _json(
        ScheduleProposal,
        proposal_view(proposal),
        headers={
            "ETag": etag(proposal["version"]),
            "Cache-Control": "no-store",
        },
    )


@doctor_router.post(
    "/{doctor_id}/schedules/{proposal_id}/reconcile",
    response_model=ScheduleProposal,
)
async def reconcile_schedule(
    doctor_id: str,
    proposal_id: str,
    body: EmptyCommand,
    request: Request,
    if_match_header: str | None = Header(default=None, alias="If-Match"),
    principal: Principal = Depends(
        require_current_roles("hospital_admin", "doctor")
    ),
    session: AsyncSession = Depends(get_database_session),
    key_header: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    del body
    validate_query_keys(request, set())
    doctor_id = parse_id(doctor_id)
    proposal_id = parse_id(proposal_id)
    expected_version = parse_if_match(if_match_header)
    key = idempotency_key(key_header)
    doctor = await _authorized_doctor(session, doctor_id, principal)
    initial = await list_schedules(
        session,
        doctor_id=doctor_id,
        cursor=None,
        limit=1,
        proposal_id=proposal_id,
    )
    if not initial:
        raise ApiError(404, "not_found")
    body = {}
    replay = await _preflight_replay(
        session,
        principal,
        route_key=request.url.path,
        key=key,
        body=body,
        if_match=if_match_header,
    )
    if replay is not None:
        return replay
    if initial[0]["version"] != expected_version:
        raise ApiError(412, "version_conflict")
    await session.commit()
    try:
        decision = await _schedule_decision(request, principal, proposal_id)
    except ApiError as error:
        if error.status_code != 409 or error.code != "decision_pending":
            raise

        async def pending_operation():
            raise error

        return await execute_idempotent(
            session,
            request,
            principal,
            route_key=request.url.path,
            key=key,
            body=body,
            if_match=if_match_header,
            operation=pending_operation,
            no_store=True,
        )
    if (
        decision.proposal_id != proposal_id
        or decision.doctor_id != doctor_id
        or decision.revision != initial[0]["revision"]
    ):
        raise ApiError(503, "dependency_unavailable")

    async def operation():
        current_doctor = await get_doctor(session, doctor_id, for_update=True)
        if current_doctor is None:
            raise ApiError(404, "not_found")
        if (
            principal.authorized_role == "doctor"
            and str(current_doctor["staff_user_id"]) != principal.user_id
        ):
            raise ApiError(404, "not_found")
        current = await list_schedules(
            session,
            doctor_id=doctor_id,
            cursor=None,
            limit=1,
            proposal_id=proposal_id,
            for_update=True,
        )
        if not current:
            raise ApiError(404, "not_found")
        proposal = current[0]
        if proposal["version"] != expected_version:
            raise ApiError(412, "version_conflict")
        ack = (
            await session.execute(
                text(
                    "SELECT accepted,operational_version,reason,conflicts "
                    "FROM schedule_acknowledgements "
                    "WHERE schedule_version_id=:proposal_id"
                ),
                {"proposal_id": int(proposal_id)},
            )
        ).mappings().first()
        if ack is not None:
            same = (
                ack["accepted"] == (decision.state == "accepted")
                and ack["operational_version"] == decision.version
                and (ack["reason"] or None) == decision.reason_code
                and [str(value) for value in ack["conflicts"]]
                == decision.conflicting_appointment_ids
            )
            if not same:
                raise ApiError(409, "conflict")
            output = ScheduleProposal.model_validate(proposal_view(proposal)).model_dump(
                mode="json"
            )
            return 200, output, etag(proposal["version"])
        if proposal["status"] != "pending":
            raise ApiError(409, "conflict")
        new_version = proposal["version"] + 1
        await session.execute(
            text(
                "UPDATE schedule_versions SET status=:status,version=:version,"
                "updated_at=CURRENT_TIMESTAMP WHERE id=:proposal_id"
            ),
            {
                "status": decision.state,
                "version": new_version,
                "proposal_id": int(proposal_id),
            },
        )
        await session.execute(
            text(
                """INSERT INTO schedule_acknowledgements
                     (id,schedule_version_id,accepted,operational_version,reason,conflicts)
                   VALUES (:id,:proposal_id,:accepted,:operational_version,:reason,
                           CAST(:conflicts AS jsonb))"""
            ),
            {
                "id": new_id(),
                "proposal_id": int(proposal_id),
                "accepted": decision.state == "accepted",
                "operational_version": decision.version,
                "reason": decision.reason_code,
                "conflicts": json.dumps(decision.conflicting_appointment_ids),
            },
        )
        proposals = await list_schedules(
            session,
            doctor_id=doctor_id,
            cursor=None,
            limit=1,
            proposal_id=proposal_id,
        )
        proposal = proposals[0]
        await append_audit(
            session,
            request,
            actor_user_id=principal.user_id,
            action="doctor.schedule.reconciled",
            resource_type="schedule_proposal",
            resource_id=proposal_id,
            resource_version=proposal["version"],
            details={
                "decision": decision.state,
                "conflict_count": len(decision.conflicting_appointment_ids),
            },
        )
        await append_outbox(
            session,
            request,
            event_type="doctor.schedule.reconciled.v1",
            aggregate_type="schedule_proposal",
            aggregate_id=proposal_id,
            aggregate_version=proposal["version"],
            payload={
                "resource_id": proposal_id,
                "version": proposal["version"],
                "state": proposal["status"],
            },
        )
        output = ScheduleProposal.model_validate(proposal_view(proposal)).model_dump(
            mode="json"
        )
        return 200, output, etag(proposal["version"])

    return await execute_idempotent(
        session,
        request,
        principal,
        route_key=request.url.path,
        key=key,
        body=body,
        if_match=if_match_header,
        operation=operation,
        no_store=True,
    )
