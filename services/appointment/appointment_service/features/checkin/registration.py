"""Appointment-owned QR check-in module. Routes stay dormant until G2 assembly."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import select, text, update

from ...wire import ID
from ... import phase3_core as shared_core
from .schemas import (
    CheckinResult,
    DoctorIdentity,
    EmptyBody,
    PatientStatus,
    QueueEntry,
    StaffCheckinBody,
    TokenBody,
    TokenIssue,
)


PUBLIC = "/api/v1/appointments"
TOKEN_PURPOSE = "check_in"
TOKEN_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
TOKEN_LENGTH = 22
TOKEN_MAX = 1 << 128
TOKEN_PATTERN = re.compile(r"^[0-9A-Za-z]{22}$")

_SCHEMA_SPEC: dict[str, Any] = {
    "tables": [
        {
            "name": "checkin_links",
            "owner": "appointment",
            "reuse_existing_table": True,
            "purpose": "single-use check-in bearer secret; no record access",
        }
    ],
    "columns": [
        {
            "table": "checkin_links",
            "name": "workflow_version",
            "type": "BIGINT",
            "nullable": False,
            "default": None,
            "constraints": "workflow_version BETWEEN 1 AND 9007199254740991",
        },
        {
            "table": "checkin_links",
            "name": "schedule_fingerprint",
            "type": "VARCHAR(64)",
            "nullable": False,
            "default": None,
            "constraints": "schedule_fingerprint ~ '^[0-9a-f]{64}$'",
        },
    ],
    "indexes": [
        {
            "name": "uq_checkin_links_token_hash",
            "table": "checkin_links",
            "unique": True,
            "columns": ["token_hash"],
        },
        {
            "name": "uq_checkin_links_live_appointment_purpose",
            "table": "checkin_links",
            "unique": True,
            "columns": ["appointment_id", "purpose"],
            "where": "consumed_at IS NULL AND revoked_at IS NULL",
        },
    ],
    "constraints": [
        {
            "name": "fk_checkin_links_appointment_id_appointments",
            "table": "checkin_links",
            "expression": "appointment_id REFERENCES appointments(id) ON DELETE RESTRICT",
        },
        {
            "name": "ck_checkin_links_check_in_purpose",
            "table": "checkin_links",
            "expression": "purpose = 'check_in'",
        },
        {
            "name": "ck_checkin_links_token_hash_sha256",
            "table": "checkin_links",
            "expression": "token_hash ~ '^[0-9a-f]{64}$'",
        },
        {
            "name": "ck_checkin_links_workflow_version_safe",
            "table": "checkin_links",
            "expression": "workflow_version BETWEEN 1 AND 9007199254740991",
        },
        {
            "name": "ck_checkin_links_schedule_fingerprint_sha256",
            "table": "checkin_links",
            "expression": "schedule_fingerprint ~ '^[0-9a-f]{64}$'",
        },
    ],
    "preflight": [
        "Reject non-empty legacy checkin_links data unless every row is reviewed as purpose check_in with a valid token digest, workflow binding and schedule fingerprint.",
        "Confirm one unconsumed and unrevoked row per appointment/purpose before creating the partial unique index; do not delete or rewrite rows.",
        "Keep the existing appointment foreign key and token-hash uniqueness; no cross-service foreign keys.",
    ],
    "runtime_grants": [
        {
            "role": "appointment_app",
            "table": "checkin_links",
            "privileges": ["SELECT", "INSERT", "UPDATE"],
        }
    ],
}


class CheckinFailure(Exception):
    """A safe feature error with the frozen error-envelope code."""

    def __init__(self, status_code: int, code: str, details: dict[str, Any] | None = None):
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.details = details


class _NeedsNewExecution(Exception):
    """Private preflight signal used to distinguish a saved same-key replay."""


class _RetryCheckinDiscovery(Exception):
    """Roll back and rediscover when a workflow queue binding changed."""


def _fail(code: str, status_code: int = 409, details: dict[str, Any] | None = None) -> None:
    raise CheckinFailure(status_code, code, details)


def _wire_time(value) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_id() -> int:
    return secrets.randbelow((1 << 63) - 1) + 1


def encode_token(value: bytes) -> str:
    """Canonical 22-character Base62 encoding of exactly 128 random bits."""
    if not isinstance(value, bytes) or len(value) != 16:
        raise ValueError("Check-in token entropy must be exactly 128 bits")
    number = int.from_bytes(value, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 62)
        encoded = TOKEN_ALPHABET[remainder] + encoded
    return encoded.rjust(TOKEN_LENGTH, TOKEN_ALPHABET[0])


def canonical_token(token: object) -> bool:
    if not isinstance(token, str) or TOKEN_PATTERN.fullmatch(token) is None:
        return False
    number = 0
    for char in token:
        number = number * 62 + TOKEN_ALPHABET.index(char)
    if number >= TOKEN_MAX:
        return False
    return encode_token(number.to_bytes(16, "big")) == token


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8", "surrogatepass")).hexdigest()


def landing_path(appointment_id: str, token: str) -> str:
    if not canonical_token(token):
        raise ValueError("Only canonical check-in tokens can be linked")
    return f"/patient/check-in#appointment_id={appointment_id}&token={token}"


def schema_spec() -> dict[str, Any]:
    """Return the non-executable requirements Agent 1 assembles in 0006."""
    return json.loads(json.dumps(_SCHEMA_SPEC))


def register_tables(metadata) -> None:
    """Reuse G0 metadata and leave all DDL to the Appointment migration owner."""
    table = metadata.tables.get("checkin_links")
    if table is None or table.name != "checkin_links":
        raise RuntimeError("G0 checkin_links table is required")


def _error(request: Request, status_code: int, code: str, details=None) -> JSONResponse:
    body = {
        "error": {
            "code": code,
            "message": "The check-in request could not be completed.",
            "request_id": str(getattr(request.state, "request_id", "00000000-0000-0000-0000-000000000000")),
        }
    }
    if details is not None:
        body["error"]["details"] = details
    headers = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
    if status_code == 503:
        headers["Retry-After"] = "1"
    return JSONResponse(body, status_code=status_code, headers=headers)


def _success(core, status_code: int, value: dict) -> JSONResponse:
    response = core.response(status_code, value)
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _decorate_checkin_response(response: JSONResponse) -> JSONResponse:
    """Add workflow ETag to the nested CheckinResult response."""
    try:
        value = json.loads(response.body)
        workflow = value.get("workflow") if isinstance(value, dict) else None
        if isinstance(workflow, dict) and isinstance(workflow.get("version"), int):
            response.headers["ETag"] = f'"{workflow["version"]}"'
    except (TypeError, ValueError):
        pass
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


async def _replay_before_owner_calls(core, request, principal, normalized_body):
    """Use the shared command wrapper so same-key success replays before owner reads."""
    async def new_execution(_session):
        raise _NeedsNewExecution()

    try:
        return await core.execute(request, principal, normalized_body, new_execution)
    except _NeedsNewExecution:
        return None


async def _execute_with_discovery_retry(core, request, principal, normalized_body, work):
    """Retry a fresh transaction if the workflow's queue child changed on discovery."""
    for attempt in range(3):
        try:
            return await core.execute(request, principal, normalized_body, work)
        except _RetryCheckinDiscovery:
            if attempt == 2:
                _fail("dependency_unavailable", 503)
    _fail("dependency_unavailable", 503)


