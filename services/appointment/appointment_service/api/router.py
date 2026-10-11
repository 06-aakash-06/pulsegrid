"""Frozen Phase 2.3 public commands and private owner-only leaves."""
import base64
import json
from datetime import timedelta
from typing import Annotated
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter
from sqlalchemy import select, and_, or_, func, literal
from ..authorization import authenticated_user
from ..dependencies import current, private_principal
from ..wire import (
    ID, Time, Book, Move, Cancel, Decide, Hold, Identity, PatientStatus, ProposalContext,
    AppointmentView, AppointmentPage, AvailabilityView, DecisionView,
    ConsultationContextView, BillingContextView, OperationalStatusView,
)
from .. import models as m
from .. import operations as op

async def command_query_keys(request:Request):
    if request.method=='POST' and request.query_params:
        op.fail('validation_error',422)


api_router=APIRouter(dependencies=[Depends(command_query_keys)])
PUBLIC='/api/v1/appointments'


def factory(request):
    result=request.app.state.database.session_factory
    if result is None:
        op.fail('dependency_unavailable',503)
    return result


def response(code,value):
    headers={'Cache-Control':'no-store'}
    if 'version' in value:
        headers['ETag']=f'"{value["version"]}"'
    return JSONResponse(value,status_code=code,headers=headers)


def query_keys(request,allowed):
    if set(request.query_params)-set(allowed) or any(len(request.query_params.getlist(k))!=1 for k in request.query_params):
        op.fail('validation_error',422)


async def early_replay(request,p,body,caller=None):
    identity,fingerprint=op.idempotency(request,p,body,caller)
    async with factory(request)() as session:
        cached=await op.replay(session,identity,fingerprint)
    return identity,fingerprint,cached


async def execute(request,p,body,work,caller=None):
    identity,fingerprint=op.idempotency(request,p,body,caller)
    code,value=await op.command(factory(request),identity,fingerprint,work)
    return response(code,value)


async def doctor_identity(request,p,slot_id):
    async with factory(request)() as session:
        slot=await op.row(session,m.slots,slot_id)
    value=await request.app.state.domain_client.get(request,p,'doctor',
        f'/internal/v1/doctors/{slot["doctor_id"]}/identity','doctors:identity',Identity)
    if value.doctor_id!=str(slot['doctor_id']) or not value.active:
        op.fail('invalid_reference',422)
    return value


async def patient_status(request,p,patient_id):
    status=await request.app.state.domain_client.get(request,p,'patient',
        f'/internal/v1/patients/{patient_id}/status','patients:status',PatientStatus)
    if status.patient_id!=patient_id or not status.active:
        op.fail('invalid_reference',422)


async def accessible(request,p,aid,write=False):
    async with factory(request)() as session:
        a=await op.row(session,m.appointments,aid)
    op.can_access(p,a,write)
    return a


@api_router.post(PUBLIC+'/schedule-decisions', response_model=DecisionView, status_code=201)
async def decide(request:Request,body:Decide,p=Depends(authenticated_user)):
    await current(request,p,('hospital_admin','doctor'))
    identity,fingerprint,cached=await early_replay(request,p,body.model_dump())
    if cached:
        async with factory(request)() as session:
            d=await op.row(session,m.schedule_proposals,body.proposal_id)
        schedule_scope(p,d['staff_user_id'])
        return response(*cached)
    ctx=await request.app.state.domain_client.get(request,p,'doctor',
        f'/internal/v1/doctors/{body.doctor_id}/schedule-proposals/{body.proposal_id}',
        'schedules:read',ProposalContext)
    schedule_scope(p,ctx.staff_user_id)
    if ctx.proposal.id!=body.proposal_id or ctx.proposal.doctor_id!=body.doctor_id or not ctx.active:
        op.fail('invalid_reference',422)
    validate_proposal(ctx.proposal)
    return await execute(request,p,body.model_dump(),lambda s:op.decide(s,request,p,body,ctx))


def schedule_scope(p,staff_user_id,receptionist=False):
    if 'hospital_admin' in p.roles or receptionist and 'receptionist' in p.roles:
        return
    if 'doctor' in p.roles and p.user_id==str(staff_user_id):
        return
    op.fail('not_found',404)


