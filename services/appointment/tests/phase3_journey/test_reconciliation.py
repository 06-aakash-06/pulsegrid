"""Durable source projection and discharge checks on real PostgreSQL."""
import asyncio
from datetime import timedelta
from sqlalchemy import select, update, insert, text
from fastapi import HTTPException
from appointment_service import models as m, operations as op, phase3_core as core
from appointment_service.integration import create_episode
from appointment_service.features.queue import service as queue
from appointment_service.features.journey import service
from ..test_concurrency import run, booking, request, patient


async def setup(db, *, started=True):
    async with db.session_factory() as session, session.begin():
        start=op.now()+timedelta(minutes=10)
        await session.execute(update(m.slots).where(m.slots.c.id==1).values(starts_at=start,ends_at=start+timedelta(minutes=5)))
        await session.execute(update(m.doctor_schedule_snapshots).values(policy_snapshot={'timezone':'UTC'}))
    _, a=await booking(db)
    async with db.session_factory() as session,session.begin():
        ctx=await core.lock_context(session,request(),core.worker_actor(),core.LockPlan(appointment_ids=(int(a['id']),)))
        jid=await create_episode(session,ctx,await op.row(session,m.appointments,a['id']))
        await op.flush_effects(session)
    async with db.session_factory() as session,session.begin():
        ctx=await core.lock_context(session,request(),core.worker_actor(),core.LockPlan(appointment_ids=(int(a['id']),),queue_days=((1,op.now().date()),)))
        e=await queue.allocate_on_checkin(session,ctx);await op.flush_effects(session)
    if not started:
        return a,jid
    async with db.session_factory() as session,session.begin():
        plan=await queue._complete_plan(session,1,op.now().date())
        ctx=await core.lock_context(session,request(),core.worker_actor(),plan)
        await queue.start_entry(session,ctx,int(e['id']),1);await op.flush_effects(session)
    async with db.session_factory() as session,session.begin():
        await session.execute(insert(m.clinical_holds).values(appointment_id=int(a['id']),consultation_id=700,state='finalized'))
    return a,jid


def test_no_show_after_window_closes_updates_queue_journey_and_history(database, monkeypatch):
    async def work(db):
        a,jid=await setup(db, started=False)
        aid=int(a['id'])
        async with db.session_factory() as session:
            workflow=await core.read_workflow(session,aid)
        closed_at=workflow['window_ends_at']+timedelta(seconds=1)
        # Only this disposable test uses a clock override; persistent data is untouched.
        monkeypatch.setattr(op,'now',lambda: closed_at)
        async with db.session_factory() as session,session.begin():
            plan=await queue._complete_plan(session,1,closed_at.date(),(aid,))
            ctx=await core.lock_context(session,request(),core.worker_actor(),plan)
            result=await queue.no_show(session,ctx,aid,workflow['version'],'Synthetic missed appointment')
            await op.flush_effects(session)
            assert result['state']=='no_show'
        async with db.session_factory() as session:
            entry=await queue._entry(session,workflow['queue_entry_id'])
            assert entry['state']=='no_show' and entry['position'] is None
            journey=await op.row(session,m.journeys,jid)
            assert journey['state']=='no_show'
            history=(await session.execute(text(
                'SELECT to_state,occurred_at FROM journey_transitions WHERE journey_id=:jid AND stage IS NULL ORDER BY id'
            ),{'jid':jid})).mappings().all()
            assert history[-1]['to_state']=='no_show'
            assert history[-1]['occurred_at']>=history[0]['occurred_at']
            queue_history=(await session.execute(text(
                "SELECT to_state FROM queue_transitions WHERE entry_id=:eid ORDER BY id"
            ),{'eid':entry['id']})).scalars().all()
            assert queue_history==['waiting','no_show']
    run(database,work)


def sources(a, balance=0, revision=2):
    stamp=op.wire_time(op.now());aid=a['id']
    return {'records':dict(appointment_id=aid,patient_id='11',doctor_id='1',revision=2,observed_at=stamp,
        consultation=dict(id='700',status='finalized',version=2,record_revision=1,prescription=None)),
        'billing':dict(appointment_id=aid,patient_id='11',revision=revision,observed_at=stamp,
        invoice=dict(id='800',status='paid' if not balance else 'open',currency='INR',total_minor=1000,
        paid_minor=1000-balance,balance_minor=balance,version=revision,
        charge_source_keys=[dict(source_service='records',source_item_id='700')]))}


