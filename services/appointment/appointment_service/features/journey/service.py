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


async def fetch(request, journey):
    """No database connection survives any source HTTP request."""
    from .snapshots import SnapshotUnavailable
    client = request.app.state.snapshot_client
    aid, pid = journey['appointment_id'], journey['patient_id']
    sources = {}; failures = {}
    try:
        sources['records'] = await client.episode(request, 'records', aid, pid)
    except (SnapshotUnavailable, ValueError, KeyError, TypeError):
        failures['records'] = 'owner_unavailable'
    consultation = sources.get('records', {}).get('consultation')
    prescription = consultation.get('prescription') if consultation else None
    if prescription:
        try:
            sources['pharmacy'] = await client.episode(request, 'pharmacy', aid, pid, prescription['id'])
        except (SnapshotUnavailable, ValueError, KeyError, TypeError):
            failures['pharmacy'] = 'owner_unavailable'
    try:
        sources['billing'] = await client.episode(request, 'billing', aid, pid)
    except (SnapshotUnavailable, ValueError, KeyError, TypeError):
        failures['billing'] = 'owner_unavailable'
    return sources, failures


async def apply(session, context, journey_id, sources, failures, expected=None, discharge=False, reason=None):
    """Versioned local projection. Source absence remains pending, never complete."""
    from datetime import timedelta
    from .projection import project
    from .snapshots import validate, SnapshotUnavailable
    from ..queue import service as queue
    journey = await op.row(session, m.journeys, journey_id)
    aid = journey['appointment_id']
    core.require_context(session, context)
    if aid not in context.bookings or int(journey_id) not in context.plan.journey_ids:
        raise op.Restart()
    if expected is not None and journey['version'] != expected:
        op.fail('version_conflict',412)
    snapshot = (await session.execute(select(m.journey_snapshots).where(
        m.journey_snapshots.c.journey_id == journey['id']))).mappings().one()
    sources = dict(sources); failures = dict(failures)
    for owner, data in list(sources.items()):
        try:
            validate(data,owner,aid,journey['patient_id'])
        except (ValueError,KeyError,TypeError,SnapshotUnavailable):
            failures[owner]='source_invalid';sources.pop(owner);continue
        revision = snapshot[owner+'_revision']
        if revision is not None and data['revision'] < revision:
            failures[owner]='source_changed';sources.pop(owner)
    booking = context.bookings[aid]
    workflow = await core.read_workflow(session, aid)
    records = sources.get('records'); hold = context.holds.get(aid)
    clinical = records.get('consultation') if records else None
    if (workflow['state']=='in_consultation' and clinical and clinical['status']=='finalized' and
            hold and hold['state']=='finalized'):
        await queue.complete_from_records(session,context,records)
        workflow=await core.read_workflow(session,aid)
    result = project(booking,workflow,hold,records,sources.get('pharmacy'),sources.get('billing'))
    old_records = snapshot['sources'].get('records',{}).get('consultation')
    amendment = bool(old_records and clinical and old_records['record_revision'] > 0 and
                     clinical['record_revision'] > old_records['record_revision'])
    review = snapshot['review_required'] or result['review_required'] or amendment
    # Unknown/invalid owner stages cannot authorize discharge. Retain known data
    # for diagnosis, but the projected decision uses only this fresh source batch.
    eligible = result['discharge_eligible'] and not review and not failures and workflow['state']=='completed'
    new_vector = {owner: data['revision'] for owner,data in sources.items()}
    old_vector = {owner:snapshot[owner+'_revision'] for owner in ('records','pharmacy','billing') if snapshot[owner+'_revision'] is not None}
    changed = any(old_vector.get(owner) != version for owner,version in new_vector.items())
    if discharge:
        if (not eligible or journey['state']!='ready' or changed or
            any(not 0 <= (context.now-__import__('datetime').datetime.fromisoformat(data['observed_at'].replace('Z','+00:00'))).total_seconds() <= 5 for data in sources.values())):
            op.fail('source_changed' if changed else 'journey_not_ready')
        target='discharged'
    elif workflow['state'] in ('cancelled','no_show'):
        target=workflow['state']
    elif journey['state']=='discharged':
        target='reopened' if changed or not eligible else 'discharged'
    else:
        target='ready' if eligible else 'reopened' if journey['state']=='reopened' else 'active'
    for stage in result['stages']:
        row = (await session.execute(select(m.journey_stages).where(
            m.journey_stages.c.journey_id==journey['id'],m.journey_stages.c.stage==stage['name']))).mappings().one()
        if row['state'] != stage['state'] or row['source_resources'] != stage['sources']:
            await session.execute(update(m.journey_stages).where(m.journey_stages.c.journey_id==journey['id'],
                m.journey_stages.c.stage==stage['name']).values(state=stage['state'],source_resources=stage['sources'],
                observed_at=context.now if stage['state'] in ('complete','skipped') else None,
                version=row['version']+1,updated_at=context.now))
    retained={**snapshot['sources'],**sources}
    values=dict(sources=retained,pending_reasons={s['name']:s['pending_reason'] for s in result['stages'] if s['pending_reason']},
        expected_source_keys=[{'source_service':o,'source_item_id':i} for o,i in result['expected_sources']],
        review_required=review,last_reconciled_at=context.now,last_error='owner_unavailable' if failures else None,
        attempts=snapshot['attempts']+1 if failures else 0,
        next_attempt_at=context.now+timedelta(seconds=min(60,2**min(snapshot['attempts'],6)) if failures else 10))
    for owner,data in sources.items(): values[owner+'_revision']=data['revision']
    await session.execute(update(m.journey_snapshots).where(m.journey_snapshots.c.journey_id==journey['id']).values(**values))
    version=journey['version']+1
    await session.execute(update(m.journeys).where(m.journeys.c.id==journey['id']).values(state=target,version=version,updated_at=context.now))
    action='journey_discharged' if discharge else 'journey_reopened' if target=='reopened' and journey['state']=='discharged' else 'journey_updated'
    core.stage_effect(session,context,action,journey['id'],version,dict(resource_id=str(journey['id']),version=version,state=target),reason)
    return await view(session,journey['id'])


