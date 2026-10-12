"""Unmounted Billing insurance routes; coordinator provides auth and transactions."""

from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any, Mapping

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from .contracts import InsuranceValidationError, validate_id
from .estimate import estimate

router = APIRouter()
_ROUTES = "/api/v1/billing"


def _error(request: Request, status: int, code: str) -> JSONResponse:
    messages = {
        "invalid_request": "The insurance request is invalid.",
        "provider_not_found": "The configured synthetic provider was not found.",
        "run_not_found": "The crawler run was not found.",
        "insurance_rules_unavailable": "No current synthetic insurance rule is available.",
        "source_revision_conflict": "The provider published conflicting content for this rule revision.",
    }
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": messages.get(code, "The insurance operation could not be completed."), "request_id": str(request.state.request_id)}},
        headers={"Cache-Control": "no-store"},
    )


def _stored_response(result: Any) -> Response:
    if isinstance(result, Response):
        return result
    status = getattr(result, "status_code", None)
    body = getattr(result, "body", None)
    etag = getattr(result, "etag", None)
    if status is None and isinstance(result, tuple) and len(result) == 3:
        status, body, version = result
        etag = f'"{version}"' if version is not None else None
    if type(status) is not int or not isinstance(body, dict):
        raise RuntimeError("insurance command adapter returned an invalid response")
    headers = {"Cache-Control": "no-store"}
    if etag is not None:
        headers["ETag"] = etag
    return JSONResponse(status_code=status, content=body, headers=headers)


async def _request_json(request: Request) -> dict[str, Any]:
    if request.query_params:raise HTTPException(422,detail={"code":"invalid_request"})
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(422, detail={"code": "invalid_request"}) from exc
    if not isinstance(body, dict):
        raise HTTPException(422, detail={"code": "invalid_request"})
    return body


def _query(request: Request, allowed: set[str]) -> tuple[str | None, int]:
    for key in request.query_params.keys():
        if key not in allowed or len(request.query_params.getlist(key)) != 1:
            raise HTTPException(422, detail={"code": "invalid_request"})
    raw_limit = request.query_params.get("limit", "20")
    try:
        limit = int(raw_limit)
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "invalid_request"}) from exc
    if not 1 <= limit <= 100:
        raise HTTPException(422, detail={"code": "invalid_request"})
    return request.query_params.get("cursor"), limit


def _current_time(ports: Any) -> datetime:
    candidate = getattr(ports, "now", None)
    value = candidate() if callable(candidate) else datetime.now(timezone.utc)
    if hasattr(value, "__await__"):
        raise RuntimeError("insurance route now port must be synchronous")
    return value


def _observe_estimate(ports: Any, elapsed_seconds: float) -> None:
    observer = getattr(ports, "observer", None)
    if observer is None:
        return
    try:
        observer.observe(
            "pulsegrid_insurance_estimate_seconds",
            elapsed_seconds,
            {"owner": "billing"},
        )
    except Exception:
        return


@router.get(f"{_ROUTES}/insurance/providers")
async def list_providers(request: Request):
    ports = request.app.state.insurance_ports
    try:
        principal = await ports.authorize(
            request, ("billing_staff", "hospital_admin"), None, False
        )
        cursor, limit = _query(request, {"cursor", "limit"})
        async with ports.read_session() as session:
            page = await ports.repository.list_providers(session, cursor, limit)
        return JSONResponse(status_code=200, content=page, headers={"Cache-Control": "no-store"})
    except HTTPException:
        raise
    except InsuranceValidationError as error:
        if error.code=="source_revision_conflict":return _error(request,409,error.code)
        return _error(request, 422, "invalid_request")


@router.post(f"{_ROUTES}/insurance/providers/{{provider_id}}/refresh")
async def refresh_provider(provider_id: str, request: Request):
    ports = request.app.state.insurance_ports
    try:
        provider_id = validate_id(provider_id, name="provider_id")
        principal = await ports.authorize(
            request, ("billing_staff", "hospital_admin"), provider_id, True
        )
        body = await _request_json(request)
        if body:
            raise HTTPException(422, detail={"code": "invalid_request"})

        reserved_run_id=await ports.allocate_id()

        async def operation(session: Any, context: Any):
            run = await ports.repository.enqueue_run(session, provider_id, allocated_id=reserved_run_id)
            run_id = validate_id(run["id"], name="run_id")
            version = int(run.get("version", 1))
            return 202, {
                "run_id": run_id,
                "provider_id": provider_id,
                "state": "pending",
                "version": version,
            }, version

        result = await ports.command(
            request,
            principal,
            f"{_ROUTES}/insurance/providers/{{provider_id}}/refresh",
            body,
            request.headers.get("If-Match"),
            operation,
        )
        return _stored_response(result)
    except HTTPException:
        raise
    except InsuranceValidationError as error:
        if error.code=="source_revision_conflict":return _error(request,409,error.code)
        return _error(request, 422, "invalid_request")
    except KeyError:
        return _error(request, 404, "provider_not_found")


