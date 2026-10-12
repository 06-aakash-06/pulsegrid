import asyncio
import json
from collections import Counter
from dataclasses import replace

import pytest
from pulsegrid_key_value_cache import Cache, CacheEntry, CacheUnavailable, InvalidEntry, logical_key, redis_client


class Placement:
    epoch = 1
    def locate(self, key: bytes) -> str:
        assert isinstance(key, bytes)
        return 'cache_a'


class Metrics:
    def __init__(self): self.counts = Counter()
    def increment(self, name, labels, value=1): self.counts[(name, labels.get('outcome', labels.get('kind')))] += value
    def observe(self, *args): pass
    def gauge(self, *args): pass


def build(port, **kwargs):
    return Cache(Placement(), {'cache_a': redis_client(f'redis://127.0.0.1:{port}')}, **kwargs)


def key(**kwargs):
    return logical_key(owner='doctor', schema=1, visibility={'tenant': 'synthetic', 'role': 'patient'}, revision=kwargs.get('revision', 1), filters={'q': 'synthetic'})


async def test_get_set_delete_metrics(redis_node):
    metrics = Metrics()
    c = build(redis_node[0], observer=metrics)
    try:
        assert await c.get(key()) is None
        e = CacheEntry(b'hello', 1, c.clock() + 30000)
        await c.set(key(), e, 30000)
        assert await c.get(key()) == e
        assert await c.invalidate(key())
        assert await c.get(key()) is None
        assert metrics.counts[('pulsegrid_cache_requests_total', 'hit')] == 1
        assert metrics.counts[('pulsegrid_cache_requests_total', 'miss')] == 2
    finally: await c.close()


async def test_cache_aside_concurrent(redis_node):
    c = build(redis_node[0], max_loaders=2)
    calls, active, maximum = 0, 0, 0
    async def loader():
        nonlocal calls, active, maximum
        calls += 1; active += 1; maximum = max(maximum, active)
        await asyncio.sleep(.005)
        active -= 1
        return CacheEntry(b'payload', 1, c.clock() + 30000)
    try:
        results = await asyncio.gather(*(c.get_or_load(key(), loader) for _ in range(12)))
        assert all(r.payload == b'payload' for r in results)
        assert maximum <= 2
        before = calls
        await c.get_or_load(key(), loader)
        assert calls == before
    finally: await c.close()


async def test_ttl_and_application_expiry(redis_node):
    now = [1000000]
    c = build(redis_node[0], clock=lambda: now[0])
    try:
        await c.set(key(), CacheEntry(b'a', 1, now[0]+100), 100)
        now[0] += 100
        assert await c.get(key()) is None
        await c.set(key(), CacheEntry(b'a', 1, now[0]+30), 30)
        await asyncio.sleep(.05)
        assert await c.get(key()) is None
    finally: await c.close()


@pytest.mark.parametrize('raw', [b'garbage', b'[]', b'null', b'{}', b'{"schema_version":2}', b'"a"', b'1', b'x'*65537])
async def test_corruption_miss(redis_node, raw):
    c = build(redis_node[0])
    try:
        client, physical = c._target(key())
        await client.set(physical, raw)
        assert await c.get(key()) is None
    finally: await c.close()


async def test_revision_owner_epoch_isolation(redis_node):
    c = build(redis_node[0]); other = build(redis_node[0], owner='pharmacy')
    try:
        await c.set(key(), CacheEntry(b'a', 1, c.clock()+30000), 30000)
        assert await c.get(key(revision=2)) is None
        assert await other.get(key()) is None
        c.placement.epoch = 2
        assert await c.get(key()) is None
    finally:
        await c.close(); await other.close()


async def test_redis_outage_and_recovery(redis_node):
    port, process = redis_node
    c = build(port)
    async def loader(): return CacheEntry(b'owner', 2, c.clock()+30000)
    try:
        await c.set(key(), CacheEntry(b'cached', 1, c.clock()+30000), 30000)
        process.terminate(); process.wait(timeout=5)
        assert (await c.get_or_load(key(), loader)).payload == b'owner'
        assert (await c.health())['state'] == 'degraded'
        assert not await c.invalidate(key())
        async def broken(): raise RuntimeError('owner503')
        with pytest.raises(RuntimeError, match='owner503'): await c.get_or_load(key(), broken)
    finally: await c.close()


async def test_deadline_observer_and_missing_node():
    class Slow:
        async def get(self, *args): await asyncio.sleep(1)
        async def aclose(self): pass
    class BadObserver:
        def increment(self, *args): raise RuntimeError()
        def observe(self, *args): raise RuntimeError()
    c = Cache(Placement(), {'cache_a': Slow()}, observer=BadObserver())
    start = asyncio.get_running_loop().time()
    with pytest.raises(CacheUnavailable): await c.get(key())
    assert asyncio.get_running_loop().time()-start < .2
    c.clients = {}
    with pytest.raises(CacheUnavailable): await c.get(key())
    await c.close()