async def _lock_appointment_context(core, session, request, principal, appointment_id: str):
    """Discover queue children before asking G0 to acquire its canonical lock set."""
    aid = int(appointment_id)
    workflow = await core.read_workflow(session, appointment_id)
    from ... import models as m
    from ..queue.service import _timezone
    booking = (await session.execute(select(m.appointments).where(m.appointments.c.id == aid))).mappings().one()
    policy = (await session.execute(select(m.doctor_schedule_snapshots.c.policy_snapshot).where(
        m.doctor_schedule_snapshots.c.doctor_id == booking['doctor_id']))).scalar_one()
    day = shared_core.op.now().astimezone(_timezone(policy)).date()
    rows = (await session.execute(select(m.queue_entries.c.id, m.queue_entries.c.local_date).where(
        m.queue_entries.c.doctor_id == booking['doctor_id']))).all()
    queue_days = tuple(sorted({(booking['doctor_id'], day)} | {(booking['doctor_id'], r.local_date) for r in rows}))
    queue_entry_ids = tuple(sorted(r.id for r in rows))
    try:
        return await core.lock_context(
            session,
            request,
            core.ActorScope.user(principal),
            core.LockPlan(
                appointment_ids=(aid,),
                queue_days=queue_days,
                queue_entry_ids=queue_entry_ids,
            ),
        )
    except ValueError as exc:
        # A concurrent check-in may have bound a queue child after the unlocked
        # discovery. G0 requires a whole-transaction restart, never a late lock.
        raise _RetryCheckinDiscovery() from exc


