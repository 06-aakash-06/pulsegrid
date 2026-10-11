"""Local transactions: idempotency, sorted locks, constraints, audit and outbox."""
import asyncio
import hashlib
import json
import random
import re
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import select, insert, update, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from . import models as m

ACTIVE=('confirmed','checked_in','in_consultation')


def now():
    return datetime.now(timezone.utc)


def new_id():
    return secrets.randbelow(2**63-1)+1


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def fail(code,status=409):
    raise HTTPException(status,detail=code)


def wire_time(value):
    return value.astimezone(timezone.utc).isoformat().replace('+00:00','Z')


def appointment(row):
    return {**{k:str(row[k]) for k in ('id','patient_id','doctor_id','slot_id')},
        'journey_id':None,'starts_at':wire_time(row['starts_at']),
        'ends_at':wire_time(row['ends_at']),'state':row['state'],'version':row['version']}


def decision(row):
    return {'proposal_id':str(row['id']),'doctor_id':str(row['doctor_id']),
        'revision':row['revision'],'state':row['state'],'reason_code':row['reason_code'],
        'conflicting_appointment_ids':[str(i) for i in row['conflicting_appointment_ids']],
        'version':row['version']}


def precondition(value):
    if value is None:
        fail('precondition_required',428)
    if not re.fullmatch(r'"[1-9][0-9]{0,15}"',value) or int(value[1:-1])>9007199254740991:
        fail('bad_request',400)
    return int(value[1:-1])


def idempotency(request, principal, body, caller=None):
    key=request.headers.get('Idempotency-Key','')
    if not re.fullmatch(r'[\x21-\x7e]{16,128}',key):
        fail('validation_error',422)
    scope=f'user:{principal.user_id}'
    if caller:
        scope=f'service:{caller}:'+scope
    route=request.url.path
    fingerprint=digest({'body':body,'if_match':request.headers.get('If-Match'),'path':route})
    return {'principal_scope':scope,'method':'POST','route_template':route,'key':key},fingerprint


async def advisory(session,value):
    number=int.from_bytes(hashlib.sha256(value.encode()).digest()[:8],signed=True)
    await session.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':number})


async def row(session,table,id_value,lock=False):
    stmt=select(table).where(table.c.id==int(id_value))
    if lock:
        stmt=stmt.with_for_update()
    result=(await session.execute(stmt)).mappings().first()
    if result is None:
        fail('not_found',404)
    return dict(result)


async def audit(session,request,principal,action,resource_id,reason=None):
    metadata={'action':action,'result':'success','actor_user_id':principal.user_id,
        'resource_id':str(resource_id),'request_id':str(request.state.request_id),
        'correlation_id':str(request.state.correlation_id),'occurred_at':wire_time(now())}
    if reason:
        metadata['reason_digest']=hashlib.sha256(reason.encode()).hexdigest()
    await session.execute(text('SELECT public.appointment_append_audit(:id,CAST(:metadata AS jsonb))'),
        {'id':new_id(),'metadata':canonical(metadata)})


async def _append_effect(session,request,principal,action,row_value,payload,reason=None):
    await audit(session,request,principal,action,row_value['id'],reason)
    event_id=new_id()
    kind='schedule' if action.startswith('schedule_') else 'appointment'
    names={'booked':'appointment.booked.v1','cancelled':'appointment.cancelled.v1',
        'rescheduled':'appointment.rescheduled.v1','schedule_accepted':'appointment.schedule.accepted.v1',
        'schedule_rejected':'appointment.schedule.rejected.v1',
        'clinical_hold':'appointment.clinical_hold.acquired.v1',
        'hold_finalized':'appointment.clinical_hold.finalized.v1'}
    event_type=names[action]
    envelope={'event_id':str(event_id),'event_type':event_type,'schema_version':1,
        'producer':'appointment','occurred_at':wire_time(now()),'aggregate_type':kind,
        'aggregate_id':str(row_value['id']),'aggregate_version':row_value['version'],
        'correlation_id':str(request.state.correlation_id),'request_id':str(request.state.request_id),
        'causation_id':None,'traceparent':getattr(request.state,'traceparent',None),'payload':payload}
    await session.execute(insert(m.outbox_events).values(event_id=event_id,
        aggregate_type=kind,aggregate_id=row_value['id'],aggregate_version=row_value['version'],
        event_type=event_type,envelope=envelope))



