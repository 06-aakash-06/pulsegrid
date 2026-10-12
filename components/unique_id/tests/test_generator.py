import asyncio
import os
import pytest
from pulsegrid_unique_id import Config, EPOCH_MS, Generator, IdUnavailable, Reservation, PostgresWorkerStore, worker_identity


class Clock:
    def __init__(self): self.now = EPOCH_MS + 1000
    def __call__(self): return self.now
    async def sleep(self, seconds): self.now += 1


class FakeStore:
    def __init__(self): self.end = 0; self.owned = False
    async def open(self, worker_id):
        if self.owned: raise IdUnavailable('worker_conflict')
        self.owned = True
    async def reserve(self, worker_id, now_ms, span_ms):
        start = max(now_ms, self.end + 1)
        self.end = start + span_ms - 1
        return Reservation(start, self.end)
    async def assert_owned(self, worker_id):
        if not self.owned: raise IdUnavailable('ownership_lost')
    async def close(self): self.owned = False


async def make(config=None):
    clock, store = Clock(), FakeStore()
    g = Generator(config or Config(256), store, clock=clock, sleep=clock.sleep)
    await g.start()
    return g, clock, store


async def test_layout_parallel_overflow():
    g, clock, _ = await make()
    ids = await asyncio.gather(*(g.next_id() for _ in range(5000)))
    assert ids == sorted(set(ids))
    assert g.decode(ids[0]) == dict(timestamp_ms=EPOCH_MS+1000, worker_id=256, sequence=0)
    assert g.decode(ids[4095])['sequence'] == 4095
    assert g.decode(ids[4096])['timestamp_ms'] == EPOCH_MS+1001


@pytest.mark.parametrize('rollback', [1, 100, 10000])
async def test_rollback(rollback):
    g, clock, _ = await make()
    await g.next_id()
    clock.now -= rollback
    with pytest.raises(IdUnavailable): await g.next_id()
    clock.now += rollback + 10
    with pytest.raises(IdUnavailable): await g.next_id()
    assert g.health()['state'] == 'degraded'


async def test_restart_skips_reserved_range_and_close():
    g, clock, store = await make()
    before = await g.next_id()
    end = store.end
    await g.close()
    await g.start()
    after = await g.next_id()
    assert after > before and g.decode(after)['timestamp_ms'] > end
    await g.close()
    with pytest.raises(IdUnavailable): await g.next_id()


@pytest.mark.parametrize('now', [EPOCH_MS-1, EPOCH_MS+(1<<41), True, 1.5])
async def test_invalid_timestamp(now):
    c = Clock(); c.now = now
    with pytest.raises(IdUnavailable): await Generator(Config(256), FakeStore(), clock=c).start()


async def test_workers_and_conflicts():
    workers = [await make(Config(i)) for i in range(16)]
    ids = [await g.next_id() for g, _, _ in workers]
    assert len(set(ids)) == 16
    g, c, s = workers[0]
    with pytest.raises(IdUnavailable): await Generator(Config(0), s, clock=c).start()


async def test_ownership_loss_and_observer_failure():
    g, _, s = await make()
    g.observer = object()
    await g.next_id()
    s.owned = False
    with pytest.raises(IdUnavailable): await g.next_id()


async def test_deadline():
    g, c, _ = await make(Config(256, sequence_bits=1, timestamp_bits=52, wait_ms=10))
    g.sleep = asyncio.sleep
    await g.next_id(); await g.next_id()
    with pytest.raises(IdUnavailable, match='deadline'): await g.next_id()


@pytest.mark.parametrize('kwargs', [{'worker_id': -1}, {'worker_id': True}, {'worker_id':1024}, {'worker_id':896}, {'worker_id':1,'span_ms':1001}, {'worker_id':1,'timestamp_bits':40}])
def test_bad_config(kwargs):
    with pytest.raises(ValueError): Config(**kwargs)


def test_partition_decode():
    assert worker_identity(5,127) == 767
    for codes in [(7,0),(0,128),(True,0)]:
        with pytest.raises(ValueError): worker_identity(*codes)
    g = Generator(Config(0), FakeStore())
    for value in [0,-1,1<<63,True,'12']:
        with pytest.raises(ValueError): g.decode(value)


async def test_postgres_restart_conflict_loss_rollback():
    dsn = os.environ['ID_TEST_DSN']
    import psycopg
    async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as conn:
        await conn.execute('TRUNCATE id_worker_state')
    c = Clock()
    s = PostgresWorkerStore(dsn)
    g = Generator(Config(256), s, clock=c, sleep=c.sleep)
    await g.start()
    other = Generator(Config(256), PostgresWorkerStore(dsn), clock=c)
    with pytest.raises(IdUnavailable, match='worker_conflict'): await other.start()
    value = await g.next_id()
    async with s._connection.transaction():
        await s._connection.execute('CREATE TEMP TABLE rollback_entity(id bigint PRIMARY KEY)')
        await s._connection.execute('INSERT INTO rollback_entity VALUES (%s)', (value,))
        await s._connection.execute('ROLLBACK')
    end = g._range.end_ms
    await g.close()
    replacement = Generator(Config(256), PostgresWorkerStore(dsn), clock=c, sleep=c.sleep)
    await replacement.start()
    assert replacement.decode(await replacement.next_id())['timestamp_ms'] > end
    await replacement.store._connection.close()
    with pytest.raises(IdUnavailable): await replacement.next_id()
    await replacement.close()

