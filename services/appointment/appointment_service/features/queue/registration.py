"""Frozen Phase 3 queue exports; routes remain disabled until G2 review."""
from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field
from sqlalchemy import select

from appointment_service import models as m, operations as op, phase3_core as core
from appointment_service.wire import ID, Input
from . import service
from .schema_spec import schema_spec


class Empty(Input):
    pass


class Reason(Input):
    reason: str = Field(min_length=1, max_length=500)


def register_tables(metadata) -> None:
    service.register_tables(metadata)


async def allocate_on_checkin(session, context) -> dict:
    return await service.allocate_on_checkin(session, context)


async def complete_from_records(session, context, records_snapshot) -> None:
    await service.complete_from_records(session, context, records_snapshot)


async def cancel_for_booking_change(session, context, appointment_id) -> None:
    await service.cancel_for_booking_change(session, context, appointment_id)


async def _doctor_scope(request, principal, doctor_id):
    role = await core.current(request, principal, ('doctor', 'receptionist'))
    async with core.session_factory(request)() as session:
        row = (await session.execute(select(m.doctor_schedule_snapshots.c.staff_user_id).where(
            m.doctor_schedule_snapshots.c.doctor_id == doctor_id))).scalar_one_or_none()
    if row is None or (role == 'doctor' and str(row) != principal.user_id):
        op.fail('not_found', 404)
    return role


async def _entry_scope(request, principal, entry_id):
    async with core.session_factory(request)() as session:
        entry = await service._entry(session, entry_id)
    await core.current(request, principal, ('doctor',))
    async with core.session_factory(request)() as session:
        user_id = (await session.execute(select(m.doctor_schedule_snapshots.c.staff_user_id).where(
            m.doctor_schedule_snapshots.c.doctor_id == entry['doctor_id']))).scalar_one_or_none()
    if user_id is None or str(user_id) != principal.user_id:
        op.fail('not_found', 404)
    return entry