@router.get(f"{_ROUTES}/insurance/runs/{{run_id}}")
async def get_run(run_id: str, request: Request):
    ports = request.app.state.insurance_ports
    try:
        _query(request,set())
        run_id = validate_id(run_id, name="run_id")
        await ports.authorize(request, ("billing_staff", "hospital_admin"), run_id, False)
        async with ports.read_session() as session:
            run = await ports.repository.get_run(session, run_id)
        if run is None:
            return _error(request, 404, "run_not_found")
        return JSONResponse(status_code=200, content=run, headers={"Cache-Control": "no-store"})
    except HTTPException:
        raise
    except InsuranceValidationError as error:
        if error.code=="source_revision_conflict":return _error(request,409,error.code)
        return _error(request, 422, "invalid_request")


@router.post(f"{_ROUTES}/invoices/{{invoice_id}}/insurance-estimates")
async def create_estimate(invoice_id: str, request: Request):
    ports = request.app.state.insurance_ports
    try:
        invoice_id = validate_id(invoice_id, name="invoice_id")
        principal = await ports.authorize(request, ("patient", "billing_staff"), invoice_id, True)
        body = await _request_json(request)
        if set(body) != {"provider_id", "policy_code"} or not isinstance(body["policy_code"], str):
            raise HTTPException(422, detail={"code": "invalid_request"})
        provider_id = validate_id(body["provider_id"], name="provider_id")
        now = _current_time(ports)
        estimate_id = await ports.allocate_id()

        async def operation(session: Any, context: Any):
            started_ns = time.perf_counter_ns()
            try:
                invoice = await ports.read_invoice(session, invoice_id)
                if invoice is None:
                    raise HTTPException(404)
                stored = await ports.repository.policy_for_estimate(
                    session, provider_id, body["policy_code"], now
                )
                if stored is None:
                    raise HTTPException(409, detail={"code": "insurance_rules_unavailable"})
                policy_export = stored["policy_export"]
                snapshot = {
                    "id": invoice["id"],
                    "version": invoice["version"],
                    "balance_minor": invoice["balance_minor"],
                    "items": invoice["items"],
                    "_insurance": {
                        "estimate_id": estimate_id,
                        "provider_id": policy_export.provider_id,
                        "rules_id": stored["rules_id"],
                        "source_run_id": policy_export.source_run_id,
                        "source_id": policy_export.source_id,
                        "source_path": policy_export.source_path,
                        "source_version": policy_export.source_version,
                        "content_hash": policy_export.content_hash,
                        "observed_at": policy_export.observed_at,
                        "source_fetched_at": stored["source_fetched_at"],
                    },
                }
                result = estimate(
                    snapshot, policy_export.rule, stored.get("database_now", now)
                )
                await ports.repository.create_estimate(session, result)
                return 201, result, result["version"]
            finally:
                _observe_estimate(
                    ports, (time.perf_counter_ns() - started_ns) / 1_000_000_000
                )

        command_result = await ports.command(
            request,
            principal,
            f"{_ROUTES}/invoices/{{invoice_id}}/insurance-estimates",
            body,
            request.headers.get("If-Match"),
            operation,
        )
        return _stored_response(command_result)
    except HTTPException:
        raise
    except InsuranceValidationError as error:
        if error.code=="source_revision_conflict":return _error(request,409,error.code)
        return _error(request, 422, "invalid_request")


@router.get(f"{_ROUTES}/invoices/{{invoice_id}}/insurance-estimates")
async def list_estimates(invoice_id: str, request: Request):
    ports = request.app.state.insurance_ports
    try:
        invoice_id = validate_id(invoice_id, name="invoice_id")
        await ports.authorize(request, ("patient", "billing_staff"), invoice_id, False)
        cursor, limit = _query(request, {"cursor", "limit"})
        async with ports.read_session() as session:
            page = await ports.repository.list_estimates(session, invoice_id, cursor, limit)
        return JSONResponse(status_code=200, content=page, headers={"Cache-Control": "no-store"})
    except HTTPException:
        raise
    except InsuranceValidationError as error:
        if error.code=="source_revision_conflict":return _error(request,409,error.code)
        return _error(request, 422, "invalid_request")


def register_routes(app: Any, ports: Any) -> None:
    """Mount into a supplied test app; production mounting stays coordinator-owned."""
    app.state.insurance_ports = ports
    app.include_router(router)
