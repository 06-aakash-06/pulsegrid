import asyncio
from dataclasses import replace
import hashlib
from time import perf_counter
import pytest
from redis.exceptions import ResponseError
from pulsegrid_rate_limiter import *
from pulsegrid_rate_limiter.limiter import SCRIPT, SCRIPT_SHA
from pulsegrid_rate_limiter.local import LocalBuckets

SECRET = b'synthetic-test-key-not-deployment!'*2

def config(server=None, **kw):
    values = dict(enabled=True, hmac_secret=SECRET, redis_endpoint=server.url if server else 'redis://127.0.0.1:1')
    values.update(kw)
    return LimiterConfig(**values)

def bucket(name='one', cap=12, rate=4, cost=1, policy='test'):
    return BucketRequest(hashlib.sha256(name.encode()).hexdigest(),
        BucketSpec(policy, cap, rate, cost, (cap*1000000+rate-1)//rate+1000))

@pytest.mark.parametrize('values', [
    {'capacity':0}, {'cost':13}, {'cost':True}, {'idle_ttl_ms':1},
    {'refill_milli_tokens_per_second':0}, {'capacity':2**53},
    {'policy_id':'x:spoof'}, {'refill_milli_tokens_per_second':2**53-1}])
def test_invalid_spec(values):
    with pytest.raises(InvalidConfiguration):
        replace(bucket().spec, **values)

@pytest.mark.parametrize('values', [{'max_replicas':0}, {'enabled':'true'},
    {'hmac_secret':b'short'}, {'command_timeout_ms':51}, {'decision_timeout_ms':101},
    {'local_bounded_key_capacity':10001}, {'policy_version':'v2'}])
def test_invalid_config(values):
    with pytest.raises(InvalidConfiguration):
        config(**values)

async def test_capacity_compound_and_retry(redis_server):
    limiter = RateLimiter(config(redis_server))
    a, b = bucket('a',cap=4), bucket('b',cap=8)
    try:
        for _ in range(4):
            assert (await limiter.admit([a, b])).allowed
        old = await limiter.redis.hgetall(limiter.key(b))
        result = await limiter.admit([a,b])
        assert not result.allowed and result.mode == 'redis' and 249000 <= result.retry_after_ms <= 250000
        assert await limiter.redis.hgetall(limiter.key(b)) == old
        assert rejection_metadata(result)[0:2] == (429, 'rate_limited')
        assert rejection_metadata(result)[2]['Retry-After'] == '250'
    finally:
        await limiter.close()

async def test_real_concurrent_replicas_exact_burst(redis_server):
    limiters = [RateLimiter(config(redis_server)) for _ in range(4)]
    buckets = [bucket('a',cap=40,rate=4),bucket('b',cap=100,rate=4),bucket('c',cap=200,rate=4)]
    try:
        await limiters[0].redis.script_load(SCRIPT)
        semaphore = asyncio.Semaphore(16)
        async def consume(i):
            async with semaphore:
                return await limiters[i%4].admit(buckets)
        results = await asyncio.gather(*(consume(i) for i in range(140)))
        assert all(r.mode == 'redis' for r in results)
        assert sum(r.allowed for r in results) == 40
        assert int(await limiters[0].redis.hget(limiters[0].key(buckets[1]),'tokens')) >= 60000
    finally:
        await asyncio.gather(*(l.close() for l in limiters))

async def test_fractional_redis_refill_clock_rollback_and_expiry(redis_server):
    l = RateLimiter(config(redis_server))
    b = bucket(cap=4,rate=100)
    try:
        for _ in range(4): assert (await l.admit([b])).allowed
        # Seed exact past time; script itself still uses real Redis TIME.
        sec, usec = await l.redis.time()
        now = sec*1000+usec//1000
        await l.redis.hset(l.key(b), mapping={'last':now-1250,'tokens':0,'carry':0})
        result = await l.admit([b])
        assert not result.allowed and 125 <= result.remaining_milli_tokens <= 135
        assert 8650 <= result.retry_after_ms <= 8750
        await l.redis.hset(l.key(b), mapping={'last':now+10000,'tokens':0,'carry':0})
        assert (await l.admit([b])).remaining_milli_tokens == 0
        await l.redis.hset(l.key(b), mapping={'last':now-40000,'tokens':0,'carry':0})
        assert (await l.admit([b])).allowed
        assert await l.redis.pttl(l.key(b)) > 40000
        # Long idle clamps before multiplication and caps refill.
        await l.redis.hset(l.key(b), mapping={'last':0,'tokens':0,'carry':0})
        assert (await l.admit([b])).remaining_milli_tokens == 3000
    finally: await l.close()

async def test_noscript(redis_server):
    l = RateLimiter(config(redis_server))
    try:
        assert (await l.admit([bucket()])).allowed
        await l.redis.script_flush()
        assert (await l.admit([bucket()])).mode == 'redis'
    finally: await l.close()

async def test_script_type_validation_before_any_write(redis_server):
    l = RateLimiter(config(redis_server))
    a,b = bucket('a'),bucket('b')
    try:
        await l.redis.set(l.key(b),'wrong-type')
        with pytest.raises(ResponseError, match='INVALID_TYPE'):
            await l.redis.eval(SCRIPT, 2, l.key(a),l.key(b),12000,4,1000,3001000,12000,4,1000,3001000)
        assert not await l.redis.exists(l.key(a))
    finally: await l.close()

async def test_policy_change_is_unavailable(redis_server):
    l = RateLimiter(config(redis_server))
    try:
        assert (await l.admit([bucket()])).allowed
        result = await l.admit([bucket(cap=16)])
        assert result.reason == 'unavailable'
    finally: await l.close()

class FailedRedis:
    def __init__(self, error=None, slow=False): self.error=error; self.calls=0; self.slow=slow
    async def evalsha(self,*args):
        self.calls += 1
        if self.slow: await asyncio.sleep(1)
        raise self.error or ConnectionError('offline')
    async def aclose(self): pass

@pytest.mark.parametrize('error', [ResponseError('OOM command not allowed'), ResponseError('BUSY running script'), OSError('offline')])
async def test_errors_conservative_nonresetting(error):
    l = RateLimiter(config(), redis_client=FailedRedis(error))
    b=bucket(cap=8,rate=4)
    results = [await l.admit([b]) for _ in range(10)]
    assert sum(r.allowed for r in results)==2
    assert all(r.mode=='local' for r in results)
    assert (await l.health())['state']=='degraded'

async def test_timeout_ambiguity_no_transport_retry():
    fake=FailedRedis(slow=True)
    l=RateLimiter(config(decision_timeout_ms=20),redis_client=fake)
    start=perf_counter()
    result=await l.admit([bucket()])
    assert result.mode=='local' and fake.calls==1 and perf_counter()-start < .15

async def test_cardinality_and_aggregate_do_not_fail_open():
    l=RateLimiter(config(local_bounded_key_capacity=2),redis_client=FailedRedis(OSError()))
    assert (await l.admit([bucket('a'),bucket('aggregate')])).allowed
    assert (await l.admit([bucket('new'),bucket('aggregate')])).reason=='unavailable'
    assert len(l.local.states)==2

async def test_local_partitions_all_replicas():
    ls=[RateLimiter(config(),redis_client=FailedRedis(OSError())) for _ in range(4)]
    results=await asyncio.gather(*(ls[i%4].admit([bucket(cap=12)]) for i in range(50)))
    assert sum(r.allowed for r in results)==12

async def test_real_outage_two_seconds_and_recovery(redis_server):
    l=RateLimiter(config(redis_server))
    b=bucket(cap=8,rate=4)
    try:
        assert (await l.admit([b])).allowed
        assert (await l.admit([b])).allowed
        redis_server.stop()
        for _ in range(8):
            assert not (await l.admit([b])).allowed  # shadow exhausted local budget
        await asyncio.sleep(2)
        assert not (await l.admit([b])).allowed
        redis_server.start()
        result=await l.admit([b])
        assert result.allowed and result.mode=='redis'
        redis_server.stop()
        assert not (await l.admit([b])).allowed  # repeated transition never resets local
        redis_server.start()
        assert (await l.admit([b])).mode=='redis'
        assert (await l.health())['state']=='ok'
    finally: await l.close()

async def test_disabled_and_invalid_requests(redis_server):
    l=RateLimiter(LimiterConfig())
    assert (await l.health())['state']=='disabled'
    assert (await l.admit([bucket()])).allowed
    for buckets in ([], [bucket()]*4, [bucket()]*2, [bucket(cap=1)], [object()]):
        assert (await l.admit(buckets)).reason=='unavailable'

async def test_observer_failures_do_not_affect_admission(redis_server):
    class Broken:
        def increment(self,*a): raise RuntimeError('observer failed')
        def observe(self,*a): raise RuntimeError('observer failed')
    l=RateLimiter(config(redis_server),observer=Broken())
    try: assert (await l.admit([bucket()])).allowed
    finally: await l.close()

def test_local_fractional_precision_and_safe_eviction():
    from pulsegrid_rate_limiter.limiter import KeyedBucket
    clock=[0]
    local=LocalBuckets(4,1,lambda:clock[0])
    b=KeyedBucket('one',bucket(cap=4,rate=100).spec)
    assert local.decide([b]).allowed
    for ms in range(1,40001):
        clock[0]=ms*1000000
        result=local.decide([b])
        if ms < 40000: assert not result.allowed
    assert result.allowed
    clock[0] += 1000*1000000
    assert local.decide([KeyedBucket('new', b.spec)]).reason=='unavailable'
    clock[0] += 50000*1000000
    assert local.decide([KeyedBucket('new', b.spec)]).allowed

async def test_invalid_redis_state_cannot_select_fresh_local_quota(redis_server):
    first=RateLimiter(config(redis_server))
    new_replica=RateLimiter(config(redis_server))
    try:
        b=bucket()
        await first.redis.set(first.key(b),'corrupt')
        assert (await new_replica.admit([b])).reason=='unavailable'
        assert not new_replica.local.states
    finally: await first.close(); await new_replica.close()

async def test_timeout_after_real_consumption_does_not_reexecute(redis_server):
    from redis.asyncio import Redis
    client=Redis.from_url(redis_server.url)
    class Ambiguous:
        calls=0
        async def evalsha(self,*args):
            self.calls+=1
            result=await client.evalsha(*args)
            raise TimeoutError('lost response after consumption')
        async def aclose(self): await client.aclose()
    fake=Ambiguous()
    l=RateLimiter(config(redis_server),redis_client=fake)
    try:
        await client.script_load(SCRIPT)
        b=bucket(cap=8)
        assert (await l.admit([b])).allowed
        assert fake.calls==1
        assert int(await client.hget(l.key(b),'tokens'))==7000
        assert (await l.admit([b])).allowed
        assert not (await l.admit([b])).allowed
        assert fake.calls==3
    finally: await l.close()

async def test_real_redis_oom_and_recovery(redis_server):
    l=RateLimiter(config(redis_server))
    try:
        await l.redis.script_load(SCRIPT)
        await l.redis.config_set('maxmemory',1)
        result=await l.admit([bucket()])
        assert result.mode=='local' and result.allowed
    finally:
        await l.redis.config_set('maxmemory',64*1024*1024)
    try:
        assert (await l.admit([bucket()])).mode=='redis'
    finally: await l.close()

async def test_real_redis_busy_bounded_script(redis_server):
    from redis.asyncio import Redis
    client=Redis.from_url(redis_server.url,socket_timeout=2)
    l=RateLimiter(config(redis_server))
    try:
        await client.script_load(SCRIPT)
        await client.config_set('lua-time-limit',1)
        # Finite read-only test script, owns this disposable Redis, no writes.
        script="local s=redis.call('TIME'); local start=s[1]*1000000+s[2]; for i=1,1000000 do local t=redis.call('TIME'); if t[1]*1000000+t[2]-start>300000 then break end end return 1"
        task=asyncio.create_task(client.eval(script,0))
        await asyncio.sleep(.03)
        result=await l.admit([bucket()])
        assert result.mode=='local' and result.allowed
        await task
        await client.config_set('lua-time-limit',5000)
        assert (await l.admit([bucket()])).mode=='redis'
    finally:
        await client.aclose(); await l.close()

@pytest.mark.parametrize('message', ['NOPERM permission denied', 'CROSSSLOT keys mismatch', 'unknown command EVALSHA'])
async def test_redis_configuration_errors_fail_closed(message):
    l=RateLimiter(config(),redis_client=FailedRedis(ResponseError(message)))
    assert (await l.admit([bucket()])).reason=='unavailable'
    assert not l.local.states

def test_denied_local_churn_does_not_allocate_new_identities():
    from pulsegrid_rate_limiter.limiter import KeyedBucket
    local=LocalBuckets(4,10000,lambda:0)
    spec=bucket(cap=4,rate=100).spec
    agg=KeyedBucket('aggregate',spec)
    assert local.decide([KeyedBucket('first',spec),agg]).allowed
    for i in range(100):
        assert not local.decide([KeyedBucket(f'new-{i}',spec),agg]).allowed
    assert len(local.states)==2


async def test_redis_bad_credentials_fail_closed():
    from redis.exceptions import AuthenticationError
    l=RateLimiter(config(),redis_client=FailedRedis(AuthenticationError('invalid password')))
    assert (await l.admit([bucket()])).reason=='unavailable'
    assert not l.local.states

async def test_metric_labels_and_mode_transitions(redis_server):
    class Capture:
        def __init__(self): self.events=[]
        def increment(self,name,labels,value=1): self.events.append((name,dict(labels),value))
        def observe(self,name,seconds,labels): self.events.append((name,dict(labels),seconds))
    observer=Capture()
    l=RateLimiter(config(redis_server),observer=observer)
    try:
        await l.admit([bucket()])
        redis_server.stop()
        await l.admit([bucket()])
        redis_server.start()
        await l.admit([bucket()])
        transitions=[e for e in observer.events if e[0]=='pulsegrid_admission_mode_transitions_total']
        assert len(transitions)==2
        for _,labels,_ in observer.events:
            assert set(labels) <= {'policy','outcome','backend'}
            assert labels['policy']=='test'
    finally: await l.close()

async def test_heterogeneous_compound_policies_are_atomic(redis_server):
    l=RateLimiter(config(redis_server))
    a,b=bucket('a',cap=4,policy='source_gate'),bucket('b',cap=8,policy='principal_gate')
    try:
        for _ in range(4): assert (await l.admit([a,b])).allowed
        old=await l.redis.hgetall(l.key(b))
        assert not (await l.admit([a,b])).allowed
        assert await l.redis.hgetall(l.key(b))==old
    finally: await l.close()

async def test_varying_request_cost_matches_redis_and_local(redis_server):
    l=RateLimiter(config(redis_server))
    a=bucket(cap=16,rate=4,cost=1)
    b=bucket(cap=16,rate=4,cost=2)
    try:
        assert (await l.admit([a])).allowed
        assert (await l.admit([b])).allowed
        assert int(await l.redis.hget(l.key(a),'tokens')) >= 13000
        redis_server.stop()
        assert (await l.admit([a])).allowed # 4 local tokens - shadow 1 - shadow 2 - 1
        assert not (await l.admit([b])).allowed
    finally: await l.close()

def test_saturated_eviction_work_is_bounded():
    from pulsegrid_rate_limiter.limiter import KeyedBucket
    clock=[0]
    local=LocalBuckets(4,100,lambda:clock[0])
    spec=bucket(cap=4,rate=100).spec
    for i in range(100): assert local.decide([KeyedBucket(str(i),spec)]).allowed
    clock[0]=100000*1000000
    count=[0]
    original=local._refill
    def measured(s,now):
        count[0]+=1
        return original(s,now)
    local._refill=measured
    assert local.decide([KeyedBucket('new',spec)]).allowed
    assert count[0] <= 32

def test_eviction_never_removes_a_requested_bucket_from_cardinality_accounting():
    from pulsegrid_rate_limiter.limiter import KeyedBucket
    clock=[0]
    local=LocalBuckets(4,2,lambda:clock[0])
    spec=bucket(cap=4,rate=100).spec
    a,b,c=[KeyedBucket(name,spec) for name in ('a','b','c')]
    assert local.decide([a]).allowed
    assert local.decide([b]).allowed
    clock[0]=100000*1000000
    assert local.decide([a,c]).allowed
    assert set(local.states)=={'a','c'} and len(local.states)==2
