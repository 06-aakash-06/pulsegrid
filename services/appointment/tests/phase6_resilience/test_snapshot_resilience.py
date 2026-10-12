"""Focused retry, breaker and bulkhead checks for optional journey reads."""
import asyncio
from types import SimpleNamespace

import httpx
import pytest

from appointment_service.features.journey import snapshots
from appointment_service.features.journey.resilience import CircuitBreaker, CircuitOpen


def request_context():
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(auth_config=None, phase4_observer=None)),
        state=SimpleNamespace(request_id='synthetic-request', correlation_id='synthetic-correlation'))


def run(coro):
    return asyncio.run(coro)


def test_retries_one_safe_get_then_opens_and_half_open_recovers(monkeypatch):
    monkeypatch.setattr(snapshots, 'service_token', lambda *args: 'synthetic-service-token')
    calls = 0
    clock = [0.0]
    delays = []

    async def sleep(delay): delays.append(delay)

    def owner(_request):
        nonlocal calls
        calls += 1
        if calls <= 6:
            return httpx.Response(503, json={'error': 'synthetic-unavailable'})
        return httpx.Response(200, json={'revision': 1})

    client = snapshots.SnapshotClient(httpx.MockTransport(owner), clock=lambda: clock[0],
                                      sleep=sleep, jitter=lambda: 0)

    async def check():
        try:
            for _ in range(3):
                with pytest.raises(snapshots.SnapshotUnavailable):
                    await client.request(request_context(), 'records', 'workflow:records-read', '/synthetic')
            assert calls == 6  # Two bounded GET attempts per logical read.
            assert delays == [0.050, 0.050, 0.050]
            assert client.breakers['records'].state == 'OPEN'
            with pytest.raises(snapshots.SnapshotUnavailable):
                await client.request(request_context(), 'records', 'workflow:records-read', '/synthetic')
            assert calls == 6  # OPEN fails before another dependency request.
            clock[0] = 6.0
            assert await client.request(request_context(), 'records', 'workflow:records-read', '/synthetic') == {'revision': 1}
            assert calls == 7 and client.breakers['records'].state == 'CLOSED'
        finally:
            await client.close()

    run(check())


def test_ordinary_4xx_and_429_are_not_breaker_failures(monkeypatch):
    monkeypatch.setattr(snapshots, 'service_token', lambda *args: 'synthetic-service-token')

    async def check():
        for status in (401, 403, 409, 422, 429):
            calls = 0
            def owner(_request):
                nonlocal calls
                calls += 1
                return httpx.Response(status, headers={'Retry-After': 'not-a-date'} if status == 429 else {})
            client = snapshots.SnapshotClient(httpx.MockTransport(owner), jitter=lambda: 0)
            try:
                with pytest.raises(snapshots.SnapshotUnavailable):
                    await client.request(request_context(), 'records', 'workflow:records-read', '/synthetic')
                assert calls == 1
                assert client.breakers['records'].state == 'CLOSED'
                assert not client.breakers['records'].failures
            finally:
                await client.close()

        calls = 0
        def too_long_rate_limit(_request):
            nonlocal calls
            calls += 1
            return httpx.Response(429, headers={'Retry-After': '5'})
        client = snapshots.SnapshotClient(httpx.MockTransport(too_long_rate_limit), jitter=lambda: 0)
        try:
            with pytest.raises(snapshots.SnapshotUnavailable):
                await client.request(request_context(), 'records', 'workflow:records-read', '/synthetic')
            assert calls == 1 and not client.breakers['records'].failures
        finally:
            await client.close()

        calls = 0
        def rate_limited_then_ok(_request):
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(429, headers={'Retry-After': '0'})
            return httpx.Response(200, json={'revision': 2})
        client = snapshots.SnapshotClient(httpx.MockTransport(rate_limited_then_ok), jitter=lambda: 0)
        try:
            assert await client.request(request_context(), 'records', 'workflow:records-read', '/synthetic') == {'revision': 2}
            assert calls == 2 and client.breakers['records'].state == 'CLOSED'
        finally:
            await client.close()

    run(check())


def test_404_is_unknown_and_does_not_trip_breaker(monkeypatch):
    monkeypatch.setattr(snapshots, 'service_token', lambda *args: 'synthetic-service-token')
    client = snapshots.SnapshotClient(httpx.MockTransport(lambda _request: httpx.Response(404)))

    async def check():
        try:
            with pytest.raises(snapshots.SnapshotUnknown):
                await client.request(request_context(), 'records', 'workflow:records-read', '/synthetic')
            assert client.breakers['records'].state == 'CLOSED'
            assert not client.breakers['records'].failures
        finally:
            await client.close()

    run(check())


