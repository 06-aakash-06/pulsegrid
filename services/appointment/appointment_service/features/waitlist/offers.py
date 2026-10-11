"""Durable bounded capacity offers; callers hold G0 parent/FIFO/job locks.

No owner HTTP calls, timers, commits or broker delivery occur in participants.
"""
from datetime import timedelta
from sqlalchemy import select, insert, update, text
from ... import models as m, operations as op, phase3_core as core
from . import operations as w

OFFER_LIFETIME = timedelta(minutes=5)


def view(row):
    return {**{k: str(row[k]) for k in ('id', 'entry_id', 'slot_id', 'patient_id')},
            'state': row['state'], 'expires_at': op.wire_time(row['expires_at']),
            'appointment_id': str(row['appointment_id']) if row['appointment_id'] else None,
            'version': row['version']}


def effect(session, ctx, row):
    core.stage_effect(session, ctx, 'offer_' + row['state'], row['id'], row['version'],
                      dict(resource_id=str(row['id']), version=row['version'], state=row['state']))


async def pending(session, sid):
    row = (await session.execute(select(m.waitlist_offers).where(
        m.waitlist_offers.c.slot_id == sid, m.waitlist_offers.c.state == 'pending'))).mappings().first()
    return dict(row) if row else None


async def end(session, ctx, offer, state, appointment_id=None):
    if offer['state'] != 'pending' or state not in ('accepted', 'declined', 'expired', 'revoked'):
        op.fail('invalid_transition')
    row = dict((await session.execute(update(m.waitlist_offers).where(
        m.waitlist_offers.c.id == offer['id']).values(state=state, appointment_id=appointment_id,
        version=offer['version'] + 1, updated_at=ctx.now).returning(m.waitlist_offers))).mappings().one())
    effect(session, ctx, row)
    return row


async def promote(session, ctx, prepared, create_episode=None):
    """Offer the FIFO eligible patient; expire durably before choosing a successor."""
    core.require_context(session, ctx)
    sid = prepared.slot_id
    if sid not in ctx.plan.waitlist_slot_ids or sid not in ctx.plan.promotion_slot_ids:
        raise ValueError('Offer requires FIFO and job locks')
    offer = await pending(session, sid)
    if offer:
        if offer['expires_at'] > ctx.now:
            return None
        await end(session, ctx, offer, 'expired')
        entry = await op.row(session, m.waitlist_entries, offer['entry_id'])
        if entry['state'] == 'waiting':
            await w.transition(session, ctx, entry, 'skipped', 'offer_expired')
        # Discovery before expiry contained the expiring entry. Remove that exact
        # row; concurrent membership changes still roll back and rediscover.
        from dataclasses import replace
        prepared = replace(prepared, members=tuple(x for x in prepared.members if x[0] != entry['id']))
    rows = await w.candidates(session, sid)
    if tuple((r['id'], r['version']) for r in rows) != prepared.members:
        raise op.Restart()
    if not set(prepared.patient_ids) <= set(ctx.plan.waitlist_patient_ids):
        raise ValueError('Eligibility locks missing')
    slot = await op.row(session, m.slots, sid)
    occupied = (await session.execute(select(m.appointments.c.id).where(
        m.appointments.c.slot_id == sid, m.appointments.c.state.in_(op.ACTIVE)))).first()
    if occupied:
        await finish_job(session, sid, ctx.now)
        return None
    await w.merge_status(session, prepared.batch, ctx.now)
    reason = ('slot_retired' if slot['state'] != 'bookable' else
              'window_closed' if slot['starts_at'] <= ctx.now else None)
    for entry in rows:
        if reason:
            await w.transition(session, ctx, entry, 'skipped', reason)
            continue
        status = (await session.execute(select(m.patient_status_snapshots).where(
            m.patient_status_snapshots.c.patient_id == entry['patient_id']))).mappings().first()
        if not status or not w.fresh(status['observed_at'], ctx.now):
            break  # Unknown first patient blocks FIFO, never bypassed on outage.
        if not status['active']:
            await w.transition(session, ctx, entry, 'skipped', 'inactive_patient')
            continue
        overlap = (await session.execute(select(m.appointments.c.id).where(
            m.appointments.c.patient_id == entry['patient_id'], m.appointments.c.state.in_(op.ACTIVE),
            m.appointments.c.starts_at < slot['ends_at'], m.appointments.c.ends_at > slot['starts_at']))).first()
        if overlap:
            await w.transition(session, ctx, entry, 'skipped', 'patient_overlap')
            continue
        doctor = (await session.execute(select(m.doctor_schedule_snapshots).where(
            m.doctor_schedule_snapshots.c.doctor_id == slot['doctor_id']))).mappings().one()
        if doctor['accepted_revision'] != slot['schedule_revision']:
            break
        offer = dict((await session.execute(insert(m.waitlist_offers).values(id=op.new_id(),
            entry_id=entry['id'], slot_id=sid, patient_id=entry['patient_id'], state='pending',
            expires_at=min(ctx.now + OFFER_LIFETIME, slot['starts_at']))
            .returning(m.waitlist_offers))).mappings().one())
        effect(session, ctx, offer)
        await w.mark_pending(session, sid, ctx.now)
        return offer
    if await w.candidates(session, sid):
        await w.mark_pending(session, sid, ctx.now)
    else:
        await finish_job(session, sid, ctx.now)
    return None