def validate_proposal(proposal):
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        if len(proposal.timezone)>128:
            raise ValueError()
        ZoneInfo(proposal.timezone)
    except (ZoneInfoNotFoundError,ValueError):
        op.fail('dependency_unavailable',503)
    intervals=proposal.intervals
    step=timedelta(minutes=proposal.slot_minutes)
    if len(intervals)>64 or proposal.status not in ('pending','accepted','rejected'):
        op.fail('dependency_unavailable',503)
    count=0
    for index,interval in enumerate(intervals):
        if interval.starts_at<=op.now() or interval.ends_at>op.now()+timedelta(days=366) or (interval.ends_at-interval.starts_at)%step:
            op.fail('dependency_unavailable',503)
        if index and intervals[index-1].ends_at>interval.starts_at:
            op.fail('dependency_unavailable',503)
        count+=(interval.ends_at-interval.starts_at)//step
    if count>1000 or intervals and intervals[-1].ends_at-intervals[0].starts_at>timedelta(days=31):
        op.fail('dependency_unavailable',503)


@api_router.get(PUBLIC+'/schedule-decisions/{proposal_id}', response_model=DecisionView)
async def get_decision(request:Request,proposal_id:ID,p=Depends(authenticated_user)):
    query_keys(request,())
    await current(request,p,('hospital_admin','receptionist','doctor'))
    async with factory(request)() as s,s.begin():
        d=await op.row(s,m.schedule_proposals,proposal_id)
        schedule_scope(p,d['staff_user_id'],True)
        await op.audit(s,request,p,'read',proposal_id)
        return response(200,op.decision(d))


@api_router.get(PUBLIC+'/availability', response_model=AvailabilityView)
async def availability(request:Request,doctor_id:ID,
        start:Annotated[Time,Query(alias='from')],end:Annotated[Time,Query(alias='to')],
        p=Depends(authenticated_user)):
    query_keys(request,('doctor_id','from','to'))
    if not start<end or end-start>timedelta(days=31):
        op.fail('validation_error',422)
    async with factory(request)() as s:
        # A single statement gives revision and slots one PostgreSQL statement snapshot.
        occupied=select(m.appointments.c.id).where(m.appointments.c.slot_id==m.slots.c.id,
            m.appointments.c.state.in_(op.ACTIVE)).exists()
        if getattr(request.app.state,'phase3_enabled',False):
            reserved=select(m.waitlist_entries.c.id).where(m.waitlist_entries.c.slot_id==m.slots.c.id,m.waitlist_entries.c.state=='waiting').exists()
            occupied=occupied|reserved
        valid=and_(m.slots.c.doctor_id==m.doctor_schedule_snapshots.c.doctor_id,
            m.slots.c.state=='bookable',m.slots.c.starts_at>=start,m.slots.c.ends_at<=end,
            m.slots.c.starts_at>op.now(),~occupied)
        rows=(await s.execute(select(m.slots,m.doctor_schedule_snapshots.c.accepted_revision)
            .select_from(m.doctor_schedule_snapshots.outerjoin(m.slots,valid))
            .where(m.doctor_schedule_snapshots.c.doctor_id==int(doctor_id))
            .order_by(m.slots.c.starts_at,m.slots.c.id).limit(1001))).mappings().all()
    if len(rows)>1000:
        op.fail('validation_error',422)
    slots=[{'id':str(r['id']),'doctor_id':str(r['doctor_id']),'starts_at':op.wire_time(r['starts_at']),
        'ends_at':op.wire_time(r['ends_at']),'state':r['state'],'revision':r['schedule_revision']} for r in rows if r['id'] is not None]
    return response(200,{'slots':slots,'accepted_revision':rows[0]['accepted_revision'] if rows else 0,
        'observed_at':op.wire_time(op.now())})


@api_router.post(PUBLIC, response_model=AppointmentView, status_code=201)
async def book(request:Request,body:Book,p=Depends(authenticated_user)):
    role=await current(request,p,('receptionist','patient'))
    if role=='patient' and p.patient_id!=body.patient_id:
        op.fail('not_found',404)
    _,_,cached=await early_replay(request,p,body.model_dump())
    if cached:
        return response(*cached)
    await patient_status(request,p,body.patient_id)
    identity=await doctor_identity(request,p,body.slot_id)
    if getattr(request.app.state,'phase3_enabled',False):
        from ..integration import book as integrated_book
        return await execute(request,p,body.model_dump(),lambda s:integrated_book(s,request,p,body,identity))
    return await execute(request,p,body.model_dump(),lambda s:op.book(s,request,p,body,identity))


