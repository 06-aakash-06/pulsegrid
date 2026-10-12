import asyncio
import importlib.util
import json
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from pulsegrid_key_value_cache import Cache, CacheEntry, InvalidEntry, canonical_json, redis_client
from doctor_service.features.directory_cache import DirectoryFilters, cache_projection, load_projection, read_revision, validate_projection

spec = importlib.util.spec_from_file_location('cache_fixtures', Path(__file__).resolve().parents[4]/'experiments/phase4/key_value_cache/fixtures.py')
fixtures = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixtures)


class Placement:
    epoch = 1
    def locate(self, key): return 'cache_a'


async def test_real_postgres_parity_pagination_revision_race_outage():
    with fixtures.storage() as (dsn, ports, processes):
        engine = create_async_engine(dsn, pool_size=4, max_overflow=0)
        cache = Cache(Placement(), {'cache_a': redis_client(f'redis://127.0.0.1:{ports[0]}')})
        sessions = async_sessionmaker(engine)
        try:
            await fixtures.seed(engine, 50)
            # Batch creation commonly gives many rows the identical timestamp.
            async with engine.begin() as conn:
                await conn.execute(text("UPDATE doctors SET created_at='2026-01-01'::timestamptz"))
            f = DirectoryFilters('synthetic', 'patient')
            async def loader():
                async with sessions() as s: return await load_projection(s, f)
            async with sessions() as s: revision = await read_revision(s)
            expected_rev, expected = await loader()
            first = await cache_projection(cache, revision, f, loader)
            assert first == json.loads(expected)
            assert first['next_cursor']
            from doctor_service.wire import decode_cursor, filter_digest
            cursor = decode_cursor(first['next_cursor'], filter_digest({'active':True,'q':None,'specialty_id':None}))
            next_filters = DirectoryFilters('synthetic', 'patient', cursor=cursor)
            async with sessions() as s: _, page2 = await load_projection(s, next_filters)
            assert not set(i['id'] for i in first['items']) & set(i['id'] for i in json.loads(page2)['items'])
            # Actual old owner repository allowlisted payload parity.
            from doctor_service.repository import list_doctors
            async with sessions() as s:
                rows = await list_doctors(s, active=True, specialty_id=None, query=None, cursor=None, limit=21)
            assert first['items'] == [{k: row[k] if k != 'id' else str(row[k]) for k in ('id','display_name','specialties')} for row in rows[:20]]
            started, release = asyncio.Event(), asyncio.Event()
            async def late():
                snapshot = await loader(); started.set(); await release.wait(); return snapshot
            await cache.invalidate(f.key(revision))
            task = asyncio.create_task(cache_projection(cache, revision, f, late))
            await started.wait()
            async with engine.begin() as conn:
                await conn.execute(text("UPDATE doctors SET display_name='Renamed' WHERE id=1"))
                await conn.execute(text('UPDATE directory_revision SET revision=revision+1'))
            release.set(); await task
            async with sessions() as s: current = await read_revision(s)
            assert current == 2
            result = await cache_projection(cache, current, f, loader)
            assert result['items'][0]['display_name'] == 'Renamed'
            # Revision moves after initial read: current snapshot returned, old key unpopulated.
            await cache.invalidate(f.key(1))
            raced = await cache_projection(cache, 1, f, loader)
            assert raced == result and await cache.get(f.key(1)) is None
            # Sensitive data or wrong source version on a valid envelope never served.
            bad = canonical_json({'schema_version':1,'items':[{'id':'1','display_name':'x','specialties':[], 'staff_user_id':'1'}],'next_cursor':None})
            await cache.set(f.key(current), CacheEntry(bad,current,cache.clock()+30000),30000)
            assert await cache_projection(cache,current,f,loader) == result
            await cache.set(f.key(current), CacheEntry(expected,1,cache.clock()+30000),30000)
            assert await cache_projection(cache,current,f,loader) == result
            # Two independent replica cache objects observe same durable owner revision.
            replica = Cache(Placement(), {'cache_a':redis_client(f'redis://127.0.0.1:{ports[0]}')})
            try: assert await cache_projection(replica,current,f,loader) == result
            finally: await replica.close()
            # Committed deactivation and specialty/association mutations invalidate by revision.
            async with engine.begin() as conn:
                await conn.execute(text('UPDATE doctors SET active=false WHERE id=1'))
                await conn.execute(text("UPDATE specialties SET name='Renamed specialty' WHERE id=3"))
                await conn.execute(text('UPDATE doctor_specialties SET specialty_id=3 WHERE doctor_id=3'))
                await conn.execute(text('UPDATE directory_revision SET revision=revision+1'))
            async with sessions() as s: current = await read_revision(s)
            result = await cache_projection(cache,current,f,loader)
            assert '1' not in {item['id'] for item in result['items']}
            assert next(item for item in result['items'] if item['id']=='3')['specialties'] == [{'id':'3','name':'Renamed specialty'}]
            processes[0].terminate(); processes[0].wait(timeout=5)
            assert await cache_projection(cache,current,f,loader) == result
            async def unavailable(): raise RuntimeError('owner503')
            with pytest.raises(RuntimeError, match='owner503'): await cache_projection(cache,current,f,unavailable)
        finally:
            await cache.close(); await engine.dispose()


