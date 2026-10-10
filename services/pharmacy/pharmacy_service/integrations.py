"""Bounded adapters for the Pharmacy service's frozen Records interfaces."""

from __future__ import annotations

import asyncio
import random
import re
import time
from dataclasses import dataclass

import httpx
from fastapi import HTTPException, Request

from .authorization import Principal, service_token, valid_id

_ID = re.compile(r"^[1-9][0-9]{0,18}$")


@dataclass(frozen=True)
class PrescriptionItemContext:
    item_id: str
    medicine_id: str
    quantity: int


@dataclass(frozen=True)
class PrescriptionContext:
    prescription_id: str
    consultation_id: str
    appointment_id: str
    patient_id: str
    journey_id: str | None
    revision: int
    state: str
    version: int
    items: tuple[PrescriptionItemContext, ...]


class CircuitBreaker:
    """Small process-local guard; PostgreSQL remains the source of correctness."""

    def __init__(self) -> None:
        self.failures = 0
        self.opened_at: float | None = None

    def check(self) -> None:
        if self.opened_at is not None and time.monotonic() - self.opened_at < 15:
            raise HTTPException(503, detail={"code": "dependency_unavailable"})
        if self.opened_at is not None:
            self.opened_at = None
            self.failures = 0

    def failed(self) -> None:
        self.failures += 1
        if self.failures >= 5:
            self.opened_at = time.monotonic()

    def succeeded(self) -> None:
        self.failures = 0
        self.opened_at = None


def _is_version(value: object) -> bool:
    return type(value) is int and 1 <= value <= 9_007_199_254_740_991


def _validate_context(payload: object, requested_id: str) -> PrescriptionContext:
    if not isinstance(payload, dict) or set(payload) != {
        "prescription_id",
        "consultation_id",
        "appointment_id",
        "patient_id",
        "journey_id",
        "revision",
        "state",
        "items",
        "version",
    }:
        raise ValueError("unexpected prescription context shape")
    for key in ("prescription_id", "consultation_id", "appointment_id", "patient_id"):
        value = payload[key]
        if not isinstance(value, str) or not _ID.fullmatch(value) or not valid_id(value):
            raise ValueError("invalid prescription context identifier")
    if payload["prescription_id"] != requested_id:
        raise ValueError("prescription context identifier mismatch")
    if payload["journey_id"] is not None:
        raise ValueError("unexpected journey reference")
    if payload["state"] not in ("issued", "revoked"):
        raise ValueError("invalid prescription state")
    if not _is_version(payload["revision"]) or not _is_version(payload["version"]):
        raise ValueError("invalid prescription version")
    raw_items = payload["items"]
    if not isinstance(raw_items, list) or len(raw_items) > 50:
        raise ValueError("invalid prescription items")
    items = []
    seen = set()
    for item in raw_items:
        if not isinstance(item, dict) or set(item) != {"id", "medicine_id", "quantity"}:
            raise ValueError("unexpected prescription item shape")
        item_id = item["id"]
        medicine_id = item["medicine_id"]
        quantity = item["quantity"]
        if (
            not isinstance(item_id, str)
            or not _ID.fullmatch(item_id)
            or not valid_id(item_id)
            or not isinstance(medicine_id, str)
            or not _ID.fullmatch(medicine_id)
            or not valid_id(medicine_id)
            or type(quantity) is not int
            or not 1 <= quantity <= 1_000_000
            or item_id in seen
        ):
            raise ValueError("invalid prescription item")
        seen.add(item_id)
        items.append(PrescriptionItemContext(item_id, medicine_id, quantity))
    return PrescriptionContext(
        prescription_id=payload["prescription_id"],
        consultation_id=payload["consultation_id"],
        appointment_id=payload["appointment_id"],
        patient_id=payload["patient_id"],
        journey_id=None,
        revision=payload["revision"],
        state=payload["state"],
        version=payload["version"],
        items=tuple(items),
    )


async def get_prescription_context(
    request: Request, principal: Principal, prescription_id: str
) -> PrescriptionContext:
    """GET a live Records snapshot before any Pharmacy transaction or lock."""
    breaker: CircuitBreaker = request.app.state.records_circuit
    breaker.check()
    config = request.app.state.auth_config
    token = service_token(
        config, "prescriptions:dispensing-context", target="records"
    )
    headers = {
        "Authorization": "Bearer " + token,
        "X-Delegated-Authorization": "Bearer " + principal.access_token,
        "X-Request-ID": str(request.state.request_id),
        "X-Correlation-ID": str(request.state.correlation_id),
    }
    if getattr(request.state, "traceparent", None):
        headers["traceparent"] = request.state.traceparent

    last_status: int | None = None
    timed_out = False
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(1.0),
                follow_redirects=False,
                trust_env=False,
                transport=getattr(request.app.state, "records_transport", None),
            ) as client:
                response = await client.get(
                    f"{config.records_url}/internal/v1/prescriptions/{prescription_id}/dispensing-context",
                    headers=headers,
                )
            if len(response.content) > 65536:
                breaker.failed()
                raise HTTPException(503, detail={"code": "dependency_unavailable"})
            if response.status_code == 200:
                try:
                    context = _validate_context(response.json(), prescription_id)
                except (ValueError, TypeError):
                    breaker.failed()
                    raise HTTPException(
                        503, detail={"code": "dependency_unavailable"}
                    ) from None
                breaker.succeeded()
                return context
            if response.status_code == 404:
                raise HTTPException(422, detail={"code": "invalid_reference"})
            if response.status_code == 403:
                raise HTTPException(403)
            if response.status_code < 500:
                breaker.failed()
                raise HTTPException(503, detail={"code": "dependency_unavailable"})
            breaker.failed()
            last_status = response.status_code
        except HTTPException:
            raise
        except httpx.TimeoutException:
            breaker.failed()
            timed_out = True
        except httpx.HTTPError:
            breaker.failed()
        if attempt == 0:
            await asyncio.sleep(random.uniform(0.05, 0.15))

    if timed_out and last_status is None:
        raise HTTPException(504, detail={"code": "dependency_timeout"})
    raise HTTPException(503, detail={"code": "dependency_unavailable"})
