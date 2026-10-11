"""Bounded one-shot worker adapter; no G1 process startup or owner fixtures."""
import secrets
from datetime import timedelta
from sqlalchemy import select, text
from ... import operations as op, phase3_core as core, models as m
from .operations import candidates, prepare, promote, mark_pending


async def repair(factory,limit=50):
    """Every five seconds in G3: repair lost release wakeups in parent lock order."""
    if not 1 <= limit <= 50:
        raise ValueError('Bounded scan required')
    async with factory() as session:
        occupied = select(m.appointments.c.id).where(m.appointments.c.slot_id == m.slots.c.id,
            m.appointments.c.state.in_(op.ACTIVE)).exists()
        waiting = select(m.waitlist_entries.c.id).where(m.waitlist_entries.c.slot_id == m.slots.c.id,
            m.waitlist_entries.c.state == 'waiting').exists()
        ids = list((await session.execute(select(m.slots.c.id).where(~occupied,waiting)
            .order_by(m.slots.c.id).limit(limit))).scalars())
    for sid in ids:
        async with factory() as session,session.begin():
            await op.lock_resources(session,[sid])
            if await candidates(session,sid):
                await mark_pending(session,sid,op.now())
    return len(ids)


async def claim(factory):
    now = op.now()
    token = secrets.token_hex(24)
    async with factory() as session,session.begin():
        row = (await session.execute(text('''SELECT slot_id,version FROM promotion_jobs
            WHERE pending AND next_attempt_at<=:now AND (lease_expires_at IS NULL OR lease_expires_at<=:now)
            ORDER BY next_attempt_at,slot_id LIMIT 1 FOR UPDATE SKIP LOCKED'''),dict(now=now))).mappings().first()
        if row is None:
            return None
        await session.execute(text('''UPDATE promotion_jobs SET lease_token=:token,
            lease_expires_at=:expires,version=version+1 WHERE slot_id=:slot'''),
            dict(token=token,expires=now+timedelta(seconds=30),slot=row['slot_id']))
    return row['slot_id'],token


async def run_once(factory,request,fetch,create_episode=None):
    claimed = await claim(factory)
    if claimed is None:
        return False
    sid,token = claimed
    prepared = await prepare(factory,sid,fetch)
    async with factory() as session:
        version = (await session.execute(text('SELECT version FROM promotion_jobs WHERE slot_id=:slot'),
            dict(slot=sid))).scalar_one()
    identity = dict(principal_scope='service:appointment:waitlist',method='POST',
        route_template=f'/worker/waitlist/{sid}',key=token)

    async def work(session):
        ctx = await core.lock_context(session,request,core.worker_actor(),core.LockPlan(waitlist_slot_ids=(sid,),
            waitlist_patient_ids=prepared.patient_ids,promotion_slot_ids=(sid,)))
        job = (await session.execute(text('SELECT * FROM promotion_jobs WHERE slot_id=:slot FOR UPDATE'),
            dict(slot=sid))).mappings().one()
        if job['lease_token'] != token or job['lease_expires_at'] <= ctx.now or not job['pending']:
            return 200,{'lost_lease':True}
        result = await promote(session,ctx,prepared,create_episode)
        job = (await session.execute(text('SELECT * FROM promotion_jobs WHERE slot_id=:slot'),dict(slot=sid))).mappings().one()
        if job['pending']:
            attempts = job['attempt_count']+1
            await session.execute(text('''UPDATE promotion_jobs SET attempt_count=:attempts,
                next_attempt_at=:next,lease_token=NULL,lease_expires_at=NULL,version=version+1
                WHERE slot_id=:slot'''),dict(attempts=attempts,next=ctx.now+timedelta(seconds=min(60,2**min(attempts-1,6))),slot=sid))
        return 200,{'appointment_id':str(result['id']) if result else None}

    await core.command(factory,identity,op.digest({'slot_id':str(sid),'job_version':version}),work)
    return True