@pytest.mark.parametrize('payload', [b'null', b'[]', b'{"schema_version":1,"items":[3],"next_cursor":null}', b'{"schema_version":true,"items":[],"next_cursor":null}'])
def test_invalid_projection(payload):
    with pytest.raises(InvalidEntry): validate_projection(payload)


def test_partition_and_filters():
    f = DirectoryFilters('tenant_a','patient',query='doctor')
    assert f.key(1) != DirectoryFilters('tenant_b','patient',query='doctor').key(1)
    assert f.key(1) != DirectoryFilters('tenant_a','doctor',query='doctor').key(1)
    assert f.key(1) != f.key(2)
    with pytest.raises(ValueError): DirectoryFilters('a','patient',query=' Doctor ')


@pytest.mark.parametrize('role', ['patient','doctor','receptionist','pharmacist','billing_staff','emergency_staff','hospital_admin','ops'])
def test_all_existing_authenticated_role_partitions(role):
    assert DirectoryFilters('synthetic',role).key(1)


@pytest.mark.parametrize('payload', [
    b'{"schema_version":1,"schema_version":2,"items":[],"next_cursor":null}',
    b'{"schema_version":1,"items":[{"id":"01","display_name":"x","specialties":[]}],"next_cursor":null}',
    b'{"schema_version":1,"items":[{"id":"9223372036854775808","display_name":"x","specialties":[]}],"next_cursor":null}',
    b'{"schema_version":1,"items":[],"next_cursor":1}',
])
def test_strict_projection_serialization(payload):
    with pytest.raises(InvalidEntry): validate_projection(payload)


async def test_actual_owner_database_outage_does_not_serve_warm_cache():
    import subprocess
    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import DBAPIError
    with fixtures.storage() as (dsn,ports,processes):
        engine=create_async_engine(dsn,pool_size=2,max_overflow=0)
        sessions=async_sessionmaker(engine)
        cache=Cache(Placement(),{'cache_a':redis_client(f'redis://127.0.0.1:{ports[0]}')})
        filters=DirectoryFilters('synthetic','patient')
        try:
            await fixtures.seed(engine,30)
            async def loader():
                async with sessions() as s: return await load_projection(s,filters)
            async def read():
                async with sessions() as s: revision=await read_revision(s)
                return await cache_projection(cache,revision,filters,loader)
            expected=await read()
            assert await cache.get(filters.key(1)) is not None
            async with engine.connect() as conn:
                directory=Path((await conn.execute(text('SHOW data_directory'))).scalar_one())
            port=make_url(dsn).port
            subprocess.run(['pg_ctl','-D',str(directory),'-m','fast','-w','stop'],check=True,stdout=subprocess.DEVNULL,timeout=10)
            try:
                with pytest.raises(DBAPIError): await read()
                # Redis is still available and warm; current DB revision remains mandatory.
                assert await cache.get(filters.key(1)) is not None
            finally:
                await engine.dispose()
                subprocess.run(['pg_ctl','-D',str(directory),'-l',str(directory.parent/'postgres.log'),'-o',f'-h 127.0.0.1 -p {port} -k {directory.parent}','-w','start'],check=True,stdout=subprocess.DEVNULL,timeout=10)
            assert await read() == expected
        finally:
            await cache.close(); await engine.dispose()