def stage_effect(session, request, principal, action, row_value, payload, reason=None):
    """Participants stage effects; only command finalization acquires audit head."""
    if not session.in_transaction() or session.info.get('effects_flushed'):
        raise RuntimeError('Effects require an unfinished owner transaction')
    # Copy mutable payloads so later participant changes cannot rewrite effects.
    session.info.setdefault('appointment_effects', []).append(
        (request, principal, action, dict(row_value), json.loads(canonical(payload)), reason))


async def effect(session,request,principal,action,row_value,payload,reason=None):
    stage_effect(session,request,principal,action,row_value,payload,reason)


async def flush_effects(session):
    if session.info.get('effects_flushed'):
        raise RuntimeError('Effects already finalized')
    session.info['effects_flushed'] = True
    from .phase3_core import FeatureEffect, append_feature_effect
    for item in session.info.pop('appointment_effects', []):
        if isinstance(item, FeatureEffect):
            await append_feature_effect(session, item)
        else:
            await _append_effect(session, *item)


async def replay(session,identity,fingerprint):
    criteria=[m.idempotency_requests.c[k]==v for k,v in identity.items()]
    found=(await session.execute(select(m.idempotency_requests).where(*criteria))).mappings().first()
    if found:
        if found['request_hash']!=fingerprint:
            fail('conflict')
        return found['response_code'],found['response']


async def command(factory,identity,fingerprint,work):
    for attempt in range(3):
        try:
            async with factory() as session,session.begin():
                await advisory(session,'command:'+canonical(identity))
                cached=await replay(session,identity,fingerprint)
                if cached:
                    return cached
                code,result=await work(session)
                await flush_effects(session)
                await session.execute(insert(m.idempotency_requests).values(**identity,
                    request_hash=fingerprint,response_code=code,response=result,expires_at=now()+timedelta(days=1)))
                return code,result
        except Restart:
            if attempt==2:
                fail('dependency_unavailable',503)
        except DBAPIError as exc:
            state=getattr(exc.orig,'sqlstate',None)
            constraint=getattr(getattr(exc.orig,'diag',None),'constraint_name','') or ''
            if state in ('40P01','40001') or state=='23505' and (constraint.startswith('pk_') or constraint=='uq_audit_entries_entry_id'):
                if attempt==2:
                    fail('dependency_unavailable',503)
            elif state in ('23505','23P01'):
                if constraint=='appointments_patient_overlap':
                    fail('patient_overlap')
                if constraint in ('ix_appointments_active_slot','slots_doctor_overlap'):
                    fail('slot_occupied')
                fail('clinical_hold' if constraint=='clinical_holds_consultation_id_key' else 'conflict')
            elif state=='23514':
                fail('clinical_hold' if constraint=='appointment_clinical_hold' else 'conflict')
            else:
                raise
        await asyncio.sleep(random.uniform(.01,.05))


class Restart(Exception):
    """Preliminary discovery changed; rollback before acquiring new locks."""


async def lock_doctors(session,doctor_ids):
    for doctor_id in sorted(set(doctor_ids)):
        await session.execute(select(m.doctor_schedule_snapshots).where(
            m.doctor_schedule_snapshots.c.doctor_id==doctor_id).with_for_update())