@api_router.get(PUBLIC, response_model=AppointmentPage)
async def appointments(request:Request,patient_id:ID|None=None,doctor_id:ID|None=None,
        state:str|None=None,cursor:str|None=None,limit:int=Query(default=20,ge=1,le=100),
        p=Depends(authenticated_user)):
    query_keys(request,('patient_id','doctor_id','state','cursor','limit'))
    role=await current(request,p,('receptionist','patient','doctor'))
    if state is not None and state not in ('confirmed','cancelled'):
        op.fail('validation_error',422)
    conditions=[]
    if role=='patient':
        if not p.patient_id:
            op.fail('not_found',404)
        conditions.append(m.appointments.c.patient_id==int(p.patient_id))
    elif role=='doctor':
        conditions.append(m.appointments.c.doctor_user_id==int(p.user_id))
    filters={'patient_id':patient_id,'doctor_id':doctor_id,'state':state,'scope':[p.user_id,role,p.patient_id]}
    filter_hash=op.digest(filters)
    for key,value in (('patient_id',patient_id),('doctor_id',doctor_id),('state',state)):
        if value is not None:
            conditions.append(m.appointments.c[key]==(value if key=='state' else int(value)))
    if cursor:
        try:
            if len(cursor)>2048:
                raise ValueError()
            data=json.loads(base64.b64decode(cursor+'='*(-len(cursor)%4),altchars=b'-_',validate=True))
            if set(data)!= {'created_at','id','filter_hash'} or data['filter_hash']!=filter_hash:
                raise ValueError()
            stamp=TypeAdapter(Time).validate_python(data['created_at'])
            cid=int(TypeAdapter(ID).validate_python(data['id']))
        except (ValueError,TypeError,KeyError):
            op.fail('bad_request',400)
        conditions.append(or_(m.appointments.c.created_at>stamp,
            and_(m.appointments.c.created_at==stamp,m.appointments.c.id>cid)))
    async with factory(request)() as s,s.begin():
        rows=(await s.execute(select(m.appointments).where(*conditions)
            .order_by(m.appointments.c.created_at,m.appointments.c.id).limit(limit+1))).mappings().all()
        refs=dict((await s.execute(select(m.appointment_workflows.c.appointment_id,m.appointment_workflows.c.journey_id).where(m.appointment_workflows.c.appointment_id.in_([r['id'] for r in rows])))).all())
        await op.audit(s,request,p,'read',p.user_id)
    next_cursor=None
    if len(rows)>limit:
        last=rows[limit-1]
        next_cursor=base64.urlsafe_b64encode(op.canonical({'created_at':op.wire_time(last['created_at']),
            'id':str(last['id']),'filter_hash':filter_hash}).encode()).decode().rstrip('=')
    return response(200,{'items':[{**op.appointment(r),'journey_id':str(refs[r['id']]) if r['id'] in refs else None} for r in rows[:limit]],'next_cursor':next_cursor})


@api_router.get(PUBLIC+'/{appointment_id}', response_model=AppointmentView)
async def get_appointment(request:Request,appointment_id:ID,p=Depends(authenticated_user)):
    query_keys(request,())
    await current(request,p,('receptionist','patient','doctor'))
    async with factory(request)() as s,s.begin():
        a=await op.row(s,m.appointments,appointment_id)
        op.can_access(p,a)
        await op.audit(s,request,p,'read',appointment_id)
        jid=(await s.execute(select(m.appointment_workflows.c.journey_id).where(m.appointment_workflows.c.appointment_id==int(appointment_id)))).scalar_one_or_none()
        return response(200,{**op.appointment(a),'journey_id':str(jid) if jid else None})


@api_router.post(PUBLIC+'/{appointment_id}/cancel', response_model=AppointmentView)
async def cancel(request:Request,appointment_id:ID,body:Cancel,p=Depends(authenticated_user)):
    await current(request,p,('receptionist','patient'))
    a=await accessible(request,p,appointment_id,True)
    _,_,cached=await early_replay(request,p,body.model_dump())
    if cached:
        return response(*cached)
    op.precondition(request.headers.get('If-Match'))
    if getattr(request.app.state,'phase3_enabled',False):
        from ..integration import change as integrated_change,prepare_release
        prepared=await prepare_release(request,a)
        return await execute(request,p,body.model_dump(),lambda s:integrated_change(s,request,p,appointment_id,body,prepared))
    return await execute(request,p,body.model_dump(),lambda s:op.change(s,request,p,appointment_id,body))


@api_router.post(PUBLIC+'/{appointment_id}/reschedule', response_model=AppointmentView)
async def reschedule(request:Request,appointment_id:ID,body:Move,p=Depends(authenticated_user)):
    await current(request,p,('receptionist','patient'))
    a=await accessible(request,p,appointment_id,True)
    _,_,cached=await early_replay(request,p,body.model_dump())
    if cached:
        return response(*cached)
    op.precondition(request.headers.get('If-Match'))
    await patient_status(request,p,str(a['patient_id']))
    identity=await doctor_identity(request,p,body.target_slot_id)
    if getattr(request.app.state,'phase3_enabled',False):
        from ..integration import change as integrated_change,prepare_release
        prepared=await prepare_release(request,a)
        return await execute(request,p,body.model_dump(),lambda s:integrated_change(s,request,p,appointment_id,body,prepared,identity))
    return await execute(request,p,body.model_dump(),lambda s:op.change(s,request,p,appointment_id,body,identity))


