import asyncio
from dataclasses import replace
from datetime import timedelta
from types import MappingProxyType

import pytest
from fastapi import HTTPException, FastAPI
from pydantic import ValidationError
from sqlalchemy import select, insert, update, text

from appointment_service import models as m, operations as op, phase3_core as core, extensions
from appointment_service.features.waitlist import operations as w, worker
from appointment_service.features.waitlist.wire import Join, EligibilityBatch
from appointment_service.features.waitlist.schema_spec import schema_spec
from ..test_concurrency import run, booking, mutation, request, patient, identity


async def schema(db):
    # Actual migrations now supply these tables and runtime grants.
    return None


async def enroll(db,pid='12',sid=1,r=None):
    p=patient(pid); r=r or request('/api/v1/appointments/waitlists')
    body=Join(patient_id=pid,slot_id=str(sid),expected_schedule_revision=1)
    ident,fp=op.idempotency(r,p,body.model_dump())
    try:
        return await core.command(db.session_factory,ident,fp,lambda s:w.join(s,r,p,body,identity()))
    except HTTPException as exc:
        return exc.status_code,exc.detail


async def fixture_episode(session,ctx,a):
    # Test-only replacement for Agent 4; uses real local rows and G0 checks.
    jid=op.new_id()
    await session.execute(insert(m.journeys).values(id=jid,appointment_id=a['id'],patient_id=a['patient_id'],state='active'))
    inserted=replace(ctx,bookings=MappingProxyType({**ctx.bookings,a['id']:MappingProxyType(a)}))
    session.info['phase3_lock_context']=inserted
    await core.enroll_workflow(session,inserted,a['id'],jid)
    session.info['phase3_lock_context']=ctx
    return jid


async def prepared(db,sid=1,inactive=()):
    async def fetch(ids):
        assert db.engine.pool.checkedout()==0
        return dict(items=[dict(patient_id=i,active=i not in inactive,version=1) for i in ids],observed_at=op.wire_time(op.now()))
    return await w.prepare(db.session_factory,sid,fetch)


async def promote(db,p=None,creator=fixture_episode):
    p=p or await prepared(db)
    r=request('/synthetic/promotion')
    ident=dict(principal_scope='service:appointment',method='POST',route_template=r.url.path,key=r.headers['Idempotency-Key'])
    async def work(s):
        ctx=await core.lock_context(s,r,core.worker_actor(),core.LockPlan(waitlist_slot_ids=(p.slot_id,),
            waitlist_patient_ids=p.patient_ids,promotion_slot_ids=(p.slot_id,)))
        result=await w.promote(s,ctx,p,creator)
        return 200,{'id':str(result['id']) if result else None}
    return await core.command(db.session_factory,ident,op.digest({}),work)


def test_join_twelve_retries_duplicate_and_free_slot(database):
    async def work(db):
        await booking(db)
        r=request('/api/v1/appointments/waitlists')
        results=await asyncio.gather(*(enroll(db,r=r) for _ in range(12)))
        assert all(x==results[0] for x in results)
        assert await enroll(db)==(409,'already_waiting')
        assert await enroll(db,pid='11')==(409,'already_booked')
        assert await enroll(db,pid='13',sid=2)==(409,'slot_available')
        async with db.session_factory() as s:
            assert len((await s.execute(select(m.waitlist_entries))).all())==1
            assert len((await s.execute(select(m.outbox_events))).all())==2
    run(database,work)


def test_fifo_skip_overlap_inactive_and_episode_atomicity(database):
    async def work(db):
        await schema(db)
        _,a=await booking(db)
        for pid in ('12','13','14'):
            assert (await enroll(db,pid))[0]==201
        await booking(db,pid='13',sid=3)
        p=await prepared(db,inactive=('12',))
        assert (await mutation(db,a['id'],'cancel'))[0]==200
        result=await promote(db,p)
        assert result[1]['id'] is not None
        async with db.session_factory() as s:
            rows=(await s.execute(select(m.waitlist_entries).order_by(m.waitlist_entries.c.joined_at,m.waitlist_entries.c.id))).mappings().all()
            assert [(r['state'],r['skip_reason']) for r in rows]==[('skipped','inactive_patient'),('skipped','patient_overlap'),('promoted',None)]
            assert (await op.row(s,m.appointments,result[1]['id']))['patient_id']==14
            assert len((await s.execute(select(m.appointment_workflows))).all())==1
            event=(await s.execute(select(m.outbox_events.c.envelope).where(m.outbox_events.c.event_type=='appointment.waitlist.promoted.v1'))).scalar_one()
            assert event['payload']['journey_id'] is not None
        assert (await promote(db))[1]['id'] is None
    run(database,work)