async def lock_resources(session,slot_ids,appointment_id=None):
    preliminary=[await row(session,m.slots,i) for i in sorted(set(slot_ids))]
    await lock_doctors(session,[s['doctor_id'] for s in preliminary])
    locked=[await row(session,m.slots,i,True) for i in sorted(set(slot_ids))]
    if [(s['id'],s['doctor_id']) for s in preliminary]!=[(s['id'],s['doctor_id']) for s in locked]:
        raise Restart()
    a=await row(session,m.appointments,appointment_id,True) if appointment_id else None
    if a and a['slot_id'] not in slot_ids:
        raise Restart()
    hold=None
    if a:
        hold=(await session.execute(select(m.clinical_holds).where(
            m.clinical_holds.c.appointment_id==a['id']).with_for_update())).mappings().first()
    if a:
        await session.execute(select(m.appointment_workflows).where(
            m.appointment_workflows.c.appointment_id==a['id']).with_for_update())
    return {s['id']:s for s in locked},a,hold


def can_access(principal,a,write=False):
    if 'receptionist' in principal.roles:
        return
    if 'patient' in principal.roles and principal.patient_id==str(a['patient_id']):
        return
    if not write and 'doctor' in principal.roles and principal.user_id==str(a['doctor_user_id']):
        return
    fail('not_found',404)


async def valid_slot(session,s,revision,identity):
    snapshot=(await session.execute(select(m.doctor_schedule_snapshots).where(
        m.doctor_schedule_snapshots.c.doctor_id==s['doctor_id']))).mappings().first()
    if not snapshot or s['state']!='bookable' or s['starts_at']<=now() or s['schedule_revision']!=revision or snapshot['accepted_revision']!=revision:
        fail('schedule_changed')
    if identity.doctor_id!=str(s['doctor_id']) or identity.staff_user_id!=str(snapshot['staff_user_id']) or not identity.active:
        fail('invalid_reference',422)
    return snapshot


def booking_payload(a):
    return {'appointment_id':str(a['id']),'journey_id':None,
        **{k:str(a[k]) for k in ('patient_id','doctor_id','slot_id')},
        'starts_at':wire_time(a['starts_at']),'ends_at':wire_time(a['ends_at']),
        'schedule_revision':a['schedule_revision']}


async def bump_operational_versions(session,doctor_ids):
    await session.execute(update(m.doctor_schedule_snapshots).where(
        m.doctor_schedule_snapshots.c.doctor_id.in_(set(doctor_ids))).values(
        version=m.doctor_schedule_snapshots.c.version+1,updated_at=now()))


async def book(session,request,p,body,identity):
    locked,_,_=await lock_resources(session,[int(body.slot_id)])
    s=locked[int(body.slot_id)]
    snap=await valid_slot(session,s,body.expected_schedule_revision,identity)
    a=dict((await session.execute(insert(m.appointments).values(id=new_id(),patient_id=int(body.patient_id),
        slot_id=s['id'],doctor_id=s['doctor_id'],doctor_user_id=snap['staff_user_id'],
        starts_at=s['starts_at'],ends_at=s['ends_at'],schedule_revision=s['schedule_revision'],
        state='confirmed').returning(m.appointments))).mappings().one())
    await bump_operational_versions(session,[a['doctor_id']])
    await effect(session,request,p,'booked',a,booking_payload(a))
    return 201,appointment(a)