async def finish_job(session, sid, now):
    await session.execute(text('UPDATE promotion_jobs SET pending=false, lease_token=NULL, '
        'lease_expires_at=NULL,version=version+1,updated_at=:now WHERE slot_id=:sid'), {'sid': sid, 'now': now})


async def decide(session, request, principal, offer_id, expected, accept, identity, create_episode):
    preliminary = await op.row(session, m.waitlist_offers, offer_id)
    w.scope(principal, preliminary, None, True)
    ctx = await core.lock_context(session, request, core.ActorScope.user(principal),
        core.LockPlan(waitlist_slot_ids=(preliminary['slot_id'],), promotion_slot_ids=(preliminary['slot_id'],)))
    offer = await op.row(session, m.waitlist_offers, offer_id)
    w.scope(principal, offer, None, True)
    if offer['version'] != expected:
        op.fail('version_conflict', 412)
    if offer['state'] != 'pending' or offer['expires_at'] <= ctx.now:
        op.fail('offer_unavailable')
    entry = await op.row(session, m.waitlist_entries, offer['entry_id'])
    if entry['state'] != 'waiting':
        op.fail('offer_unavailable')
    if not accept:
        result = await end(session, ctx, offer, 'declined')
        await w.transition(session, ctx, entry, 'withdrawn')
        await w.mark_pending(session, offer['slot_id'], ctx.now)
        return 200, view(result)
    slot = await op.row(session, m.slots, offer['slot_id'])
    snap = await op.valid_slot(session, slot, slot['schedule_revision'], identity)
    if create_episode is None:
        op.fail('dependency_unavailable', 503)
    aid = op.new_id()
    # Deferred local FK permits releasing the reservation first; any subsequent
    # insert/overlap/episode failure rolls the entire transaction back to pending.
    result = await end(session, ctx, offer, 'accepted', aid)
    booking = dict((await session.execute(insert(m.appointments).values(id=aid,
        patient_id=offer['patient_id'], slot_id=slot['id'], doctor_id=slot['doctor_id'],
        doctor_user_id=snap['staff_user_id'], starts_at=slot['starts_at'], ends_at=slot['ends_at'],
        schedule_revision=slot['schedule_revision'], state='confirmed').returning(m.appointments))).mappings().one())
    jid = await create_episode(session, ctx, booking)
    await w.transition(session, ctx, entry, 'promoted', appointment_id=aid)
    core.stage_effect(session, ctx, 'waitlist_promoted', aid, booking['version'],
        {**op.booking_payload(booking), 'journey_id': str(jid), 'waitlist_entry_id': str(entry['id'])})
    await op.bump_operational_versions(session, [slot['doctor_id']])
    await finish_job(session, slot['id'], ctx.now)
    appointment = op.appointment(booking); appointment['journey_id'] = str(jid)
    return 200, {'offer': view(result), 'appointment': appointment, 'version': result['version']}