def test_stale_unknown_and_newer_inactive_never_bypassed(database):
    async def work(db):
        await schema(db)
        _,a=await booking(db)
        for pid in ('12','13'):
            await enroll(db,pid)
        p=await prepared(db)
        await mutation(db,a['id'],'cancel')
        stale=replace(p,batch=p.batch.model_copy(update={'observed_at':op.now()-timedelta(seconds=61)}))
        assert (await promote(db,stale))[1]['id'] is None
        async with db.session_factory() as s:
            assert await w.pending(s,1)
            with pytest.raises(HTTPException) as exc:
                await w.guard_target(s,1)
            assert exc.value.detail=='waitlist_pending'
        async with db.session_factory() as s,s.begin():
            newer=EligibilityBatch(items=[dict(patient_id='12',active=False,version=2)],observed_at=op.now())
            await w.merge_status(s,newer,op.now())
        result=await promote(db,p)
        async with db.session_factory() as s:
            assert (await op.row(s,m.appointments,result[1]['id']))['patient_id']==13
    run(database,work)


def test_withdraw_scope_version_noop_and_promotion_race(database):
    async def work(db):
        await schema(db)
        _,a=await booking(db)
        _,entry=await enroll(db)
        async def withdraw(pid='12',version=1):
            r=request('/synthetic/withdraw',version);p=patient(pid)
            ident,fp=op.idempotency(r,p,{})
            try:
                return await core.command(db.session_factory,ident,fp,lambda s:w.withdraw(s,r,p,entry['id'],version,'synthetic'))
            except HTTPException as exc:
                return exc.status_code,exc.detail
        assert await withdraw('13')==(404,'not_found')
        await mutation(db,a['id'],'cancel')
        p=await prepared(db)
        async def competing():
            try:
                return await promote(db,p)
            except HTTPException as exc:
                return exc.status_code,exc.detail
        results=await asyncio.gather(withdraw(),competing())
        async with db.session_factory() as s:
            row=await op.row(s,m.waitlist_entries,entry['id'])
            assert row['state'] in ('promoted','withdrawn')
            count=(await s.execute(select(m.appointments).where(m.appointments.c.slot_id==1,m.appointments.c.state.in_(op.ACTIVE)))).all()
            assert len(count)==(1 if row['state']=='promoted' else 0)
        if row['state']=='withdrawn':
            assert (await withdraw(version=2))[0]==200
    run(database,work)


def test_rollback_and_missing_episode_dependency(database):
    async def work(db):
        await schema(db)
        _,a=await booking(db); await enroll(db)
        await mutation(db,a['id'],'cancel')
        assert (await promote(db,creator=None))[1]['id'] is None
        async def broken(s,ctx,a):
            await fixture_episode(s,ctx,a)
            raise RuntimeError('interrupted episode')
        with pytest.raises(RuntimeError):
            await promote(db,creator=broken)
        async with db.session_factory() as s:
            assert not (await s.execute(select(m.journeys))).all()
            assert (await w.candidates(s,1))[0]['state']=='waiting'
            assert await w.pending(s,1)
        assert (await promote(db))[1]['id'] is not None
    run(database,work)


def test_worker_lease_crash_recovery_and_repair(database):
    async def work(db):
        await schema(db)
        _,a=await booking(db);await enroll(db)
        await mutation(db,a['id'],'cancel')
        assert await worker.repair(db.session_factory)==1
        first=await worker.claim(db.session_factory)
        assert first and await worker.claim(db.session_factory) is None
        async with db.session_factory() as s,s.begin():
            await s.execute(text('UPDATE promotion_jobs SET lease_expires_at=:now'),dict(now=op.now()-timedelta(seconds=1)))
        async def fetch(ids):
            return dict(items=[dict(patient_id=i,active=True,version=1) for i in ids],observed_at=op.wire_time(op.now()))
        assert await worker.run_once(db.session_factory,request(),fetch,fixture_episode)
        assert not await worker.run_once(db.session_factory,request(),fetch,fixture_episode)
    run(database,work)


