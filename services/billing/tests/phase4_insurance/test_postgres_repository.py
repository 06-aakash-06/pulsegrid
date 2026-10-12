"""Actual PostgreSQL run uniqueness, fencing, immutable rules and retry progress."""
import asyncio,secrets
from datetime import datetime,timezone
from itertools import count
import psycopg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from sqlalchemy.engine import make_url
from billing_service.features.insurance.repository import SQLAlchemyInsuranceRepository
from billing_service.features.insurance.crawler import CrawlOutcome

def test_claim_fencing_and_new_refresh_progress(migrated_database):
    url=make_url(migrated_database)
    migration=url.set(username='billing_migration',password='migration-test')
    provider=secrets.randbelow(10**12)+10**12
    with psycopg.connect(migration.render_as_string(hide_password=False).replace('postgresql+psycopg://','postgresql://')) as c:
        c.execute('INSERT INTO insurance_providers(id,synthetic_slug,allowlisted_url) VALUES(%s,%s,%s)',(provider,'phase4-synthetic-'+str(provider),'http://fixture.test/'))
    async def work():
        engine=create_async_engine(url.set(drivername='postgresql+psycopg'),pool_size=4,max_overflow=0)
        sessions=async_sessionmaker(engine)
        ids=count(provider+1000000000000)
        async def allocate():return next(ids)
        async def effects(*args,**kwargs):pass
        repo=SQLAlchemyInsuranceRepository(sessions,allocate,audit_outbox=effects)
        try:
            run=await repo.begin_run(str(provider))
            assert (await repo.begin_run(str(provider)))['id']==run['id']
            async def claim():
                async with sessions() as s,s.begin():return await repo.claim_runs(s,datetime.now(timezone.utc),4)
            claims=await asyncio.gather(claim(),claim())
            flat=[x for group in claims for x in group if x['provider_id']==provider]
            assert len(flat)==1
            first=flat[0]
            async with sessions() as s,s.begin():
                await s.execute(text("UPDATE crawler_runs SET lease_until=CURRENT_TIMESTAMP-INTERVAL '1 second' WHERE id=:id"),{'id':run['id']})
            second=next(x for x in await claim() if x['provider_id']==provider)
            assert second['fencing_version']>first['fencing_version']
            outcome=CrawlOutcome(str(provider),str(run['id']),'complete',0,0,0,0,0,0,0,0,0,0,0)
            stale=await repo.commit_run(str(run['id']),first['fencing_version'],outcome,(),())
            assert stale['lease_owned'] is False
            current=await repo.commit_run(str(run['id']),second['fencing_version'],outcome,(),())
            assert current.get('lease_owned',True)
            # A new explicit refresh must not deadlock behind an inactive retry.
            old=await repo.begin_run(str(provider))
            async with sessions() as s,s.begin():
                await s.execute(text("UPDATE crawler_runs SET state='failed',attempt_count=1,next_attempt_at=CURRENT_TIMESTAMP-INTERVAL '1 second' WHERE id=:id"),{'id':old['id']})
            new=await repo.begin_run(str(provider))
            assert new['id']!=old['id']
            claimed=await claim()
            assert any(x['id']==new['id'] for x in claimed),claimed
        finally:await engine.dispose()
    asyncio.run(work())
