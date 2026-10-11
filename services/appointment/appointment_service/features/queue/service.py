"""Transactional queue operations. The HTTP transport is polling only."""
import base64
import binascii
import hashlib
import json
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, Table, CheckConstraint
from sqlalchemy import insert, select, text, update

from appointment_service import models as m, operations as op, phase3_core as core

MAX_SAFE = 9007199254740991
STATES = frozenset({'waiting', 'skipped', 'in_consultation', 'completed', 'cancelled', 'no_show'})


def register_tables(metadata):
    """Reuse G0 tables; expose only the new queue snapshot table to G2."""
    if metadata is not core.metadata or metadata.tables.get('queue_entries') is not m.queue_entries:
        raise ValueError('Queue requires Appointment owner metadata')
    if 'queue_snapshots' not in metadata.tables:
        Table('queue_snapshots', metadata,
              Column('doctor_id', BigInteger, ForeignKey('doctor_schedule_snapshots.doctor_id'), primary_key=True),
              Column('local_date', Date, primary_key=True),
              Column('version', BigInteger, nullable=False),
              Column('created_at', DateTime(timezone=True), nullable=False),
              Column('updated_at', DateTime(timezone=True), nullable=False),
              CheckConstraint('version BETWEEN 1 AND 9007199254740991', name='ck_queue_snapshots_safe_version'))
    return metadata.tables['queue_snapshots']


def _table():
    return register_tables(core.metadata)


def entry_view(row, *, patient_id=None):
    value = {key: str(row[key]) for key in ('id', 'appointment_id', 'doctor_id')}
    value.update(local_date=row['local_date'].isoformat(), token_number=row['token_number'],
                 state=row['state'], position=row['position'], version=row['version'])
    if patient_id is not None:
        value['patient_id'] = str(patient_id)
    return value


def _timezone(policy):
    name = policy.get('timezone') if isinstance(policy, dict) else None
    if not isinstance(name, str) or not name or len(name) > 128:
        op.fail('dependency_unavailable', 503)
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        op.fail('dependency_unavailable', 503)


async def _snapshot(session, doctor_id, local_date, *, lock=False):
    table = _table()
    stmt = select(table).where(table.c.doctor_id == doctor_id, table.c.local_date == local_date)
    if lock:
        stmt = stmt.with_for_update()
    row = (await session.execute(stmt)).mappings().first()
    return dict(row) if row else None


async def _read_doctor_guard(session, doctor_id):
    """Hold the parent stable across a multi-query polling snapshot."""
    row = (await session.execute(select(m.doctor_schedule_snapshots.c.doctor_id).where(
        m.doctor_schedule_snapshots.c.doctor_id == doctor_id).with_for_update(read=True))).scalar_one_or_none()
    if row is None:
        op.fail('not_found', 404)


async def _bump_snapshot(session, doctor_id, local_date, now):
    table = _table()
    row = await _snapshot(session, doctor_id, local_date, lock=True)
    if row is None:
        await session.execute(insert(table).values(doctor_id=doctor_id, local_date=local_date,
                                                   version=1, created_at=now, updated_at=now))
        return 1
    if row['version'] >= MAX_SAFE:
        op.fail('conflict')
    version = row['version'] + 1
    await session.execute(update(table).where(table.c.doctor_id == doctor_id,
        table.c.local_date == local_date).values(version=version, updated_at=now))
    return version


async def _waiting(session, doctor_id, local_date):
    return (await session.execute(text("""
        SELECT id, appointment_id, doctor_id, local_date, token_number, state, position, version
        FROM queue_entries WHERE doctor_id=:doctor_id AND local_date=:local_date AND state='waiting'
        ORDER BY token_number, id
    """), {'doctor_id': doctor_id, 'local_date': local_date})).mappings().all()


async def _reposition(session, context, doctor_id, local_date):
    """All affected waiting rows must already be in the canonical lock plan."""
    waiting = await _waiting(session, doctor_id, local_date)
    if any(row['id'] not in context.plan.queue_entry_ids for row in waiting):
        raise op.Restart()
    for rank, row in enumerate(waiting, 1):
        if row['position'] != rank:
            if row['version'] >= MAX_SAFE:
                op.fail('conflict')
            await session.execute(text("""
                UPDATE queue_entries SET position=:position, version=version+1, updated_at=:now
                WHERE id=:id AND state='waiting'
            """), {'position': rank, 'now': context.now, 'id': row['id']})


