"""Appointment-owned administrative Surge Mode controls."""
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import NAMESPACE_URL, uuid5
import re

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .. import operations as op
from ..authorization import Principal, require_current_role
from ..errors import error_response
from pulsegrid_rate_limiter import SurgeModeUnavailable

router = APIRouter()
PATH = "/api/v1/appointments/operations/surge-mode"
ReasonCode = Literal["capacity_pressure", "dependency_degraded", "planned_recovery", "incident_override"]


class SurgeModeCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    active: bool
    reason_code: ReasonCode
    override: bool = False

    @model_validator(mode="after")
    def validate_override(self):
        if self.override != (self.reason_code == "incident_override"):
            raise ValueError("incident_override must be explicitly selected and audited")
        return self


def _time(value):
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat().replace("+00:00", "Z")


def _view(snapshot):
    return {
        "state": snapshot.state,
        "version": snapshot.version or 0,
        "changed_at": _time(snapshot.entered_at_ms),
        "expires_at": _time(snapshot.expires_at_ms),
        "reason_code": snapshot.reason_code,
    }


def _error(request, status, code, headers=None):
    return error_response(request, status, code=code, headers=headers)


async def _append_audit(request, principal: Principal, *, action, previous, new_state,
                        reason_code, version, operation_id, override,
                        request_id=None, correlation_id=None, response=None):
    factory = request.app.state.database.session_factory
    if factory is None:
        raise SQLAlchemyError("Appointment database is unavailable")
    metadata = {
        "action": action,
        "result": "success",
        "actor_user_id": principal.user_id,
        "resource_id": "1",
        "request_id": str(request_id or request.state.request_id),
        "correlation_id": str(correlation_id or request.state.correlation_id),
        "occurred_at": op.wire_time(op.now()),
        "previous_state": previous,
        "new_state": new_state,
        "reason_code": reason_code,
        "state_version": version,
        "operation_id": str(operation_id),
        "override": override,
    }
    if response is not None:
        metadata["response"] = response
    async with factory() as session, session.begin():
        await session.execute(
            text("SELECT public.appointment_append_phase6_audit(:entry_id,CAST(:metadata AS jsonb))"),
            {"entry_id": op.new_id(), "metadata": op.canonical(metadata)},
        )
    return metadata


async def _read_operation(request, operation_id):
    factory = request.app.state.database.session_factory
    if factory is None:
        raise SQLAlchemyError("Appointment database is unavailable")
    async with factory() as session:
        rows = (await session.execute(text(
            "SELECT canonical_metadata FROM public.audit_entries "
            "WHERE chain_id='appointment' AND canonical_metadata->>'operation_id'=:operation_id "
            "ORDER BY sequence"), {"operation_id": operation_id})).scalars().all()
    requested = next((row for row in rows if row.get('action') == 'surge_mode_transition_requested'), None)
    terminal = next((row for row in rows if row.get('action') in {
        'surge_mode_transition_applied', 'surge_mode_transition_noop'
    }), None)
    return requested, terminal


def _response_from_audit(row):
    response = row.get("response")
    if not isinstance(response, dict):
        raise ValueError("Missing Surge Mode replay response")
    return JSONResponse(response, headers={"Cache-Control": "no-store"})


async def _record_terminal(request, principal, *, action, previous, new_state,
                           reason_code, version, operation_id, override, response,
                           request_id=None, correlation_id=None):
    try:
        await _append_audit(
            request, principal, action=action, previous=previous, new_state=new_state,
            reason_code=reason_code, version=version, operation_id=operation_id,
            override=override, request_id=request_id, correlation_id=correlation_id,
            response=response)
    except IntegrityError:
        # A concurrent request with this key has already committed the terminal
        # response. The unique audit index makes the effect and replay single-writer.
        try:
            _, terminal = await _read_operation(request, operation_id)
        except SQLAlchemyError:
            return _error(request, 503, "audit_unavailable", {"Retry-After": "1"})
        if terminal is not None:
            try:
                return _response_from_audit(terminal)
            except ValueError:
                pass
        return _error(request, 503, "surge_audit_confirmation_pending", {"Retry-After": "1"})
    except SQLAlchemyError:
        return _error(request, 503, "surge_audit_confirmation_pending", {"Retry-After": "1"})
    return JSONResponse(response, headers={"Cache-Control": "no-store"})


@router.get(PATH)
async def get_surge_mode(
    request: Request,
    principal: Annotated[Principal, Depends(require_current_role("hospital_admin"))],
):
    if request.query_params:
        return _error(request, 422, "validation_error")
    del principal
    limiter = getattr(request.app.state, "admission_limiter", None)
    if limiter is None:
        return _error(request, 503, "admission_unavailable", {"Retry-After": "1"})
    snapshot = await limiter.surge_mode()
    if not snapshot.available:
        return _error(request, 503, "admission_unavailable", {"Retry-After": "1"})
    return JSONResponse(_view(snapshot), headers={"Cache-Control": "no-store"})