async def change(session,request,p,aid,body,identity=None):
    preliminary=await row(session,m.appointments,aid)
    slot_ids=[preliminary['slot_id']]
    if identity:
        slot_ids.append(int(body.target_slot_id))
    locked,a,hold=await lock_resources(session,slot_ids,aid)
    can_access(p,a,True)
    if a['version']!=precondition(request.headers.get('If-Match')):
        fail('version_conflict',412)
    if not identity and a['state']=='cancelled':
        return 200,appointment(a)
    if hold:
        fail('clinical_hold')
    workflow=(await session.execute(select(m.appointment_workflows).where(
        m.appointment_workflows.c.appointment_id==a['id']))).mappings().first()
    # Enrollment remains disabled at G0. Fail closed until G2 wires all
    # participants; never mutate an enrolled row without token/queue/journey hooks.
    if workflow:
        fail('workflow_locked')
    if a['state']!='confirmed':
        fail('cancelled' if a['state']=='cancelled' else 'conflict')
    values={'version':a['version']+1,'updated_at':now()}
    action='cancelled'
    payload=booking_payload(a)
    if identity:
        target=locked[int(body.target_slot_id)]
        snap=await valid_slot(session,target,body.expected_schedule_revision,identity)
        values.update(slot_id=target['id'],doctor_id=target['doctor_id'],doctor_user_id=snap['staff_user_id'],
            starts_at=target['starts_at'],ends_at=target['ends_at'],schedule_revision=target['schedule_revision'])
        action='rescheduled'
        previous={'previous_slot_id':str(a['slot_id']),'previous_starts_at':wire_time(a['starts_at']),
            'previous_ends_at':wire_time(a['ends_at'])}
    else:
        values['state']='cancelled'
        payload['reason_code']='requested'
    updated=dict((await session.execute(update(m.appointments).where(m.appointments.c.id==a['id']).values(**values)
        .returning(m.appointments))).mappings().one())
    if identity:
        payload={**booking_payload(updated),**previous}
    await bump_operational_versions(session,[a['doctor_id'],updated['doctor_id']])
    await effect(session,request,p,action,updated,payload,body.reason if not identity else None)
    return 200,appointment(updated)


async def decide(session,request,p,body,context):
    proposal=context.proposal
    doctor_id=int(body.doctor_id)
    await advisory(session,f'doctor-init:{doctor_id}')
    await session.execute(pg_insert(m.doctor_schedule_snapshots).values(doctor_id=doctor_id,
        accepted_revision=0,policy_snapshot={},staff_user_id=int(context.staff_user_id),
        last_decided_proposal_revision=0).on_conflict_do_nothing())
    snap=(await session.execute(select(m.doctor_schedule_snapshots).where(
        m.doctor_schedule_snapshots.c.doctor_id==doctor_id).with_for_update())).mappings().one()
    prior=(await session.execute(select(m.schedule_proposals).where(m.schedule_proposals.c.id==int(body.proposal_id)))).mappings().first()
    if prior:
        if prior['doctor_id']!=doctor_id or prior['revision']!=proposal.revision:
            fail('conflict')
        return 201,decision(prior)
    if snap['accepted_revision']!=body.expected_accepted_revision:
        fail('schedule_changed')
    if proposal.revision!=snap['last_decided_proposal_revision']+1:
        fail('revision_gap')
    if snap['staff_user_id']!=int(context.staff_user_id):
        fail('invalid_reference',422)
    existing=(await session.execute(select(m.slots).where(m.slots.c.doctor_id==doctor_id).order_by(m.slots.c.id).with_for_update())).mappings().all()
    bookings=(await session.execute(select(m.appointments).where(m.appointments.c.doctor_id==doctor_id,
        m.appointments.c.state.in_(ACTIVE)).order_by(m.appointments.c.id).with_for_update())).mappings().all()
    intervals=[]
    step=timedelta(minutes=proposal.slot_minutes)
    for interval in proposal.intervals:
        t=interval.starts_at
        while t<interval.ends_at:
            intervals.append((t,t+step))
            t+=step
    wanted=set(intervals)
    conflicts=[str(a['id']) for a in bookings if (a['starts_at'],a['ends_at']) not in wanted]
    state='rejected' if conflicts else 'accepted'
    if not conflicts:
        # Retire first, avoiding transient exclusion collisions during replacement.
        await session.execute(update(m.slots).where(m.slots.c.doctor_id==doctor_id).values(state='retired',updated_at=now()))
        by_interval={(s['starts_at'],s['ends_at']):s for s in existing}
        for start,end in intervals:
            if (start,end) in by_interval:
                await session.execute(update(m.slots).where(m.slots.c.id==by_interval[start,end]['id']).values(
                    state='bookable',schedule_revision=proposal.revision,version=m.slots.c.version+1,updated_at=now()))
            else:
                await session.execute(insert(m.slots).values(id=new_id(),doctor_id=doctor_id,
                    starts_at=start,ends_at=end,schedule_revision=proposal.revision,state='bookable'))
    values={'last_decided_proposal_revision':proposal.revision,'version':snap['version']+1,'updated_at':now()}
    if not conflicts:
        values.update(accepted_revision=proposal.revision,policy_snapshot=proposal.model_dump(mode='json'))
    await session.execute(update(m.doctor_schedule_snapshots).where(m.doctor_schedule_snapshots.c.doctor_id==doctor_id).values(**values))
    d=dict((await session.execute(insert(m.schedule_proposals).values(id=int(body.proposal_id),doctor_id=doctor_id,
        revision=proposal.revision,state=state,staff_user_id=int(context.staff_user_id),
        reason_code='booked_interval_removed' if conflicts else None,conflicting_appointment_ids=conflicts)
        .returning(m.schedule_proposals))).mappings().one())
    payload={'proposal_id':str(d['id']),'doctor_id':str(doctor_id),'revision':d['revision']}
    payload.update({'reason_code':d['reason_code'],'conflicting_appointment_ids':conflicts} if conflicts else {'accepted_at':wire_time(now())})
    await effect(session,request,p,'schedule_'+state,d,payload)
    return 201,decision(d)


