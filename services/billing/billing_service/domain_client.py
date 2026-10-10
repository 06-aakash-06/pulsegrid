"""Bounded private REST reads for Billing's documented source contexts."""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass

import httpx
from fastapi import HTTPException, Request
from pydantic import ValidationError

from .authorization import Principal, service_token
from .schemas import (
    AppointmentBillingContext,
    ConsultationChargeContext,
    DispensingChargeContext,
)

MAX_BODY_BYTES = 256 * 1024
CALL_TIMEOUT_SECONDS = 1.0
TOTAL_TIMEOUT_SECONDS = 5.0


@dataclass
class Circuit:
    failures: int = 0
    opened_until: float = 0.0
    probe_active: bool = False
    lock: asyncio.Lock | None = None

    async def acquire(self) -> bool:
        if self.lock is None:
            self.lock = asyncio.Lock()
        async with self.lock:
            now = time.monotonic()
            if self.opened_until > now:
                return False
            if self.opened_until and self.probe_active:
                return False
            if self.opened_until:
                self.probe_active = True
            return True

    async def complete(self, succeeded: bool) -> None:
        if self.lock is None:
            self.lock = asyncio.Lock()
        async with self.lock:
            if succeeded:
                self.failures = 0
                self.opened_until = 0.0
                self.probe_active = False
            else:
                self.failures += 1
                self.probe_active = False
                if self.failures >= 5:
                    self.opened_until = time.monotonic() + 15.0


class DomainClient:
    def __init__(self, config):
        self.config = config
        self.circuits = {
            "appointment": Circuit(),
            "records": Circuit(),
            "pharmacy": Circuit(),
        }

    async def appointment_billing_context(
        self, request: Request, principal: Principal, appointment_id: str
    ) -> AppointmentBillingContext | None:
        value = await self._get(
            request,
            principal,
            service="appointment",
            scope="appointments:billing-context",
            base=self.config.appointment_url,
            path=f"/internal/v1/appointments/{appointment_id}/billing-context",
        )
        return self._parse(AppointmentBillingContext, value) if value is not None else None

    async def consultation_charge_context(
        self, request: Request, principal: Principal, consultation_id: str
    ) -> ConsultationChargeContext | None:
        value = await self._get(
            request,
            principal,
            service="records",
            scope="consultations:charge-context",
            base=self.config.records_url,
            path=f"/internal/v1/consultations/{consultation_id}/charge-context",
        )
        return self._parse(ConsultationChargeContext, value) if value is not None else None

    async def dispensing_charge_context(
        self, request: Request, principal: Principal, dispensing_id: str
    ) -> DispensingChargeContext | None:
        value = await self._get(
            request,
            principal,
            service="pharmacy",
            scope="dispensings:charge-context",
            base=self.config.pharmacy_url,
            path=f"/internal/v1/dispensings/{dispensing_id}/charge-context",
        )
        return self._parse(DispensingChargeContext, value) if value is not None else None

    @staticmethod
    def _parse(model, value):
        try:
            return model.model_validate(value)
        except ValidationError:
            raise HTTPException(
                503,
                detail={
                    "code": "dependency_unavailable",
                    "message": "A source service returned an invalid response.",
                },
            ) from None

    async def _get(
        self,
        request: Request,
        principal: Principal,
        *,
        service: str,
        scope: str,
        base: str,
        path: str,
    ) -> dict | None:
        circuit = self.circuits[service]
        if not await circuit.acquire():
            raise HTTPException(
                503,
                detail={"code": "dependency_unavailable", "message": "A required service is unavailable."},
                headers={"Retry-After": "1"},
            )
        client: httpx.AsyncClient = request.app.state.domain_http_client
        headers = {
            "Authorization": "Bearer " + service_token(self.config, scope, target=service),
            "X-Delegated-Authorization": "Bearer " + principal.access_token,
            "X-Request-ID": str(request.state.request_id),
            "X-Correlation-ID": str(request.state.correlation_id),
        }
        if request.state.traceparent:
            headers["traceparent"] = request.state.traceparent

        try:
            async with asyncio.timeout(TOTAL_TIMEOUT_SECONDS):
                for attempt in range(2):
                    try:
                        result = await client.get(
                            base + path,
                            headers=headers,
                            timeout=CALL_TIMEOUT_SECONDS,
                            follow_redirects=False,
                        )
                    except httpx.TimeoutException:
                        if attempt == 0:
                            await asyncio.sleep(random.uniform(0.05, 0.15))
                            continue
                        await circuit.complete(False)
                        raise HTTPException(
                            504,
                            detail={"code": "dependency_timeout", "message": "A required service did not respond in time."},
                        ) from None
                    except httpx.HTTPError:
                        if attempt == 0:
                            await asyncio.sleep(random.uniform(0.05, 0.15))
                            continue
                        await circuit.complete(False)
                        raise HTTPException(
                            503,
                            detail={"code": "dependency_unavailable", "message": "A required service is unavailable."},
                            headers={"Retry-After": "1"},
                        ) from None

                    if result.status_code >= 500:
                        if attempt == 0:
                            await asyncio.sleep(random.uniform(0.05, 0.15))
                            continue
                        await circuit.complete(False)
                        raise HTTPException(
                            503,
                            detail={"code": "dependency_unavailable", "message": "A required service is unavailable."},
                            headers={"Retry-After": "1"},
                        )
                    await circuit.complete(True)
                    if result.status_code == 404:
                        return None
                    if result.status_code != 200:
                        if result.status_code == 403:
                            raise HTTPException(403)
                        if result.status_code in (408, 504):
                            raise HTTPException(
                                504,
                                detail={"code": "dependency_timeout", "message": "A required service did not respond in time."},
                            )
                        if result.status_code == 422:
                            raise HTTPException(
                                422,
                                detail={"code": "invalid_reference", "message": "A referenced source is invalid."},
                            )
                        raise HTTPException(
                            503,
                            detail={"code": "dependency_unavailable", "message": "A required service is unavailable."},
                        )
                    if len(result.content) > MAX_BODY_BYTES:
                        raise HTTPException(503)
                    try:
                        body = result.json()
                    except ValueError:
                        raise HTTPException(503) from None
                    if not isinstance(body, dict):
                        raise HTTPException(503)
                    return body
        except TimeoutError:
            await circuit.complete(False)
            raise HTTPException(
                504,
                detail={"code": "dependency_timeout", "message": "A required service did not respond in time."},
            ) from None
        raise HTTPException(503)
