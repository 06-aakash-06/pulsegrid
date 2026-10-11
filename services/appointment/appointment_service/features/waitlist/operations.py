"""Waitlist participants. All effects remain in the caller's G0 transaction."""
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select, insert, update, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ... import models as m, operations as op, phase3_core as core
from .wire import Waitlist, EligibilityBatch


def view(row):
    return Waitlist(**{k: str(row[k]) for k in ('id','slot_id','patient_id')},
        state=row['state'], joined_at=row['joined_at'], version=row['version'],
        promoted_appointment_id=str(row['promoted_appointment_id']) if row['promoted_appointment_id'] else None,
        skip_reason=row['skip_reason']).model_dump(mode='json')


def scope(principal, row, doctor_user_id, write=False):
    if 'receptionist' in principal.roles:
        return
    if 'patient' in principal.roles and principal.patient_id == str(row['patient_id']):
        return
    if not write and 'doctor' in principal.roles and principal.user_id == str(doctor_user_id):
        return
    op.fail('not_found',404)


async def candidates(session, slot_id):
    return [dict(r) for r in (await session.execute(select(m.waitlist_entries).where(
        m.waitlist_entries.c.slot_id == int(slot_id), m.waitlist_entries.c.state == 'waiting')
        .order_by(m.waitlist_entries.c.joined_at,m.waitlist_entries.c.id).limit(50))).mappings()]


async def join(session, request, principal, body, identity):
    scope(principal,{'patient_id':int(body.patient_id)},None,True)
    ctx = await core.lock_context(session,request,core.ActorScope.user(principal),
        core.LockPlan(waitlist_slot_ids=(int(body.slot_id),)))
    slot = await op.row(session,m.slots,body.slot_id)
    await op.valid_slot(session,slot,body.expected_schedule_revision,identity)
    active = (await session.execute(select(m.appointments).where(m.appointments.c.slot_id == slot['id'],
        m.appointments.c.state.in_(op.ACTIVE)))).mappings().first()
    if active and active['patient_id'] == int(body.patient_id):
        op.fail('already_booked')
    if any(r['patient_id'] == int(body.patient_id) for r in (await session.execute(
        select(m.waitlist_entries).where(m.waitlist_entries.c.slot_id == slot['id'],
        m.waitlist_entries.c.state == 'waiting'))).mappings()):
        op.fail('already_waiting')
    if not active:
        op.fail('slot_available')
    row = dict((await session.execute(insert(m.waitlist_entries).values(id=op.new_id(),
        slot_id=slot['id'],patient_id=int(body.patient_id),state='waiting',joined_at=ctx.now)
        .returning(m.waitlist_entries))).mappings().one())
    stage(session,ctx,'waitlist_joined',row)
    return 201,view(row)


def stage(session,ctx,action,row,reason=None):
    core.stage_effect(session,ctx,action,row['id'],row['version'],
        dict(resource_id=str(row['id']),version=row['version'],state=row['state']),reason)


async def transition(session,ctx,row,state,reason=None,appointment_id=None):
    if row['state'] != 'waiting' or state not in ('withdrawn','skipped','promoted'):
        op.fail('invalid_transition')
    value = dict((await session.execute(update(m.waitlist_entries).where(m.waitlist_entries.c.id == row['id'])
        .values(state=state,skip_reason=reason,promoted_appointment_id=appointment_id,
                version=row['version']+1,updated_at=ctx.now).returning(m.waitlist_entries))).mappings().one())
    if state != 'promoted':
        stage(session,ctx,'waitlist_'+state,value)
    return value


async def withdraw(session,request,principal,entry_id,version,reason):
    preliminary = await op.row(session,m.waitlist_entries,entry_id)
    ctx = await core.lock_context(session,request,core.ActorScope.user(principal),
        core.LockPlan(waitlist_slot_ids=(preliminary['slot_id'],)))
    row = await op.row(session,m.waitlist_entries,entry_id)
    if row['slot_id'] != preliminary['slot_id']:
        raise op.Restart()
    slot = await op.row(session,m.slots,row['slot_id'])
    doctor = (await session.execute(select(m.doctor_schedule_snapshots).where(
        m.doctor_schedule_snapshots.c.doctor_id == slot['doctor_id']))).mappings().one()
    scope(principal,row,doctor['staff_user_id'],True)
    if row['version'] != version:
        op.fail('version_conflict',412)
    if row['state'] == 'withdrawn':
        return 200,view(row)
    value = await transition(session,ctx,row,'withdrawn')
    # Reason is hashed only, never stored in waitlist/outbox content.
    from dataclasses import replace
    import hashlib
    session.info['appointment_effects'][-1] = replace(session.info['appointment_effects'][-1],
        reason_digest=hashlib.sha256(reason.encode()).hexdigest())
    return 200,view(value)


