import asyncio
from datetime import timedelta
from types import SimpleNamespace

import psycopg
import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import insert, select, text, update

from appointment_service import models as m, operations as op, phase3_core as core
from appointment_service.database import Database
from appointment_service.features.queue import registration, service
from ..test_concurrency import booking, patient, request, run


def install_queue_schema(database):
    """Only this random isolated test database; production migration is G2."""
    with psycopg.connect(host=database.db_host, port=database.db_port,
                         dbname=database.db_name, user='appointment_owner') as conn:
        conn.execute('ALTER TABLE queue_entries ADD COLUMN position integer')
        conn.execute('CREATE TABLE queue_snapshots (doctor_id bigint NOT NULL REFERENCES '
                     'doctor_schedule_snapshots(doctor_id), local_date date NOT NULL, '
                     'version bigint NOT NULL CHECK (version BETWEEN 1 AND 9007199254740991), '
                     'created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL, '
                     'PRIMARY KEY (doctor_id, local_date))')
        conn.execute('GRANT SELECT,INSERT,UPDATE ON queue_snapshots TO appointment_app')
    service.register_tables(core.metadata)


async def enroll(db, aid, journey_id):
    async with db.session_factory() as session, session.begin():
        booking_row = await op.row(session, m.appointments, aid)
        await session.execute(insert(m.journeys).values(id=journey_id,
            appointment_id=aid, patient_id=booking_row['patient_id'], state='active'))
        await session.execute(insert(m.appointment_workflows).values(
            appointment_id=aid, journey_id=journey_id, patient_id=booking_row['patient_id'],
            doctor_id=booking_row['doctor_id'], slot_id=booking_row['slot_id'],
            schedule_revision=1, schedule_fingerprint=core.schedule_fingerprint(booking_row),
            state='booked', window_starts_at=booking_row['starts_at']-timedelta(minutes=30),
            window_ends_at=booking_row['starts_at']+timedelta(minutes=15)))


async def move_test_slots_into_window(db):
    start = op.now()+timedelta(minutes=10)
    async with db.session_factory() as session, session.begin():
        for sid, offset in ((1, 0), (2, 5)):
            await session.execute(update(m.slots).where(m.slots.c.id == sid).values(
                starts_at=start+timedelta(minutes=offset),
                ends_at=start+timedelta(minutes=offset+5)))


async def checkin(db, aid):
    actor = core.ActorScope.user(patient())
    async with db.session_factory() as session, session.begin():
        booking_row = await op.row(session, m.appointments, aid)
        day = op.now().date()
        existing = (await session.execute(select(m.queue_entries.c.id).where(
            m.queue_entries.c.doctor_id == booking_row['doctor_id']))).scalars().all()
        context = await core.lock_context(session, request(), actor, core.LockPlan(
            appointment_ids=(aid,), doctor_ids=(booking_row['doctor_id'],),
            queue_days=((booking_row['doctor_id'], day),), queue_entry_ids=tuple(existing)))
        return await registration.allocate_on_checkin(session, context)


def test_registration_manifest_and_cursor_contract():
    app = FastAPI()
    registration.register_tables(core.metadata)
    registration.register_routes(app, core)
    assert callable(registration.allocate_on_checkin)
    assert callable(registration.complete_from_records)
    assert {'tables', 'columns', 'indexes', 'constraints', 'preflight', 'runtime_grants'} <= registration.schema_spec().keys()
    paths = set(app.openapi()['paths'])
    assert '/api/v1/appointments/queues' in paths
    assert '/api/v1/appointments/queue-entries/{entry_id}/start' in paths
    assert '/api/v1/appointments/{appointment_id}/no-show' in paths
    scope = service._scope_hash(1, op.now().date(), None, core.ActorScope.user(patient()))
    cursor = service.cursor_encode(2, 3, 4, scope)
    assert service.cursor_decode(cursor, scope)['v'] == 2
    with pytest.raises(HTTPException) as exc:
        service.cursor_decode(cursor, 'another-scope')
    assert exc.value.status_code == 400