async def _entry(session, entry_id):
    row = (await session.execute(text("""
        SELECT id, appointment_id, doctor_id, local_date, token_number, state, position, version
        FROM queue_entries WHERE id=:id
    """), {'id': entry_id})).mappings().first()
    if row is None:
        op.fail('not_found', 404)
    return dict(row)


async def _complete_plan(session, doctor_id, local_date, appointment_id=()):
    """Discover before locking; doctor parent serializes membership recheck."""
    rows = (await session.execute(select(m.queue_entries.c.id, m.queue_entries.c.appointment_id,
        m.queue_entries.c.local_date).where(m.queue_entries.c.doctor_id == doctor_id))).all()
    ids = {int(value) for value in appointment_id}
    ids.update(row.appointment_id for row in rows)
    days = {(doctor_id, local_date)} | {(doctor_id, row.local_date) for row in rows}
    return core.LockPlan(doctor_ids=(doctor_id,), appointment_ids=tuple(sorted(ids)),
                         queue_days=tuple(sorted(days)),
                         queue_entry_ids=tuple(sorted(row.id for row in rows)))


async def allocate_on_checkin(session, context) -> dict:
    """Check-in participant; caller has already checked token/window/authority.

    G2 must supply a complete queue lock plan. A missing lock is a safe retry,
    never a late reverse-order lock acquisition.
    """
    core.require_context(session, context)
    if len(context.plan.appointment_ids) != 1:
        raise ValueError('Allocation requires one checked-in booking context')
    aid = context.plan.appointment_ids[0]
    booking = context.bookings[aid]
    workflow = await core.read_workflow(session, aid)
    if booking['state'] != 'confirmed' or workflow is None or workflow['state'] != 'booked' or workflow['queue_entry_id'] is not None:
        op.fail('invalid_transition')
    if not workflow['window_starts_at'] <= context.now < workflow['window_ends_at']:
        op.fail('checkin_window_closed')
    if aid in context.holds:
        op.fail('clinical_hold')
    doctor_id = workflow['doctor_id']
    if doctor_id != booking['doctor_id']:
        op.fail('invalid_reference', 422)
    snapshot = (await session.execute(select(m.doctor_schedule_snapshots).where(
        m.doctor_schedule_snapshots.c.doctor_id == doctor_id))).mappings().one()
    local_date = context.now.astimezone(_timezone(snapshot['policy_snapshot'])).date()
    if (doctor_id, local_date) not in context.plan.queue_days:
        raise op.Restart()
    existing = (await session.execute(select(m.queue_entries.c.id).where(
        m.queue_entries.c.appointment_id == aid))).scalar_one_or_none()
    if existing is not None:
        op.fail('invalid_transition')
    counter = (await session.execute(select(m.queue_counters).where(
        m.queue_counters.c.doctor_id == doctor_id,
        m.queue_counters.c.local_date == local_date))).mappings().first()
    token = counter['next_token'] if counter else 1
    if token > MAX_SAFE:
        op.fail('conflict')
    if counter:
        await session.execute(update(m.queue_counters).where(m.queue_counters.c.doctor_id == doctor_id,
            m.queue_counters.c.local_date == local_date).values(next_token=token+1))
    else:
        await session.execute(insert(m.queue_counters).values(doctor_id=doctor_id,
            local_date=local_date, next_token=2))
    waiting = await _waiting(session, doctor_id, local_date)
    if any(row['id'] not in context.plan.queue_entry_ids for row in waiting):
        raise op.Restart()
    new_id = op.new_id()
    await session.execute(text("""
        INSERT INTO queue_entries (id, appointment_id, doctor_id, local_date,
            token_number, state, position, version, created_at, updated_at)
        VALUES (:id, :aid, :doctor_id, :local_date, :token, 'waiting', :position,
            1, :now, :now)
    """), {'id': new_id, 'aid': aid, 'doctor_id': doctor_id, 'local_date': local_date,
            'token': token, 'position': len(waiting)+1, 'now': context.now})
    await session.execute(update(m.appointment_workflows).where(
        m.appointment_workflows.c.appointment_id == aid).values(
        state='checked_in', queue_entry_id=new_id,
        version=workflow['version']+1, updated_at=context.now))
    await _bump_snapshot(session, doctor_id, local_date, context.now)
    core.stage_effect(session, context, 'workflow_checked_in', aid, workflow['version']+1,
        {'resource_id': str(aid), 'version': workflow['version']+1, 'state': 'checked_in'})
    return entry_view(await _entry(session, new_id))