async def context(session,a):
    # One statement snapshot keeps the hold and its appointment version aligned.
    joined=(await session.execute(select(m.appointments,m.clinical_holds.c.state.label('hold_state'))
        .select_from(m.appointments.outerjoin(m.clinical_holds,
            m.clinical_holds.c.appointment_id==m.appointments.c.id))
        .where(m.appointments.c.id==a['id']))).mappings().one()
    return {'appointment_id':str(joined['id']),'patient_id':str(joined['patient_id']),
        'doctor_id':str(joined['doctor_id']),'doctor_user_id':str(joined['doctor_user_id']),
        'journey_id':None,'state':joined['state'],'clinical_hold':joined['hold_state'] or 'none',
        'version':joined['version']}


async def clinical_hold(session,request,p,aid,body,finalize=False):
    preliminary=await row(session,m.appointments,aid)
    _,a,hold=await lock_resources(session,[preliminary['slot_id']],aid)
    if 'doctor' not in p.roles or p.user_id!=str(a['doctor_user_id']):
        fail('not_found',404)
    if a['version']!=precondition(request.headers.get('If-Match')):
        fail('version_conflict',412)
    workflow=(await session.execute(select(m.appointment_workflows).where(
        m.appointment_workflows.c.appointment_id==a['id']))).mappings().first()
    if workflow and workflow['state']!='in_consultation':
        fail('workflow_locked')
    if a['state']!='confirmed':
        fail('appointment_unavailable')
    if hold and hold['consultation_id']!=int(body.consultation_id):
        fail('clinical_hold')
    if finalize and not hold:
        fail('clinical_hold')
    changed=not hold or finalize and hold['state']=='active'
    if changed:
        if hold:
            await session.execute(update(m.clinical_holds).where(m.clinical_holds.c.appointment_id==a['id']).values(state='finalized'))
        else:
            await session.execute(insert(m.clinical_holds).values(appointment_id=a['id'],consultation_id=int(body.consultation_id),state='active'))
        a=dict((await session.execute(update(m.appointments).where(m.appointments.c.id==a['id']).values(
            version=a['version']+1,updated_at=now()).returning(m.appointments))).mappings().one())
        await effect(session,request,p,'hold_finalized' if finalize else 'clinical_hold',a,
            {'resource_id':str(a['id']),'version':a['version'],'state':'finalized' if finalize else 'active'})
    return 200,await context(session,a)