def _link_table(metadata):
    return metadata.tables["checkin_links"]


async def _booking(core, request, appointment_id: str) -> dict:
    table = core.metadata.tables["appointments"]
    async with core.session_factory(request)() as session:
        row = (await session.execute(select(table).where(table.c.id == int(appointment_id)))).mappings().first()
    if row is None:
        _fail("not_found", 404)
    return dict(row)


async def _owner_eligibility(request: Request, principal, booking: dict) -> None:
    """Validate current Patient/Doctor owner snapshots before opening a command transaction."""
    client = getattr(request.app.state, "domain_client", None)
    if client is None:
        _fail("dependency_unavailable", 503)
    try:
        patient = await client.get(
            request,
            principal,
            "patient",
            f"/internal/v1/patients/{booking['patient_id']}/status",
            "patients:status",
            PatientStatus,
        )
        doctor = await client.get(
            request,
            principal,
            "doctor",
            f"/internal/v1/doctors/{booking['doctor_id']}/identity",
            "doctors:identity",
            DoctorIdentity,
        )
    except CheckinFailure:
        raise
    if (
        patient.patient_id != str(booking["patient_id"])
        or not patient.active
        or doctor.doctor_id != str(booking["doctor_id"])
        or doctor.staff_user_id != str(booking["doctor_user_id"])
        or not doctor.active
    ):
        _fail("invalid_transition")


def _locked_rows(core, context, appointment_id: str):
    aid = int(appointment_id)
    booking = context.bookings.get(aid)
    workflow = context.workflows.get(aid)
    if booking is None:
        _fail("not_found", 404)
    if workflow is None:
        _fail("invalid_transition")
    return booking, workflow


def _validate_schedule_binding(core, booking: dict, workflow: dict) -> None:
    if (
        workflow["patient_id"] != booking["patient_id"]
        or workflow["doctor_id"] != booking["doctor_id"]
        or workflow["slot_id"] != booking["slot_id"]
        or workflow["schedule_revision"] != booking["schedule_revision"]
        or workflow["schedule_fingerprint"] != core.schedule_fingerprint(booking)
    ):
        _fail("invalid_transition")


def _check_precondition(core, request: Request, workflow: dict) -> None:
    expected = core.precondition(request.headers.get("If-Match"))
    if workflow["version"] != expected:
        _fail("version_conflict", 412)


def _require_booked(booking: dict, workflow: dict, context) -> None:
    if (
        booking["state"] != "confirmed"
        or workflow["state"] != "booked"
        or int(booking["id"]) in context.holds
    ):
        _fail("invalid_transition")