def test_circuit_breaker_rolling_window_and_single_half_open_probe():
    clock = [0.0]
    breaker = CircuitBreaker(clock=lambda: clock[0])

    async def check():
        for moment in (0.0, 1.0, 12.0):
            clock[0] = moment
            await breaker.failed(await breaker.acquire())
        assert breaker.state == 'CLOSED'  # Older failures fell outside the 10s window.
        for _ in range(2):
            await breaker.failed(await breaker.acquire())
        assert breaker.state == 'OPEN'
        clock[0] += 6.0
        async def try_probe():
            try: return await breaker.acquire()
            except CircuitOpen: return None
        probes = await asyncio.gather(*(try_probe() for _ in range(8)))
        assert sum(permit is not None for permit in probes) == 1
        probe = next(permit for permit in probes if permit is not None)
        assert probe.half_open_probe and breaker.state == 'HALF_OPEN'
        await breaker.cancelled(probe)
        assert breaker.state == 'HALF_OPEN' and not breaker.probe_in_flight
        next_probe = await breaker.acquire()
        await breaker.succeeded(next_probe)
        assert breaker.state == 'CLOSED' and not breaker.failures
        for _ in range(3): await breaker.failed(await breaker.acquire())
        assert breaker.state == 'OPEN'
        clock[0] += 6.0
        await breaker.failed(await breaker.acquire())  # A failed half-open probe reopens immediately.
        assert breaker.state == 'OPEN'
        with pytest.raises(CircuitOpen): await breaker.acquire()

    run(check())


def test_bulkhead_bounds_parallel_reads_and_releases_on_saturation(monkeypatch):
    monkeypatch.setattr(snapshots, 'service_token', lambda *args: 'synthetic-service-token')

    class GateStream(httpx.AsyncByteStream):
        def __init__(self, release, started):
            self.release, self.started = release, started
        async def __aiter__(self):
            self.started[0] += 1
            if self.started[0] == 2: self.release[0].set()
            await self.release[1].wait()
            yield b'{"revision": 1}'
        async def aclose(self): return None

    async def check():
        release = [asyncio.Event(), asyncio.Event()]
        started = [0]
        client = snapshots.SnapshotClient(httpx.MockTransport(
            lambda _request: httpx.Response(200, stream=GateStream(release, started))))
        context = request_context()
        async def read():
            return await client.request(context, 'records', 'workflow:records-read', '/synthetic')
        first = asyncio.create_task(read())
        second = asyncio.create_task(read())
        try:
            await asyncio.wait_for(release[0].wait(), 0.5)
            assert client.in_flight['records'] == 2
            with pytest.raises(snapshots.SnapshotUnavailable, match='dependency_saturated'):
                await read()
            release[1].set()
            assert await asyncio.gather(first, second) == [{'revision': 1}, {'revision': 1}]
            assert client.in_flight['records'] == 0
            assert client.bulkheads['records']._value == 2
        finally:
            release[1].set()
            for task in (first, second):
                if not task.done(): task.cancel()
            await asyncio.gather(first, second, return_exceptions=True)
            await client.close()

    run(check())


def test_total_deadline_and_cancellation_release_half_open_permit(monkeypatch):
    monkeypatch.setattr(snapshots, 'service_token', lambda *args: 'synthetic-service-token')

    class GateStream(httpx.AsyncByteStream):
        def __init__(self, entered, gate): self.entered, self.gate = entered, gate
        async def __aiter__(self):
            self.entered.set()
            await self.gate.wait()
            yield b'{"revision": 1}'
        async def aclose(self): return None

    async def check():
        clock = [0.0]
        entered = asyncio.Event()
        gate = asyncio.Event()
        client = snapshots.SnapshotClient(httpx.MockTransport(
            lambda _request: httpx.Response(200, stream=GateStream(entered, gate))), clock=lambda: clock[0])
        breaker = client._breaker(request_context(), 'records')
        try:
            for _ in range(3): await breaker.failed(await breaker.acquire())
            clock[0] = 6.0
            task = asyncio.create_task(client.request(
                request_context(), 'records', 'workflow:records-read', '/synthetic'))
            await asyncio.wait_for(entered.wait(), 0.5)
            assert breaker.state == 'HALF_OPEN' and breaker.probe_in_flight
            task.cancel()
            with pytest.raises(asyncio.CancelledError): await task
            assert breaker.state == 'HALF_OPEN' and not breaker.probe_in_flight
            assert client.in_flight['records'] == 0 and client.bulkheads['records']._value == 2

            gate.set()
            assert await client.request(request_context(), 'records', 'workflow:records-read', '/synthetic') == {'revision': 1}
            assert breaker.state == 'CLOSED'
        finally:
            gate.set()
            await client.close()

    run(check())


def test_total_timeout_is_bounded_and_counted_once(monkeypatch):
    monkeypatch.setattr(snapshots, 'service_token', lambda *args: 'synthetic-service-token')

    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            await asyncio.sleep(0.2)
            yield b'{"revision": 1}'
        async def aclose(self):
            return None

    async def check():
        calls = 0
        def owner(_request):
            nonlocal calls
            calls += 1
            return httpx.Response(200, stream=SlowStream())
        client = snapshots.SnapshotClient(httpx.MockTransport(owner))
        client.TOTAL_TIMEOUT_SECONDS = 0.05
        start = asyncio.get_running_loop().time()
        try:
            with pytest.raises(snapshots.SnapshotUnavailable):
                await client.request(request_context(), 'records', 'workflow:records-read', '/synthetic')
            elapsed = asyncio.get_running_loop().time() - start
            assert elapsed < 0.15
            assert calls == 1
            assert list(client.breakers['records'].failures)
        finally:
            await client.close()

    run(check())