async def reconcile(db,jid,data,expected=None,discharge=False):
    r=request('/synthetic/discharge' if discharge else '/synthetic/reconcile',expected)
    ident,fp=op.idempotency(r,patient(),{})
    async def work(session):
        journey=await op.row(session,m.journeys,jid)
        a=await op.row(session,m.appointments,journey['appointment_id'])
        plan=await queue._complete_plan(session,a['doctor_id'],op.now().date(),(a['id'],))
        ctx=await core.lock_context(session,r,core.worker_actor(),plan)
        return 200,await service.apply(session,ctx,jid,data,{},expected,discharge,'synthetic' if discharge else None)
    try:return await core.command(db.session_factory,ident,fp,work)
    except HTTPException as exc:return exc.status_code,exc.detail


def test_complete_no_prescription_discharge_and_late_reopen(database):
    async def work(db):
        a,jid=await setup(db)
        _, ready=await reconcile(db,jid,sources(a))
        assert ready['state']=='ready' and ready['discharge_eligible']
        assert [s['state'] for s in ready['stages']]==['complete','complete','complete','skipped','skipped','complete']
        outcomes=await asyncio.gather(*(reconcile(db,jid,sources(a),ready['version'],True) for _ in range(8)))
        assert sum(code==200 for code,_ in outcomes)==1
        assert sum(code==412 for code,_ in outcomes)==7
        _, reopened=await reconcile(db,jid,sources(a, balance=100,revision=3))
        assert reopened['state']=='reopened' and not reopened['discharge_eligible']
        async with db.session_factory() as session:
            states=(await session.execute(text('SELECT to_state FROM journey_transitions WHERE journey_id=:jid AND stage IS NULL ORDER BY id'),{'jid':jid})).scalars().all()
            assert states==['active','ready','discharged','reopened']
    run(database,work)


def test_zero_balance_missing_sources_outage_and_recovery(database):
    async def work(db):
        a,jid=await setup(db);data=sources(a)
        data['billing']['invoice']['charge_source_keys']=[]
        _, pending=await reconcile(db,jid,data)
        assert not pending['discharge_eligible'] and pending['stages'][-1]['pending_reason']=='missing_charges'
        _, pending=await reconcile(db,jid,{})
        assert not pending['discharge_eligible'] and pending['stages'][2]['state']=='pending'
        assert (await reconcile(db,jid,{},pending['version'],True))[0]==409
        _, recovered=await reconcile(db,jid,sources(a))
        assert recovered['discharge_eligible']
        older=sources(a,revision=1)
        _, pending=await reconcile(db,jid,older)
        assert not pending['discharge_eligible']
    run(database,work)


def test_competing_reconciliation_and_completion_have_one_versioned_effect(database):
    async def work(db):
        a,jid=await setup(db)
        async with db.session_factory() as session:
            before=await service.view(session,jid)
        outcomes=await asyncio.gather(*(reconcile(db,jid,sources(a),before['version']) for _ in range(8)))
        assert sorted(code for code,_ in outcomes)==[200]+[412]*7
        async with db.session_factory() as session:
            workflow=await core.read_workflow(session,a['id'])
            assert workflow['state']=='completed'
            transitions=(await session.execute(text("SELECT count(*) FROM queue_transitions WHERE entry_id=:id AND to_state='completed'"),{'id':workflow['queue_entry_id']})).scalar_one()
            assert transitions==1
    run(database,work)


def test_unchanged_worker_refresh_preserves_staff_review_version(database):
    async def work(db):
        a,jid=await setup(db)
        _,first=await reconcile(db,jid,sources(a))
        _,heartbeat=await reconcile(db,jid,sources(a))
        assert heartbeat['version']==first['version']
        assert heartbeat['last_reconciled_at']>=first['last_reconciled_at']
        assert heartbeat['stages']==first['stages']
        # A review survives a heartbeat; a real source revision remains a change.
        assert (await reconcile(db,jid,sources(a),first['version'],True))[0]==200
        _,changed=await reconcile(db,jid,sources(a,balance=100,revision=3))
        assert changed['state']=='reopened' and changed['version']>first['version']
    run(database,work)