async def _issue_in_transaction(core, session, request, principal, appointment_id: str):
    context = await _lock_appointment_context(core, session, request, principal, appointment_id)
    booking, workflow = _locked_rows(core, context, appointment_id)
    _validate_schedule_binding(core, booking, workflow)
    _check_precondition(core, request, workflow)
    _require_booked(booking, workflow, context)
    if context.now >= workflow["window_ends_at"]:
        _fail("invalid_transition")

    links = (await session.execute(text(
        "SELECT id FROM checkin_links WHERE appointment_id = :appointment_id "
        "AND purpose = :purpose ORDER BY id"
    ), {"appointment_id": int(appointment_id), "purpose": TOKEN_PURPOSE})).all()
    if links:
        now = context.now
        await session.execute(text(
            "UPDATE checkin_links SET revoked_at = :now, version = version + 1, updated_at = :now "
            "WHERE appointment_id = :appointment_id AND purpose = :purpose "
            "AND consumed_at IS NULL AND revoked_at IS NULL"
        ), {"now": now, "appointment_id": int(appointment_id), "purpose": TOKEN_PURPOSE})
        workflow_table = core.metadata.tables["appointment_workflows"]
        updated = (await session.execute(update(workflow_table).where(
            workflow_table.c.appointment_id == int(appointment_id),
            workflow_table.c.version == workflow["version"],
            workflow_table.c.state == "booked",
        ).values(version=workflow_table.c.version + 1, updated_at=now)
            .returning(workflow_table))).mappings().one_or_none()
        if updated is None:
            _fail("version_conflict", 412)
        workflow = dict(updated)

    token = encode_token(secrets.token_bytes(16))
    expires_at = min(context.now + timedelta(hours=24), workflow["window_ends_at"])
    link_id = _new_id()
    await session.execute(text(
        "INSERT INTO checkin_links "
        "(id, appointment_id, token_hash, purpose, expires_at, workflow_version, schedule_fingerprint) "
        "VALUES (:id, :appointment_id, :token_hash, :purpose, :expires_at, :workflow_version, :schedule_fingerprint)"
    ), {
        "id": link_id,
        "appointment_id": int(appointment_id),
        "token_hash": token_digest(token),
        "purpose": TOKEN_PURPOSE,
        "expires_at": expires_at,
        "workflow_version": workflow["version"],
        "schedule_fingerprint": workflow["schedule_fingerprint"],
    })
    safe_value = {
        "link_id": str(link_id),
        "appointment_id": appointment_id,
        "expires_at": _wire_time(expires_at),
        "version": 1,
    }
    core.stage_effect(session, context, 'workflow_link_issued', int(appointment_id), workflow['version'],
        {'resource_id': appointment_id, 'version': workflow['version'], 'state': 'booked'})
    return safe_value, token


async def _revoke_open_links(session, appointment_id: int, now) -> None:
    await session.execute(text(
        "UPDATE checkin_links SET revoked_at = :now, version = version + 1, updated_at = :now "
        "WHERE appointment_id = :appointment_id AND purpose = :purpose "
        "AND consumed_at IS NULL AND revoked_at IS NULL"
    ), {"now": now, "appointment_id": appointment_id, "purpose": TOKEN_PURPOSE})


