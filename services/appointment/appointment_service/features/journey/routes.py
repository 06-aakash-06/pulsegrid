"""Persisted journey reads and explicit source reconciliation/discharge commands."""
from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy import select, text
from ... import models as m, operations as op, phase3_core as core
from ...wire import ID, Input, Cancel
from ...api.router import early_replay
from . import service

router=APIRouter()
PREFIX='/api/v1/appointments/journeys'


class Empty(Input):
    pass


async def authorized(request,p,jid,write=False):
    await core.current(request,p,('receptionist',) if write else ('patient','receptionist','doctor'))
    async with core.session_factory(request)() as session:
        journey=await op.row(session,m.journeys,jid)
        booking=await op.row(session,m.appointments,journey['appointment_id'])
    op.can_access(p,booking)
    return journey


@router.get(PREFIX)
async def listing(request:Request,patient_id:ID|None=None,appointment_id:ID|None=None,
                  state:str|None=None,cursor:ID|None=None,limit:int=Query(20,ge=1,le=100),
                  p=Depends(core.authenticated_user)):
    core.query_keys(request,('patient_id','appointment_id','state','cursor','limit'))
    role=await core.current(request,p,('patient','receptionist','doctor'))
    conditions=[m.journeys.c.id>int(cursor or '0')]
    if role=='patient':
        if not p.patient_id or patient_id and patient_id!=p.patient_id: op.fail('not_found',404)
        patient_id=p.patient_id
    if role=='doctor': conditions.append(m.appointments.c.doctor_user_id==int(p.user_id))
    if patient_id: conditions.append(m.journeys.c.patient_id==int(patient_id))
    if appointment_id: conditions.append(m.journeys.c.appointment_id==int(appointment_id))
    if state:
        if state not in ('active','ready','discharged','reopened','cancelled','no_show'):op.fail('validation_error',422)
        conditions.append(m.journeys.c.state==state)
    async with core.session_factory(request)() as session,session.begin():
        ids=(await session.execute(select(m.journeys.c.id).join(m.appointments,
            m.appointments.c.id==m.journeys.c.appointment_id).where(*conditions).order_by(m.journeys.c.id).limit(limit+1))).scalars().all()
        result=[await service.view(session,jid) for jid in ids[:limit]]
        await op.audit(session,request,p,'read',p.user_id)
    return core.response(200,dict(items=result,next_cursor=str(ids[limit-1]) if len(ids)>limit else None))


@router.get(PREFIX+'/{journey_id}')
async def detail(request:Request,journey_id:ID,p=Depends(core.authenticated_user)):
    core.query_keys(request,())
    await authorized(request,p,journey_id)
    async with core.session_factory(request)() as session,session.begin():
        result=await service.view(session,journey_id)
        await op.audit(session,request,p,'read',journey_id)
    return core.response(200,result)


@router.get(PREFIX+'/{journey_id}/history')
async def history(request:Request,journey_id:ID,cursor:ID|None=None,limit:int=Query(20,ge=1,le=100),
                  p=Depends(core.authenticated_user)):
    core.query_keys(request,('cursor','limit'))
    await authorized(request,p,journey_id)
    async with core.session_factory(request)() as session,session.begin():
        rows=(await session.execute(text('SELECT id,stage,from_state,to_state,occurred_at FROM journey_transitions '
            'WHERE journey_id=:jid AND id>:cursor ORDER BY id LIMIT :limit'),
            dict(jid=int(journey_id),cursor=int(cursor or '0'),limit=limit+1))).mappings().all()
        await op.audit(session,request,p,'read',journey_id)
    return core.response(200,dict(items=[dict(id=str(r['id']),stage=r['stage'],from_state=r['from_state'],
        to_state=r['to_state'],occurred_at=op.wire_time(r['occurred_at'])) for r in rows[:limit]],
        next_cursor=str(rows[limit-1]['id']) if len(rows)>limit else None))


async def command(request,p,jid,body,discharge):
    core.query_keys(request,())
    journey=await authorized(request,p,jid,write=discharge)
    _,_,cached=await early_replay(request,p,body.model_dump())
    if cached:return core.response(*cached)
    expected=core.precondition(request.headers.get('If-Match'))
    sources,failures=await service.fetch(request,journey)
    async def work(session):
        from ..queue.service import _complete_plan
        booking=await op.row(session,m.appointments,journey['appointment_id'])
        plan=await _complete_plan(session,booking['doctor_id'],booking['starts_at'].date(),(booking['id'],))
        ctx=await core.lock_context(session,request,core.ActorScope.user(p),plan)
        result=await service.apply(session,ctx,jid,sources,failures,expected,discharge,
                                   body.reason if discharge else None)
        return 200,result
    return await core.execute(request,p,body.model_dump(),work)


@router.post(PREFIX+'/{journey_id}/reconcile')
async def reconcile(request:Request,journey_id:ID,body:Empty,p=Depends(core.authenticated_user)):
    return await command(request,p,journey_id,body,False)


@router.post(PREFIX+'/{journey_id}/discharge')
async def discharge(request:Request,journey_id:ID,body:Cancel,p=Depends(core.authenticated_user)):
    return await command(request,p,journey_id,body,True)