@api_router.get('/internal/v1/schedule-decisions/{proposal_id}', response_model=DecisionView)
async def private_decision(request:Request,proposal_id:ID):
    query_keys(request,())
    p=private_principal(request,'doctor','schedule-decisions:read')
    async with factory(request)() as s,s.begin():
        d=await op.row(s,m.schedule_proposals,proposal_id)
        schedule_scope(p,d['staff_user_id'])
        await op.audit(s,request,p,'read',proposal_id)
        return response(200,op.decision(d))


@api_router.get('/internal/v1/doctors/{doctor_id}/operational-status', response_model=OperationalStatusView)
async def operational_status(request:Request,doctor_id:ID):
    query_keys(request,())
    p=private_principal(request,'doctor','schedules:status')
    async with factory(request)() as s,s.begin():
        slots=select(func.count()).select_from(m.slots).where(m.slots.c.doctor_id==int(doctor_id),
            m.slots.c.state=='bookable',m.slots.c.starts_at>op.now()).scalar_subquery()
        bookings=select(func.count()).select_from(m.appointments).where(m.appointments.c.doctor_id==int(doctor_id),
            m.appointments.c.state=='confirmed').scalar_subquery()
        one=select(literal(1)).subquery()
        result=(await s.execute(select(m.doctor_schedule_snapshots.c.staff_user_id,
            m.doctor_schedule_snapshots.c.version,slots.label('slot_count'),bookings.label('booking_count'))
            .select_from(one.outerjoin(m.doctor_schedule_snapshots,
                m.doctor_schedule_snapshots.c.doctor_id==int(doctor_id))))).mappings().one()
        # Without a snapshot there is no local trusted mapping for own-doctor scope.
        schedule_scope(p,result['staff_user_id'])
        await op.audit(s,request,p,'read',doctor_id)
        return response(200,{'doctor_id':doctor_id,'bookable_slot_count':result['slot_count'],
            'confirmed_booking_count':result['booking_count'],'version':result['version'] or 1})



@api_router.get('/internal/v1/appointments/{appointment_id}/consultation-context', response_model=ConsultationContextView)
async def consultation_context(request:Request,appointment_id:ID):
    query_keys(request,())
    p=private_principal(request,'records','appointments:consultation-context')
    async with factory(request)() as s,s.begin():
        a=await op.row(s,m.appointments,appointment_id)
        result=await op.context(s,a)
        if not ('doctor' in p.roles and p.user_id==result['doctor_user_id'] or
                'patient' in p.roles and p.patient_id==result['patient_id']):
            op.fail('not_found',404)
        await op.audit(s,request,p,'read',appointment_id)
        return response(200,result)


@api_router.get('/internal/v1/appointments/{appointment_id}/billing-context', response_model=BillingContextView)
async def billing_context(request:Request,appointment_id:ID):
    query_keys(request,())
    p=private_principal(request,'billing','appointments:billing-context')
    if 'billing_staff' not in p.roles:
        op.fail('forbidden',403)
    async with factory(request)() as s,s.begin():
        a=await op.row(s,m.appointments,appointment_id)
        await op.audit(s,request,p,'read',appointment_id)
        return response(200,{'appointment_id':appointment_id,'patient_id':str(a['patient_id']),
            'state':a['state'],'version':a['version']})


async def hold_command(request,appointment_id,body,finalize):
    p=private_principal(request,'records','appointments:clinical-hold')
    await accessible_hold(request,p,appointment_id)
    _,_,cached=await early_replay(request,p,body.model_dump(),'records')
    if cached:
        return response(*cached)
    op.precondition(request.headers.get('If-Match'))
    return await execute(request,p,body.model_dump(),lambda s:op.clinical_hold(
        s,request,p,appointment_id,body,finalize),'records')


async def accessible_hold(request,p,aid):
    async with factory(request)() as s:
        a=await op.row(s,m.appointments,aid)
    if 'doctor' not in p.roles or p.user_id!=str(a['doctor_user_id']):
        op.fail('not_found',404)
    return a


@api_router.post('/internal/v1/appointments/{appointment_id}/clinical-hold', response_model=ConsultationContextView)
async def acquire_hold(request:Request,appointment_id:ID,body:Hold):
    return await hold_command(request,appointment_id,body,False)


@api_router.post('/internal/v1/appointments/{appointment_id}/clinical-hold/finalize', response_model=ConsultationContextView)
async def finalize_hold(request:Request,appointment_id:ID,body:Hold):
    return await hold_command(request,appointment_id,body,True)
