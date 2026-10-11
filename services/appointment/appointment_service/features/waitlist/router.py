"""Frozen routes, mounted only by explicit G2 registration."""
import base64
import json
from fastapi import APIRouter, Depends, Request, Query
from pydantic import TypeAdapter
from sqlalchemy import select, func, and_, or_
from ... import models as m, operations as op
from ...wire import ID, Time
from ...api.router import PUBLIC, command_query_keys, early_replay, doctor_identity, patient_status
from . import operations as w
from .wire import Join, Withdraw, Waitlist, Page, SlotStatus


def make_router(core):
    router = APIRouter(dependencies=[Depends(command_query_keys)])

    async def stored(request,p,entry_id,write=False):
        async with core.session_factory(request)() as session:
            row = await op.row(session,m.waitlist_entries,entry_id)
            doctor_user = (await session.execute(select(m.doctor_schedule_snapshots.c.staff_user_id)
                .join(m.slots,m.slots.c.doctor_id == m.doctor_schedule_snapshots.c.doctor_id)
                .where(m.slots.c.id == row['slot_id']))).scalar_one()
        w.scope(p,row,doctor_user,write)
        return row

    @router.post(PUBLIC+'/waitlists',response_model=Waitlist,status_code=201)
    async def join(request:Request,body:Join,p=Depends(core.authenticated_user)):
        role = await core.authorize(request,p,('receptionist','patient'))
        if role == 'patient' and p.patient_id != body.patient_id:
            op.fail('not_found',404)
        _,_,cached = await early_replay(request,p,body.model_dump())
        if cached:
            return core.response(*cached)
        await patient_status(request,p,body.patient_id)
        identity = await doctor_identity(request,p,body.slot_id)
        return await core.execute(request,p,body.model_dump(),lambda s:w.join(s,request,p,body,identity))

    @router.get(PUBLIC+'/waitlists',response_model=Page)
    async def listing(request:Request,patient_id:ID|None=None,slot_id:ID|None=None,
                      state:str|None=None,cursor:str|None=None,limit:int=Query(20,ge=1,le=100),
                      p=Depends(core.authenticated_user)):
        core.query_keys(request,('patient_id','slot_id','state','cursor','limit'))
        role = await core.authorize(request,p,('receptionist','patient','doctor'))
        if state is not None and state not in ('waiting','promoted','withdrawn','skipped'):
            op.fail('validation_error',422)
        conditions = []
        if role == 'patient':
            if not p.patient_id or patient_id is not None and patient_id != p.patient_id:
                op.fail('not_found',404)
            conditions.append(m.waitlist_entries.c.patient_id == int(p.patient_id))
        elif role == 'doctor':
            conditions.append(m.doctor_schedule_snapshots.c.staff_user_id == int(p.user_id))
        for name,value in (('patient_id',patient_id),('slot_id',slot_id),('state',state)):
            if value is not None:
                conditions.append(m.waitlist_entries.c[name] == (value if name == 'state' else int(value)))
        binding = op.digest(dict(patient_id=patient_id,slot_id=slot_id,state=state,scope=[p.user_id,role,p.patient_id]))
        if cursor:
            try:
                if len(cursor)>2048:
                    raise ValueError()
                data = json.loads(base64.b64decode(cursor+'='*(-len(cursor)%4),altchars=b'-_',validate=True))
                if set(data) != {'joined_at','id','filter_hash'} or data['filter_hash'] != binding:
                    raise ValueError()
                stamp = TypeAdapter(Time).validate_python(data['joined_at'])
                cid = int(TypeAdapter(ID).validate_python(data['id']))
            except (ValueError,TypeError,KeyError):
                op.fail('bad_request',400)
            conditions.append(or_(m.waitlist_entries.c.joined_at>stamp,and_(m.waitlist_entries.c.joined_at==stamp,m.waitlist_entries.c.id>cid)))
        async with core.session_factory(request)() as session,session.begin():
            rows = (await session.execute(select(m.waitlist_entries).join(m.slots,m.slots.c.id==m.waitlist_entries.c.slot_id)
                .join(m.doctor_schedule_snapshots,m.doctor_schedule_snapshots.c.doctor_id==m.slots.c.doctor_id)
                .where(*conditions).order_by(m.waitlist_entries.c.joined_at,m.waitlist_entries.c.id).limit(limit+1))).mappings().all()
            await op.audit(session,request,p,'read',p.user_id)
        next_cursor = None
        if len(rows)>limit:
            last = rows[limit-1]
            next_cursor = base64.urlsafe_b64encode(op.canonical(dict(joined_at=op.wire_time(last['joined_at']),
                id=str(last['id']),filter_hash=binding)).encode()).decode().rstrip('=')
        return core.response(200,dict(items=[w.view(r) for r in rows[:limit]],next_cursor=next_cursor))

    @router.get(PUBLIC+'/waitlists/{entry_id}',response_model=Waitlist)
    async def get(request:Request,entry_id:ID,p=Depends(core.authenticated_user)):
        core.query_keys(request,())
        await core.authorize(request,p,('receptionist','patient','doctor'))
        row = await stored(request,p,entry_id)
        async with core.session_factory(request)() as session,session.begin():
            await op.audit(session,request,p,'read',entry_id)
        return core.response(200,w.view(row))

    @router.post(PUBLIC+'/waitlists/{entry_id}/withdraw',response_model=Waitlist)
    async def withdraw(request:Request,entry_id:ID,body:Withdraw,p=Depends(core.authenticated_user)):
        await core.authorize(request,p,('receptionist','patient'))
        await stored(request,p,entry_id,True)
        _,_,cached = await early_replay(request,p,body.model_dump())
        if cached:
            return core.response(*cached)
        version = core.precondition(request.headers.get('If-Match'))
        return await core.execute(request,p,body.model_dump(),lambda s:w.withdraw(s,request,p,entry_id,version,body.reason))

    @router.get(PUBLIC+'/waitlist-slots/{slot_id}',response_model=SlotStatus)
    async def slot_status(request:Request,slot_id:ID,p=Depends(core.authenticated_user)):
        core.query_keys(request,())
        role = await core.authorize(request,p,('receptionist','patient','doctor'))
        async with core.session_factory(request)() as session,session.begin():
            row = (await session.execute(select(m.slots,m.doctor_schedule_snapshots.c.staff_user_id,
                m.doctor_schedule_snapshots.c.accepted_revision).join(m.doctor_schedule_snapshots,
                m.doctor_schedule_snapshots.c.doctor_id==m.slots.c.doctor_id).where(m.slots.c.id==int(slot_id)))).mappings().first()
            if row is None or role == 'doctor' and p.user_id != str(row['staff_user_id']):
                op.fail('not_found',404)
            count = (await session.execute(select(func.count()).select_from(m.waitlist_entries).where(
                m.waitlist_entries.c.slot_id==int(slot_id),m.waitlist_entries.c.state=='waiting'))).scalar_one()
            pending = await w.pending(session,slot_id)
            await op.audit(session,request,p,'read',slot_id)
        return core.response(200,dict(slot_id=slot_id,waiting_count=count,promotion_pending=pending,
            accepted_revision=row['accepted_revision'],observed_at=op.wire_time(op.now())))
    return router
