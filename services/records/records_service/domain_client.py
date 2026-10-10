"""Bounded authenticated REST calls. Never used while holding a DB lock."""

import asyncio
import os
import random
import time

import httpx
from fastapi import HTTPException

from .authorization import service_token
from .clinical_schemas import AppointmentContext, Medicines, PatientStatus, StaffStatus


class DomainClient:
    def __init__(self):
        self.failures = {}
        self.open_until = {}
        self.bases = {
            d: os.environ.get(
                f"PULSEGRID_RECORDS_{d.upper()}_URL", f"http://{d}:8000"
            ).rstrip("/")
            for d in ("patient", "appointment", "pharmacy")
        }

    async def call(
        self,
        request,
        principal,
        domain,
        scope,
        path,
        schema,
        *,
        body=None,
        key=None,
        version=None,
    ):
        if self.open_until.get(domain, 0) > time.monotonic():
            raise HTTPException(503)
        deadline = getattr(request.state, "domain_deadline", time.monotonic() + 5)
        request.state.domain_deadline = deadline
        headers = {
            "Authorization": "Bearer "
            + service_token(request.app.state.auth_config, scope, domain),
            "X-Delegated-Authorization": "Bearer " + principal.access_token,
            "X-Request-ID": str(request.state.request_id),
            "X-Correlation-ID": str(request.state.correlation_id),
        }
        if getattr(request.state, "traceparent", None):
            headers["traceparent"] = request.state.traceparent
        if key:
            headers["Idempotency-Key"] = key
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        for attempt in range(2 if key is None else 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HTTPException(504)
            try:
                async with asyncio.timeout(min(1, remaining)):
                    async with httpx.AsyncClient(
                        timeout=min(1, remaining),
                        trust_env=False,
                        follow_redirects=False,
                    ) as client:
                        async with client.stream(
                            "GET" if body is None else "POST",
                            self.bases[domain] + path,
                            headers=headers,
                            json=body,
                        ) as response:
                            data = bytearray()
                            async for chunk in response.aiter_bytes():
                                data.extend(chunk)
                                if len(data) > 262144:
                                    raise HTTPException(503)
                            status = response.status_code
                if status == 200:
                    result = schema.model_validate_json(data)
                    self.failures[domain] = 0
                    self.open_until.pop(domain, None)
                    return result.model_dump(mode="json")
                if status < 500:
                    if status in (401, 403, 404):
                        raise HTTPException(404)
                    if status == 422:
                        raise HTTPException(422, detail="invalid_reference")
                    if status in (409, 412, 428):
                        raise HTTPException(status)
                    raise HTTPException(503)
                failure = 503
            except (httpx.TimeoutException, TimeoutError):
                failure = 504
            except httpx.HTTPError:
                failure = 503
            except ValueError:
                raise HTTPException(503) from None
            self.failures[domain] = self.failures.get(domain, 0) + 1
            if self.failures[domain] >= 5:
                self.open_until[domain] = time.monotonic() + 15
                raise HTTPException(failure)
            if attempt == 0 and key is None:
                await asyncio.sleep(random.uniform(0.05, 0.15))
        raise HTTPException(failure)

    async def context(self, request, principal, appointment_id):
        result = await self.call(
            request,
            principal,
            "appointment",
            "appointments:consultation-context",
            f"/internal/v1/appointments/{appointment_id}/consultation-context",
            AppointmentContext,
        )
        if result["appointment_id"] != str(appointment_id):
            raise HTTPException(503)
        return result

    async def patient(self, request, principal, patient_id):
        try:
            result = await self.call(
                request,
                principal,
                "patient",
                "patients:status",
                f"/internal/v1/patients/{patient_id}/status",
                PatientStatus,
            )
        except HTTPException as exc:
            if exc.status_code == 404:
                raise HTTPException(422, detail="invalid_reference") from None
            raise
        if result["patient_id"] != str(patient_id):
            raise HTTPException(503)
        if not result["active"]:
            raise HTTPException(422, detail="invalid_reference")
        return result

    async def staff(self, request, principal, user_id):
        try:
            result = await self.call(
                request,
                principal,
                "patient",
                "users:staff-status",
                f"/internal/v1/users/{user_id}/staff-status",
                StaffStatus,
            )
        except HTTPException as exc:
            if exc.status_code == 404:
                raise HTTPException(422, detail="invalid_reference") from None
            raise
        if result["user_id"] != str(user_id):
            raise HTTPException(503)
        if not result["active"] or "doctor" not in result["roles"]:
            raise HTTPException(422, detail="invalid_reference")
        return result

    async def medicines(self, request, principal, ids):
        if not ids:
            return {}
        result = await self.call(
            request,
            principal,
            "pharmacy",
            "medicines:validate",
            "/internal/v1/medicines/validate",
            Medicines,
            body={"medicine_ids": ids},
        )
        items = result["items"]
        if len(items) != len(ids) or {i["id"] for i in items} != set(ids):
            raise HTTPException(503)
        if any(not i["active"] for i in items):
            raise HTTPException(422, detail="invalid_reference")
        return {i["id"]: i for i in items}

    async def hold(self, request, principal, preparation, *, finalize=False):
        suffix = "/finalize" if finalize else ""
        key = f"records-clinical-hold{'-finalize' if finalize else ''}-{preparation['consultation_id']}"
        result = await self.call(
            request,
            principal,
            "appointment",
            "appointments:clinical-hold",
            f"/internal/v1/appointments/{preparation['appointment_id']}/clinical-hold{suffix}",
            AppointmentContext,
            body={"consultation_id": str(preparation["consultation_id"])},
            key=key,
            version=preparation["hold_version"],
        )
        expected = "finalized" if finalize else "active"
        if (
            result["appointment_id"] != str(preparation["appointment_id"])
            or result["doctor_user_id"] != principal.user_id
            or result["clinical_hold"] != expected
            or result["state"] != "confirmed"
        ):
            raise HTTPException(503)
        return result
