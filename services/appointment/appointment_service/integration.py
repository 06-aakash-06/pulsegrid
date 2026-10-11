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
