"""Bounded private HTTP clients for Doctor's documented leaf dependencies."""

from __future__ import annotations

import asyncio
import json
import random
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import Request

from .authorization import Principal, service_token

MAX_PRIVATE_RESPONSE_BYTES = 256 * 1024


class DependencyUnavailable(Exception):
    pass


class DependencyTimeout(Exception):
    pass


class RemoteResponse(Exception):
    def __init__(self, status_code: int, body: dict[str, Any] | None = None):
        self.status_code = status_code
        self.body = body or {}
        super().__init__(status_code)


@dataclass
class _Circuit:
    failures: int = 0
    opened_until: float = 0.0
    probe_in_flight: bool = False


class DoctorDependencyClient:
    """Use <=1 second safe GET attempts and a per-owner process-local circuit."""

    def __init__(self) -> None:
        self._circuits: dict[str, _Circuit] = {}
        self._guard = threading.Lock()

    def _permit(self, owner: str) -> bool:
        now = time.monotonic()
        with self._guard:
            circuit = self._circuits.setdefault(owner, _Circuit())
            if circuit.opened_until <= now:
                if circuit.opened_until and circuit.probe_in_flight:
                    return False
                if circuit.opened_until:
                    circuit.probe_in_flight = True
                return True
            return False

    def _success(self, owner: str) -> None:
        with self._guard:
            self._circuits[owner] = _Circuit()

    def _failure(self, owner: str) -> None:
        with self._guard:
            circuit = self._circuits.setdefault(owner, _Circuit())
            circuit.probe_in_flight = False
            circuit.failures += 1
            if circuit.failures >= 5:
                circuit.opened_until = time.monotonic() + 15.0

    async def _get(
        self,
        request: Request,
        principal: Principal,
        *,
        owner: str,
        scope: str,
        target: str,
        url: str,
    ) -> dict[str, Any]:
        if not self._permit(owner):
            raise DependencyUnavailable()
        try:
            service_jwt = service_token(request.app.state.auth_config, scope, target)
        except Exception as exc:
            self._failure(owner)
            raise DependencyUnavailable() from exc
        headers = {
            "Authorization": "Bearer " + service_jwt,
            "X-Delegated-Authorization": "Bearer " + principal.access_token,
            "X-Request-ID": str(request.state.request_id),
            "X-Correlation-ID": str(request.state.correlation_id),
        }
        if getattr(request.state, "traceparent", None):
            headers["traceparent"] = request.state.traceparent

        last_error: Exception | None = None
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(
                    timeout=1.0, follow_redirects=False, trust_env=False
                ) as client:
                    async with client.stream("GET", url, headers=headers) as response:
                        chunks = bytearray()
                        async for chunk in response.aiter_bytes():
                            chunks.extend(chunk)
                            if len(chunks) > MAX_PRIVATE_RESPONSE_BYTES:
                                raise DependencyUnavailable()
                        if response.status_code >= 500:
                            last_error = DependencyUnavailable()
                        else:
                            self._success(owner)
                            try:
                                body = json.loads(chunks) if chunks else {}
                            except (json.JSONDecodeError, UnicodeDecodeError):
                                raise DependencyUnavailable() from None
                            if not isinstance(body, dict):
                                raise DependencyUnavailable()
                            if response.status_code != 200:
                                raise RemoteResponse(response.status_code, body)
                            return body
            except RemoteResponse:
                raise
            except (httpx.TimeoutException, TimeoutError) as exc:
                last_error = exc
            except (httpx.HTTPError, DependencyUnavailable) as exc:
                last_error = exc
            if attempt == 0:
                await asyncio.sleep(random.uniform(0.05, 0.15))
        self._failure(owner)
        if isinstance(last_error, (httpx.TimeoutException, TimeoutError)):
            raise DependencyTimeout() from None
        raise DependencyUnavailable() from None

    async def staff_status(
        self, request: Request, principal: Principal, user_id: str
    ) -> dict[str, Any]:
        url = request.app.state.auth_config.patient_staff_status_url.format(
            user_id=user_id
        )
        return await self._get(
            request,
            principal,
            owner="patient",
            scope="users:staff-status",
            target="patient",
            url=url,
        )

    async def schedule_decision(
        self, request: Request, principal: Principal, proposal_id: str
    ) -> dict[str, Any]:
        url = request.app.state.auth_config.appointment_schedule_decision_url.format(
            proposal_id=proposal_id
        )
        return await self._get(
            request,
            principal,
            owner="appointment",
            scope="schedule-decisions:read",
            target="appointment",
            url=url,
        )

    async def operational_status(
        self, request: Request, principal: Principal, doctor_id: str
    ) -> dict[str, Any]:
        url = request.app.state.auth_config.appointment_operational_status_url.format(
            doctor_id=doctor_id
        )
        return await self._get(
            request,
            principal,
            owner="appointment",
            scope="schedules:status",
            target="appointment",
            url=url,
        )
