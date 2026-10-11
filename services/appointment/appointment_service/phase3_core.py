"""Service-local G0 interfaces. No feature business logic or automatic enrollment."""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from types import MappingProxyType
from typing import Literal, Mapping

from fastapi import HTTPException
from pydantic import model_validator
from sqlalchemy import select, insert, text

from . import models as m, operations as op
from .authorization import authenticated_user
from .dependencies import current, private_principal
from .database import get_database_session
from .wire import ID, Time, Version, Input

metadata = m.metadata


class CheckinWindow(Input):
    starts_at: Time
    ends_at: Time

    @model_validator(mode='after')
    def valid_interval(self):
        if self.ends_at <= self.starts_at:
            raise ValueError('Invalid check-in window')
        return self


class Workflow(Input):
    appointment_id: ID
    journey_id: ID
    patient_id: ID
    doctor_id: ID
    state: Literal['booked', 'checked_in', 'in_consultation', 'completed', 'cancelled', 'no_show']
    checkin_window: CheckinWindow
    queue_entry_id: ID | None
    version: Version


@dataclass(frozen=True)
class ActorScope:
    """Verified identity snapshot, deliberately excludes bearer credentials."""
    user_id: str | None
    patient_id: str | None
    roles: frozenset[str]
    auth_version: int | None
    service: str | None = None

    @classmethod
    def user(cls, principal):
        return cls(principal.user_id, principal.patient_id,
                   frozenset(principal.roles), principal.auth_version)


def worker_actor():
    """Local scheduler identity; never masquerades as a clinician/user."""
    return ActorScope(None, None, frozenset(), None, 'appointment')


@dataclass(frozen=True)
class LockPlan:
    """Complete discovered sets. Parents serialize absent child/counter inserts.

    Doctor/day includes counter and future snapshot row; G0 has no snapshot
    table. Future revisions extend this helper before queue activation.
    """
    doctor_ids: tuple[int, ...] = ()
    slot_ids: tuple[int, ...] = ()
    appointment_ids: tuple[int, ...] = ()
    checkin_link_ids: tuple[int, ...] = ()
    waitlist_slot_ids: tuple[int, ...] = ()
    queue_days: tuple[tuple[int, date], ...] = ()
    queue_entry_ids: tuple[int, ...] = ()
    journey_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class Context:
    request_id: str
    correlation_id: str
    traceparent: str | None
    actor: ActorScope
    now: datetime
    bookings: Mapping[int, Mapping] = field(repr=False)
    workflows: Mapping[int, Mapping] = field(repr=False)
    holds: Mapping[int, Mapping] = field(repr=False)
    plan: LockPlan


def frozen_rows(rows, key):
    return MappingProxyType({r[key]: MappingProxyType(dict(r)) for r in rows})


async def _lock(session, table, column, ids, *ordering):
    if not ids:
        return []
    stmt = select(table).where(column.in_(sorted(set(ids)))).order_by(*(ordering or (column,))).with_for_update()
    return (await session.execute(stmt)).mappings().all()