def register_routes(app, core_module) -> None:
    if core_module is not core:
        raise ValueError('Queue must use shared G0 core')
    router = APIRouter()
    prefix = '/api/v1/appointments'

    @router.get(prefix + '/queues')
    async def staff_queue(request: Request, doctor_id: ID, local_date: date,
                          state: str | None = None, cursor: str | None = None,
                          limit: int = Query(default=20, ge=1, le=100),
                          principal=Depends(core.authenticated_user)):
        core.query_keys(request, {'doctor_id', 'local_date', 'state', 'cursor', 'limit'})
        if state is not None and state not in service.STATES:
            op.fail('validation_error', 422)
        await _doctor_scope(request, principal, int(doctor_id))
        async with core.session_factory(request)() as session, session.begin():
            result = await service.staff_snapshot(session, int(doctor_id), local_date,
                                                  state, cursor, limit, core.ActorScope.user(principal))
        return core.response(200, result)

    @router.get(prefix + '/{appointment_id}/queue')
    async def own_queue(request: Request, appointment_id: ID,
                        principal=Depends(core.authenticated_user)):
        core.query_keys(request, set())
        await core.authorize(request, principal, ('patient', 'receptionist', 'doctor'),
                             appointment_id)
        async with core.session_factory(request)() as session, session.begin():
            result = await service.own_snapshot(session, appointment_id)
        response = core.response(200, result)
        response.headers['ETag'] = f'"{result["entry"]["version"]}"'
        return response

    @router.post(prefix + '/queue-entries/{entry_id}/start')
    async def start(request: Request, entry_id: ID, body: Empty,
                    principal=Depends(core.authenticated_user)):
        entry = await _entry_scope(request, principal, int(entry_id))
        expected = core.precondition(request.headers.get('If-Match'))
        actor = core.ActorScope.user(principal)

        async def work(session):
            plan = await service._complete_plan(session, entry['doctor_id'], entry['local_date'])
            context = await core.lock_context(session, request, actor, plan)
            current = await service._entry(session, int(entry_id))
            if current['doctor_id'] != entry['doctor_id'] or current['local_date'] != entry['local_date']:
                raise op.Restart()
            result = await service.start_entry(session, context, int(entry_id), expected)
            return 200, result

        return await core.execute(request, principal, body.model_dump(), work)

    @router.post(prefix + '/{appointment_id}/no-show')
    async def mark_no_show(request: Request, appointment_id: ID, body: Reason,
                           principal=Depends(core.authenticated_user)):
        await core.authorize(request, principal, ('receptionist',), appointment_id, write=True)
        expected = core.precondition(request.headers.get('If-Match'))
        reason = body.reason.strip()
        if not reason:
            op.fail('validation_error', 422)
        actor = core.ActorScope.user(principal)

        async def work(session):
            booking = await op.row(session, m.appointments, int(appointment_id))
            workflow = await core.read_workflow(session, appointment_id)
            if workflow is None:
                op.fail('not_found', 404)
            queue_id = workflow['queue_entry_id']
            day = None
            if queue_id is not None:
                entry = await service._entry(session, queue_id)
                day = entry['local_date']
            plan = await service._complete_plan(session, booking['doctor_id'],
                day or booking['starts_at'].date(), (int(appointment_id),))
            context = await core.lock_context(session, request, actor, plan)
            if context.workflows[int(appointment_id)]['queue_entry_id'] != queue_id:
                raise op.Restart()
            result = await service.no_show(session, context, appointment_id, expected, reason)
            return 200, result

        return await core.execute(request, principal, body.model_dump(), work)

    async def transition(request, principal, entry_id, body, recall):
        core.query_keys(request, ())
        entry = await _entry_scope(request, principal, int(entry_id))
        expected = core.precondition(request.headers.get('If-Match'))
        reason = body.reason.strip()
        if not reason:
            op.fail('validation_error', 422)
        async def work(session):
            plan = await service._complete_plan(session, entry['doctor_id'], entry['local_date'])
            ctx = await core.lock_context(session, request, core.ActorScope.user(principal), plan)
            return 200, await service.skip_or_recall(session, ctx, int(entry_id), expected, recall, reason)
        return await core.execute(request, principal, body.model_dump(), work)

    @router.post(prefix + '/queue-entries/{entry_id}/skip')
    async def skip(request: Request, entry_id: ID, body: Reason, principal=Depends(core.authenticated_user)):
        return await transition(request, principal, entry_id, body, False)

    @router.post(prefix + '/queue-entries/{entry_id}/recall')
    async def recall(request: Request, entry_id: ID, body: Reason, principal=Depends(core.authenticated_user)):
        return await transition(request, principal, entry_id, body, True)

    @router.get(prefix + '/queue-entries/{entry_id}/history')
    async def history(request: Request, entry_id: ID, cursor: ID | None = None,
                      limit: int = Query(20, ge=1, le=100), principal=Depends(core.authenticated_user)):
        from sqlalchemy import text
        core.query_keys(request, ('cursor', 'limit'))
        async with core.session_factory(request)() as session:
            entry = await service._entry(session, int(entry_id))
        await core.authorize(request, principal, ('patient', 'receptionist', 'doctor'), entry['appointment_id'])
        async with core.session_factory(request)() as session, session.begin():
            rows = (await session.execute(text('SELECT id,from_state,to_state,occurred_at,version '
                'FROM queue_transitions WHERE entry_id=:entry AND id>:cursor ORDER BY id LIMIT :limit'),
                dict(entry=int(entry_id),cursor=int(cursor or '0'),limit=limit+1))).mappings().all()
            await op.audit(session, request, principal, 'read', entry_id)
        return core.response(200, dict(items=[dict(id=str(r['id']),from_state=r['from_state'],
            to_state=r['to_state'],occurred_at=op.wire_time(r['occurred_at']),version=r['version']) for r in rows[:limit]],
            next_cursor=str(rows[limit-1]['id']) if len(rows)>limit else None))

    app.include_router(router)
