"""Real PostgreSQL, separate pool connections, and the production command code."""
import asyncio
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import insert, select, text, update
from sqlalchemy.exc import IntegrityError, DBAPIError
from appointment_service.database import Database
from appointment_service.authorization import Principal
from appointment_service import operations as op, models as m
from appointment_service.wire import Book, Move, Cancel, Hold, Identity, Decide, ProposalContext


def request(path='/api/v1/appointments',version=None):
    return SimpleNamespace(headers={'Idempotency-Key':uuid4().hex,**({'If-Match':f'"{version}"'} if version else {})},
        url=SimpleNamespace(path=path),state=SimpleNamespace(request_id=uuid4(),correlation_id=uuid4(),traceparent=None))


def patient(pid='11'):
    return Principal(pid,pid,frozenset({'patient'}),1,'test')


def identity(did=1):
    return Identity(doctor_id=str(did),staff_user_id=str(100+did),active=True,version=1)


async def seed(db):
    start=op.now()+timedelta(days=2)
    async with db.session_factory() as s,s.begin():
        for did in (1,2):
            await s.execute(insert(m.doctor_schedule_snapshots).values(doctor_id=did,accepted_revision=1,
                policy_snapshot={},staff_user_id=100+did,last_decided_proposal_revision=1))
        for sid,did,offset in ((1,1,0),(2,1,30),(3,2,0),(4,2,30),(5,1,60)):
            await s.execute(insert(m.slots).values(id=sid,doctor_id=did,schedule_revision=1,
                starts_at=start+timedelta(minutes=offset),ends_at=start+timedelta(minutes=offset+30),state='bookable'))
    return start


async def booking(db,pid='11',sid=1,r=None):
    p=patient(pid); r=r or request()
    body=Book(patient_id=pid,slot_id=str(sid),expected_schedule_revision=1)
    async with db.session_factory() as s:
        sl=await op.row(s,m.slots,sid)
    ident,fp=op.idempotency(r,p,body.model_dump())
    try:
        return await op.command(db.session_factory,ident,fp,lambda s:op.book(s,r,p,body,identity(sl['doctor_id'])))
    except HTTPException as exc:
        return exc.status_code,exc.detail


async def mutation(db,a,kind,version=1,sid=2,r=None,pid='11'):
    p=patient(pid); r=r or request(f'/api/v1/appointments/{a}/{kind}',version)
    body=Cancel(reason='synthetic cancellation') if kind=='cancel' else Move(target_slot_id=str(sid),expected_schedule_revision=1)
    ident,fp=op.idempotency(r,p,body.model_dump())
    did=1 if sid in (1,2,5) else 2
    try:
        return await op.command(db.session_factory,ident,fp,lambda s:op.change(s,r,p,a,body,identity(did) if kind=='reschedule' else None))
    except HTTPException as exc:
        return exc.status_code,exc.detail


def run(database,work):
    async def wrapped():
        db=Database(database)
        await db.start()
        try:
            await seed(db)
            return await work(db)
        finally:
            await db.close()
    return asyncio.run(wrapped())


def test_twenty_patients_exactly_one_exclusive_booking(database):
    async def work(db):
        results=await asyncio.gather(*(booking(db,str(1000+i)) for i in range(20)))
        assert sum(code==201 for code,_ in results)==1
        assert sum(code==409 and value=='slot_occupied' for code,value in results)==19
        async with db.session_factory() as s:
            for table in (m.appointments,m.audit_entries,m.outbox_events,m.idempotency_requests):
                assert len((await s.execute(select(table))).all())==1
    run(database,work)


def test_duplicate_retries_commit_once_and_replay_original(database):
    async def work(db):
        r=request()
        results=await asyncio.gather(*(booking(db,r=r) for _ in range(12)))
        assert all(result==results[0] for result in results)
        a=results[0][1]['id']
        assert (await mutation(db,a,'cancel'))[0]==200
        assert await booking(db,r=r)==results[0]
        changed=Book(patient_id='11',slot_id='2',expected_schedule_revision=1)
        ident,fp=op.idempotency(r,patient(),changed.model_dump())
        with pytest.raises(HTTPException) as exc:
            await op.command(db.session_factory,ident,fp,lambda _:None)
        assert exc.value.status_code==409
    run(database,work)


def test_patient_overlap_across_doctors_and_adjacent_allowed(database):
    async def work(db):
        results=await asyncio.gather(booking(db,sid=1),booking(db,sid=3))
        assert sorted(code for code,_ in results)==[201,409]
        assert next(value for code,value in results if code==409)=='patient_overlap'
        assert (await booking(db,sid=2))[0]==201
    run(database,work)


def test_failed_reschedule_keeps_original(database):
    async def work(db):
        _,a=await booking(db)
        await booking(db,pid='12',sid=2)
        assert await mutation(db,a['id'],'reschedule')==(409,'slot_occupied')
        async with db.session_factory() as s:
            original=await op.row(s,m.appointments,a['id'])
            assert original['slot_id']==1 and original['version']==1 and original['state']=='confirmed'
            assert len((await s.execute(select(m.outbox_events))).all())==2
    run(database,work)