async def pending(session,slot_id):
    return bool((await session.execute(text('SELECT pending FROM promotion_jobs WHERE slot_id=:slot'),
        {'slot':int(slot_id)})).scalar())


async def mark_pending(session,slot_id,now):
    await session.execute(text('''INSERT INTO promotion_jobs(slot_id,next_attempt_at,updated_at)
        VALUES (:slot,:now,:now) ON CONFLICT(slot_id) DO UPDATE SET pending=true,
        version=promotion_jobs.version+1, next_attempt_at=CASE WHEN promotion_jobs.pending
            THEN promotion_jobs.next_attempt_at ELSE EXCLUDED.next_attempt_at END,
        updated_at=EXCLUDED.updated_at'''),dict(slot=int(slot_id),now=now))


async def guard_target(session,slot_id):
    """Call only after doctor/slot lock; G2 book/move/availability wiring."""
    if await candidates(session,slot_id) or await pending(session,slot_id):
        op.fail('waitlist_pending')


@dataclass(frozen=True)
class Prepared:
    slot_id: int
    members: tuple[tuple[int,int], ...]
    batch: EligibilityBatch | None
    patient_ids: tuple[int, ...]


async def prepare(factory,slot_id,fetch):
    """No session/transaction survives the owner HTTP call."""
    async with factory() as session:
        rows = await candidates(session,slot_id)
    batch = None
    if rows:
        try:
            batch = EligibilityBatch.model_validate(await fetch(list(dict.fromkeys(str(r['patient_id']) for r in rows))))
            if {i.patient_id for i in batch.items} != {str(r['patient_id']) for r in rows}:
                batch = None
        except (TimeoutError, ValueError):
            pass
        except Exception as exc:
            from fastapi import HTTPException
            if not isinstance(exc,HTTPException):
                raise
    return Prepared(int(slot_id),tuple((r['id'],r['version']) for r in rows),batch,
        tuple(sorted({r['patient_id'] for r in rows})))


def fresh(observed_at,now):
    return timedelta(0) <= now-observed_at <= timedelta(seconds=60)


async def merge_status(session,batch,now):
    if batch is None or not fresh(batch.observed_at,now):
        return
    # Snapshots are acquired in sorted patient order, after FIFO and before jobs.
    for item in sorted(batch.items,key=lambda i:int(i.patient_id)):
        stmt = pg_insert(m.patient_status_snapshots).values(patient_id=int(item.patient_id),active=item.active,
            source_version=item.version,observed_at=batch.observed_at)
        await session.execute(stmt.on_conflict_do_update(index_elements=['patient_id'],set_={
            'active':stmt.excluded.active,'source_version':stmt.excluded.source_version,
            'observed_at':stmt.excluded.observed_at,'version':m.patient_status_snapshots.c.version+1,
            'updated_at':now},where=(stmt.excluded.source_version > m.patient_status_snapshots.c.source_version) |
            ((stmt.excluded.source_version == m.patient_status_snapshots.c.source_version) &
             (stmt.excluded.active == m.patient_status_snapshots.c.active) &
             (stmt.excluded.observed_at > m.patient_status_snapshots.c.observed_at))))