@router.post(PATH)
async def set_surge_mode(
    body: SurgeModeCommand,
    request: Request,
    principal: Annotated[Principal, Depends(require_current_role("hospital_admin"))],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
):
    if request.query_params:
        return _error(request, 422, "validation_error")
    limiter = getattr(request.app.state, "admission_limiter", None)
    if limiter is None:
        return _error(request, 503, "admission_unavailable", {"Retry-After": "1"})
    target = "SURGE" if body.active else "RECOVERY"
    if not re.fullmatch(r"[\x21-\x7e]{16,128}", idempotency_key):
        return _error(request, 422, "validation_error")

    operation_id = str(uuid5(NAMESPACE_URL,
        f"pulsegrid-appointment-surge-v1:{principal.user_id}:{idempotency_key}"))
    actor_digest = request.app.state.admission_adapter.deriver.principal(principal.user_id)
    try:
        prior, terminal = await _read_operation(request, operation_id)
    except SQLAlchemyError:
        return _error(request, 503, "audit_unavailable", {"Retry-After": "1"})
    operation_record = prior or terminal
    if operation_record is not None and (
        operation_record.get("new_state") != target
        or operation_record.get("reason_code") != body.reason_code
        or operation_record.get("override") is not body.override
    ):
        return _error(request, 409, "idempotency_conflict")
    if terminal is not None:
        try:
            return _response_from_audit(terminal)
        except ValueError:
            return _error(request, 503, "audit_unavailable", {"Retry-After": "1"})

    snapshot = await limiter.surge_mode()
    if not snapshot.available:
        return _error(request, 503, "admission_unavailable", {"Retry-After": "1"})

    if prior is None:
        try:
            prior = await _append_audit(
                request,
                principal,
                action="surge_mode_transition_requested",
                previous=snapshot.state,
                new_state=target,
                reason_code=body.reason_code,
                version=snapshot.version or 0,
                operation_id=operation_id,
                override=body.override,
            )
        except IntegrityError:
            # Equal concurrent keys serialize through the audit uniqueness gate.
            try:
                prior, terminal = await _read_operation(request, operation_id)
            except SQLAlchemyError:
                return _error(request, 503, "audit_unavailable", {"Retry-After": "1"})
            operation_record = prior or terminal
            if operation_record is None:
                return _error(request, 503, "audit_unavailable", {"Retry-After": "1"})
            if (operation_record.get("new_state") != target
                    or operation_record.get("reason_code") != body.reason_code
                    or operation_record.get("override") is not body.override):
                return _error(request, 409, "idempotency_conflict")
            if terminal is not None:
                try:
                    return _response_from_audit(terminal)
                except ValueError:
                    return _error(request, 503, "audit_unavailable", {"Retry-After": "1"})
            snapshot = await limiter.surge_mode()
            if not snapshot.available:
                return _error(request, 503, "admission_unavailable", {"Retry-After": "1"})
        except SQLAlchemyError:
            return _error(request, 503, "audit_unavailable", {"Retry-After": "1"})

    try:
        original_version = int(prior["state_version"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return _error(request, 503, "audit_unavailable", {"Retry-After": "1"})
    if snapshot.operation_id == operation_id and snapshot.state == target:
        replay = _view(snapshot)
        return await _record_terminal(
            request, principal, action="surge_mode_transition_applied",
            previous=prior["previous_state"], new_state=target,
            reason_code=body.reason_code, version=snapshot.version or 0,
            operation_id=operation_id, override=body.override, response=replay,
            request_id=prior["request_id"], correlation_id=prior["correlation_id"])
    if snapshot.version != original_version or snapshot.state != prior.get("previous_state"):
        return _error(request, 409, "surge_state_changed")
    if snapshot.state == target or (not body.active and snapshot.state == "NORMAL"):
        replay = _view(snapshot)
        return await _record_terminal(
            request, principal, action="surge_mode_transition_noop",
            previous=snapshot.state, new_state=snapshot.state,
            reason_code=body.reason_code, version=snapshot.version or 0,
            operation_id=operation_id, override=body.override, response=replay,
            request_id=prior["request_id"], correlation_id=prior["correlation_id"])

    try:
        status, previous, updated = await limiter.transition_surge_mode(
            snapshot,
            target,
            reason_code=body.reason_code,
            operation_id=str(operation_id),
            actor_digest=actor_digest,
            override=body.override,
        )
    except SurgeModeUnavailable:
        return _error(request, 503, "admission_unavailable", {"Retry-After": "1"})
    if status == "conflict":
        if updated.operation_id == operation_id and updated.state == target:
            replay = _view(updated)
            return await _record_terminal(
                request, principal, action="surge_mode_transition_applied",
                previous=previous, new_state=target, reason_code=body.reason_code,
                version=updated.version or 0, operation_id=operation_id,
                override=body.override, response=replay,
                request_id=prior["request_id"], correlation_id=prior["correlation_id"])
        return _error(request, 409, "surge_state_changed")
    if status == "cooldown":
        retry_after = max(1, int(((updated.expires_at_ms or 0) - (op.now().timestamp() * 1000) + 999) // 1000))
        return _error(request, 409, "surge_transition_cooldown", {"Retry-After": str(retry_after)})
    if status != "applied":
        return _error(request, 409, "surge_state_changed")

    return await _record_terminal(
        request, principal, action="surge_mode_transition_applied",
        previous=previous, new_state=updated.state, reason_code=body.reason_code,
        version=updated.version or 0, operation_id=operation_id,
        override=body.override, response=_view(updated),
        request_id=prior["request_id"], correlation_id=prior["correlation_id"])