def test_concurrent_cancel_reschedule_serializes_with_etag(database):
    async def work(db):
        _,a=await booking(db)
        results=await asyncio.gather(mutation(db,a['id'],'cancel'),mutation(db,a['id'],'reschedule',sid=4))
        assert sorted(code for code,_ in results)==[200,412]
        async with db.session_factory() as s:
            stored=await op.row(s,m.appointments,a['id'])
            assert stored['version']==2
            assert stored['state']=='cancelled' or stored['slot_id']==4
    run(database,work)


def test_cancel_noop_and_invalid_transition(database):
    async def work(db):
        _,a=await booking(db)
        assert (await mutation(db,a['id'],'cancel'))[0]==200
        assert (await mutation(db,a['id'],'cancel',version=2))[0]==200
        assert await mutation(db,a['id'],'reschedule',version=2)==(409,'cancelled')
        async with db.session_factory() as s:
            assert len((await s.execute(select(m.outbox_events))).all())==2
            with pytest.raises(IntegrityError):
                await s.execute(update(m.appointments).where(m.appointments.c.id==int(a['id'])).values(state='confirmed'))
    run(database,work)


def test_rollback_after_insert_leaves_no_partial_effect(database):
    async def work(db):
        r=request(); p=patient(); b=Book(patient_id='11',slot_id='1',expected_schedule_revision=1)
        async def broken(s):
            await op.book(s,r,p,b,identity())
            raise RuntimeError('injected rollback')
        ident,fp=op.idempotency(r,p,b.model_dump())
        with pytest.raises(RuntimeError):
            await op.command(db.session_factory,ident,fp,broken)
        async with db.session_factory() as s:
            for table in (m.appointments,m.outbox_events,m.audit_entries,m.idempotency_requests):
                assert not (await s.execute(select(table))).all()
        assert (await booking(db))[0]==201
    run(database,work)


def test_clinical_hold_race_and_finalization(database):
    async def work(db):
        _,a=await booking(db)
        p=Principal('101',None,frozenset({'doctor'}),1,'test')
        async def hold(finalize=False,version=1):
            r=request('/internal/v1/appointments/'+a['id']+'/clinical-hold'+('/finalize' if finalize else ''),version)
            b=Hold(consultation_id='800')
            ident,fp=op.idempotency(r,p,b.model_dump(),'records')
            try:
                return await op.command(db.session_factory,ident,fp,lambda s:op.clinical_hold(s,r,p,a['id'],b,finalize))
            except HTTPException as e:
                return e.status_code,e.detail
        results=await asyncio.gather(hold(),mutation(db,a['id'],'cancel'))
        assert sorted(code for code,_ in results)==[200,412]
        async with db.session_factory() as s:
            stored=await op.row(s,m.appointments,a['id'])
        if stored['state']=='confirmed':
            assert await mutation(db,a['id'],'cancel',version=2)==(409,'clinical_hold')
            assert (await hold(True,2))[1]['clinical_hold']=='finalized'
            assert (await hold(True,3))[1]['version']==3
    run(database,work)


def test_database_exclusions_copy_guard_and_audit_grants(database):
    async def work(db):
        async with db.session_factory() as s:
            slot=await op.row(s,m.slots,1)
        async with db.session_factory() as s,s.begin():
            with pytest.raises(IntegrityError) as exc:
                await s.execute(insert(m.slots).values(id=99,doctor_id=1,schedule_revision=1,
                    starts_at=slot['starts_at']+timedelta(minutes=1),ends_at=slot['ends_at'],state='bookable'))
            assert exc.value.orig.sqlstate=='23P01'
        async with db.session_factory() as s,s.begin():
            with pytest.raises(IntegrityError) as exc:
                await s.execute(insert(m.appointments).values(id=98,patient_id=11,slot_id=1,doctor_id=2,
                    doctor_user_id=102,starts_at=slot['starts_at'],ends_at=slot['ends_at'],schedule_revision=1,state='confirmed'))
            assert exc.value.orig.diag.constraint_name=='appointment_slot_copy'
        async with db.session_factory() as s:
            with pytest.raises(DBAPIError):
                await s.execute(text("UPDATE audit_heads SET last_hash='bad'"))
        async with db.session_factory() as s:
            with pytest.raises(DBAPIError):
                await s.execute(text("SELECT appointment_append_audit(99,'{\"action\":\"invented\",\"result\":\"success\"}')"))
    run(database,work)