def test_allocation_persistence_fifo_and_concurrent_start(database):
    install_queue_schema(database)

    async def work(db):
        await move_test_slots_into_window(db)
        async with db.session_factory() as session, session.begin():
            await session.execute(update(m.doctor_schedule_snapshots).values(
                policy_snapshot={'timezone': 'UTC'}))
        _, first_booking = await booking(db, '11', 1)
        _, second_booking = await booking(db, '12', 2)
        first_aid, second_aid = int(first_booking['id']), int(second_booking['id'])
        await enroll(db, first_aid, 7001)
        await enroll(db, second_aid, 7002)
        first = await checkin(db, first_aid)
        second = await checkin(db, second_aid)
        assert (first['token_number'], first['position']) == (1, 1)
        assert (second['token_number'], second['position']) == (2, 2)
        assert first['id'] != second['id']

        async def start(entry):
            req = request(f'/api/v1/appointments/queue-entries/{entry["id"]}/start', entry['version'])
            principal = SimpleNamespace(user_id='101')
            identity, fingerprint = op.idempotency(req, principal, {})

            async def command(session):
                plan = await service._complete_plan(session, 1, op.now().date())
                context = await core.lock_context(session, req, core.ActorScope.user(patient()), plan)
                return 200, await service.start_entry(session, context, int(entry['id']), entry['version'])

            try:
                return await op.command(db.session_factory, identity, fingerprint, command)
            except HTTPException as exc:
                return exc.status_code, exc.detail

        results = await asyncio.gather(start(first), start(second))
        assert sum(code == 200 for code, _ in results) == 1
        assert next(value for code, value in results if code != 200) in (
            'doctor_busy', 'not_queue_head', 'version_conflict')
        async with db.session_factory() as session:
            first_row = await service._entry(session, int(first['id']))
            second_row = await service._entry(session, int(second['id']))
            assert first_row['state'] == 'in_consultation'
            assert first_row['position'] is None
            assert second_row['position'] == 1
            own = await service.own_snapshot(session, second_aid)
            assert 'patient_id' not in own['entry']
            assert own['queue_version'] == 3
            staff = await service.staff_snapshot(session, 1, op.now().date(), None, None, 1,
                                                 core.ActorScope.user(patient()))
            assert staff['next_cursor']
            with pytest.raises(HTTPException) as exc:
                await service.staff_snapshot(session, 1, op.now().date(), None,
                                             service.cursor_encode(1, 1, 1,
                                                 service._scope_hash(1, op.now().date(), None,
                                                     core.ActorScope.user(patient()))), 1,
                                             core.ActorScope.user(patient()))
            assert exc.value.detail == 'queue_changed'
    run(database, work)


def test_duplicate_start_replay(database):
    install_queue_schema(database)

    async def work(db):
        await move_test_slots_into_window(db)
        async with db.session_factory() as session, session.begin():
            await session.execute(update(m.doctor_schedule_snapshots).values(
                policy_snapshot={'timezone': 'UTC'}))
        _, b = await booking(db)
        aid = int(b['id'])
        await enroll(db, aid, 7003)
        entry = await checkin(db, aid)
        req = request(f'/api/v1/appointments/queue-entries/{entry["id"]}/start', 1)
        principal = SimpleNamespace(user_id='101')
        identity, fingerprint = op.idempotency(req, principal, {})

        async def command(session):
            plan = await service._complete_plan(session, 1, op.now().date())
            ctx = await core.lock_context(session, req, core.ActorScope.user(patient()), plan)
            return 200, await service.start_entry(session, ctx, int(entry['id']), 1)

        first, replay = await asyncio.gather(
            op.command(db.session_factory, identity, fingerprint, command),
            op.command(db.session_factory, identity, fingerprint, command))
        assert first == replay
        async with db.session_factory() as session:
            count = (await session.execute(text("SELECT count(*) FROM queue_entries WHERE state='in_consultation'"))).scalar_one()
            assert count == 1
    run(database, work)


def test_completion_requires_finalized_matching_record_and_hold(database):
    install_queue_schema(database)

    async def work(db):
        await move_test_slots_into_window(db)
        async with db.session_factory() as session, session.begin():
            await session.execute(update(m.doctor_schedule_snapshots).values(
                policy_snapshot={'timezone': 'UTC'}))
        _, b = await booking(db)
        aid = int(b['id'])
        await enroll(db, aid, 7010)
        entry = await checkin(db, aid)
        req = request(f'/api/v1/appointments/queue-entries/{entry["id"]}/start', 1)
        async with db.session_factory() as session, session.begin():
            plan = await service._complete_plan(session, 1, op.now().date())
            ctx = await core.lock_context(session, req, core.ActorScope.user(patient()), plan)
            await service.start_entry(session, ctx, int(entry['id']), 1)
        async with db.session_factory() as session, session.begin():
            await session.execute(insert(m.clinical_holds).values(
                appointment_id=aid, consultation_id=8801, state='finalized'))

        snapshot = {'appointment_id': str(aid), 'patient_id': '11', 'doctor_id': '1',
                    'consultation': {'id': '8801', 'status': 'finalized'}}
        async with db.session_factory() as session, session.begin():
            plan = await service._complete_plan(session, 1, op.now().date())
            ctx = await core.lock_context(session, request(), core.worker_actor(), plan)
            with pytest.raises(HTTPException) as exc:
                await service.complete_from_records(session, ctx,
                    {**snapshot, 'consultation': {'id': '8802', 'status': 'finalized'}})
            assert exc.value.detail == 'invalid_reference'
            await service.complete_from_records(session, ctx, snapshot)
            await service.complete_from_records(session, ctx, snapshot)
        async with db.session_factory() as session:
            final = await service._entry(session, int(entry['id']))
            assert final['state'] == 'completed' and final['position'] is None
            workflow = await core.read_workflow(session, aid)
            assert workflow['state'] == 'completed'
    run(database, work)


