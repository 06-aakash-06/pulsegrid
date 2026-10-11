import asyncio
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError
from sqlalchemy import insert, select, text, update
from sqlalchemy.exc import DBAPIError

from appointment_service import phase3_core as core, extensions, operations as op, models as m
from appointment_service.main import create_app
from ..test_concurrency import run, booking, request, patient, mutation


def test_linear_g0_migration_chain():
    from pathlib import Path
    config = Config(str(Path(__file__).resolve().parents[2] / 'alembic.ini'))
    config.set_main_option('script_location', str(Path(__file__).resolve().parents[2] / 'migrations'))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ['0004_phase3_core']
    assert [r.revision for r in script.walk_revisions()] == [
        '0004_phase3_core','0003_booking','0002_explicit_worker','0001_initial']
    assert all(r.branch_labels == set() and not r.is_merge_point for r in script.walk_revisions())


def test_disabled_registration_preserves_legacy_openapi():
    app = create_app()
    with patch.object(extensions, 'import_module', side_effect=AssertionError('must not import')):
        blank = FastAPI()
        extensions.register_extensions(blank, core)
    assert not app.state.appointment_extensions
    schema = app.openapi()
    legacy = schema['components']['schemas']['AppointmentView']['properties']
    assert legacy['state']['enum'] == ['confirmed','cancelled']
    assert legacy['journey_id']['type'] == 'null'
    assert not any('workflow' in path or 'waitlist' in path or 'queue' in path for path in schema['paths'])
    for path in ('/api/v1/appointments', '/api/v1/appointments/{appointment_id}',
                 '/api/v1/appointments/{appointment_id}/cancel',
                 '/internal/v1/appointments/{appointment_id}/clinical-hold'):
        assert path in schema['paths']


def test_registration_allowlist_exports_order_and_metadata():
    calls = []
    module = SimpleNamespace(
        register_routes=lambda app, c: calls.append(('routes', c)),
        register_tables=lambda metadata: calls.append(('tables', metadata)),
        schema_spec=lambda: {'tables': []},
        allocate_on_checkin=lambda *args: None, complete_from_records=lambda *args: None)
    app = FastAPI()
    with patch.object(extensions, 'import_module', return_value=module) as loader:
        extensions.register_extensions(app, core, enabled=('queue',))
        loader.assert_called_once_with('appointment_service.features.queue.registration')
    assert calls == [('tables',m.metadata),('routes',core)]
    with pytest.raises(TypeError):
        app.state.appointment_extensions['other'] = module
    for enabled in (('unknown',),('queue','queue')):
        with pytest.raises(ValueError):
            extensions.register_extensions(FastAPI(),core,enabled=enabled)
    with patch.object(extensions,'import_module',return_value=SimpleNamespace()):
        with pytest.raises(TypeError):
            extensions.register_extensions(FastAPI(),core,enabled=('journey',))
    with pytest.raises(RuntimeError):
        extensions.register_extensions(app,core)


async def fixture_context(db):
    _, a = await booking(db)
    return int(a['id'])


def test_lock_context_order_immutable_and_enrollment(database):
    async def work(db):
        aid = await fixture_context(db)
        async with db.session_factory() as s, s.begin():
            queries = []
            from sqlalchemy import event
            def record(conn,cursor,statement,parameters,context,many):
                if 'FOR UPDATE' in statement:
                    queries.append(statement)
            event.listen(db.engine.sync_engine,'before_cursor_execute',record)
            ctx = await core.lock_context(s,request(),core.ActorScope.user(patient()),
                core.LockPlan(appointment_ids=(aid,),waitlist_slot_ids=(1,),queue_days=((1,op.now().date()),)))
            event.remove(db.engine.sync_engine,'before_cursor_execute',record)
            names = ['doctor_schedule_snapshots','slots','appointments','clinical_holds',
                     'appointment_workflows','waitlist_entries','queue_counters']
            assert [next(name for name in names if 'FROM '+name+' ' in q or 'FROM '+name+'\n' in q) for q in queries] == names
            with pytest.raises(FrozenInstanceError):
                ctx.now = op.now()
            with pytest.raises(TypeError):
                ctx.bookings[aid]['patient_id'] = 99
            assert 'test' not in repr(ctx.actor)
            assert await core.read_workflow(s,aid) is None
            assert not (await s.execute(select(m.appointment_workflows))).all()
            with pytest.raises(RuntimeError):
                await core.lock_context(s,request(),core.worker_actor(),core.LockPlan())
            await s.execute(insert(m.journeys).values(id=500,appointment_id=aid,patient_id=11,state='active'))
            wf = await core.enroll_workflow(s,ctx,aid,500)
            wire = core.workflow_view(wf)
            assert wire['journey_id']=='500' and wire['state']=='booked' and wire['queue_entry_id'] is None
            with pytest.raises(ValidationError):
                core.Workflow.model_validate({**wire,'version':True})
        assert await mutation(db,aid,'cancel') == (409,'workflow_locked')
    run(database,work)