async def _redeem_in_transaction(
    core, app, session, request, principal, appointment_id: str, token: str | None, reason: str | None
):
    context = await _lock_appointment_context(core, session, request, principal, appointment_id)
    booking, workflow = _locked_rows(core, context, appointment_id)
    if token is None:
        _check_precondition(core, request, workflow)
    if context.now < workflow["window_starts_at"] or context.now >= workflow["window_ends_at"]:
        _fail("checkin_window_closed")

    link = None
    if canonical_token(token):
        rows = (await session.execute(text(
            "SELECT id, appointment_id, token_hash, purpose, expires_at, consumed_at, revoked_at, "
            "workflow_version, schedule_fingerprint, version "
            "FROM checkin_links WHERE appointment_id = :appointment_id AND purpose = :purpose "
            "AND token_hash = :token_hash"
        ), {
            "appointment_id": int(appointment_id),
            "purpose": TOKEN_PURPOSE,
            "token_hash": token_digest(token),
        })).mappings().all()
        link = rows[0] if len(rows) == 1 else None
    if token is not None:
        if (
            link is None
            or link["consumed_at"] is not None
            or link["revoked_at"] is not None
            or link["expires_at"] <= context.now
            or link["workflow_version"] != workflow["version"]
            or link["schedule_fingerprint"] != workflow["schedule_fingerprint"]
            or workflow["schedule_fingerprint"] != core.schedule_fingerprint(booking)
        ):
            _fail("token_invalid")
        _check_precondition(core, request, workflow)
    else:
        _validate_schedule_binding(core, booking, workflow)
    _require_booked(booking, workflow, context)

    if token is None:
        await _revoke_open_links(session, int(appointment_id), context.now)

    if token is not None:
        consumed = (await session.execute(text(
            "UPDATE checkin_links SET consumed_at = :now, version = version + 1, updated_at = :now "
            "WHERE id = :link_id AND consumed_at IS NULL AND revoked_at IS NULL "
            "AND expires_at > :now AND workflow_version = :workflow_version "
            "AND schedule_fingerprint = :schedule_fingerprint RETURNING id"
        ), {
            "now": context.now,
            "link_id": link["id"],
            "workflow_version": workflow["version"],
            "schedule_fingerprint": workflow["schedule_fingerprint"],
        })).first()
        if consumed is None:
            _fail("token_invalid")

    # Agent 3 owns queue state/counters. This reviewed participant shares the
    # existing locked Appointment transaction and never sees the bearer secret.
    queue_entry = await core.invoke_participant(app, "queue", "allocate_on_checkin", session, context)
    try:
        queue_entry = QueueEntry.model_validate(queue_entry).model_dump(mode="json")
    except (ValidationError, TypeError, ValueError):
        _fail("dependency_unavailable", 503)
    if (
        queue_entry["appointment_id"] != appointment_id
        or queue_entry["doctor_id"] != str(booking["doctor_id"])
        or queue_entry["state"] != "waiting"
    ):
        _fail("dependency_unavailable", 503)

    updated = await core.read_workflow(session, appointment_id)
    if (updated['state'] != 'checked_in' or updated['queue_entry_id'] != int(queue_entry['id'])
            or updated['version'] != workflow['version'] + 1):
        _fail('dependency_unavailable', 503)
    # Queue allocation owns the single shared workflow transition and audit.
    from ..journey.service import local_stages
    await local_stages(session, context, int(appointment_id))
    workflow_value = core.workflow_view(updated)
    return 200, {"workflow": workflow_value, "queue_entry": queue_entry}


async def revoke_for_booking_change(session, context, appointment_id=None) -> None:
    """Revoke every unconsumed QR under the framework's already-held link locks."""
    core = shared_core
    core.require_context(session, context)
    targets=(int(appointment_id),) if appointment_id is not None else context.plan.appointment_ids
    for appointment_id in targets:
        if appointment_id in context.workflows:
            await _revoke_open_links(session, appointment_id, context.now)