async def test_postgres_cross_process_duplicate():
    import subprocess, sys
    dsn = os.environ['ID_TEST_DSN']
    store = PostgresWorkerStore(dsn)
    await store.open(300)
    try:
        code = '''import asyncio, os
from pulsegrid_unique_id import PostgresWorkerStore, IdUnavailable
async def run():
 s=PostgresWorkerStore(os.environ['ID_TEST_DSN'])
 try:
  await s.open(300)
 except IdUnavailable as e:
  assert str(e)=='worker_conflict'
 else:
  raise AssertionError('duplicate worker accepted')
 finally:
  await s.close()
asyncio.run(run())'''
        result = await asyncio.to_thread(subprocess.run, [sys.executable,'-c',code], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        await store.assert_owned(300)
    finally:
        await store.close()


async def test_postgres_commit_without_issue_restart():
    dsn = os.environ['ID_TEST_DSN']
    store = PostgresWorkerStore(dsn)
    c = Clock()
    g = Generator(Config(301), store, clock=c, sleep=c.sleep)
    await g.start()
    end = g._range.end_ms
    await g.close()
    await g.start()
    assert g.decode(await g.next_id())['timestamp_ms'] > end
    await g.close()


async def test_explicit_advisory_unlock_poison():
    g = Generator(Config(302), PostgresWorkerStore(os.environ['ID_TEST_DSN']))
    await g.start()
    await g.store._connection.execute('SELECT pg_advisory_unlock(74104,302)')
    with pytest.raises(IdUnavailable, match='ownership_lost'): await g.next_id()
    await g.close()

async def test_store_start_error_is_typed():
    class Broken(FakeStore):
        async def open(self, worker_id): raise OSError('private backend detail')
    g = Generator(Config(256), Broken())
    with pytest.raises(IdUnavailable, match='store_unavailable'): await g.start()
    assert g.health()['state'] == 'degraded'


async def test_cancel_wait_poison():
    g, _, s = await make()
    await g.close(); await g.start()
    async def block(seconds): await asyncio.Event().wait()
    g.sleep = block
    task = asyncio.create_task(g.next_id())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert g.health()['state'] == 'degraded'
    await g.close()


async def test_postgres_whole_command_pk_retry_only():
    import psycopg
    dsn = os.environ['ID_TEST_DSN']
    g = Generator(Config(303), PostgresWorkerStore(dsn))
    await g.start()
    async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as c:
        await c.execute('CREATE TEMP TABLE retry_entities(id bigint CONSTRAINT entity_pk PRIMARY KEY, amount int CHECK(amount>0))')
        await c.execute('CREATE TEMP TABLE retry_effects(value int)')
        duplicate = await g.next_id()
        await c.execute('INSERT INTO retry_entities VALUES (%s,1)', (duplicate,))
        attempts = 0
        async def command(amount, always_duplicate=False):
            nonlocal attempts
            for attempt in range(3):
                value = duplicate if always_duplicate or attempt==0 else await g.next_id()
                attempts += 1
                try:
                    async with c.transaction():
                        await c.execute('INSERT INTO retry_effects VALUES (1)')
                        await c.execute('INSERT INTO retry_entities VALUES (%s,%s)', (value,amount))
                    return value
                except psycopg.errors.UniqueViolation as e:
                    if e.diag.constraint_name != 'entity_pk': raise
            raise IdUnavailable('collision_retry_exhausted')
        assert await command(1) != duplicate
        assert (await (await c.execute('SELECT count(*) FROM retry_effects')).fetchone())[0] == 1
        attempts = 0
        with pytest.raises(IdUnavailable, match='collision_retry_exhausted'): await command(1, True)
        assert attempts == 3
        attempts = 0
        # First command attempt has a duplicate PK; use CHECK violation independently.
        with pytest.raises(psycopg.errors.CheckViolation): await command(-1)
        assert attempts == 1  # PostgreSQL CHECK validation precedes PK conflict.
    await g.close()

async def test_rollover_reservation_and_epoch_zero():
    g, c, s = await make(Config(0,span_ms=1))
    a = await g.next_id()
    c.now += 1
    b = await g.next_id()
    assert b > a and s.end == c.now
    c = Clock(); c.now = EPOCH_MS
    g = Generator(Config(0),FakeStore(),clock=c,sleep=c.sleep)
    await g.start()
    assert await g.next_id() == 1


async def test_parallel_postgres_workers():
    dsn = os.environ['ID_TEST_DSN']
    gs = [Generator(Config(400+i),PostgresWorkerStore(dsn)) for i in range(16)]
    try:
        for g in gs: await g.start()
        async def generate(g):
            ids = [await g.next_id() for _ in range(200)]
            assert ids == sorted(set(ids))
            return ids
        groups = await asyncio.gather(*(generate(g) for g in gs))
        assert len({value for group in groups for value in group}) == 3200
    finally:
        for g in gs: await g.close()

async def test_deadline_waiter_poison_fences_inflight():
    g, _, store = await make(Config(256,wait_ms=20))
    entered = asyncio.Event()
    release = asyncio.Event()
    async def delayed(worker_id):
        entered.set()
        await release.wait()
    store.assert_owned = delayed
    first = asyncio.create_task(g.next_id())
    await entered.wait()
    second = asyncio.create_task(g.next_id())
    await asyncio.sleep(.03)
    release.set()
    result = await asyncio.gather(first,second,return_exceptions=True)
    assert all(isinstance(r,IdUnavailable) for r in result)
    assert g.health()['state']=='degraded'
    await g.close()

async def test_distinct_processes_unique():
    import sys, json
    code = '''import asyncio, os, sys, json
from pulsegrid_unique_id import Config,Generator,PostgresWorkerStore
async def main():
 g=Generator(Config(int(sys.argv[1])),PostgresWorkerStore(os.environ['ID_TEST_DSN']))
 try:
  await g.start()
  print(json.dumps([await g.next_id() for _ in range(1000)]))
 finally: await g.close()
asyncio.run(main())'''
    async def child(worker):
        p = await asyncio.create_subprocess_exec(sys.executable,'-c',code,str(worker),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        stdout,stderr = await p.communicate()
        assert p.returncode==0,stderr.decode()
        ids=json.loads(stdout)
        assert ids == sorted(set(ids))
        return ids
    groups=await asyncio.gather(*(child(500+i) for i in range(4)))
    assert len({v for ids in groups for v in ids})==4000


def test_max_bit_vector():
    g=Generator(Config(0),FakeStore())
    assert g.decode((1<<63)-1)==dict(timestamp_ms=EPOCH_MS+(1<<41)-1,worker_id=1023,sequence=4095)

async def test_clock_advances_during_ownership_check():
    g,c,s = await make()
    original=s.assert_owned
    async def check(worker_id):
        await original(worker_id)
        c.now += 1
    s.assert_owned=check
    ids=[await g.next_id() for _ in range(5)]
    assert ids==sorted(set(ids))
    assert g.decode(ids[-1])['timestamp_ms']==c.now

async def test_last_valid_timestamp_before_overflow():
    c = Clock(); c.now = EPOCH_MS+(1<<41)-1
    g=Generator(Config(0),FakeStore(),clock=c,sleep=c.sleep)
    await g.start()
    assert g.decode(await g.next_id())['timestamp_ms']==c.now
    c.now+=1
    with pytest.raises(IdUnavailable,match='invalid_timestamp'): await g.next_id()
    await g.close()

@pytest.mark.parametrize('stage', ['reserved', 'issued', 'rolled_back'])
async def test_killed_process_restart(stage):
    import sys, json
    worker = {'reserved':600,'issued':601,'rolled_back':602}[stage]
    code = '''import asyncio, os, sys, json, psycopg
from pulsegrid_unique_id import Config,Generator,PostgresWorkerStore
async def main():
 dsn=os.environ['ID_TEST_DSN']
 g=Generator(Config(int(sys.argv[1])),PostgresWorkerStore(dsn))
 await g.start()
 value=None
 if sys.argv[2]!='reserved': value=await g.next_id()
 if sys.argv[2]=='rolled_back':
  async with await psycopg.AsyncConnection.connect(dsn,autocommit=True) as c:
   await c.execute('CREATE TEMP TABLE crash_entity(id bigint PRIMARY KEY)')
   try:
    async with c.transaction():
     await c.execute('INSERT INTO crash_entity VALUES (%s)',(value,))
     raise RuntimeError('synthetic business rollback')
   except RuntimeError: pass
 print(json.dumps(dict(end_ms=g._range.end_ms,value=value)),flush=True)
 await asyncio.Event().wait()
asyncio.run(main())'''
    p = await asyncio.create_subprocess_exec(sys.executable,'-c',code,str(worker),stage,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    replacement = None
    try:
        raw = await asyncio.wait_for(p.stdout.readline(),5)
        assert raw, (await p.stderr.read()).decode()
        prior=json.loads(raw)
        p.kill(); await p.wait()
        assert p.returncode < 0
        for attempt in range(20):
            replacement=Generator(Config(worker),PostgresWorkerStore(os.environ['ID_TEST_DSN']))
            try:
                await replacement.start()
                break
            except IdUnavailable as exc:
                assert str(exc)=='worker_conflict'
                await replacement.close()
                await asyncio.sleep(.01)
        else: raise AssertionError('crashed session lock not released')
        value=await replacement.next_id()
        assert replacement.decode(value)['timestamp_ms']>prior['end_ms']
        if prior['value'] is not None: assert value>prior['value']
    finally:
        if p.returncode is None: p.kill(); await p.wait()
        if replacement is not None: await replacement.close()