def test_fifty_direct_arrivals_cannot_bypass_atomic_release(database):
    from appointment_service.database import Database
    from appointment_service.wire import Cancel
    async def work(db):
        await schema(db)
        _,a=await booking(db);await enroll(db)
        prep=await prepared(db)
        second=Database(db.settings);await second.start()
        try:
            async def release():
                r=request('/synthetic/cancel',1);p=patient('11');b=Cancel(reason='synthetic')
                ident,fp=op.idempotency(r,p,b.model_dump())
                return await op.command(db.session_factory,ident,fp,lambda s:w.change_with_promotion(
                    s,r,p,a['id'],b,prep,create_episode=fixture_episode))
            async def direct(i):
                p=patient(str(1000+i));r=request();b=Join(patient_id=p.patient_id,slot_id='1',expected_schedule_revision=1)
                ident,fp=op.idempotency(r,p,b.model_dump())
                try:
                    return await op.command(second.session_factory,ident,fp,lambda s:w.book_with_waitlist_guard(s,r,p,b,identity()))
                except HTTPException as exc:
                    return exc.status_code,exc.detail
            results=await asyncio.gather(release(),*(direct(i) for i in range(50)))
            assert results[0][0]==200
            assert all(code==409 for code,_ in results[1:])
            async with db.session_factory() as s:
                rows=(await s.execute(select(m.appointments).where(m.appointments.c.slot_id==1,m.appointments.c.state.in_(op.ACTIVE)))).mappings().all()
                assert len(rows)==1 and rows[0]['patient_id']==12
                assert len((await s.execute(select(m.appointment_workflows))).all())==1
        finally:
            await second.close()
    run(database,work)


@pytest.mark.parametrize('mode',['retired','past','inactive'])
def test_more_than_fifty_candidates_bounded_continuation(database,mode):
    async def work(db):
        await schema(db)
        _,a=await booking(db)
        async with db.session_factory() as s,s.begin():
            for i in range(53):
                await s.execute(insert(m.waitlist_entries).values(id=2000+i,slot_id=1,patient_id=2000+i,
                    state='waiting',joined_at=op.now()+timedelta(microseconds=i)))
        await mutation(db,a['id'],'cancel')
        if mode!='inactive':
            async with db.session_factory() as s,s.begin():
                if mode=='retired':
                    await s.execute(update(m.slots).where(m.slots.c.id==1).values(state='retired'))
                else:
                    # Shift cancelled booking too: copy guard is irrelevant to terminal rows.
                    await s.execute(update(m.slots).where(m.slots.c.id==1).values(
                        starts_at=op.now()-timedelta(hours=2),ends_at=op.now()-timedelta(hours=1)))
        prep=await prepared(db,inactive=tuple(str(i) for i in range(2000,2053)))
        assert len(prep.members)==50
        assert (await promote(db,prep))[1]['id'] is None
        async with db.session_factory() as s:
            assert len(await w.candidates(s,1))==3 and await w.pending(s,1)
        assert (await promote(db,await prepared(db,inactive=tuple(str(i) for i in range(2000,2053)))))[1]['id'] is None
        async with db.session_factory() as s:
            assert not await w.candidates(s,1) and not await w.pending(s,1)
    run(database,work)


