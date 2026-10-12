"""Appointment control-route checks over a disposable database and ASGI app."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import text

from appointment_service.authorization import Principal
from appointment_service.database import Database
from appointment_service.features.surge_mode import PATH, router
from appointment_service.middleware import install_request_context
from appointment_service.errors import error_response
from appointment_service.logging_config import get_service_logger
from pulsegrid_rate_limiter import IdentityDeriver, SurgeModeSnapshot


class FakeLimiter:
    def __init__(self, snapshot=None):
        self.snapshot = snapshot or SurgeModeSnapshot('NORMAL', version=0)
        self.calls = 0
        self.lock = asyncio.Lock()

    async def surge_mode(self):
        return self.snapshot

    async def transition_surge_mode(self, snapshot, target, *, reason_code, operation_id,
                                    actor_digest, override):
        async with self.lock:
            self.calls += 1
            if snapshot.state == 'UNKNOWN':
                raise AssertionError('unavailable state must not attempt a transition')
            if snapshot.version != self.snapshot.version or snapshot.state != self.snapshot.state:
                return 'conflict', self.snapshot.state, self.snapshot
            previous = snapshot.state
            now = int(datetime.now(timezone.utc).timestamp() * 1000)
            updated = SurgeModeSnapshot(target, (snapshot.version or 0) + 1,
                now, now + 120000, reason_code, operation_id)
            self.snapshot = updated
            return 'applied', previous, updated


def make_app(settings, limiter, monkeypatch):
    monkeypatch.setenv('PULSEGRID_APPOINTMENT_PHASE3_ENABLED', 'false')
    monkeypatch.setenv('PULSEGRID_APPOINTMENT_PHASE4_ADMISSION_ENABLED', 'false')
    database = Database(settings)
    app = FastAPI()
    app.include_router(router)
    install_request_context(app)
    app.state.database = database
    app.state.logger = get_service_logger('appointment', 'ERROR')
    app.state.admission_limiter = limiter
    app.state.admission_adapter = SimpleNamespace(deriver=IdentityDeriver(b'synthetic-test-hmac-secret-' * 2))
    app.state.admission_error_response = error_response

    async def current_admin(request: Request):
        bearer = request.headers.get('Authorization')
        if bearer == 'Bearer synthetic-admin':
            return Principal('7001', None, frozenset({'hospital_admin'}), 1, 'synthetic-admin')
        if bearer == 'Bearer synthetic-user':
            raise HTTPException(403)
        raise HTTPException(401)

    for route in router.routes:
        for dependency in route.dependant.dependencies:
            if dependency.call.__name__ == 'dependency':
                app.dependency_overrides[dependency.call] = current_admin
    return app, database


def test_surge_api_requires_admin_and_audits_applied_transition(database, monkeypatch):
    limiter = FakeLimiter()
    app, db = make_app(database, limiter, monkeypatch)

    async def check():
        await db.start()
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                unauthorized = await client.post(PATH, json={'active': True, 'reason_code': 'capacity_pressure'},
                                                 headers={'X-Role': 'hospital_admin', 'Idempotency-Key': 'phase6-test-key-0001'})
                assert unauthorized.status_code == 401 and limiter.calls == 0
                forbidden = await client.post(PATH, json={'active': True, 'reason_code': 'capacity_pressure'},
                                              headers={'Authorization': 'Bearer synthetic-user', 'Idempotency-Key': 'phase6-test-key-0002'})
                assert forbidden.status_code == 403 and limiter.calls == 0
                invalid_override = await client.post(PATH,
                    json={'active': True, 'reason_code': 'incident_override', 'override': False},
                    headers={'Authorization': 'Bearer synthetic-admin', 'Idempotency-Key': 'phase6-test-key-0003'})
                assert invalid_override.status_code == 422 and limiter.calls == 0
                missing_key = await client.post(PATH,
                    json={'active': True, 'reason_code': 'capacity_pressure'},
                    headers={'Authorization': 'Bearer synthetic-admin'})
                assert missing_key.status_code == 422 and limiter.calls == 0

                activated = await client.post(PATH,
                    json={'active': True, 'reason_code': 'capacity_pressure'},
                    headers={'Authorization': 'Bearer synthetic-admin', 'Idempotency-Key': 'phase6-test-key-1001'})
                assert activated.status_code == 200 and activated.json()['state'] == 'SURGE'
                assert limiter.calls == 1
                limiter.snapshot = SurgeModeSnapshot('RECOVERY', 9, 123000, 999999, 'planned_recovery')
                replay = await client.post(PATH,
                    json={'active': True, 'reason_code': 'capacity_pressure'},
                    headers={'Authorization': 'Bearer synthetic-admin', 'Idempotency-Key': 'phase6-test-key-1001'})
                assert replay.status_code == 200 and replay.json() == activated.json()
                assert limiter.calls == 1
                conflict = await client.post(PATH,
                    json={'active': False, 'reason_code': 'planned_recovery'},
                    headers={'Authorization': 'Bearer synthetic-admin', 'Idempotency-Key': 'phase6-test-key-1001'})
                assert conflict.status_code == 409
                status = await client.get(PATH, headers={'Authorization': 'Bearer synthetic-admin'})
                assert status.status_code == 200 and status.json()['version'] == 9

            async with db.session_factory() as session:
                rows = (await session.execute(text(
                    "SELECT sequence,canonical_metadata FROM public.audit_entries "
                    "WHERE chain_id='appointment' ORDER BY sequence"))).mappings().all()
                assert [row['canonical_metadata']['action'] for row in rows] == [
                    'surge_mode_transition_requested', 'surge_mode_transition_applied']
                assert all(row['canonical_metadata']['actor_user_id'] == '7001' for row in rows)
                assert all(row['canonical_metadata']['reason_code'] == 'capacity_pressure' for row in rows)
                assert all('patient_id' not in row['canonical_metadata'] for row in rows)
        finally:
            await db.close()

    asyncio.run(check())


def test_surge_api_does_not_audit_or_claim_success_when_redis_state_is_unknown(database, monkeypatch):
    limiter = FakeLimiter(SurgeModeSnapshot('UNKNOWN'))
    app, db = make_app(database, limiter, monkeypatch)

    async def check():
        await db.start()
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                response = await client.post(PATH,
                    json={'active': True, 'reason_code': 'capacity_pressure'},
                    headers={'Authorization': 'Bearer synthetic-admin', 'Idempotency-Key': 'phase6-test-key-2001'})
                assert response.status_code == 503
                assert response.json()['error']['code'] == 'admission_unavailable'
            async with db.session_factory() as session:
                count = (await session.execute(text(
                    "SELECT count(*) FROM public.audit_entries WHERE chain_id='appointment'"))).scalar_one()
                assert count == 0
            assert limiter.calls == 0
        finally:
            await db.close()

    asyncio.run(check())


def test_surge_api_persists_noop_replay_and_rejects_key_reuse(database, monkeypatch):
    limiter = FakeLimiter()
    app, db = make_app(database, limiter, monkeypatch)

    async def check():
        await db.start()
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                headers = {'Authorization': 'Bearer synthetic-admin', 'Idempotency-Key': 'phase6-test-key-3001'}
                response = await client.post(PATH,
                    json={'active': False, 'reason_code': 'planned_recovery'}, headers=headers)
                assert response.status_code == 200 and response.json()['state'] == 'NORMAL'
                assert limiter.calls == 0
                replay = await client.post(PATH,
                    json={'active': False, 'reason_code': 'planned_recovery'}, headers=headers)
                assert replay.status_code == 200 and replay.json() == response.json()
                conflict = await client.post(PATH,
                    json={'active': True, 'reason_code': 'planned_recovery'}, headers=headers)
                assert conflict.status_code == 409 and limiter.calls == 0

            async with db.session_factory() as session:
                actions = (await session.execute(text(
                    "SELECT canonical_metadata->>'action' FROM public.audit_entries "
                    "WHERE chain_id='appointment' ORDER BY sequence"))).scalars().all()
                assert actions == ['surge_mode_transition_requested', 'surge_mode_transition_noop']
        finally:
            await db.close()

    asyncio.run(check())


def test_concurrent_equal_surge_commands_have_one_audited_effect(database, monkeypatch):
    limiter = FakeLimiter()
    app, db = make_app(database, limiter, monkeypatch)

    async def check():
        await db.start()
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                headers = {'Authorization': 'Bearer synthetic-admin', 'Idempotency-Key': 'phase6-test-key-4001'}
                responses = await asyncio.gather(*(
                    client.post(PATH, json={'active': True, 'reason_code': 'capacity_pressure'}, headers=headers)
                    for _ in range(4)
                ))
                assert [response.status_code for response in responses] == [200, 200, 200, 200]
                assert all(response.json()['state'] == 'SURGE' for response in responses)
                assert limiter.snapshot.version == 1

            async with db.session_factory() as session:
                rows = (await session.execute(text(
                    "SELECT canonical_metadata->>'action' FROM public.audit_entries "
                    "WHERE chain_id='appointment' ORDER BY sequence"))).scalars().all()
                assert rows == ['surge_mode_transition_requested', 'surge_mode_transition_applied']
        finally:
            await db.close()

    asyncio.run(check())
