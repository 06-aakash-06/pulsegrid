"""Journey reads use only Appointment-owned persisted metadata."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from ... import models as m, operations as op
from ...authorization import authenticated_user
from ...dependencies import current
from ...api.router import factory, response, query_keys
from .projection import STAGES

router = APIRouter()
PREFIX = '/api/v1/appointments/journeys'


async def _authorized(request, principal, journey_id):
    await current(request, principal, ('patient', 'receptionist', 'doctor'))
    async with factory(request)() as session:
        journey = await op.row(session, m.journeys, journey_id)
        booking = await op.row(session, m.appointments, journey['appointment_id'])
        op.can_access(principal, booking)
        stages = (await session.execute(select(m.journey_stages).where(
            m.journey_stages.c.journey_id == journey['id']))).mappings().all()
    return journey, stages


def _view(journey, rows):
    by_name = {row['stage']: row for row in rows}
    if set(by_name) != set(STAGES):
        op.fail('dependency_unavailable', 503)
    stages = []
    for name in STAGES:
        row = by_name[name]
        stages.append(dict(name=name, state=row['state'], sources=row['source_resources'],
                           observed_at=op.wire_time(row['observed_at']) if row['observed_at'] else None,
                           pending_reason='awaiting_source' if row['state'] == 'pending' else None))
    if journey['state'] in ('ready', 'discharged', 'reopened'):
        # G2 must supply persisted source freshness/review metadata before these
        # states can be presented as financially or clinically reconciled.
        op.fail('dependency_unavailable', 503)
    return dict(id=str(journey['id']), appointment_id=str(journey['appointment_id']),
                patient_id=str(journey['patient_id']), state=journey['state'], stages=stages,
                discharge_eligible=False, review_required=False, last_reconciled_at=None,
                version=journey['version'])


@router.get(PREFIX + '/{journey_id}')
async def get_journey(journey_id: str, request: Request, principal=Depends(authenticated_user)):
    query_keys(request, ())
    if not journey_id.isdecimal() or not 0 < int(journey_id) < 2**63:
        op.fail('validation_error', 422)
    journey, stages = await _authorized(request, principal, journey_id)
    return response(200, _view(journey, stages))