async def lock_context(session, request, actor, plan: LockPlan):
    """Acquire all locks once in frozen order; discovery changes restart command.

    Call before any domain lock or audit. Actor must originate in verified auth
    and current authority before command replay, or the internal scheduler.
    No network here or in participants. Contexts are valid only in this session.
    """
    if not session.in_transaction() or session.info.get('phase3_lock_context') or session.info.get('effects_flushed'):
        raise RuntimeError('Lock context requires a fresh owner transaction')
    discovered = (await session.execute(select(m.appointments).where(
        m.appointments.c.id.in_(plan.appointment_ids)))).mappings().all() if plan.appointment_ids else []
    if len(discovered) != len(set(plan.appointment_ids)):
        op.fail('not_found', 404)
    slot_ids = set(plan.slot_ids) | set(plan.waitlist_slot_ids) | {a['slot_id'] for a in discovered}
    slots = (await session.execute(select(m.slots).where(m.slots.c.id.in_(slot_ids)))).mappings().all() if slot_ids else []
    if len(slots) != len(slot_ids):
        op.fail('not_found', 404)
    doctor_ids = set(plan.doctor_ids) | {s['doctor_id'] for s in slots} | {d for d, _ in plan.queue_days}
    doctors = await _lock(session, m.doctor_schedule_snapshots,
                          m.doctor_schedule_snapshots.c.doctor_id, doctor_ids)
    if len(doctors) != len(doctor_ids):
        op.fail('not_found', 404)
    locked_slots = await _lock(session, m.slots, m.slots.c.id, slot_ids)
    if [(s['id'], s['doctor_id']) for s in sorted(slots, key=lambda s:s['id'])] != [(s['id'], s['doctor_id']) for s in locked_slots]:
        raise op.Restart()
    bookings = await _lock(session, m.appointments, m.appointments.c.id, plan.appointment_ids)
    if [(a['id'],a['slot_id'],a['doctor_id']) for a in sorted(discovered,key=lambda a:a['id'])] != [(a['id'],a['slot_id'],a['doctor_id']) for a in bookings]:
        raise op.Restart()
    holds = await _lock(session, m.clinical_holds, m.clinical_holds.c.appointment_id, plan.appointment_ids)
    workflows = await _lock(session, m.appointment_workflows, m.appointment_workflows.c.appointment_id, plan.appointment_ids)
    # Include all children of locked bookings; callers include other feature
    # resources up front, never acquire them after this context is returned.
    link_ids = set(plan.checkin_link_ids)
    if plan.appointment_ids:
        link_ids.update((await session.execute(select(m.checkin_links.c.id).where(
            m.checkin_links.c.appointment_id.in_(plan.appointment_ids)))).scalars().all())
    links = await _lock(session, m.checkin_links, m.checkin_links.c.id, link_ids)
    if any(r['appointment_id'] not in plan.appointment_ids for r in links):
        raise ValueError('Link parent missing from lock plan')
    await _lock(session, m.waitlist_entries, m.waitlist_entries.c.slot_id, plan.waitlist_slot_ids,
                m.waitlist_entries.c.joined_at, m.waitlist_entries.c.id)
    for doctor_id, local_date in sorted(set(plan.queue_days)):
        await session.execute(select(m.queue_counters).where(
            m.queue_counters.c.doctor_id == doctor_id,
            m.queue_counters.c.local_date == local_date).with_for_update())
    queue_ids = set(plan.queue_entry_ids) | {w['queue_entry_id'] for w in workflows if w['queue_entry_id'] is not None}
    queues = await _lock(session, m.queue_entries, m.queue_entries.c.id, queue_ids)
    if any(q['doctor_id'] not in doctor_ids or (q['doctor_id'],q['local_date']) not in plan.queue_days for q in queues):
        raise ValueError('Queue doctor/day missing from lock plan')
    journey_ids = set(plan.journey_ids) | {w['journey_id'] for w in workflows}
    journeys = await _lock(session, m.journeys, m.journeys.c.id, journey_ids)
    if any(j['appointment_id'] not in plan.appointment_ids for j in journeys):
        raise ValueError('Journey parent missing from lock plan')
    await _lock(session, m.journey_stages, m.journey_stages.c.journey_id, journey_ids,
                m.journey_stages.c.journey_id, m.journey_stages.c.stage)
    complete_plan = LockPlan(tuple(sorted(doctor_ids)), tuple(sorted(slot_ids)),
        tuple(sorted(set(plan.appointment_ids))), tuple(sorted(link_ids)),
        tuple(sorted(set(plan.waitlist_slot_ids))), tuple(sorted(set(plan.queue_days))),
        tuple(sorted(queue_ids)), tuple(sorted(journey_ids)))
    ctx = Context(str(request.state.request_id), str(request.state.correlation_id),
                  getattr(request.state, 'traceparent', None), actor, op.now(),
                  frozen_rows(bookings,'id'), frozen_rows(workflows,'appointment_id'),
                  frozen_rows(holds,'appointment_id'), complete_plan)
    session.info['phase3_lock_context'] = ctx
    return ctx


