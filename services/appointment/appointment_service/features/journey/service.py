"""Local durable projection writes, coordinated under the shared lock context."""
from sqlalchemy import select, update
from ... import models as m, operations as op, phase3_core as core


async def local_stages(session, context, aid):
    core.require_context(session, context)
    workflow = await core.read_workflow(session, aid)
    if workflow is None:
        return
    values = {'check_in': 'complete'} if workflow['state'] in ('checked_in', 'in_consultation', 'completed') else {}
    if workflow['state'] == 'completed':
        values['consultation'] = 'complete'
    for stage, state in values.items():
        await session.execute(update(m.journey_stages).where(
            m.journey_stages.c.journey_id == workflow['journey_id'], m.journey_stages.c.stage == stage,
            m.journey_stages.c.state != state).values(state=state, observed_at=context.now,
            version=m.journey_stages.c.version+1, updated_at=context.now))