async def promote(session,ctx,prepared,create_episode=None):
    core.require_context(session,ctx)
    if prepared.slot_id not in ctx.plan.waitlist_slot_ids:
        raise ValueError('Slot FIFO locks missing')
    rows = await candidates(session,prepared.slot_id)
    if tuple((r['id'],r['version']) for r in rows) != prepared.members:
        raise op.Restart()
    if not set(prepared.patient_ids)<=set(ctx.plan.waitlist_patient_ids) or prepared.slot_id not in ctx.plan.promotion_slot_ids:
        raise ValueError('Promotion status/job locks missing from context')
    slot = await op.row(session,m.slots,prepared.slot_id)
    occupied = (await session.execute(select(m.appointments.c.id).where(
        m.appointments.c.slot_id == slot['id'],m.appointments.c.state.in_(op.ACTIVE)))).first()
    if occupied:
        await session.execute(text('''UPDATE promotion_jobs SET pending=false,lease_token=NULL,
            lease_expires_at=NULL,version=version+1,updated_at=:now WHERE slot_id=:slot'''),
            dict(slot=slot['id'],now=ctx.now))
        return None
    await merge_status(session,prepared.batch,ctx.now)
    reason = 'slot_retired' if slot['state'] != 'bookable' else 'window_closed' if slot['starts_at'] <= ctx.now else None
    result = None
    for row in rows:
        if reason:
            await transition(session,ctx,row,'skipped',reason)
            continue
        status = (await session.execute(select(m.patient_status_snapshots).where(
            m.patient_status_snapshots.c.patient_id == row['patient_id']))).mappings().first()
        if not status or not fresh(status['observed_at'],ctx.now):
            break
        if not status['active']:
            await transition(session,ctx,row,'skipped','inactive_patient')
            continue
        if create_episode is None:
            break  # G2 journey/workflow dependency must never be fabricated.
        doctor = (await session.execute(select(m.doctor_schedule_snapshots).where(
            m.doctor_schedule_snapshots.c.doctor_id == slot['doctor_id']))).mappings().one()
        if doctor['accepted_revision'] != slot['schedule_revision']:
            break
        try:
            async with session.begin_nested():
                result = dict((await session.execute(insert(m.appointments).values(id=op.new_id(),
                    slot_id=slot['id'],patient_id=row['patient_id'],doctor_id=slot['doctor_id'],
                    doctor_user_id=doctor['staff_user_id'],schedule_revision=slot['schedule_revision'],
                    starts_at=slot['starts_at'],ends_at=slot['ends_at'],state='confirmed')
                    .returning(m.appointments))).mappings().one())
        except DBAPIError as exc:
            if getattr(getattr(exc.orig,'diag',None),'constraint_name',None) != 'appointments_patient_overlap':
                raise
            await transition(session,ctx,row,'skipped','patient_overlap')
            continue
        journey_id = await create_episode(session,ctx,result)
        # Verify real local identities and workflow before reporting promotion.
        journey = await op.row(session,m.journeys,journey_id)
        workflow = await core.read_workflow(session,result['id'])
        if not workflow or (journey['appointment_id'],journey['patient_id'],workflow['journey_id']) != (
                result['id'],result['patient_id'],int(journey_id)):
            raise RuntimeError('Episode creator did not stage matching journey/workflow')
        await transition(session,ctx,row,'promoted',appointment_id=result['id'])
        payload = {**op.booking_payload(result),'journey_id':str(journey_id),'waitlist_entry_id':str(row['id'])}
        core.stage_effect(session,ctx,'waitlist_promoted',result['id'],result['version'],payload)
        await op.bump_operational_versions(session,[slot['doctor_id']])
        break
    remaining = await candidates(session,slot['id'])
    if remaining and result is None:
        await mark_pending(session,slot['id'],ctx.now)
    else:
        await session.execute(text('''UPDATE promotion_jobs SET pending=false,lease_token=NULL,
            lease_expires_at=NULL,version=version+1,updated_at=:now WHERE slot_id=:slot'''),dict(slot=slot['id'],now=ctx.now))
    return result


async def on_slot_released(session,context,eligibility_snapshot):
    """G2 injects a reviewed episode creator; no network or commits here."""
    await promote(session,context,eligibility_snapshot,session.info.get('waitlist_episode_creator'))


async def book_with_waitlist_guard(session,request,principal,body,identity):
    """G2 replacement command participant; legacy public route is untouched."""
    ctx=await core.lock_context(session,request,core.ActorScope.user(principal),
        core.LockPlan(waitlist_slot_ids=(int(body.slot_id),)))
    await guard_target(session,body.slot_id)
    return await op.book(session,request,principal,body,identity,phase3_context=ctx)


async def change_with_promotion(session,request,principal,aid,body,prepared,identity=None,create_episode=None):
    """Atomic old-slot release + promotion; eligibility was fetched before entry.

    Enrolled booking changes remain fail-closed until G2 assembles all lifecycle
    participants. This adapter preserves v1 responses and legacy hold semantics.
    """
    preliminary=await op.row(session,m.appointments,aid)
    if prepared.slot_id != preliminary['slot_id']:
        raise op.Restart()
    slots={prepared.slot_id}
    if identity:
        slots.add(int(body.target_slot_id))
    ctx=await core.lock_context(session,request,core.ActorScope.user(principal),
        core.LockPlan(appointment_ids=(int(aid),),waitlist_slot_ids=tuple(sorted(slots)),
            waitlist_patient_ids=prepared.patient_ids,promotion_slot_ids=(prepared.slot_id,)))
    if identity:
        await guard_target(session,body.target_slot_id)
    result=await op.change(session,request,principal,aid,body,identity,phase3_context=ctx)
    if ctx.bookings[int(aid)]['state']=='confirmed' and (not identity or prepared.slot_id!=int(body.target_slot_id)):
        try:
            await promote(session,ctx,prepared,create_episode)
        except op.Restart:
            # Candidate discovery may change during the pre-lock HTTP request.
            # Persist the permitted release; a fresh worker pass rechecks FIFO.
            await mark_pending(session,prepared.slot_id,ctx.now)
    return result
