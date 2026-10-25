"""Sequential coordinator assembly of the service-local feature participants."""
from dataclasses import replace
from types import MappingProxyType
from sqlalchemy import select
from . import models as m, phase3_core as core


async def create_episode(session, context, booking):
    from .features.journey.registration import on_booking_created
    inserted = replace(context, bookings=MappingProxyType({booking['id']: MappingProxyType(dict(booking))}))
    session.info['phase3_lock_context'] = inserted
    try:
        await on_booking_created(session, inserted)
        jid = (await session.execute(select(m.journeys.c.id).where(
            m.journeys.c.appointment_id == booking['id']))).scalar_one()
        await core.enroll_workflow(session, inserted, booking['id'], jid)
        return jid
    finally:
        session.info['phase3_lock_context'] = context


async def book(session,request,principal,body,identity):
    from . import operations as op
    from .features.waitlist.operations import guard_target
    ctx=await core.lock_context(session,request,core.ActorScope.user(principal),
        core.LockPlan(waitlist_slot_ids=(int(body.slot_id),),promotion_slot_ids=(int(body.slot_id),)))
    await guard_target(session,body.slot_id)
    code,value=await op.book(session,request,principal,body,identity,phase3_context=ctx)
    booking=await op.row(session,m.appointments,value['id'])
    jid=await create_episode(session,ctx,booking)
    value['journey_id']=str(jid)
    return code,value


async def change(session,request,principal,aid,body,prepared,identity=None):
    from dataclasses import replace
    from datetime import timedelta
    from . import operations as op
    from .features.waitlist import operations as waitlist,offers
    from .features.queue import service as queue
    from .features.checkin.registration import revoke_for_booking_change
    from .features.journey.registration import on_booking_changed
    preliminary=await op.row(session,m.appointments,aid)
    if preliminary['slot_id']!=prepared.slot_id:raise op.Restart()
    plan=await queue._complete_plan(session,preliminary['doctor_id'],preliminary['starts_at'].date(),(int(aid),))
    slots={prepared.slot_id}
    if identity:slots.add(int(body.target_slot_id))
    plan=replace(plan,waitlist_slot_ids=tuple(sorted(slots)),waitlist_patient_ids=prepared.patient_ids,
                 promotion_slot_ids=(prepared.slot_id,))
    ctx=await core.lock_context(session,request,core.ActorScope.user(principal),plan)
    if identity:await waitlist.guard_target(session,body.target_slot_id)
    a=ctx.bookings[int(aid)];op.can_access(principal,a,True)
    if a['version']!=op.precondition(request.headers.get('If-Match')):op.fail('version_conflict',412)
    wf=ctx.workflows.get(int(aid))
    if not identity and a['state']=='cancelled':
        return 200,{**op.appointment(a),'journey_id':str(wf['journey_id']) if wf else None}
    if wf:
        if int(aid) in ctx.holds:op.fail('clinical_hold')
        if wf['state'] not in (('booked',) if identity else ('booked','checked_in')):op.fail('workflow_locked')
        await revoke_for_booking_change(session,ctx,aid)
        if not identity:await queue.cancel_for_booking_change(session,ctx,int(aid))
    code,value=await op.change(session,request,principal,aid,body,identity,phase3_context=ctx,workflow_participants=True)
    changed=await op.row(session,m.appointments,aid)
    if wf and identity:
        await session.execute(m.appointment_workflows.update().where(m.appointment_workflows.c.appointment_id==int(aid))
            .values(slot_id=changed['slot_id'],doctor_id=changed['doctor_id'],schedule_revision=changed['schedule_revision'],
                schedule_fingerprint=core.schedule_fingerprint(changed),window_starts_at=changed['starts_at']-timedelta(minutes=30),
                window_ends_at=changed['starts_at']+timedelta(minutes=15),version=wf['version']+1,updated_at=ctx.now))
    if wf:
        await on_booking_changed(session,ctx,aid)
        value['journey_id']=str(wf['journey_id'])
    if a['state']=='confirmed' and (not identity or prepared.slot_id!=int(body.target_slot_id)):
        await waitlist.mark_pending(session,prepared.slot_id,ctx.now)
        try:await offers.promote(session,ctx,prepared)
        except op.Restart:
            # Release remains permitted even if owner-discovery membership moved.
            await waitlist.mark_pending(session,prepared.slot_id,ctx.now)
    return code,value


async def prepare_release(request,booking):
    from .features.waitlist.operations import prepare
    from .features.waitlist.eligibility import fetch as fetch_eligibility
    async def fetch(ids):
        return await fetch_eligibility(request,ids)
    return await prepare(core.session_factory(request),booking['slot_id'],fetch)