def require_context(session, context):
    if not session.in_transaction() or session.info.get('phase3_lock_context') is not context or session.info.get('effects_flushed'):
        raise RuntimeError('Participant requires this transaction’s locked context')


async def read_workflow(session, appointment_id):
    """Read-only helper, never enrolls on GET. Resource scope is caller checked."""
    result = (await session.execute(select(m.appointment_workflows).where(
        m.appointment_workflows.c.appointment_id == int(appointment_id)))).mappings().first()
    return dict(result) if result else None


def workflow_view(row):
    return Workflow(appointment_id=str(row['appointment_id']), journey_id=str(row['journey_id']),
        patient_id=str(row['patient_id']), doctor_id=str(row['doctor_id']), state=row['state'],
        checkin_window=CheckinWindow(starts_at=row['window_starts_at'], ends_at=row['window_ends_at']),
        queue_entry_id=str(row['queue_entry_id']) if row['queue_entry_id'] is not None else None,
        version=row['version']).model_dump(mode='json')


def schedule_fingerprint(booking):
    return op.digest({k: str(booking[k]) if k in ('slot_id','doctor_id') else
                      op.wire_time(booking[k]) if k in ('starts_at','ends_at') else booking[k]
                      for k in ('slot_id','doctor_id','schedule_revision','starts_at','ends_at')})


async def enroll_workflow(session, context, appointment_id, journey_id):
    """Stage shared row only after Agent 4 stages a real journey.

    Not an endpoint or activation switch. No fake journey or automatic backfill.
    Caller stages journey effects, then core flushes audit/outbox/result together.
    """
    require_context(session, context)
    a = context.bookings[int(appointment_id)]
    if a['id'] in context.holds or a['state'] != 'confirmed' or a['starts_at'] <= context.now:
        op.fail('invalid_transition')
    if a['id'] in context.workflows:
        op.fail('conflict')
    journey = await op.row(session, m.journeys, journey_id)
    if (journey['appointment_id'],journey['patient_id']) != (a['id'],a['patient_id']):
        op.fail('invalid_reference',422)
    value = (await session.execute(insert(m.appointment_workflows).values(
        appointment_id=a['id'], journey_id=int(journey_id), patient_id=a['patient_id'],
        doctor_id=a['doctor_id'], slot_id=a['slot_id'], schedule_revision=a['schedule_revision'],
        schedule_fingerprint=schedule_fingerprint(a), state='booked',
        window_starts_at=a['starts_at']-timedelta(minutes=30),
        window_ends_at=a['starts_at']+timedelta(minutes=15)).returning(m.appointment_workflows))).mappings().one()
    return dict(value)


# Public shared adapters passed to register_routes(app, core).
from .api.router import factory as session_factory, response, query_keys, execute
command = op.command
precondition = op.precondition
can_access = op.can_access

FEATURE_EVENTS = MappingProxyType({
    'waitlist_joined': ('waitlist', 'appointment.waitlist.joined.v1'),
    'waitlist_withdrawn': ('waitlist', 'appointment.waitlist.withdrawn.v1'),
    'waitlist_skipped': ('waitlist', 'appointment.waitlist.skipped.v1'),
    'waitlist_promoted': ('appointment', 'appointment.waitlist.promoted.v1'),
    'workflow_checked_in': ('workflow', 'appointment.workflow.checked_in.v1'),
    'workflow_consultation_started': ('workflow', 'appointment.workflow.consultation_started.v1'),
    'workflow_completed': ('workflow', 'appointment.workflow.completed.v1'),
    'workflow_no_show': ('workflow', 'appointment.workflow.no_show.v1'),
    'workflow_cancelled': ('workflow', 'appointment.workflow.cancelled.v1'),
    'journey_created': ('journey', 'appointment.journey.created.v1'),
    'journey_updated': ('journey', 'appointment.journey.updated.v1'),
    'journey_discharged': ('journey', 'appointment.journey.discharged.v1'),
    'journey_reopened': ('journey', 'appointment.journey.reopened.v1'),
})


@dataclass(frozen=True)
class FeatureEffect:
    context: Context
    action: str
    resource_id: int
    version: int
    payload_json: str
    reason_digest: str | None