@pytest.mark.parametrize('fault',['none','participant','audit','outbox','response'])
def test_atomic_feature_effects_and_late_audit(database,fault):
    async def work(db):
        aid = await fixture_context(db)
        r=request('/synthetic-core-test'); p=patient()
        identity,fp=op.idempotency(r,p,{})
        async def work(s):
            ctx=await core.lock_context(s,r,core.worker_actor(),core.LockPlan(appointment_ids=(aid,)))
            await s.execute(insert(m.journeys).values(id=501,appointment_id=aid,patient_id=11,state='active'))
            await core.enroll_workflow(s,ctx,aid,501)
            core.stage_effect(s,ctx,'journey_created',501,1,dict(resource_id='501',version=1,state='active'))
            # Legacy booking audit is the only audit so far: participants have not
            # locked the audit head or appended any feature success yet.
            assert len((await s.execute(select(m.audit_entries))).all()) == 1
            if fault=='participant':
                raise RuntimeError('participant failure')
            if fault=='audit':
                from dataclasses import replace
                s.info['appointment_effects'][0]=replace(s.info['appointment_effects'][0],context=replace(ctx,request_id='invalid'))
            if fault=='outbox':
                s.info['appointment_effects'][0]=core.FeatureEffect(ctx,'journey_created',501,0,'{}',None)
            return (200,{'version':1}) if fault!='response' else (999,{'version':1})
        if fault=='none':
            first=await op.command(db.session_factory,identity,fp,work)
            assert await op.command(db.session_factory,identity,fp,work)==first
        else:
            with pytest.raises((RuntimeError,DBAPIError,HTTPException)):
                await op.command(db.session_factory,identity,fp,work)
        async with db.session_factory() as s:
            n=1 if fault=='none' else 0
            assert len((await s.execute(select(m.appointment_workflows))).all())==n
            assert len((await s.execute(select(m.journeys))).all())==n
            for table in (m.audit_entries,m.outbox_events,m.idempotency_requests):
                assert len((await s.execute(select(table))).all())==1+n
            if n:
                rows=(await s.execute(select(m.audit_entries).order_by(m.audit_entries.c.sequence))).mappings().all()
                assert rows[1]['prev_hash']==rows[0]['entry_hash']
                assert rows[1]['canonical_metadata']['actor_service']=='appointment'
    run(database,work)


@pytest.mark.parametrize('values',[
    {'state':'fake'}, {'version':0}, {'version':9007199254740992},
    {'schedule_revision':0}, {'schedule_fingerprint':'raw-token'},
    {'patient_id':-1}, {'patient_id':12}, {'doctor_id':2}, {'slot_id':2},
    {'journey_id':999}, {'queue_entry_id':999}, {'state':'checked_in'},
    {'window_ends_at':op.now()},
])
def test_workflow_database_bypass_rejected(database,values):
    async def work(db):
        aid=await fixture_context(db)
        with pytest.raises(DBAPIError):
            async with db.session_factory() as s,s.begin():
                ctx=await core.lock_context(s,request(),core.ActorScope.user(patient()),core.LockPlan(appointment_ids=(aid,)))
                await s.execute(insert(m.journeys).values(id=502,appointment_id=aid,patient_id=11,state='active'))
                await core.enroll_workflow(s,ctx,aid,502)
                await s.execute(update(m.appointment_workflows).where(m.appointment_workflows.c.appointment_id==aid).values(**values))
        async with db.session_factory() as s:
            assert not (await s.execute(select(m.appointment_workflows))).all()
    run(database,work)