async def test_entry_bounds(redis_node):
    c = build(redis_node[0], clock=lambda: 1000000)
    try:
        for e in [CacheEntry(b'x'*50000, 1, c.clock()+30000), CacheEntry(b'a', True, c.clock()+30000), CacheEntry(b'a', 1, c.clock()), CacheEntry(b'a', 1, c.clock()+60001)]:
            with pytest.raises(InvalidEntry): await c.set(key(), e, 30000)
        for ttl in [0, 60001, True]:
            with pytest.raises(InvalidEntry): await c.set(key(), CacheEntry(b'a', 1, c.clock()+30000), ttl)
    finally: await c.close()


async def test_loader_saturation_bypasses_to_owner(redis_node):
    metrics = Metrics(); c = build(redis_node[0], max_loaders=1, wait_ms=1, observer=metrics)
    async def loader():
        await asyncio.sleep(.03)
        return CacheEntry(b'owner', 1, c.clock()+30000)
    try:
        results = await asyncio.gather(*(c.get_or_load(key(), loader) for _ in range(5)))
        assert len(results) == 5
        assert metrics.counts[('pulsegrid_cache_requests_total', 'bypass')] >= 1
    finally: await c.close()


def test_key_stable_and_private():
    a = logical_key(owner='doctor', schema=1, revision=1, visibility={'role':'patient','tenant':'a'}, filters={'q':'Private name','limit':20})
    b = logical_key(owner='doctor', schema=1, revision=1, visibility={'tenant':'a','role':'patient'}, filters={'limit':20,'q':'Private name'})
    assert a == b
    c = Cache(Placement(), {'cache_a': object()})
    assert 'Private' not in c._target(a)[1]
    assert logical_key(owner='doctor', schema=1, revision=1, visibility={'tenant':'b','role':'patient'}, filters={'limit':20,'q':'Private name'}) != a


async def test_structural_ring_adapter_and_no_failure_reassignment(redis_node):
    class Snapshot:
        epoch = 7
    class FrozenRingSubstitute:
        def snapshot(self): return Snapshot()
        def locate(self, key: bytes): return 'cache_a'
    class RingAdapter:
        def __init__(self, ring): self.ring = ring
        @property
        def epoch(self): return self.ring.snapshot().epoch
        def locate(self, key): return self.ring.locate(key)
    c = Cache(RingAdapter(FrozenRingSubstitute()), {'cache_a':redis_client(f'redis://127.0.0.1:{redis_node[0]}')})
    try:
        assert ':7:' in c._target(key())[1]
        await c.set(key(), CacheEntry(b'v',1,c.clock()+30000),30000)
        assert (await c.get(key())).payload == b'v'
        redis_node[1].terminate(); redis_node[1].wait(timeout=5)
        with pytest.raises(CacheUnavailable): await c.get(key())
        assert c.placement.epoch == 7
    finally: await c.close()


async def test_cancellation_releases_loader(redis_node):
    c = build(redis_node[0], max_loaders=1)
    started = asyncio.Event()
    async def loader():
        started.set()
        await asyncio.sleep(10)
    task = asyncio.create_task(c.get_or_load(key(),loader))
    try:
        await started.wait(); task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert c._loaders._value == 1
    finally: await c.close()


async def test_shared_cache_aside_budget_and_no_retry_on_unavailable():
    class SlowClient:
        sets = 0
        async def get(self, key): await asyncio.sleep(.06); return None
        async def set(self, *args, **kwargs):
            self.sets += 1
            await asyncio.sleep(.08)
        async def aclose(self): pass
    client = SlowClient(); c = Cache(Placement(),{'cache_a':client})
    async def loader(): return CacheEntry(b'owner',1,c.clock()+30000)
    start = asyncio.get_running_loop().time()
    assert (await c.get_or_load(key(),loader)).payload == b'owner'
    assert asyncio.get_running_loop().time()-start < .13
    assert (await c.health())['state'] == 'degraded'
    class Unavailable(SlowClient):
        async def get(self,key): raise OSError()
    unavailable = Unavailable(); c.clients={'cache_a':unavailable}
    assert (await c.get_or_load(key(),loader)).payload == b'owner'
    assert unavailable.sets == 0
    await c.close()


@pytest.mark.parametrize('config', [{'ttl_ms':True}, {'ttl_ms':60001}, {'max_loaders':33}, {'wait_ms':0}])
def test_configuration_bounds(config):
    with pytest.raises(ValueError): Cache(Placement(), {}, **config)
