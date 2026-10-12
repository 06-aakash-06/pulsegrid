"""Frozen Appointment URL short-link routes and lifecycle participant."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from ... import models, operations as op, phase3_core
from ...errors import error_response
from ...wire import ID, Input
from .ports import ShortLinksPorts
from .repository import ShortLinkRepository, is_token_hash_collision
from .schema_spec import register_tables as _register_tables
from .schema_spec import schema_spec


PUBLIC = "/api/v1/appointments"
ALIAS_ROUTE = "/s/{alias}"
ALIAS_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
ALIAS_LENGTH = 22
ALIAS_MAX = 1 << 128
ALIAS_PATTERN = re.compile(r"^[0-9A-Za-z]{22}$")
PURPOSES = ("appointment", "check_in")
MAX_COLLISION_ATTEMPTS = 3
RESOLUTION_ROLES = ("patient", "receptionist")


class CreateBody(Input):
    purpose: Literal["appointment", "check_in"]


class EmptyBody(Input):
    pass


def _fail(code: str, status_code: int = 409) -> None:
    raise HTTPException(status_code, detail=code)


def _wire_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def encode_alias(entropy: bytes) -> str:
    """Encode exactly 128 random bits as canonical fixed-width Base62."""
    if not isinstance(entropy, bytes) or len(entropy) != 16:
        raise ValueError("Short-link aliases require exactly 128 random bits")
    number = int.from_bytes(entropy, "big")
    result = ""
    while number:
        number, remainder = divmod(number, 62)
        result = ALIAS_ALPHABET[remainder] + result
    return result.rjust(ALIAS_LENGTH, ALIAS_ALPHABET[0])


def canonical_alias(value: object) -> bool:
    if not isinstance(value, str) or ALIAS_PATTERN.fullmatch(value) is None:
        return False
    number = 0
    for character in value:
        number = number * 62 + ALIAS_ALPHABET.index(character)
    return number < ALIAS_MAX and encode_alias(number.to_bytes(16, "big")) == value


def alias_digest(alias: str) -> str:
    if not canonical_alias(alias):
        raise ValueError("Only canonical aliases can be digested")
    return hashlib.sha256(alias.encode("ascii")).hexdigest()


def register_tables(metadata) -> None:
    _register_tables(metadata)


def _observer(ports: ShortLinksPorts):
    try:
        return ports.observer
    except Exception:
        return None


def _increment(ports: ShortLinksPorts, name: str, labels: dict[str, str]) -> None:
    observer = _observer(ports)
    if observer is None:
        return
    try:
        observer.increment(name, labels)
    except Exception:
        # Metrics are observational and must not change a business result.
        return


def _observe(ports: ShortLinksPorts, name: str, seconds: float, labels: dict[str, str]) -> None:
    observer = _observer(ports)
    if observer is None:
        return
    try:
        observer.observe(name, max(0.0, seconds), labels)
    except Exception:
        return


def _labels(outcome: str, kind: str | None = None) -> dict[str, str]:
    result = {"owner": "appointment", "outcome": outcome}
    if kind in PURPOSES:
        result["kind"] = kind
    return result


def _json_success(status: int, body: dict[str, Any], *, etag: str | None = None) -> JSONResponse:
    headers = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
    if etag is not None:
        headers["ETag"] = etag
    return JSONResponse(body, status_code=status, headers=headers)


def _response_resource_id(response: Any) -> str | None:
    """Read only the safe persisted ID when a same-key issuance is replayed."""
    try:
        if isinstance(response, dict):
            value = response
        elif isinstance(response, tuple) and len(response) >= 2:
            value = response[1]
        else:
            value = json.loads(response.body)
        if isinstance(value, dict):
            candidate = value.get("id") or value.get("link_id")
            if isinstance(candidate, str) and candidate.isdecimal() and int(candidate) > 0:
                return candidate
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return None


def _body_error(request: Request) -> JSONResponse:
    return error_response(
        request,
        422,
        code="validation_error",
        details={"fields": [{"location": "body", "code": "invalid"}]},
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


async def _parse_body(request: Request, model):
    try:
        raw = await request.json()
        return model.model_validate(raw)
    except (ValueError, TypeError, ValidationError):
        return None


def _no_query(request: Request) -> None:
    if request.query_params:
        _fail("bad_request", 400)


def _booking_workflow(context: Any, appointment_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    aid = int(appointment_id)
    bookings = getattr(context, "bookings", None)
    workflows = getattr(context, "workflows", None)
    booking = bookings.get(aid) if bookings is not None else None
    workflow = workflows.get(aid) if workflows is not None else None
    if booking is None:
        _fail("not_found", 404)
    if workflow is None:
        _fail("invalid_transition", 409)
    return dict(booking), dict(workflow)


def _validate_booking_workflow(booking: dict[str, Any], workflow: dict[str, Any]) -> None:
    if (
        booking.get("state") != "confirmed"
        or workflow.get("state") != "booked"
        or workflow.get("patient_id") != booking.get("patient_id")
        or workflow.get("doctor_id") != booking.get("doctor_id")
        or workflow.get("slot_id") != booking.get("slot_id")
        or workflow.get("schedule_revision") != booking.get("schedule_revision")
    ):
        _fail("invalid_transition", 409)
    try:
        fingerprint = phase3_core.schedule_fingerprint(booking)
    except (KeyError, TypeError, ValueError):
        _fail("dependency_unavailable", 503)
    if workflow.get("schedule_fingerprint") != fingerprint:
        _fail("invalid_transition", 409)
    version = workflow.get("version")
    if type(version) is not int or not 1 <= version <= 9007199254740991:
        _fail("dependency_unavailable", 503)


def _stage_effect(ports: ShortLinksPorts, session, context, action: str, row: dict[str, Any]) -> None:
    payload = {
        "resource_id": str(row["id"]),
        "version": int(row["version"]),
        "state": "revoked" if action == "short_link_revoked" else "active",
    }
    ports.stage_effect(session, context, action, int(row["id"]), int(row["version"]), payload)


async def _create_in_transaction(
    ports: ShortLinksPorts,
    session,
    context,
    request: Request,
    principal,
    appointment_id: str,
    purpose: str,
    link_id: int,
    expected_workflow_version: int,
    issued: dict[str, Any],
) -> tuple[int, dict[str, Any], int]:
    locked_context = await ports.lock_context(session, request, principal, appointment_id)
    booking, workflow = _booking_workflow(locked_context, appointment_id)
    _validate_booking_workflow(booking, workflow)
    if workflow["version"] != expected_workflow_version:
        _fail("version_conflict", 412)
    if int(appointment_id) in getattr(locked_context, "holds", {}):
        _fail("clinical_hold", 409)

    repository = ShortLinkRepository(session)
    database_now = await repository.database_now()
    starts_at = booking["starts_at"]
    window_ends_at = workflow.get("window_ends_at")
    if purpose == "appointment":
        if starts_at <= database_now:
            _fail("invalid_transition", 409)
        expires_at = min(database_now + timedelta(hours=24), starts_at + timedelta(minutes=15))
    else:
        if window_ends_at is None or window_ends_at <= database_now:
            _fail("invalid_transition", 409)
        expires_at = min(database_now + timedelta(hours=24), window_ends_at)

    previous = await repository.revoke_open_for_appointment(
        int(appointment_id), database_now, purpose
    )
    for old_link in previous:
        _stage_effect(ports, session, locked_context, "short_link_revoked", old_link)

    token_hash = None
    alias = None
    for _attempt in range(MAX_COLLISION_ATTEMPTS):
        candidate = encode_alias(secrets.token_bytes(16))
        candidate_hash = alias_digest(candidate)
        if await repository.by_digest(candidate_hash) is not None:
            _increment(ports, "pulsegrid_short_link_collisions_total", _labels("digest_collision", purpose))
            continue
        try:
            await repository.insert(
                {
                    "id": link_id,
                    "appointment_id": int(appointment_id),
                    "purpose": purpose,
                    "token_hash": candidate_hash,
                    "expires_at": expires_at,
                    "revoked_at": None,
                    "workflow_version": workflow["version"],
                    "schedule_fingerprint": workflow["schedule_fingerprint"],
                    "version": 1,
                }
            )
        except IntegrityError as exc:
            if not is_token_hash_collision(exc):
                raise
            _increment(ports, "pulsegrid_short_link_collisions_total", _labels("unique_collision", purpose))
            continue
        alias = candidate
        token_hash = candidate_hash
        break

    if alias is None or token_hash is None:
        _fail("dependency_unavailable", 503)

    safe_body = {
        "id": str(link_id),
        "appointment_id": appointment_id,
        "purpose": purpose,
        "expires_at": _wire_time(expires_at),
        "version": 1,
    }
    _stage_effect(ports, session, locked_context, "short_link_created", {
        "id": link_id,
        "version": 1,
    })
    issued["short_path"] = f"/s/{alias}"
    return 201, safe_body, 1


async def _revoke_in_transaction(
    ports: ShortLinksPorts,
    session,
    request: Request,
    principal,
    appointment_id: str,
    link_id: str,
    expected_version: int,
) -> tuple[int, dict[str, Any], int]:
    context = await ports.lock_context(session, request, principal, appointment_id)
    booking, _workflow = _booking_workflow(context, appointment_id)
    repository = ShortLinkRepository(session)
    existing = await repository.by_id(int(link_id))
    if existing is None or existing["appointment_id"] != int(appointment_id):
        _fail("not_found", 404)
    if existing["version"] != expected_version:
        _fail("version_conflict", 412)

    if existing["revoked_at"] is None:
        now = await repository.database_now()
        updated = await repository.revoke_one(
            int(link_id), int(appointment_id), expected_version, now
        )
        if updated is None:
            _fail("version_conflict", 412)
        existing = updated
        _stage_effect(ports, session, context, "short_link_revoked", existing)

    body = {
        "id": str(existing["id"]),
        "appointment_id": str(booking["id"]),
        "purpose": existing["purpose"],
        "expires_at": _wire_time(existing["expires_at"]),
        "revoked": True,
        "version": int(existing["version"]),
    }
    return 200, body, int(existing["version"])


def _principal_roles(principal: Any) -> set[str]:
    roles = principal.get("roles", ()) if isinstance(principal, dict) else getattr(principal, "roles", ())
    return set(roles or ())


def _landing_path(principal: Any, purpose: str, appointment_id: str) -> str:
    roles = _principal_roles(principal)
    if "receptionist" in roles:
        return f"/receptionist/appointments#appointment_id={appointment_id}"
    if purpose == "check_in":
        return f"/patient/check-in#appointment_id={appointment_id}"
    return "/patient/appointments"


def _wants_html(request: Request) -> bool:
    """Use the static browser handoff only when JSON was not also requested."""
    qualities: dict[str, float] = {}
    for part in request.headers.get("Accept", "").split(","):
        media, *parameters = part.strip().split(";")
        quality = 1.0
        for parameter in parameters:
            key, separator, value = parameter.strip().partition("=")
            if separator and key.lower() == "q":
                try:
                    quality = float(value)
                except ValueError:
                    quality = 0.0
        qualities[media.strip().lower()] = quality
    return qualities.get("text/html", 0.0) > 0 and qualities.get("application/json", 0.0) == 0


def _missing_or_invalid(request: Request) -> JSONResponse:
    return error_response(
        request,
        404,
        code="not_found",
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


def _safe_authorize_error(exc: HTTPException) -> HTTPException:
    if exc.status_code == 401:
        return HTTPException(401, detail="unauthorized")
    if exc.status_code in (403, 404):
        # Scope mismatch uses the same response as missing, expired or revoked.
        return HTTPException(404, detail="not_found")
    return exc


def _metric_outcome(exc: Exception | None) -> str:
    if exc is None:
        return "resolved"
    if isinstance(exc, HTTPException):
        if exc.status_code == 401:
            return "unauthorized"
        if exc.status_code == 404:
            return "not_found"
        return "rejected"
    return "error"


def _is_workflow_binding_valid(link: dict[str, Any], booking: dict[str, Any], workflow: dict[str, Any]) -> bool:
    try:
        _validate_booking_workflow(booking, workflow)
    except HTTPException:
        return False
    return (
        workflow["version"] == link["workflow_version"]
        and workflow["schedule_fingerprint"] == link["schedule_fingerprint"]
    )


async def _revoke_for_booking_change(session, context, appointment_id: int | None = None) -> None:
    phase3_core.require_context(session, context)
    repository = ShortLinkRepository(session)
    targets = (int(appointment_id),) if appointment_id is not None else tuple(context.plan.appointment_ids)
    for target in targets:
        if target not in context.workflows:
            continue
        now = await repository.database_now()
        rows = await repository.revoke_open_for_appointment(target, now)
        for row in rows:
            _stage_effect_from_core(session, context, "short_link_revoked", row)


def _stage_effect_from_core(session, context, action: str, row: dict[str, Any]) -> None:
    """Lifecycle hooks use the current owner effect participant directly."""
    payload = {"resource_id": str(row["id"]), "version": int(row["version"]), "state": "revoked"}
    phase3_core.stage_effect(session, context, action, int(row["id"]), int(row["version"]), payload)


async def revoke_for_booking_change(session, context, appointment_id=None) -> None:
    """Revoke aliases while the coordinator's canonical Appointment locks are held."""
    await _revoke_for_booking_change(session, context, appointment_id)