async def start_entry(session, context, entry_id, expected_version):
    core.require_context(session, context)
    entry = await _entry(session, entry_id)
    if entry['id'] not in context.plan.queue_entry_ids or entry['appointment_id'] not in context.bookings:
        raise op.Restart()
    if entry['version'] != expected_version:
        op.fail('version_conflict', 412)
    if entry['state'] != 'waiting':
        op.fail('invalid_transition')
    booking = context.bookings[entry['appointment_id']]
    workflow = await core.read_workflow(session, entry['appointment_id'])
    if booking['state'] != 'confirmed' or workflow is None or workflow['state'] != 'checked_in' or workflow['queue_entry_id'] != entry_id:
        op.fail('invalid_transition')
    if entry['appointment_id'] in context.holds:
        op.fail('clinical_hold')
    busy = (await session.execute(select(m.queue_entries.c.id).where(
        m.queue_entries.c.doctor_id == entry['doctor_id'],
        m.queue_entries.c.state == 'in_consultation'))).scalar_one_or_none()
    if busy is not None:
        op.fail('doctor_busy')
    waiting = await _waiting(session, entry['doctor_id'], entry['local_date'])
    if not waiting or waiting[0]['id'] != entry_id:
        op.fail('not_queue_head')
    await session.execute(text("""
        UPDATE queue_entries SET state='in_consultation', position=NULL,
            version=version+1, updated_at=:now WHERE id=:id
    """), {'now': context.now, 'id': entry_id})
    await session.execute(update(m.appointment_workflows).where(
        m.appointment_workflows.c.appointment_id == entry['appointment_id']).values(
        state='in_consultation', version=workflow['version']+1, updated_at=context.now))
    await _reposition(session, context, entry['doctor_id'], entry['local_date'])
    await _bump_snapshot(session, entry['doctor_id'], entry['local_date'], context.now)
    core.stage_effect(session, context, 'workflow_consultation_started', entry['appointment_id'],
        workflow['version']+1, {'resource_id': str(entry['appointment_id']),
                               'version': workflow['version']+1, 'state': 'in_consultation'})
    return entry_view(await _entry(session, entry_id))


def _records_dict(snapshot):
    if hasattr(snapshot, 'model_dump'):
        return snapshot.model_dump(mode='json')
    if not isinstance(snapshot, dict):
        op.fail('invalid_reference', 422)
    return snapshot


async def complete_from_records(session, context, records_snapshot) -> None:
    core.require_context(session, context)
    data = _records_dict(records_snapshot)
    aid = int(data['appointment_id'])
    if aid not in context.bookings or aid not in context.holds:
        op.fail('clinical_hold')
    booking = context.bookings[aid]
    hold = context.holds[aid]
    workflow = await core.read_workflow(session, aid)
    consultation = data.get('consultation')
    if (workflow is None or workflow['state'] not in ('in_consultation', 'completed') or
        str(data.get('patient_id')) != str(booking['patient_id']) or
        str(data.get('doctor_id')) != str(booking['doctor_id']) or
        not isinstance(consultation, dict) or consultation.get('status') != 'finalized' or
        hold['state'] != 'finalized' or str(hold['consultation_id']) != str(consultation.get('id'))):
        op.fail('invalid_reference', 422)
    entry = await _entry(session, workflow['queue_entry_id'])
    if entry['id'] not in context.plan.queue_entry_ids:
        op.fail('invalid_transition')
    if workflow['state'] == 'completed' and entry['state'] == 'completed':
        return
    if entry['state'] != 'in_consultation':
        op.fail('invalid_transition')
    await session.execute(text("""
        UPDATE queue_entries SET state='completed', position=NULL,
            version=version+1, updated_at=:now WHERE id=:id
    """), {'now': context.now, 'id': entry['id']})
    await session.execute(update(m.appointment_workflows).where(
        m.appointment_workflows.c.appointment_id == aid).values(
        state='completed', version=workflow['version']+1, updated_at=context.now))
    await _bump_snapshot(session, entry['doctor_id'], entry['local_date'], context.now)
    core.stage_effect(session, context, 'workflow_completed', aid, workflow['version']+1,
        {'resource_id': str(aid), 'version': workflow['version']+1, 'state': 'completed'})