def test_cancellation_outage_and_changed_membership_still_commit(database):
    from appointment_service.wire import Cancel
    async def work(db):
        await schema(db)
        _,a=await booking(db);await enroll(db)
        async def unavailable(ids):
            assert db.engine.pool.checkedout()==0
            raise TimeoutError()
        prep=await w.prepare(db.session_factory,1,unavailable)
        assert prep.batch is None
        await enroll(db,'13')  # membership changed during hypothetical HTTP request
        r=request('/synthetic/cancel',1);p=patient('11');b=Cancel(reason='synthetic')
        ident,fp=op.idempotency(r,p,b.model_dump())
        result=await op.command(db.session_factory,ident,fp,lambda s:w.change_with_promotion(s,r,p,a['id'],b,prep,create_episode=fixture_episode))
        assert result[1]['state']=='cancelled'
        async with db.session_factory() as s:
            assert await w.pending(s,1)
            assert len(await w.candidates(s,1))==2
        assert (await promote(db))[1]['id'] is not None
    run(database,work)


def test_reschedule_source_promotes_target_guard_rollback(database):
    from appointment_service.wire import Move
    async def work(db):
        await schema(db)
        _,a=await booking(db);await enroll(db)
        r=request('/synthetic/move',1);p=patient('11');b=Move(target_slot_id='2',expected_schedule_revision=1)
        prep=await prepared(db)
        ident,fp=op.idempotency(r,p,b.model_dump())
        result=await op.command(db.session_factory,ident,fp,lambda s:w.change_with_promotion(s,r,p,a['id'],b,prep,identity(),fixture_episode))
        assert result[1]['slot_id']=='2' and result[1]['journey_id'] is None
        async with db.session_factory() as s:
            assert (await w.candidates(s,1))==[]
            row=(await s.execute(select(m.waitlist_entries))).mappings().one()
            assert row['state']=='promoted'
    run(database,work)


def test_worker_backoff_repair_and_two_claimers(database):
    async def work(db):
        await schema(db)
        _,a=await booking(db);await enroll(db)
        await mutation(db,a['id'],'cancel')
        await worker.repair(db.session_factory)
        results=await asyncio.gather(worker.claim(db.session_factory),worker.claim(db.session_factory))
        assert sum(x is not None for x in results)==1
        async with db.session_factory() as s,s.begin():
            await s.execute(text('UPDATE promotion_jobs SET lease_expires_at=:now'),dict(now=op.now()-timedelta(seconds=1)))
        async def unavailable(ids):
            assert db.engine.pool.checkedout()==0
            raise TimeoutError()
        assert await worker.run_once(db.session_factory,request(),unavailable,fixture_episode)
        async with db.session_factory() as s:
            row=(await s.execute(text('SELECT * FROM promotion_jobs'))).mappings().one()
            assert row['pending'] and row['attempt_count']==1 and row['lease_token'] is None
            due=row['next_attempt_at']
        await worker.repair(db.session_factory)
        async with db.session_factory() as s:
            assert (await s.execute(text('SELECT next_attempt_at FROM promotion_jobs'))).scalar_one()==due
            assert len(await w.candidates(s,1))==1
    run(database,work)


@pytest.mark.parametrize('state,target',[
    (state,target) for state in ('waiting','promoted','withdrawn','skipped')
    for target in ('waiting','promoted','withdrawn','skipped')
    if not (state=='waiting' and target in ('promoted','withdrawn','skipped'))])
def test_transition_matrix(state,target):
    # Use a session that rejects DB access: invalid edges must fail before writes.
    with pytest.raises(HTTPException) as exc:
        asyncio.run(w.transition(None,None,{'state':state},target))
    assert exc.value.detail=='invalid_transition'


@pytest.mark.parametrize('item',[
    dict(patient_id='12',active=True,version=0),dict(patient_id='12',active=True,version=True),
    dict(patient_id=12,active=True,version=1),dict(patient_id='12',active='true',version=1)])
def test_strict_eligibility(item):
    with pytest.raises(ValidationError):
        EligibilityBatch(items=[item],observed_at=op.now())


def test_freshness_exact_boundaries_and_routes():
    now=op.now()
    assert w.fresh(now-timedelta(seconds=60),now)
    assert not w.fresh(now-timedelta(seconds=60,microseconds=1),now)
    assert not w.fresh(now+timedelta(microseconds=1),now)
    app=FastAPI();extensions.register_extensions(app,core,enabled=('waitlist',))
    paths=app.openapi()['paths']
    assert len(paths)==8
    assert paths['/api/v1/appointments/waitlists'].keys() >= {'get','post'}