def test_parent_binding_and_runtime_privileges(database):
    async def work(db):
        aid=await fixture_context(db)
        async with db.session_factory() as s,s.begin():
            ctx=await core.lock_context(s,request(),core.ActorScope.user(patient()),core.LockPlan(appointment_ids=(aid,)))
            await s.execute(insert(m.journeys).values(id=503,appointment_id=aid,patient_id=11,state='active'))
            await core.enroll_workflow(s,ctx,aid,503)
        with pytest.raises(DBAPIError):
            async with db.session_factory() as s,s.begin():
                await s.execute(update(m.journeys).where(m.journeys.c.id==503).values(patient_id=12))
        for sql in ('CREATE TABLE forbidden(id bigint)', 'DELETE FROM audit_entries',
                    'UPDATE audit_heads SET last_sequence=0'):
            with pytest.raises(DBAPIError):
                async with db.session_factory() as s,s.begin():
                    await s.execute(text(sql))
        async with db.session_factory() as s:
            assert (await s.execute(text('SELECT version_num FROM alembic_version'))).scalar_one()=='0004_phase3_core'
    run(database,work)


def test_disabled_hooks_and_foreign_session_rejected(database):
    async def work(db):
        aid=await fixture_context(db)
        app=create_app()
        async with db.session_factory() as s,s.begin():
            ctx=await core.lock_context(s,request(),core.ActorScope.user(patient()),core.LockPlan(appointment_ids=(aid,)))
            with pytest.raises(HTTPException) as exc:
                await core.invoke_participant(app,'queue','allocate_on_checkin',s,ctx)
            assert exc.value.status_code==503
            with pytest.raises(ValueError):
                await core.invoke_participant(app,'queue','arbitrary_hook',s,ctx)
            async with db.session_factory() as foreign,foreign.begin():
                with pytest.raises(RuntimeError):
                    core.require_context(foreign,ctx)
            await op.flush_effects(s)
            with pytest.raises(RuntimeError):
                core.stage_effect(s,ctx,'journey_updated',700,1,dict(resource_id='700',version=1,state='active'))
    run(database,work)


def test_real_queue_binding_and_parent_guard(database):
    async def work(db):
        aid=await fixture_context(db)
        _, other=await booking(db,pid='12',sid=2)
        async with db.session_factory() as s,s.begin():
            await s.execute(insert(m.queue_entries).values(id=600,appointment_id=aid,doctor_id=1,
                local_date=op.now().date(),token_number=1,state='waiting'))
            await s.execute(insert(m.queue_entries).values(id=601,appointment_id=int(other['id']),doctor_id=1,
                local_date=op.now().date(),token_number=2,state='waiting'))
            ctx=await core.lock_context(s,request(),core.ActorScope.user(patient()),
                core.LockPlan(appointment_ids=(aid,),queue_days=((1,op.now().date()),),queue_entry_ids=(600,)))
            await s.execute(insert(m.journeys).values(id=504,appointment_id=aid,patient_id=11,state='active'))
            await core.enroll_workflow(s,ctx,aid,504)
            await s.execute(update(m.appointment_workflows).where(m.appointment_workflows.c.appointment_id==aid).values(
                state='checked_in',queue_entry_id=600))
        for table,identity,values in (
            (m.appointment_workflows,aid,dict(queue_entry_id=601)),
            (m.queue_entries,600,dict(doctor_id=2)),
            (m.appointments,aid,dict(patient_id=13)),
        ):
            with pytest.raises(DBAPIError):
                async with db.session_factory() as s,s.begin():
                    column=table.c.appointment_id if table is m.appointment_workflows else table.c.id
                    await s.execute(update(table).where(column==identity).values(**values))
    run(database,work)


def test_deferred_binding_checks_final_atomic_schedule(database):
    async def work(db):
        aid=await fixture_context(db)
        async with db.session_factory() as s,s.begin():
            ctx=await core.lock_context(s,request(),core.ActorScope.user(patient()),core.LockPlan(appointment_ids=(aid,),slot_ids=(1,2)))
            await s.execute(insert(m.journeys).values(id=505,appointment_id=aid,patient_id=11,state='active'))
            await core.enroll_workflow(s,ctx,aid,505)
            target=await op.row(s,m.slots,2)
            await s.execute(update(m.appointments).where(m.appointments.c.id==aid).values(
                slot_id=2,starts_at=target['starts_at'],ends_at=target['ends_at']))
            await s.execute(update(m.appointment_workflows).where(m.appointment_workflows.c.appointment_id==aid).values(
                slot_id=2,window_starts_at=target['starts_at']-op.timedelta(minutes=30),
                window_ends_at=target['starts_at']+op.timedelta(minutes=15),
                schedule_fingerprint=core.schedule_fingerprint({**ctx.bookings[aid],**target,'slot_id':2})))
        async with db.session_factory() as s:
            assert (await core.read_workflow(s,aid))['slot_id']==2
    run(database,work)