async def no_show(session, context, appointment_id, expected_version, reason):
    core.require_context(session, context)
    aid = int(appointment_id)
    workflow = await core.read_workflow(session, aid)
    if workflow is None:
        op.fail('not_found', 404)
    if workflow['version'] != expected_version:
        op.fail('version_conflict', 412)
    if workflow['state'] not in ('booked', 'checked_in') or context.bookings[aid]['state'] != 'confirmed':
        op.fail('invalid_transition')
    if context.now < workflow['window_ends_at']:
        op.fail('checkin_window_open')
    if aid in context.holds:
        op.fail('clinical_hold')
    if workflow['queue_entry_id'] is not None:
        entry = await _entry(session, workflow['queue_entry_id'])
        if entry['state'] not in ('waiting', 'skipped'):
            op.fail('invalid_transition')
        await session.execute(text("""
            UPDATE queue_entries SET state='no_show', position=NULL,
                version=version+1, updated_at=:now WHERE id=:id
        """), {'now': context.now, 'id': entry['id']})
        await _reposition(session, context, entry['doctor_id'], entry['local_date'])
        await _bump_snapshot(session, entry['doctor_id'], entry['local_date'], context.now)
    await session.execute(update(m.appointment_workflows).where(
        m.appointment_workflows.c.appointment_id == aid).values(
        state='no_show', version=workflow['version']+1, updated_at=context.now))
    core.stage_effect(session, context, 'workflow_no_show', aid, workflow['version']+1,
        {'resource_id': str(aid), 'version': workflow['version']+1, 'state': 'no_show'}, reason=reason)
    result = await core.read_workflow(session, aid)
    return core.workflow_view(result)


async def cancel_for_booking_change(session, context, appointment_id) -> None:
    """G2 cancellation participant; caller already validates booking ETag/scope.

    A checked-in waiting entry and workflow become terminal together. An active
    consultation, clinical hold, or completed/no-show workflow fails closed.
    """
    core.require_context(session, context)
    aid = int(appointment_id)
    if aid not in context.bookings:
        raise op.Restart()
    workflow = await core.read_workflow(session, aid)
    if workflow is None:
        return  # Historical, unenrolled Phase 2 booking.
    if aid in context.holds:
        op.fail('clinical_hold')
    if workflow['state'] not in ('booked', 'checked_in'):
        op.fail('workflow_locked')
    if workflow['queue_entry_id'] is not None:
        entry = await _entry(session, workflow['queue_entry_id'])
        if entry['id'] not in context.plan.queue_entry_ids:
            raise op.Restart()
        if entry['state'] not in ('waiting', 'skipped'):
            op.fail('workflow_locked')
        await session.execute(text("""
            UPDATE queue_entries SET state='cancelled', position=NULL,
                version=version+1, updated_at=:now WHERE id=:id
        """), {'now': context.now, 'id': entry['id']})
        await _reposition(session, context, entry['doctor_id'], entry['local_date'])
        await _bump_snapshot(session, entry['doctor_id'], entry['local_date'], context.now)
    await session.execute(update(m.appointment_workflows).where(
        m.appointment_workflows.c.appointment_id == aid).values(
        state='cancelled', version=workflow['version']+1, updated_at=context.now))
    core.stage_effect(session, context, 'workflow_cancelled', aid, workflow['version']+1,
        {'resource_id': str(aid), 'version': workflow['version']+1, 'state': 'cancelled'})


def _scope_hash(doctor_id, day, state, actor):
    raw = json.dumps([str(doctor_id), day.isoformat(), state, actor.user_id,
                      sorted(actor.roles)], separators=(',', ':'))
    return hashlib.sha256(raw.encode()).hexdigest()


def cursor_encode(version, token_number, entry_id, scope):
    raw = json.dumps({'v': version, 't': token_number, 'i': entry_id, 's': scope}, separators=(',', ':'))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip('=')


def cursor_decode(value, scope):
    try:
        data = json.loads(base64.urlsafe_b64decode(value + '=' * (-len(value) % 4)))
        if (set(data) != {'v', 't', 'i', 's'} or data['s'] != scope or
            any(type(data[k]) is not int or data[k] < 1 for k in ('v', 't', 'i'))):
            raise ValueError
        return data
    except (ValueError, UnicodeError, TypeError, KeyError, binascii.Error):
        op.fail('bad_request', 400)


