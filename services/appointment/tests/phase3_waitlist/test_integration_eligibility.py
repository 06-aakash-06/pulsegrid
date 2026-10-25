"""Production cancellation and scheduler wiring must use the Patient POST leaf."""
import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import httpx

from appointment_service import integration, integration_workers, operations as op
from appointment_service.dependencies import DomainClient
from appointment_service.features.journey.snapshots import SnapshotClient
from appointment_service.features.waitlist import eligibility, operations, worker


def application(monkeypatch):
    calls = []

    def transport(request):
        calls.append(request)
        assert request.method == 'POST'
        assert request.url.path == '/internal/v1/patients/waitlist-eligibility'
        assert request.headers['Authorization'] == 'Bearer synthetic-test-only'
        assert 'X-Delegated-Authorization' not in request.headers
        return httpx.Response(200, json={
            'items': [{'patient_id': '12', 'active': True, 'version': 1}],
            'observed_at': op.wire_time(op.now()),
        })

    monkeypatch.setattr(eligibility, 'service_token', lambda *args: 'synthetic-test-only')
    app = SimpleNamespace(state=SimpleNamespace(
        database=SimpleNamespace(session_factory=object()),
        domain_client=DomainClient(httpx.MockTransport(transport)),
        snapshot_client=SnapshotClient(httpx.MockTransport(transport)),
        auth_config=None,
        logger=Mock(),
    ))
    return app, calls


def test_booking_release_fetches_eligibility_through_service_post(monkeypatch):
    app, calls = application(monkeypatch)

    async def prepare(factory, slot_id, fetch):
        assert factory is app.state.database.session_factory
        assert slot_id == 7
        return await fetch(['12'])

    monkeypatch.setattr(operations, 'prepare', prepare)
    request = integration_workers.worker_request(app)
    result = asyncio.run(integration.prepare_release(request, {'slot_id': 7}))
    assert result.items[0].patient_id == '12'
    assert len(calls) == 1


def test_promotion_worker_uses_same_eligibility_leaf(monkeypatch):
    app, calls = application(monkeypatch)
    batches = []

    async def repair(factory):
        assert factory is app.state.database.session_factory

    async def promote(factory, request, fetch, **kwargs):
        batches.append(await fetch(['12']))
        return False

    async def no_journey(*args):
        return False

    async def end_tick(seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr(worker, 'repair', repair)
    monkeypatch.setattr(worker, 'run_once', promote)
    monkeypatch.setattr(integration_workers.journey, 'run_once', no_journey)
    monkeypatch.setattr(integration_workers.asyncio, 'sleep', end_tick)

    async def tick():
        try:
            await integration_workers.worker_loop(app)
        except asyncio.CancelledError:
            pass

    asyncio.run(tick())
    assert len(calls) == 1
    assert batches[0].items[0].patient_id == '12'
    app.state.logger.warning.assert_not_called()
