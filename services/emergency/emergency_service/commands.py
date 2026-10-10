"""Transactional emergency request commands and scoped read models."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import and_, delete, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .errors import error_payload
from .exceptions import DomainHTTPException
from .models import (
    emergency_requests,
    emergency_status_history,
    idempotency_requests,
    outbox_events,
)
from .schemas import EmergencyRequestCreate, PriorityUpdate, TransitionCommand

CLAIM_LEASE = timedelta(minutes=15)
IDEMPOTENCY_RETENTION = timedelta(hours=24)
MAX_SAFE_VERSION = 9_007_199_254_740_991
_ETAG = re.compile(r'^"([1-9][0-9]{0,15})"$')
_CURSOR = re.compile(r"^[A-Za-z0-9_-]{1,512}$")
_IDEMPOTENCY_KEY = re.compile(r"^[!-~]{16,128}$")


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    status_code: int
    body: dict[str, Any]
    etag: str | None = None


def idempotency_key_valid(key: str) -> bool:
    return bool(_IDEMPOTENCY_KEY.fullmatch(key))


def command_response(outcome: CommandOutcome) -> JSONResponse:
    headers = {"Cache-Control": "no-store"}
    if outcome.etag:
        headers["ETag"] = outcome.etag
    return JSONResponse(
        status_code=outcome.status_code,
        content=outcome.body,
        headers=headers,
    )


def _wire_time(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


async def _database_now(session: AsyncSession) -> datetime:
    value = await session.scalar(text("SELECT clock_timestamp()"))
    return value.astimezone(timezone.utc)


async def _new_id(session: AsyncSession, worker_id: int) -> int:
    """Allocate a positive CSPRNG BIGINT; local PKs remain the final backstop.

    Keep the internal worker argument compatible with agent command call sites;
    it does not allocate a worker or read/update id_worker_state in Phase 2.
    """
    for _ in range(3):
        candidate = secrets.randbelow(2**63 - 1) + 1
        collision = await session.scalar(
            text("""SELECT EXISTS (
              SELECT id FROM emergency_requests WHERE id=:candidate
              UNION ALL SELECT id FROM emergency_status_history WHERE id=:candidate
              UNION ALL SELECT event_id FROM outbox_events WHERE event_id=:candidate
              UNION ALL SELECT entry_id FROM audit_entries WHERE entry_id=:candidate
            )"""),
            {"candidate": candidate},
        )
        if not collision:
            return candidate
    raise DomainHTTPException(
        503, "dependency_unavailable", "Request processing is temporarily unavailable."
    )


def _safe_reason_digest(reason: str | None) -> str | None:
    if reason is None:
        return None
    return hashlib.sha256(reason.encode("utf-8")).hexdigest()


async def _append_audit(
    session: AsyncSession,
    request: Request,
    worker_id: int,
    *,
    actor_user_id: str | None,
    action: str,
    resource_id: str | None,
    result: str = "success",
    reason: str | None = None,
    filter_hash: str | None = None,
) -> None:
    entry_id = await _new_id(session, worker_id)
    metadata: dict[str, Any] = {
        "action": action,
        "actor_user_id": actor_user_id,
        "actor_service": "emergency",
        "occurred_at": _wire_time(await _database_now(session)),
        "request_id": str(request.state.request_id),
        "correlation_id": str(request.state.correlation_id),
        "result": result,
    }
    if resource_id is not None:
        metadata["resource_id"] = resource_id
    if reason is not None:
        metadata["reason_sha256"] = _safe_reason_digest(reason)
    if filter_hash is not None:
        metadata["filter_hash"] = filter_hash
    canonical_metadata = json.dumps(
        metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    await session.execute(
        text(
            "SELECT audit_sequence FROM append_emergency_audit "
            "(:entry_id, CAST(:canonical_metadata AS jsonb))"
        ),
        {"entry_id": entry_id, "canonical_metadata": canonical_metadata},
    )


def _request_event_payload(row: Any) -> dict[str, Any]:
    return {
        "request_id": str(row["id"]),
        "state": row["state"],
        "assigned_priority": row["assigned_priority"],
        "claimed_by_user_id": (
            str(row["claimed_by_user_id"])
            if row["claimed_by_user_id"] is not None
            else None
        ),
        "version": int(row["version"]),
    }


async def _append_outbox(
    session: AsyncSession,
    request: Request,
    worker_id: int,
    *,
    row: Any,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    event_id = await _new_id(session, worker_id)
    occurred_at = _wire_time(await _database_now(session))
    envelope = {
        "event_id": str(event_id),
        "event_type": event_type,
        "schema_version": 1,
        "producer": "emergency",
        "occurred_at": occurred_at,
        "aggregate_type": "emergency_request",
        "aggregate_id": str(row["id"]),
        "aggregate_version": int(row["version"]),
        "correlation_id": str(request.state.correlation_id),
        "request_id": str(request.state.request_id),
        "causation_id": None,
        "traceparent": getattr(request.state, "traceparent", None),
        "payload": payload,
    }
    await session.execute(
        pg_insert(outbox_events).values(
            event_id=event_id,
            aggregate_type="emergency_request",
            aggregate_id=row["id"],
            aggregate_version=row["version"],
            event_type=event_type,
            envelope=envelope,
            next_attempt_at=await _database_now(session),
        )
    )


async def _append_history(
    session: AsyncSession,
    worker_id: int,
    *,
    request_id: int,
    previous_state: str | None,
    new_state: str,
    priority: int | None,
    actor_user_id: str | None,
    reason: str,
    occurred_at: datetime | None = None,
) -> None:
    await session.execute(
        pg_insert(emergency_status_history).values(
            id=await _new_id(session, worker_id),
            request_id=request_id,
            previous_state=previous_state,
            new_state=new_state,
            priority=priority,
            actor_user_id=int(actor_user_id) if actor_user_id is not None else None,
            reason=reason,
            occurred_at=occurred_at or await _database_now(session),
        )
    )


def _request_view(row: Any, *, staff: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": str(row["id"]),
        "state": row["state"],
        "reported_urgency": row["reported_urgency"],
        "assigned_priority": row["assigned_priority"],
        "created_at": _wire_time(row["created_at"]),
        "updated_at": _wire_time(row["updated_at"]),
        "version": int(row["version"]),
    }
    if staff:
        result.update(
            {
                "patient_id": str(row["patient_id"]),
                "description": row["description"],
                "synthetic_contact": row["synthetic_contact"],
                "claimed_by_user_id": (
                    str(row["claimed_by_user_id"])
                    if row["claimed_by_user_id"] is not None
                    else None
                ),
                "claim_expires_at": _wire_time(row["claim_expires_at"]),
            }
        )
    return result


def _history_view(row: Any, *, staff: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": str(row["id"]),
        "previous_state": row["previous_state"],
        "new_state": row["new_state"],
        "priority": row["priority"],
        "occurred_at": _wire_time(row["occurred_at"]),
    }
    if staff:
        result["actor_user_id"] = (
            str(row["actor_user_id"]) if row["actor_user_id"] is not None else None
        )
        result["reason"] = row["reason"]
    return result


def _etag(version: int) -> str:
    return f'"{version}"'


def _check_if_match(value: str | None, current_version: int) -> None:
    if value is None:
        raise DomainHTTPException(
            428, "precondition_required", "If-Match is required for this change."
        )
    match = _ETAG.fullmatch(value)
    if match is None or int(match.group(1)) > MAX_SAFE_VERSION:
        raise DomainHTTPException(400, "bad_request", "If-Match must be a quoted version.")
    if int(match.group(1)) != int(current_version):
        raise DomainHTTPException(
            412, "version_conflict", "The emergency request has changed."
        )


def _conflict(request: Request, code: str, message: str) -> CommandOutcome:
    return CommandOutcome(409, error_payload(request, 409, code, message))


async def run_idempotent_post(
    session: AsyncSession,
    request: Request,
    *,
    principal_user_id: str,
    route_key: str,
    idempotency_key: str,
    body: dict[str, Any],
    if_match: str | None,
    operation: Callable[[], Awaitable[CommandOutcome]],
) -> CommandOutcome:
    """Serialize same-key POSTs and persist their exact result atomically."""
    if not idempotency_key_valid(idempotency_key):
        raise DomainHTTPException(
            400,
            "bad_request",
            "Idempotency-Key must contain 16 to 128 printable ASCII characters.",
        )
    request_fingerprint = hashlib.sha256(
        json.dumps(
            {
                "method": "POST",
                "route": route_key,
                "body": body,
                "if_match": if_match,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()
    principal_scope = "user:" + principal_user_id
    route_template = route_key
    key_values = {
        "principal_scope": principal_scope,
        "method": "POST",
        "route_template": route_template,
        "key": idempotency_key,
    }
    outcome: CommandOutcome
    async with session.begin():
        now = await _database_now(session)
        await session.execute(
            delete(idempotency_requests).where(
                idempotency_requests.c.principal_scope == principal_scope,
                idempotency_requests.c.method == "POST",
                idempotency_requests.c.route_template == route_template,
                idempotency_requests.c.key == idempotency_key,
                idempotency_requests.c.expires_at <= now,
            )
        )
        inserted = await session.execute(
            pg_insert(idempotency_requests)
            .values(
                **key_values,
                request_hash=request_fingerprint,
                response_code=200,
                response={},
                expires_at=now + IDEMPOTENCY_RETENTION,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    idempotency_requests.c.principal_scope,
                    idempotency_requests.c.method,
                    idempotency_requests.c.route_template,
                    idempotency_requests.c.key,
                ]
            )
            .returning(idempotency_requests.c.key)
        )
        inserted_new = inserted.scalar_one_or_none() is not None
        record = (
            await session.execute(
                select(idempotency_requests)
                .where(
                    idempotency_requests.c.principal_scope == principal_scope,
                    idempotency_requests.c.method == "POST",
                    idempotency_requests.c.route_template == route_template,
                    idempotency_requests.c.key == idempotency_key,
                )
                .with_for_update()
            )
        ).mappings().one()
        if record["request_hash"] != request_fingerprint:
            outcome = _conflict(
                request,
                "idempotency_key_reused",
                "Idempotency-Key was already used for a different command.",
            )
        elif not inserted_new:
            stored_body = record["response"]
            version = stored_body.get("version") if isinstance(stored_body, dict) else None
            outcome = CommandOutcome(
                int(record["response_code"]),
                stored_body,
                _etag(version) if type(version) is int else None,
            )
        else:
            outcome = await operation()
            await session.execute(
                update(idempotency_requests)
                .where(
                    idempotency_requests.c.principal_scope == principal_scope,
                    idempotency_requests.c.method == "POST",
                    idempotency_requests.c.route_template == route_template,
                    idempotency_requests.c.key == idempotency_key,
                )
                .values(
                    response_code=outcome.status_code,
                    response=outcome.body,
                )
            )
    return outcome


async def _locked_request(session: AsyncSession, request_id: str) -> Any | None:
    return (
        await session.execute(
            select(emergency_requests)
            .where(emergency_requests.c.id == int(request_id))
            .with_for_update()
        )
    ).mappings().one_or_none()


async def _status_event(
    session: AsyncSession,
    request: Request,
    worker_id: int,
    row: Any,
) -> None:
    await _append_outbox(
        session,
        request,
        worker_id,
        row=row,
        event_type="emergency.request.status.changed.v1",
        payload=_request_event_payload(row),
    )


async def _apply_state(
    session: AsyncSession,
    request: Request,
    worker_id: int,
    row: Any,
    *,
    new_state: str,
    actor_user_id: str | None,
    reason: str,
    claim_owner: str | None,
    claim_expires_at: datetime | None,
) -> Any:
    if int(row["version"]) >= MAX_SAFE_VERSION:
        raise DomainHTTPException(
            409, "conflict", "The emergency request version cannot be advanced."
        )
    occurred_at = await _database_now(session)
    updated = (
        await session.execute(
            update(emergency_requests)
            .where(
                emergency_requests.c.id == row["id"],
                emergency_requests.c.version == row["version"],
            )
            .values(
                state=new_state,
                claimed_by_user_id=int(claim_owner) if claim_owner is not None else None,
                claim_expires_at=claim_expires_at,
                version=int(row["version"]) + 1,
                updated_at=occurred_at,
            )
            .returning(emergency_requests)
        )
    ).mappings().one_or_none()
    if updated is None:
        raise DomainHTTPException(412, "version_conflict", "The emergency request has changed.")
    await _append_history(
        session,
        worker_id,
        request_id=updated["id"],
        previous_state=row["state"],
        new_state=new_state,
        priority=updated["assigned_priority"],
        actor_user_id=actor_user_id,
        reason=reason,
        occurred_at=occurred_at,
    )
    await _status_event(session, request, worker_id, updated)
    await _append_audit(
        session,
        request,
        worker_id,
        actor_user_id=actor_user_id,
        action="request.status.changed",
        resource_id=str(updated["id"]),
        reason=reason,
    )
    return updated


async def _apply_priority(
    session: AsyncSession,
    request: Request,
    worker_id: int,
    row: Any,
    *,
    priority: int,
    actor_user_id: str,
    reason: str,
    new_state: str,
) -> Any:
    if int(row["version"]) >= MAX_SAFE_VERSION:
        raise DomainHTTPException(
            409, "conflict", "The emergency request version cannot be advanced."
        )
    occurred_at = await _database_now(session)
    updated = (
        await session.execute(
            update(emergency_requests)
            .where(
                emergency_requests.c.id == row["id"],
                emergency_requests.c.version == row["version"],
            )
            .values(
                assigned_priority=priority,
                state=new_state,
                version=int(row["version"]) + 1,
                updated_at=occurred_at,
            )
            .returning(emergency_requests)
        )
    ).mappings().one_or_none()
    if updated is None:
        raise DomainHTTPException(412, "version_conflict", "The emergency request has changed.")
    await _append_history(
        session,
        worker_id,
        request_id=updated["id"],
        previous_state=row["state"],
        new_state=new_state,
        priority=priority,
        actor_user_id=actor_user_id,
        reason=reason,
        occurred_at=occurred_at,
    )
    await _status_event(session, request, worker_id, updated)
    await _append_audit(
        session,
        request,
        worker_id,
        actor_user_id=actor_user_id,
        action="request.priority.assigned",
        resource_id=str(updated["id"]),
        reason=reason,
    )
    return updated


def _command_outcome(
    status_code: int, request: Request, row: Any, *, staff: bool
) -> CommandOutcome:
    body = _request_view(row, staff=staff)
    return CommandOutcome(status_code, body, _etag(int(row["version"])))


def _error_outcome(
    request: Request,
    status_code: int,
    code: str,
    message: str,
) -> CommandOutcome:
    return CommandOutcome(
        status_code,
        error_payload(request, status_code, code, message),
    )


def _precondition_outcome(
    request: Request, if_match: str | None, current_version: int
) -> CommandOutcome | None:
    try:
        _check_if_match(if_match, current_version)
    except DomainHTTPException as error:
        return CommandOutcome(
            error.status_code,
            error_payload(
                request,
                error.status_code,
                error.code,
                error.message,
                error.details,
            ),
        )
    return None


async def create_request(
    session: AsyncSession,
    request: Request,
    body: EmergencyRequestCreate,
    *,
    principal_user_id: str,
    worker_id: int,
) -> CommandOutcome:
    async def operation() -> CommandOutcome:
        occurred_at = await _database_now(session)
        request_id = await _new_id(session, worker_id)
        row = (
            await session.execute(
                pg_insert(emergency_requests)
                .values(
                    id=request_id,
                    patient_id=int(body.patient_id),
                    synthetic_contact=body.synthetic_contact,
                    description=body.description,
                    reported_urgency=body.reported_urgency,
                    assigned_priority=None,
                    state="submitted",
                    claimed_by_user_id=None,
                    claim_expires_at=None,
                    tracking_token_hash=None,
                    tracking_expires_at=None,
                    version=1,
                    created_at=occurred_at,
                    updated_at=occurred_at,
                )
                .returning(emergency_requests)
            )
        ).mappings().one()
        await _append_history(
            session,
            worker_id,
            request_id=request_id,
            previous_state=None,
            new_state="submitted",
            priority=None,
            actor_user_id=principal_user_id,
            reason="Request submitted",
            occurred_at=occurred_at,
        )
        await _append_outbox(
            session,
            request,
            worker_id,
            row=row,
            event_type="emergency.request.submitted.v1",
            payload={
                "request_id": str(request_id),
                "patient_id": body.patient_id,
                "state": "submitted",
                "reported_urgency": body.reported_urgency,
            },
        )
        await _append_audit(
            session,
            request,
            worker_id,
            actor_user_id=principal_user_id,
            action="request.submitted",
            resource_id=str(request_id),
        )
        return _command_outcome(201, request, row, staff=False)

    return await run_idempotent_post(
        session,
        request,
        principal_user_id=principal_user_id,
        route_key="/api/v1/emergencies",
        idempotency_key=request.headers.get("Idempotency-Key", ""),
        body=body.model_dump(mode="json"),
        if_match=None,
        operation=operation,
    )


async def update_priority(
    session: AsyncSession,
    request: Request,
    request_id: str,
    body: PriorityUpdate,
    *,
    principal_user_id: str,
    worker_id: int,
    if_match: str | None,
) -> CommandOutcome:
    async with session.begin():
        row = await _locked_request(session, request_id)
        if row is None:
            raise DomainHTTPException(404, "not_found", "Emergency request was not found.")
        precondition = _precondition_outcome(request, if_match, int(row["version"]))
        if precondition is not None:
            return precondition
        if row["state"] in {"resolved", "cancelled"}:
            raise DomainHTTPException(
                409, "invalid_transition", "Priority cannot change after the request is closed."
            )
        next_state = "triaged" if row["state"] == "submitted" else row["state"]
        row = await _apply_priority(
            session,
            request,
            worker_id,
            row,
            priority=body.assigned_priority,
            actor_user_id=principal_user_id,
            reason=body.reason,
            new_state=next_state,
        )
    return _command_outcome(200, request, row, staff=True)


async def claim_request(
    session: AsyncSession,
    request: Request,
    request_id: str,
    *,
    principal_user_id: str,
    worker_id: int,
    if_match: str | None,
    idempotency_key: str,
) -> CommandOutcome:
    async def operation() -> CommandOutcome:
        row = await _locked_request(session, request_id)
        if row is None:
            return _error_outcome(request, 404, "not_found", "Emergency request was not found.")
        precondition = _precondition_outcome(request, if_match, int(row["version"]))
        if precondition is not None:
            return precondition
        now = await _database_now(session)
        if (
            row["state"] == "claimed"
            and row["claim_expires_at"] is not None
            and row["claim_expires_at"] <= now
        ):
            row = await _apply_state(
                session,
                request,
                worker_id,
                row,
                new_state="triaged",
                actor_user_id=None,
                reason="Claim lease expired",
                claim_owner=None,
                claim_expires_at=None,
            )
        if row["state"] == "claimed":
            return _conflict(
                request,
                "already_claimed",
                "Emergency request is already claimed.",
            )
        if row["state"] != "triaged":
            return _conflict(
                request, "invalid_transition", "Only triaged requests can be claimed."
            )
        expires_at = await _database_now(session) + CLAIM_LEASE
        row = await _apply_state(
            session,
            request,
            worker_id,
            row,
            new_state="claimed",
            actor_user_id=principal_user_id,
            reason="Request claimed",
            claim_owner=principal_user_id,
            claim_expires_at=expires_at,
        )
        return _command_outcome(200, request, row, staff=True)

    return await run_idempotent_post(
        session,
        request,
        principal_user_id=principal_user_id,
        route_key=f"/api/v1/emergencies/{request_id}/claim",
        idempotency_key=idempotency_key,
        body={},
        if_match=if_match,
        operation=operation,
    )


async def release_request(
    session: AsyncSession,
    request: Request,
    request_id: str,
    reason: str,
    *,
    principal_user_id: str,
    worker_id: int,
    if_match: str | None,
    idempotency_key: str,
) -> CommandOutcome:
    async def operation() -> CommandOutcome:
        row = await _locked_request(session, request_id)
        if row is None:
            return _error_outcome(request, 404, "not_found", "Emergency request was not found.")
        precondition = _precondition_outcome(request, if_match, int(row["version"]))
        if precondition is not None:
            return precondition
        now = await _database_now(session)
        if (
            row["state"] == "claimed"
            and row["claim_expires_at"] is not None
            and row["claim_expires_at"] <= now
        ):
            await _apply_state(
                session,
                request,
                worker_id,
                row,
                new_state="triaged",
                actor_user_id=None,
                reason="Claim lease expired",
                claim_owner=None,
                claim_expires_at=None,
            )
            return _conflict(
                request, "claim_expired", "The emergency request claim has expired."
            )
        if row["state"] != "claimed":
            return _conflict(
                request, "invalid_transition", "Only claimed requests can be released."
            )
        if str(row["claimed_by_user_id"]) != principal_user_id:
            return _error_outcome(
                request, 404, "not_found", "Emergency request was not found."
            )
        row = await _apply_state(
            session,
            request,
            worker_id,
            row,
            new_state="triaged",
            actor_user_id=principal_user_id,
            reason=reason,
            claim_owner=None,
            claim_expires_at=None,
        )
        return _command_outcome(200, request, row, staff=True)

    return await run_idempotent_post(
        session,
        request,
        principal_user_id=principal_user_id,
        route_key=f"/api/v1/emergencies/{request_id}/release",
        idempotency_key=idempotency_key,
        body={"reason": reason},
        if_match=if_match,
        operation=operation,
    )


async def transition_request(
    session: AsyncSession,
    request: Request,
    request_id: str,
    body: TransitionCommand,
    *,
    principal_user_id: str,
    patient_id: str | None,
    worker_id: int,
    staff_actor: bool,
    if_match: str | None,
    idempotency_key: str,
) -> CommandOutcome:
    async def operation() -> CommandOutcome:
        row = await _locked_request(session, request_id)
        if row is None:
            return _error_outcome(request, 404, "not_found", "Emergency request was not found.")
        precondition = _precondition_outcome(request, if_match, int(row["version"]))
        if precondition is not None:
            return precondition
        now = await _database_now(session)
        was_expired_claim = (
            row["state"] == "claimed"
            and row["claim_expires_at"] is not None
            and row["claim_expires_at"] <= now
        )
        if was_expired_claim:
            row = await _apply_state(
                session,
                request,
                worker_id,
                row,
                new_state="triaged",
                actor_user_id=None,
                reason="Claim lease expired",
                claim_owner=None,
                claim_expires_at=None,
            )
            if body.state in {"processing", "resolved"}:
                return _conflict(
                    request,
                    "claim_expired",
                    "The emergency request claim has expired.",
                )

        if body.state == "processing":
            if row["state"] != "claimed":
                return _conflict(
                    request,
                    "invalid_transition",
                    "Only the claiming staff member can start processing.",
                )
            if str(row["claimed_by_user_id"]) != principal_user_id:
                return _error_outcome(
                    request, 404, "not_found", "Emergency request was not found."
                )
            row = await _apply_state(
                session,
                request,
                worker_id,
                row,
                new_state="processing",
                actor_user_id=principal_user_id,
                reason=body.reason,
                claim_owner=principal_user_id,
                claim_expires_at=None,
            )
        elif body.state == "resolved":
            if row["state"] != "processing":
                return _conflict(
                    request,
                    "invalid_transition",
                    "Only processing requests can be resolved.",
                )
            if str(row["claimed_by_user_id"]) != principal_user_id:
                return _error_outcome(
                    request, 404, "not_found", "Emergency request was not found."
                )
            row = await _apply_state(
                session,
                request,
                worker_id,
                row,
                new_state="resolved",
                actor_user_id=principal_user_id,
                reason=body.reason,
                claim_owner=None,
                claim_expires_at=None,
            )
        elif body.state == "cancelled":
            if staff_actor:
                allowed = row["state"] in {"submitted", "triaged", "claimed"}
            else:
                if patient_id is None or str(row["patient_id"]) != patient_id:
                    return _error_outcome(
                        request, 404, "not_found", "Emergency request was not found."
                    )
                allowed = (
                    row["state"] in {"submitted", "triaged"}
                )
            if not allowed:
                return _conflict(
                    request,
                    "invalid_transition",
                    "This request cannot be cancelled in its current state.",
                )
            row = await _apply_state(
                session,
                request,
                worker_id,
                row,
                new_state="cancelled",
                actor_user_id=principal_user_id,
                reason=body.reason,
                claim_owner=None,
                claim_expires_at=None,
            )
        else:
            return _conflict(
                request, "invalid_transition", "The requested state transition is invalid."
            )
        return _command_outcome(200, request, row, staff=staff_actor)

    return await run_idempotent_post(
        session,
        request,
        principal_user_id=principal_user_id,
        route_key=f"/api/v1/emergencies/{request_id}/transitions",
        idempotency_key=idempotency_key,
        body=body.model_dump(mode="json"),
        if_match=if_match,
        operation=operation,
    )


async def list_requests(
    session: AsyncSession,
    request: Request,
    *,
    principal_user_id: str,
    patient_scope: str | None,
    staff: bool,
    patient_filter: str | None,
    state_filter: str | None,
    cursor: str | None,
    limit: int,
    worker_id: int,
) -> dict[str, Any]:
    normalized_patient = patient_filter if staff else patient_scope
    filters = {
        "principal_scope": principal_user_id,
        "staff": staff,
        "patient_id": normalized_patient,
        "state": state_filter,
    }
    filter_hash = hashlib.sha256(
        json.dumps(filters, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    cursor_created_at, cursor_id = _decode_cursor(cursor, filter_hash)
    conditions = []
    if normalized_patient is not None:
        conditions.append(emergency_requests.c.patient_id == int(normalized_patient))
    if state_filter is not None:
        conditions.append(emergency_requests.c.state == state_filter)
    if cursor_created_at is not None:
        conditions.append(
            or_(
                emergency_requests.c.created_at > cursor_created_at,
                and_(
                    emergency_requests.c.created_at == cursor_created_at,
                    emergency_requests.c.id > cursor_id,
                ),
            )
        )
    query = (
        select(emergency_requests)
        .where(*conditions)
        .order_by(emergency_requests.c.created_at.asc(), emergency_requests.c.id.asc())
        .limit(limit + 1)
    )
    async with session.begin():
        records = list((await session.execute(query)).mappings().all())
        more = len(records) > limit
        records = records[:limit]
        next_cursor = None
        if more and records:
            next_cursor = _encode_cursor(
                records[-1]["created_at"], records[-1]["id"], filter_hash
            )
        await _append_audit(
            session,
            request,
            worker_id,
            actor_user_id=principal_user_id,
            action="requests.listed",
            resource_id=None,
            filter_hash=filter_hash,
        )
    return {
        "items": [_request_view(row, staff=staff) for row in records],
        "next_cursor": next_cursor,
    }


async def get_request(
    session: AsyncSession,
    request: Request,
    request_id: str,
    *,
    principal_user_id: str,
    patient_scope: str | None,
    staff: bool,
    worker_id: int,
) -> tuple[dict[str, Any], str]:
    denied = False
    body: dict[str, Any] | None = None
    etag: str | None = None
    async with session.begin():
        row = (
            await session.execute(
                select(emergency_requests).where(
                    emergency_requests.c.id == int(request_id)
                )
            )
        ).mappings().one_or_none()
        if row is None:
            raise DomainHTTPException(404, "not_found", "Emergency request was not found.")
        if not staff and (
            patient_scope is None or str(row["patient_id"]) != patient_scope
        ):
            denied = True
            await _append_audit(
                session,
                request,
                worker_id,
                actor_user_id=principal_user_id,
                action="request.read",
                resource_id=request_id,
                result="denied",
            )
        else:
            await _append_audit(
                session,
                request,
                worker_id,
                actor_user_id=principal_user_id,
                action="request.read",
                resource_id=request_id,
            )
            body = _request_view(row, staff=staff)
            etag = _etag(int(row["version"]))
    if denied:
        raise DomainHTTPException(404, "not_found", "Emergency request was not found.")
    assert body is not None and etag is not None
    return body, etag


def _encode_cursor(created_at: datetime, resource_id: int, filter_hash: str) -> str:
    value = {
        "created_at": _wire_time(created_at),
        "id": str(resource_id),
        "filter_hash": filter_hash,
    }
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(
    cursor: str | None, expected_filter_hash: str
) -> tuple[datetime | None, int | None]:
    if cursor is None:
        return None, None
    if not _CURSOR.fullmatch(cursor):
        raise DomainHTTPException(400, "bad_request", "Cursor is malformed.")
    try:
        raw = base64.b64decode(
            cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True
        )
        value = json.loads(raw)
        if (
            not isinstance(value, dict)
            or set(value) != {"created_at", "id", "filter_hash"}
            or not isinstance(value["created_at"], str)
            or not isinstance(value["id"], str)
            or not isinstance(value["filter_hash"], str)
        ):
            raise ValueError
        if value["filter_hash"] != expected_filter_hash:
            raise DomainHTTPException(400, "bad_request", "Cursor filters do not match.")
        timestamp = datetime.fromisoformat(value["created_at"].replace("Z", "+00:00"))
        if timestamp.utcoffset() != timedelta(0):
            raise ValueError
        resource_id = int(value["id"])
        if resource_id < 1 or resource_id > 2**63 - 1:
            raise ValueError
        return timestamp.astimezone(timezone.utc), resource_id
    except DomainHTTPException:
        raise
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
        raise DomainHTTPException(400, "bad_request", "Cursor is malformed.") from None


async def list_history(
    session: AsyncSession,
    request: Request,
    request_id: str,
    *,
    principal_user_id: str,
    patient_scope: str | None,
    staff: bool,
    cursor: str | None,
    limit: int,
    worker_id: int,
) -> dict[str, Any]:
    filters = {
        "principal_scope": principal_user_id,
        "staff": staff,
        "request_id": request_id,
    }
    filter_hash = hashlib.sha256(
        json.dumps(filters, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    cursor_occurred_at, cursor_id = _decode_cursor(cursor, filter_hash)
    denied = False
    records: list[Any] = []
    next_cursor = None
    async with session.begin():
        parent = (
            await session.execute(
                select(emergency_requests).where(
                    emergency_requests.c.id == int(request_id)
                )
            )
        ).mappings().one_or_none()
        if parent is None:
            raise DomainHTTPException(404, "not_found", "Emergency request was not found.")
        if not staff and (
            patient_scope is None or str(parent["patient_id"]) != patient_scope
        ):
            denied = True
            await _append_audit(
                session,
                request,
                worker_id,
                actor_user_id=principal_user_id,
                action="request.history.read",
                resource_id=request_id,
                result="denied",
            )
        else:
            conditions = [
                emergency_status_history.c.request_id == int(request_id)
            ]
            if cursor_occurred_at is not None:
                conditions.append(
                    or_(
                        emergency_status_history.c.occurred_at > cursor_occurred_at,
                        and_(
                            emergency_status_history.c.occurred_at == cursor_occurred_at,
                            emergency_status_history.c.id > cursor_id,
                        ),
                    )
                )
            history_query = (
                select(emergency_status_history)
                .where(*conditions)
                .order_by(
                    emergency_status_history.c.occurred_at.asc(),
                    emergency_status_history.c.id.asc(),
                )
                .limit(limit + 1)
            )
            records = list((await session.execute(history_query)).mappings().all())
            more = len(records) > limit
            records = records[:limit]
            if more and records:
                next_cursor = _encode_cursor(
                    records[-1]["occurred_at"], records[-1]["id"], filter_hash
                )
            await _append_audit(
                session,
                request,
                worker_id,
                actor_user_id=principal_user_id,
                action="request.history.read",
                resource_id=request_id,
            )
    if denied:
        raise DomainHTTPException(404, "not_found", "Emergency request was not found.")
    return {
        "items": [_history_view(row, staff=staff) for row in records],
        "next_cursor": next_cursor,
    }


def validate_patient_filter(patient_id: str | None) -> None:
    if patient_id is not None and (
        not patient_id.isascii()
        or not patient_id.isdecimal()
        or patient_id.startswith("0")
        or len(patient_id) > 19
        or int(patient_id) > 2**63 - 1
    ):
        raise DomainHTTPException(422, "validation_error", "patient_id is invalid.")