async def view(session, jid):
    from .projection import STAGES
    journey=await op.row(session,m.journeys,jid)
    snapshot=(await session.execute(select(m.journey_snapshots).where(m.journey_snapshots.c.journey_id==int(jid)))).mappings().first()
    rows=(await session.execute(select(m.journey_stages).where(m.journey_stages.c.journey_id==int(jid)))).mappings().all()
    by_name={r['stage']:r for r in rows}
    if set(by_name)!=set(STAGES): op.fail('dependency_unavailable',503)
    stages=[dict(name=name,state=by_name[name]['state'],sources=by_name[name]['source_resources'],
        observed_at=op.wire_time(by_name[name]['observed_at']) if by_name[name]['observed_at'] else None,
        pending_reason=(snapshot['pending_reasons'].get(name,'awaiting_source') if snapshot else 'awaiting_source')
            if by_name[name]['state']=='pending' else None) for name in STAGES]
    fresh=bool(snapshot and snapshot['last_reconciled_at'] and 0 <= (op.now()-snapshot['last_reconciled_at']).total_seconds()<=5)
    return dict(id=str(journey['id']),appointment_id=str(journey['appointment_id']),patient_id=str(journey['patient_id']),
        state=journey['state'],stages=stages,discharge_eligible=bool(journey['state']=='ready' and fresh and
            snapshot and not snapshot['review_required'] and not snapshot['last_error']),
        review_required=bool(snapshot and snapshot['review_required']),
        last_reconciled_at=op.wire_time(snapshot['last_reconciled_at']) if snapshot and snapshot['last_reconciled_at'] else None,
        reconciliation=dict(state='failed' if snapshot and snapshot['last_error'] else 'pending' if any(s['state']=='pending' for s in stages) else 'complete',
            last_error=snapshot['last_error'] if snapshot else None,attempts=snapshot['attempts'] if snapshot else 0,
            next_attempt_at=op.wire_time(snapshot['next_attempt_at']) if snapshot else None),
        version=journey['version'])