async def staff_snapshot(session, doctor_id, day, state, cursor, limit, actor):
    """A shared row lock holds the revision steady until all reads finish."""
    await _read_doctor_guard(session, doctor_id)
    table = _table()
    snapshot = (await session.execute(select(table).where(table.c.doctor_id == doctor_id,
        table.c.local_date == day).with_for_update(read=True))).mappings().first()
    version = snapshot['version'] if snapshot else 1
    scope = _scope_hash(doctor_id, day, state, actor)
    decoded = cursor_decode(cursor, scope) if cursor else None
    if decoded and decoded['v'] != version:
        op.fail('queue_changed')
    conditions = [m.queue_entries.c.doctor_id == doctor_id, m.queue_entries.c.local_date == day]
    if state:
        conditions.append(m.queue_entries.c.state == state)
    if decoded:
        conditions.append((m.queue_entries.c.token_number > decoded['t']) |
            ((m.queue_entries.c.token_number == decoded['t']) & (m.queue_entries.c.id > decoded['i'])))
    rows = (await session.execute(select(m.queue_entries, m.appointments.c.patient_id).join(m.appointments,
        m.appointments.c.id == m.queue_entries.c.appointment_id).where(*conditions)
        .order_by(m.queue_entries.c.token_number, m.queue_entries.c.id).limit(limit+1))).mappings().all()
    counts = (await session.execute(text("""
        SELECT count(*) FILTER (WHERE state='waiting') AS waiting,
               count(*) FILTER (WHERE state='in_consultation') AS active
        FROM queue_entries WHERE doctor_id=:doctor_id AND local_date=:day
    """), {'doctor_id': doctor_id, 'day': day})).mappings().one()
    page = rows[:limit]
    next_cursor = (cursor_encode(version, page[-1]['token_number'], page[-1]['id'], scope)
                   if len(rows) > limit else None)
    return {'doctor_id': str(doctor_id), 'local_date': day.isoformat(),
            'items': [entry_view(row, patient_id=row['patient_id']) for row in page],
            'next_cursor': next_cursor, 'waiting_count': counts['waiting'],
            'in_consultation_count': counts['active'], 'version': version,
            'observed_at': op.wire_time(op.now())}


async def own_snapshot(session, appointment_id):
    row = (await session.execute(text("""
        SELECT id, appointment_id, doctor_id, local_date, token_number, state, position, version
        FROM queue_entries WHERE appointment_id=:aid
    """), {'aid': int(appointment_id)})).mappings().first()
    if row is None:
        op.fail('not_found', 404)
    await _read_doctor_guard(session, row['doctor_id'])
    table = _table()
    snapshot = (await session.execute(select(table).where(table.c.doctor_id == row['doctor_id'],
        table.c.local_date == row['local_date']).with_for_update(read=True))).mappings().first()
    row = await _entry(session, row['id'])
    counts = (await session.execute(text("""
        SELECT count(*) FILTER (WHERE state='waiting') AS waiting,
               count(*) FILTER (WHERE state='in_consultation') AS active
        FROM queue_entries WHERE doctor_id=:doctor_id AND local_date=:day
    """), {'doctor_id': row['doctor_id'], 'day': row['local_date']})).mappings().one()
    return {'entry': entry_view(row), 'waiting_count': counts['waiting'],
            'in_consultation_count': counts['active'],
            'queue_version': snapshot['version'] if snapshot else 1,
            'observed_at': op.wire_time(op.now())}


async def skip_or_recall(session, context, entry_id, expected_version, recall, reason):
    core.require_context(session, context)
    entry = await _entry(session, entry_id)
    if entry_id not in context.plan.queue_entry_ids or entry['appointment_id'] not in context.bookings:
        raise op.Restart()
    if entry['version'] != expected_version:
        op.fail('version_conflict', 412)
    source, target = ('skipped', 'waiting') if recall else ('waiting', 'skipped')
    workflow = await core.read_workflow(session, entry['appointment_id'])
    if (entry['state'] != source or workflow is None or workflow['state'] != 'checked_in'
            or context.bookings[entry['appointment_id']]['state'] != 'confirmed'):
        op.fail('invalid_transition')
    if entry['appointment_id'] in context.holds:
        op.fail('clinical_hold')
    await session.execute(text('UPDATE queue_entries SET state=:state,position=:position,version=version+1,'
        'updated_at=:now WHERE id=:id'), dict(state=target,position=1 if recall else None,
        now=context.now,id=entry_id))
    await _reposition(session, context, entry['doctor_id'], entry['local_date'])
    await _bump_snapshot(session, entry['doctor_id'], entry['local_date'], context.now)
    result = await _entry(session, entry_id)
    core.stage_effect(session, context, 'queue_recalled' if recall else 'queue_skipped', entry_id,
        result['version'], dict(resource_id=str(entry_id),version=result['version'],state=result['state']), reason)
    return entry_view(result)
