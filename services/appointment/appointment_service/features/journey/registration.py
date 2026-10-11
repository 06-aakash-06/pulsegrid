"""G1 journey hooks and registration; activated only by reviewed G2 assembly."""
from sqlalchemy import insert, select, update

from ... import models as m, operations as op
from .projection import STAGES


def register_tables(metadata):
    for name in ('journeys', 'journey_stages'):
        if metadata.tables[name] is not getattr(m, name):
            raise RuntimeError('Journey metadata identity changed')


def schema_spec():
    return {
        'tables': [
            {'name': 'journeys', 'reuse': True, 'columns': {'id': 'bigint PK', 'appointment_id': 'bigint NOT NULL local FK', 'patient_id': 'bigint NOT NULL', 'state': 'varchar(64) NOT NULL', 'version': 'bigint NOT NULL'}},
            {'name': 'journey_stages', 'reuse': True, 'columns': {'journey_id': 'bigint NOT NULL local FK', 'stage': 'varchar(64) NOT NULL', 'state': 'varchar(64) NOT NULL', 'source_resources': 'jsonb NOT NULL', 'observed_at': 'timestamptz NULL'}},
            {'name': 'journey_snapshots', 'columns': {'journey_id': 'bigint PK local FK', 'records_revision': 'bigint NULL', 'pharmacy_revision': 'bigint NULL', 'billing_revision': 'bigint NULL', 'expected_source_keys': 'jsonb NOT NULL', 'review_required': 'boolean NOT NULL', 'last_reconciled_at': 'timestamptz NULL', 'lease_until': 'timestamptz NULL', 'next_attempt_at': 'timestamptz NULL', 'attempts': 'integer NOT NULL'}},
            {'name': 'journey_transitions', 'columns': {'id': 'bigint PK', 'journey_id': 'bigint NOT NULL local FK', 'stage': 'varchar(64) NULL', 'from_state': 'varchar(64) NULL', 'to_state': 'varchar(64) NOT NULL', 'occurred_at': 'timestamptz NOT NULL', 'effect_key': 'varchar(256) NOT NULL UNIQUE'}},
        ],
        'indexes': [{'name': 'ix_journey_snapshots_next_attempt_at', 'table': 'journey_snapshots', 'columns': ['next_attempt_at']}],
        'constraints': ['UNIQUE journeys(appointment_id)', 'UNIQUE journey_stages(journey_id,stage)', 'CHECK journey_transitions.to_state IN (pending,complete,skipped,reopened,failed)'],
        'preflight': ['Reject unexpected existing journey rows before 0008_phase3_journey', 'Do not backfill historical appointments'],
        'runtime_grants': ['SELECT, INSERT, UPDATE on journey_snapshots and journey_transitions for appointment runtime; no DELETE'],
    }


def register_routes(app, core):
    from .routes import router
    app.include_router(router)


async def on_booking_created(session, context):
    """Create a real episode for one locked, confirmed booking; caller enrolls workflow."""
    from ... import phase3_core as core
    core.require_context(session, context)
    if len(context.bookings) != 1:
        raise ValueError('Journey creation needs one booking')
    booking = next(iter(context.bookings.values()))
    if booking['state'] != 'confirmed' or booking['id'] in context.workflows:
        op.fail('invalid_transition')
    existing = (await session.execute(select(m.journeys.c.id).where(m.journeys.c.appointment_id == booking['id']))).scalar_one_or_none()
    if existing is not None:
        return
    journey_id = op.new_id()
    await session.execute(insert(m.journeys).values(id=journey_id, appointment_id=booking['id'], patient_id=booking['patient_id'], state='active'))
    for name in STAGES:
        await session.execute(insert(m.journey_stages).values(journey_id=journey_id, stage=name,
                          state='complete' if name == 'appointment' else 'pending', source_resources=[]))
    core.stage_effect(session, context, 'journey_created', journey_id, 1,
                      {'resource_id': str(journey_id), 'version': 1, 'state': 'active'})


async def on_booking_changed(session, context):
    """Apply local cancellation or reschedule without remote reads or new locks."""
    from ... import phase3_core as core
    core.require_context(session, context)
    for booking in context.bookings.values():
        workflow = context.workflows.get(booking['id'])
        if workflow is None:
            continue
        journey = (await session.execute(select(m.journeys).where(m.journeys.c.id == workflow['journey_id']))).mappings().one()
        target = 'cancelled' if booking['state'] == 'cancelled' else 'no_show' if workflow['state'] == 'no_show' else journey['state']
        if journey['state'] in ('cancelled', 'no_show') and target != journey['state']:
            op.fail('invalid_transition')
        if target != journey['state']:
            version = journey['version'] + 1
            await session.execute(update(m.journeys).where(m.journeys.c.id == journey['id']).values(state=target, version=version, updated_at=context.now))
            core.stage_effect(session, context, 'journey_updated', journey['id'], version,
                              {'resource_id': str(journey['id']), 'version': version, 'state': target})