def test_cancellation_repositions_and_no_show_window_gate(database):
    install_queue_schema(database)

    async def work(db):
        await move_test_slots_into_window(db)
        async with db.session_factory() as session, session.begin():
            await session.execute(update(m.doctor_schedule_snapshots).values(
                policy_snapshot={'timezone': 'UTC'}))
        _, a = await booking(db, '11', 1)
        _, b = await booking(db, '12', 2)
        a_id, b_id = int(a['id']), int(b['id'])
        await enroll(db, a_id, 7020)
        await enroll(db, b_id, 7021)
        first = await checkin(db, a_id)
        second = await checkin(db, b_id)
        async with db.session_factory() as session, session.begin():
            plan = await service._complete_plan(session, 1, op.now().date())
            ctx = await core.lock_context(session, request(), core.ActorScope.user(patient()), plan)
            with pytest.raises(HTTPException) as exc:
                await service.no_show(session, ctx, a_id, 2, 'synthetic reason')
            assert exc.value.detail == 'checkin_window_open'
            await service.cancel_for_booking_change(session, ctx, a_id)
        async with db.session_factory() as session:
            assert (await service._entry(session, int(first['id'])))['state'] == 'cancelled'
            assert (await service._entry(session, int(second['id'])))['position'] == 1
            assert (await core.read_workflow(session, a_id))['state'] == 'cancelled'
    run(database, work)


def test_assigned_doctor_and_reception_scope(database, monkeypatch):
    async def fake_current(_request, principal, roles):
        role = next((name for name in roles if name in principal.roles), None)
        if role is None:
            op.fail('forbidden', 403)
        return role

    monkeypatch.setattr(core, 'current', fake_current)

    async def work(db):
        request_with_db = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(database=db)))
        own = SimpleNamespace(user_id='101', roles=frozenset({'doctor'}))
        wrong = SimpleNamespace(user_id='999', roles=frozenset({'doctor'}))
        desk = SimpleNamespace(user_id='500', roles=frozenset({'receptionist'}))
        patient_user = SimpleNamespace(user_id='11', roles=frozenset({'patient'}))
        assert await registration._doctor_scope(request_with_db, own, 1) == 'doctor'
        assert await registration._doctor_scope(request_with_db, desk, 1) == 'receptionist'
        for principal, status in ((wrong, 404), (patient_user, 403)):
            with pytest.raises(HTTPException) as exc:
                await registration._doctor_scope(request_with_db, principal, 1)
            assert exc.value.status_code == status
    run(database, work)


def test_parallel_allocation_serializes_counter_and_retries_discovery(database):
    install_queue_schema(database)

    async def work(db):
        await move_test_slots_into_window(db)
        async with db.session_factory() as session, session.begin():
            await session.execute(update(m.doctor_schedule_snapshots).values(
                policy_snapshot={'timezone': 'UTC'}))
        _, a = await booking(db, '11', 1)
        _, b = await booking(db, '12', 2)
        aids = (int(a['id']), int(b['id']))
        for aid, jid in zip(aids, (7030, 7031)):
            await enroll(db, aid, jid)

        async def allocate(aid):
            req = request(f'/api/v1/appointments/{aid}/check-in')
            identity, fingerprint = op.idempotency(req, patient(), {})

            async def command(session):
                rows = (await session.execute(select(m.queue_entries.c.id))).scalars().all()
                ctx = await core.lock_context(session, req, core.ActorScope.user(patient()),
                    core.LockPlan(appointment_ids=(aid,), doctor_ids=(1,),
                                  queue_days=((1, op.now().date()),),
                                  queue_entry_ids=tuple(rows)))
                return 200, await service.allocate_on_checkin(session, ctx)

            return await op.command(db.session_factory, identity, fingerprint, command)

        results = await asyncio.gather(*(allocate(aid) for aid in aids))
        assert sorted(result['token_number'] for _, result in results) == [1, 2]
        assert sorted(result['position'] for _, result in results) == [1, 2]
        async with db.session_factory() as session:
            next_token = (await session.execute(select(m.queue_counters.c.next_token))).scalar_one()
            assert next_token == 3
    run(database, work)