class ResourceEffect(Input):
    resource_id: ID
    version: Version
    state: Literal['waiting','promoted','withdrawn','skipped','booked','checked_in',
                   'in_consultation','completed','cancelled','no_show','active','ready',
                   'discharged','reopened']


class PromotionPayload(Input):
    appointment_id: ID
    journey_id: ID
    waitlist_entry_id: ID
    patient_id: ID
    doctor_id: ID
    slot_id: ID
    starts_at: Time
    ends_at: Time
    schedule_revision: Version


def stage_effect(session, context, action, resource_id, version, payload, reason=None):
    require_context(session, context)
    if action not in FEATURE_EVENTS:
        raise ValueError('Unknown feature event')
    if type(version) is not int or not 1 <= version <= 9007199254740991:
        raise ValueError('Invalid effect version')
    if not isinstance(resource_id, int) or isinstance(resource_id, bool) or not 0 < resource_id < 2**63:
        raise ValueError('Invalid effect resource ID')
    if action == 'waitlist_promoted':
        payload = PromotionPayload.model_validate(payload).model_dump(mode='json')
        if payload['appointment_id'] != str(resource_id):
            raise ValueError('Promotion identity mismatch')
    else:
        payload = ResourceEffect.model_validate(payload).model_dump()
        if payload['resource_id'] != str(resource_id) or payload['version'] != version:
            raise ValueError('Effect identity mismatch')
    import hashlib
    session.info.setdefault('appointment_effects', []).append(FeatureEffect(
        context, action, int(resource_id), version, op.canonical(payload),
        hashlib.sha256(reason.encode()).hexdigest() if reason else None))


async def append_feature_effect(session, effect):
    # Called exclusively by command after all participants. Never publish.
    import json
    ctx = effect.context
    aggregate, event_type = FEATURE_EVENTS[effect.action]
    audit = dict(action=effect.action, result='success', resource_id=str(effect.resource_id),
                 request_id=ctx.request_id, correlation_id=ctx.correlation_id,
                 occurred_at=op.wire_time(ctx.now))
    if ctx.actor.service:
        audit['actor_service'] = ctx.actor.service
    else:
        audit['actor_user_id'] = ctx.actor.user_id
    if effect.reason_digest:
        audit['reason_digest'] = effect.reason_digest
    await session.execute(text('SELECT public.appointment_append_phase3_audit(:id,CAST(:metadata AS jsonb))'),
                          dict(id=op.new_id(), metadata=op.canonical(audit)))
    event_id = op.new_id()
    envelope = dict(event_id=str(event_id), event_type=event_type, schema_version=1,
        producer='appointment', occurred_at=op.wire_time(ctx.now), aggregate_type=aggregate,
        aggregate_id=str(effect.resource_id), aggregate_version=effect.version,
        correlation_id=ctx.correlation_id, request_id=ctx.request_id, causation_id=None,
        traceparent=ctx.traceparent, payload=json.loads(effect.payload_json))
    await session.execute(insert(m.outbox_events).values(event_id=event_id,
        aggregate_type=aggregate, aggregate_id=effect.resource_id, aggregate_version=effect.version,
        event_type=event_type, envelope=envelope))


async def invoke_participant(app, feature, export, session, context, *args):
    """Fixed reviewed hooks only; absence fails closed, never reports success."""
    from .extensions import PARTICIPANTS
    require_context(session, context)
    if export not in PARTICIPANTS.get(feature, ()):
        raise ValueError('Unknown participant')
    module = app.state.appointment_extensions.get(feature)
    if module is None:
        raise HTTPException(503, detail='dependency_unavailable')
    return await getattr(module, export)(session, context, *args)


async def authorize(request, principal, roles, appointment_id=None, *, write=False):
    """Current authority and optional local scope, before replay/owner fetches."""
    role = await current(request, principal, roles)
    if appointment_id is not None:
        async with session_factory(request)() as session:
            booking = await op.row(session, m.appointments, appointment_id)
        can_access(principal, booking, write)
    return role