def test_schedule_rejection_preserves_bookings_and_closure(database):
    async def work(db):
        _,a=await booking(db)
        p=Principal('101',None,frozenset({'doctor'}),1,'test')
        async def decide(pid,revision,expected,intervals):
            r=request('/api/v1/appointments/schedule-decisions')
            b=Decide(doctor_id='1',proposal_id=str(pid),expected_accepted_revision=expected)
            ctx=ProposalContext(proposal={'id':str(pid),'doctor_id':'1','revision':revision,'status':'pending',
                'timezone':'UTC','slot_minutes':30,'intervals':intervals,'conflicts':[],'version':1},
                staff_user_id='101',active=True,doctor_version=1)
            ident,fp=op.idempotency(r,p,b.model_dump())
            return await op.command(db.session_factory,ident,fp,lambda s:op.decide(s,r,p,b,ctx))
        rejected=await decide(200,2,1,[])
        assert rejected[1]['state']=='rejected' and rejected[1]['conflicting_appointment_ids']==[a['id']]
        assert (await mutation(db,a['id'],'cancel'))[0]==200
        accepted=await decide(201,3,1,[])
        assert accepted[1]['state']=='accepted'
        async with db.session_factory() as s:
            assert not (await s.execute(select(m.slots).where(m.slots.c.doctor_id==1,m.slots.c.state=='bookable'))).all()
    run(database,work)


@pytest.mark.parametrize('target,expected',[(1,'ix_appointments_active_slot'),(3,'appointments_patient_overlap')])
def test_direct_sql_booking_constraints(database,target,expected):
    async def work(db):
        await booking(db)
        async with db.session_factory() as s:
            slot=await op.row(s,m.slots,target)
        async with db.session_factory() as s:
            with pytest.raises(IntegrityError) as exc:
                await s.execute(insert(m.appointments).values(id=900,patient_id=11,slot_id=target,
                    doctor_id=slot['doctor_id'],doctor_user_id=100+slot['doctor_id'],
                    starts_at=slot['starts_at'],ends_at=slot['ends_at'],schedule_revision=1,state='confirmed'))
            assert exc.value.orig.diag.constraint_name==expected
    run(database,work)


def test_cross_doctor_reschedules_share_sorted_locks(database):
    async def work(db):
        _,a=await booking(db)
        _,b=await booking(db,pid='12',sid=4)
        results=await asyncio.gather(mutation(db,a['id'],'reschedule',sid=3),
            mutation(db,b['id'],'reschedule',sid=2,pid='12'))
        assert all(code==200 for code,_ in results)
    run(database,work)


def test_schedule_preserves_booked_revision_and_future_adjacent_slots(database):
    async def work(db):
        _,a=await booking(db)
        async with db.session_factory() as s:
            sl=await op.row(s,m.slots,1)
        r=request('/api/v1/appointments/schedule-decisions')
        p=Principal('101',None,frozenset({'doctor'}),1,'test')
        b=Decide(doctor_id='1',proposal_id='400',expected_accepted_revision=1)
        ctx=ProposalContext(proposal={'id':'400','doctor_id':'1','revision':2,'status':'pending','timezone':'UTC',
            'slot_minutes':30,'intervals':[{'starts_at':sl['starts_at'],'ends_at':sl['ends_at']+timedelta(minutes=60)}],
            'conflicts':[],'version':1},staff_user_id='101',active=True,doctor_version=1)
        ident,fp=op.idempotency(r,p,b.model_dump())
        code,d=await op.command(db.session_factory,ident,fp,lambda s:op.decide(s,r,p,b,ctx))
        assert code==201 and d['state']=='accepted'
        async with db.session_factory() as s:
            booked=await op.row(s,m.appointments,a['id'])
            updated_slot=await op.row(s,m.slots,1)
        assert booked['schedule_revision']==1 and updated_slot['schedule_revision']==2
        assert (await mutation(db,a['id'],'cancel'))[0]==200
    run(database,work)


def test_postgres_serialization_retry_rolls_back_whole_command(database):
    async def work(db):
        r=request(); p=patient(); b=Book(patient_id='11',slot_id='1',expected_schedule_revision=1)
        attempts=0
        async def command(s):
            nonlocal attempts
            attempts+=1
            result=await op.book(s,r,p,b,identity())
            if attempts<3:
                await s.execute(text("DO $$ BEGIN RAISE EXCEPTION 'injected retry' USING ERRCODE='40001'; END $$"))
            return result
        ident,fp=op.idempotency(r,p,b.model_dump())
        assert (await op.command(db.session_factory,ident,fp,command))[0]==201
        assert attempts==3
        async with db.session_factory() as s:
            for table in (m.appointments,m.audit_entries,m.outbox_events,m.idempotency_requests):
                assert len((await s.execute(select(table))).all())==1
    run(database,work)


def test_id_collision_retries_are_bounded(database,monkeypatch):
    async def work(db):
        _,a=await booking(db)
        original=op.new_id
        values=iter([int(a['id']),9000,9001,9002])
        monkeypatch.setattr(op,'new_id',lambda:next(values))
        result=await booking(db,pid='12',sid=2)
        assert result[0]==201 and result[1]['id']=='9000'
        monkeypatch.setattr(op,'new_id',lambda:int(a['id']))
        assert await booking(db,pid='13',sid=3)==(503,'dependency_unavailable')
        monkeypatch.setattr(op,'new_id',original)
        async with db.session_factory() as s:
            assert len((await s.execute(select(m.appointments))).all())==2
    run(database,work)