def register_routes(app, core) -> None:
    """Mount static feature routes; the integrator supplies this module at G2."""
    router = APIRouter()

    @router.get(PUBLIC + "/{appointment_id}/workflow", response_model=core.Workflow)
    async def get_workflow(request: Request, appointment_id: ID, p=Depends(core.authenticated_user)):
        core.query_keys(request, ())
        await core.authorize(request, p, ("receptionist", "patient", "doctor"), appointment_id)
        async with core.session_factory(request)() as session:
            workflow = await core.read_workflow(session, appointment_id)
        if workflow is None:
            _fail("not_found", 404)
        return _success(core, 200, core.workflow_view(workflow))

    @router.post(PUBLIC + "/{appointment_id}/check-in-links", response_model=TokenIssue, status_code=201)
    async def issue_checkin_link(
        request: Request,
        appointment_id: ID,
        body: EmptyBody,
        p=Depends(core.authenticated_user),
    ):
        core.query_keys(request, ())
        await core.authorize(request, p, ("receptionist", "patient"), appointment_id, write=True)
        first_response: dict[str, Any] = {}

        async def work(session):
            safe_value, raw_token = await _issue_in_transaction(
                core, session, request, p, appointment_id
            )
            first_response["value"] = safe_value
            first_response["token"] = raw_token
            return 201, safe_value

        saved_response = await _execute_with_discovery_retry(core, request, p, body.model_dump(), work)
        if "token" not in first_response:
            saved = json.loads(saved_response.body)
            resource_id = saved.get("link_id") if isinstance(saved, dict) else None
            return _error(request, 409, "token_response_unavailable", {"resource_id": resource_id})
        value = {
            **first_response["value"],
            "token": first_response["token"],
            "landing_path": landing_path(appointment_id, first_response["token"]),
        }
        return _success(core, 201, TokenIssue.model_validate(value).model_dump(mode="json"))

    @router.post(PUBLIC + "/{appointment_id}/check-in", response_model=CheckinResult)
    async def check_in(
        request: Request,
        appointment_id: ID,
        body: TokenBody,
        p=Depends(core.authenticated_user),
    ):
        core.query_keys(request, ())
        await core.authorize(request, p, ("receptionist", "patient"), appointment_id, write=True)
        token_hash = token_digest(body.token)
        normalized_body = {"token_digest": token_hash}
        replay = await _replay_before_owner_calls(core, request, p, normalized_body)
        if replay is not None:
            return _decorate_checkin_response(replay)
        core.precondition(request.headers.get("If-Match"))
        booking = await _booking(core, request, appointment_id)
        await _owner_eligibility(request, p, booking)

        async def work(session):
            return await _redeem_in_transaction(core, app, session, request, p, appointment_id, body.token, None)

        response = await _execute_with_discovery_retry(core, request, p, normalized_body, work)
        return _decorate_checkin_response(response)

    @router.post(PUBLIC + "/{appointment_id}/staff-check-in", response_model=CheckinResult)
    async def staff_check_in(
        request: Request,
        appointment_id: ID,
        body: StaffCheckinBody,
        p=Depends(core.authenticated_user),
    ):
        core.query_keys(request, ())
        await core.authorize(request, p, ("receptionist",), appointment_id, write=True)
        normalized_body = body.model_dump()
        replay = await _replay_before_owner_calls(core, request, p, normalized_body)
        if replay is not None:
            return _decorate_checkin_response(replay)
        core.precondition(request.headers.get("If-Match"))
        booking = await _booking(core, request, appointment_id)
        await _owner_eligibility(request, p, booking)

        async def work(session):
            result = await _redeem_in_transaction(
                core, app, session, request, p, appointment_id, None, body.reason
            )
            return result

        # Normalized body fingerprints contain the reason but never any QR secret.
        response = await _execute_with_discovery_retry(core, request, p, normalized_body, work)
        return _decorate_checkin_response(response)

    @router.get('/internal/v1/appointments/{appointment_id}/workflow-context')
    async def workflow_context(request:Request,appointment_id:ID):
        from ... import models as m,operations as op
        from sqlalchemy import func
        core.query_keys(request,())
        p=core.private_principal(request,'records','appointments:workflow-context')
        await core.current(request,p,('doctor',))
        async with core.session_factory(request)() as session,session.begin():
            row=(await session.execute(select(m.appointments,
                func.row_to_json(m.appointment_workflows.table_valued()).label('workflow_row'),
                m.clinical_holds.c.state.label('hold_state')).outerjoin(m.appointment_workflows,
                m.appointment_workflows.c.appointment_id==m.appointments.c.id).outerjoin(m.clinical_holds,
                m.clinical_holds.c.appointment_id==m.appointments.c.id).where(m.appointments.c.id==int(appointment_id)))).mappings().first()
            if row is None or str(row['doctor_user_id'])!=p.user_id:op.fail('not_found',404)
            wf=row['workflow_row']
            if wf:
                for key in ('window_starts_at','window_ends_at'):
                    wf[key]=__import__('datetime').datetime.fromisoformat(wf[key])
            result=dict(appointment_id=appointment_id,patient_id=str(row['patient_id']),doctor_id=str(row['doctor_id']),
                doctor_user_id=str(row['doctor_user_id']),workflow=core.workflow_view(wf) if wf else None,
                clinical_hold=row['hold_state'] or 'none',version=row['version'])
            await op.audit(session,request,p,'read',appointment_id)
        return core.response(200,result)

    async def checkin_error_handler(request: Request, exc: CheckinFailure):
        return _error(request, exc.status_code, exc.code, exc.details)

    app.add_exception_handler(CheckinFailure, checkin_error_handler)
    app.include_router(router)
