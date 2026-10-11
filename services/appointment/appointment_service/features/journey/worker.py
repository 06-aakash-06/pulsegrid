"""Durable fenced one-shot reconciliation worker; all owner calls outside locks."""
import secrets
from datetime import timedelta
from sqlalchemy import select,update
from ... import models as m,operations as op,phase3_core as core
from ..queue.service import _complete_plan
from . import service


async def run_once(factory,request):
    token=secrets.token_hex(24);now=op.now()
    async with factory() as session,session.begin():
        row=(await session.execute(select(m.journey_snapshots).join(m.journeys,
            m.journeys.c.id==m.journey_snapshots.c.journey_id).where(
            m.journeys.c.state.in_(('active','ready','reopened','discharged')),
            m.journey_snapshots.c.next_attempt_at<=now,
            (m.journey_snapshots.c.lease_until.is_(None))|(m.journey_snapshots.c.lease_until<=now))
            .order_by(m.journey_snapshots.c.next_attempt_at,m.journey_snapshots.c.journey_id)
            .limit(1).with_for_update(of=m.journey_snapshots,skip_locked=True))).mappings().first()
        if row is None:return False
        jid=row['journey_id']
        await session.execute(update(m.journey_snapshots).where(m.journey_snapshots.c.journey_id==jid)
            .values(lease_token=token,lease_until=now+timedelta(seconds=30)))
        journey=await op.row(session,m.journeys,jid)
    sources,failures=await service.fetch(request,journey)
    async def work(session):
        booking=await op.row(session,m.appointments,journey['appointment_id'])
        plan=await _complete_plan(session,booking['doctor_id'],booking['starts_at'].date(),(booking['id'],))
        ctx=await core.lock_context(session,request,core.worker_actor(),plan)
        progress=(await session.execute(select(m.journey_snapshots).where(m.journey_snapshots.c.journey_id==jid))).mappings().one()
        if progress['lease_token']!=token or progress['lease_until']<=ctx.now:return 200,{'lost_lease':True}
        result=await service.apply(session,ctx,jid,sources,failures)
        await session.execute(update(m.journey_snapshots).where(m.journey_snapshots.c.journey_id==jid)
            .values(lease_token=None,lease_until=None))
        return 200,result
    ident=dict(principal_scope='service:appointment:journey',method='POST',route_template=f'/worker/journey/{jid}',key=token)
    await core.command(factory,ident,op.digest({'journey_id':str(jid)}),work)
    return True