def register_routes(app, ports: ShortLinksPorts) -> None:
    """Mount feature routes into a coordinator-supplied test or integration app."""
    register_tables(models.metadata)
    router = APIRouter()

    @router.post(PUBLIC + "/{appointment_id}/short-links", status_code=201)
    async def create_short_link(request: Request, appointment_id: ID):
        started_ns = time.perf_counter_ns()
        outcome = "error"
        purpose = None
        try:
            _no_query(request)
            body = await _parse_body(request, CreateBody)
            if body is None:
                outcome = "validation_error"
                return _body_error(request)
            purpose = body.purpose
            principal = await ports.authorize(request, RESOLUTION_ROLES, appointment_id, True)
            expected = op.precondition(request.headers.get("If-Match"))
            link_id = await ports.allocate_id()
            if type(link_id) is not int or not 0 < link_id < 2**63:
                _fail("dependency_unavailable", 503)
            issued: dict[str, str] = {}

            async def operation(session, context):
                issued.clear()
                return await _create_in_transaction(
                    ports,
                    session,
                    context,
                    request,
                    principal,
                    appointment_id,
                    purpose,
                    link_id,
                    expected,
                    issued,
                )

            response = await ports.command(
                request,
                principal,
                "POST /api/v1/appointments/{appointment_id}/short-links",
                body.model_dump(mode="json"),
                request.headers.get("If-Match"),
                operation,
            )
            if "short_path" not in issued:
                outcome = "token_response_unavailable"
                return error_response(
                    request,
                    409,
                    code="token_response_unavailable",
                    details={"resource_id": _response_resource_id(response)},
                    headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
                )
            final_response = ports.token_response(response, dict(issued))
            outcome = "created"
            _increment(ports, "pulsegrid_short_link_created_total", _labels("created", purpose))
            return final_response
        except HTTPException as exc:
            outcome = _metric_outcome(exc)
            raise _safe_authorize_error(exc) if exc.status_code in (401, 403, 404) else exc
        finally:
            _observe(
                ports,
                "pulsegrid_short_link_create_seconds",
                (time.perf_counter_ns() - started_ns) / 1_000_000_000,
                _labels(outcome, purpose),
            )

    @router.post(PUBLIC + "/{appointment_id}/short-links/{link_id}/revoke")
    async def revoke_short_link(request: Request, appointment_id: ID, link_id: ID):
        started_ns = time.perf_counter_ns()
        outcome = "error"
        try:
            _no_query(request)
            body = await _parse_body(request, EmptyBody)
            if body is None:
                outcome = "validation_error"
                return _body_error(request)
            principal = await ports.authorize(request, RESOLUTION_ROLES, appointment_id, True)
            expected = op.precondition(request.headers.get("If-Match"))

            async def operation(session, _command_context):
                return await _revoke_in_transaction(
                    ports,
                    session,
                    request,
                    principal,
                    appointment_id,
                    link_id,
                    expected,
                )

            response = await ports.command(
                request,
                principal,
                "POST /api/v1/appointments/{appointment_id}/short-links/{link_id}/revoke",
                body.model_dump(mode="json"),
                request.headers.get("If-Match"),
                operation,
            )
            outcome = "revoked"
            _increment(ports, "pulsegrid_short_link_revoked_total", _labels("revoked"))
            return response
        except HTTPException as exc:
            outcome = _metric_outcome(exc)
            raise _safe_authorize_error(exc) if exc.status_code in (401, 403, 404) else exc
        finally:
            _observe(
                ports,
                "pulsegrid_short_link_revoke_seconds",
                (time.perf_counter_ns() - started_ns) / 1_000_000_000,
                _labels(outcome),
            )

    @router.get(ALIAS_ROUTE)
    async def resolve_short_link(request: Request, alias: str):
        started_ns = time.perf_counter_ns()
        failure: Exception | None = None
        kind: str | None = None
        navigation = _wants_html(request)
        try:
            _no_query(request)
            if navigation:
                if not canonical_alias(alias):
                    _fail("not_found", 404)
                response = RedirectResponse(
                    url=f"/short-link#alias={alias}",
                    status_code=303,
                    headers={
                        "Cache-Control": "no-store",
                        "Referrer-Policy": "no-referrer",
                        "X-Content-Type-Options": "nosniff",
                    },
                )
                return response

            try:
                principal = await ports.authorize(request, RESOLUTION_ROLES, None, False)
            except HTTPException as exc:
                raise _safe_authorize_error(exc)
            if not canonical_alias(alias):
                _fail("not_found", 404)
            digest = alias_digest(alias)

            # Release the lookup connection before the owner scope port opens its
            # own bounded session/current-authority call. Nested acquisition can
            # deadlock a saturated pool even though each individual query is fast.
            async with ports.read_session() as session:
                repository = ShortLinkRepository(session)
                initial, first_now = await repository.expired_or_revoked_by_digest(digest)
                if initial is None or initial['revoked_at'] is not None or initial['expires_at'] <= first_now:
                    _fail('not_found',404)
                appointment_id=str(initial['appointment_id'])
            try:
                principal=await ports.authorize(request,RESOLUTION_ROLES,appointment_id,False)
            except HTTPException as exc:
                raise _safe_authorize_error(exc)
            async with ports.read_session() as session:
                async with session.begin():
                    # Version and fingerprint checks reject mixed snapshots if a
                    # booking mutation commits between these read-committed queries.
                    repository = ShortLinkRepository(session)
                    link, database_now = await repository.expired_or_revoked_by_digest(digest)
                    if (
                        link is None
                        or link["revoked_at"] is not None
                        or link["expires_at"] <= database_now
                    ):
                        _fail("not_found", 404)
                    kind = link["purpose"] if link["purpose"] in PURPOSES else None
                    appointment_id = str(link["appointment_id"])
                    if str(link['appointment_id']) != appointment_id:
                        _fail('not_found',404)
                    booking = await repository.booking(int(appointment_id))
                    workflow = await ports.read_workflow(session, appointment_id)
                    if (
                        booking is None
                        or workflow is None
                        or await repository.has_active_hold(int(appointment_id))
                        or not _is_workflow_binding_valid(link, booking, workflow)
                    ):
                        _fail("not_found", 404)
                    if link["purpose"] == "check_in" and workflow["window_ends_at"] <= database_now:
                        _fail("not_found", 404)
                    if link["purpose"] == "appointment" and booking["starts_at"] + timedelta(minutes=15) <= database_now:
                        _fail("not_found", 404)
                    await op.audit(session, request, principal, "read", appointment_id)
                    response_body = {
                        "appointment_id": appointment_id,
                        "purpose": link["purpose"],
                        "landing_path": _landing_path(principal, link["purpose"], appointment_id),
                        "expires_at": _wire_time(link["expires_at"]),
                    }
            failure = None
            return _json_success(200, response_body, etag=f'"{link["version"]}"')
        except HTTPException as exc:
            failure = exc
            if exc.status_code == 404:
                return _missing_or_invalid(request)
            raise
        except Exception as exc:
            failure = exc
            raise
        finally:
            outcome = "redirect" if navigation and failure is None else _metric_outcome(failure)
            if navigation:
                _increment(ports, "pulsegrid_short_link_navigation_total", _labels(outcome))
                _observe(
                    ports,
                    "pulsegrid_short_link_navigation_seconds",
                    (time.perf_counter_ns() - started_ns) / 1_000_000_000,
                    _labels(outcome),
                )
            else:
                _increment(ports, "pulsegrid_short_link_resolved_total", _labels(outcome, kind))
                _observe(
                    ports,
                    "pulsegrid_short_link_resolve_seconds",
                    (time.perf_counter_ns() - started_ns) / 1_000_000_000,
                    _labels(outcome, kind),
                )

    app.include_router(router)
