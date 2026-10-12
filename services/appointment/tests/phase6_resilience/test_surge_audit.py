"""Real PostgreSQL checks for the Phase 6 append-only audit extension."""
import asyncio
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from appointment_service import operations as op
from ..test_concurrency import run


def event(action, previous, new_state, version, reason='capacity_pressure', override=False):
    metadata = {
        'action': action,
        'result': 'success',
        'actor_user_id': '7001',
        'resource_id': '1',
        'request_id': str(uuid4()),
        'correlation_id': str(uuid4()),
        'occurred_at': op.wire_time(op.now()),
        'previous_state': previous,
        'new_state': new_state,
        'reason_code': reason,
        'state_version': str(version),
        'operation_id': str(uuid4()),
        'override': override,
    }
    if action in {'surge_mode_transition_applied', 'surge_mode_transition_noop'}:
        metadata['response'] = {
            'state': new_state,
            'version': version,
            'changed_at': op.wire_time(op.now()),
            'expires_at': None,
            'reason_code': reason,
        }
    return metadata


def test_surge_events_append_to_existing_chain_with_runtime_role(database):
    async def work(db):
        first = event('surge_mode_transition_requested', 'NORMAL', 'SURGE', 0)
        second = event('surge_mode_transition_applied', 'NORMAL', 'SURGE', 1)
        third = event('surge_mode_transition_noop', 'SURGE', 'SURGE', 1)
        async with db.session_factory() as session, session.begin():
            for metadata in (first, second, third):
                await session.execute(text(
                    'SELECT public.appointment_append_phase6_audit(:entry_id,CAST(:metadata AS jsonb))'),
                    {'entry_id': op.new_id(), 'metadata': op.canonical(metadata)})
            rows = (await session.execute(text(
                "SELECT sequence,prev_hash,entry_hash,canonical_metadata "
                "FROM public.audit_entries WHERE chain_id='appointment' ORDER BY sequence"))).mappings().all()
            assert [row['sequence'] for row in rows] == [1, 2, 3]
            assert rows[1]['prev_hash'] == rows[0]['entry_hash']
            assert all(row['canonical_metadata']['action'].startswith('surge_mode_transition_') for row in rows)
            assert all('patient_id' not in row['canonical_metadata'] and 'appointment_id' not in row['canonical_metadata'] for row in rows)
            verified = (await session.execute(text(
                "SELECT bool_and(entry_hash=encode(public.digest(convert_to(prev_hash||canonical_metadata::text,'UTF8'),'sha256'),'hex')) "
                "FROM public.audit_entries WHERE chain_id='appointment'"))).scalar_one()
            assert verified is True

            invalid = deepcopy(event('surge_mode_transition_requested', 'NORMAL', 'SURGE', 0))
            invalid.pop('previous_state')
            with pytest.raises(DBAPIError):
                async with session.begin_nested():
                    await session.execute(text(
                        'SELECT public.appointment_append_phase6_audit(:entry_id,CAST(:metadata AS jsonb))'),
                        {'entry_id': op.new_id(), 'metadata': op.canonical(invalid)})
            assert (await session.execute(text(
                "SELECT last_sequence FROM public.audit_heads WHERE chain_id='appointment'"))).scalar_one() == 3

    run(database, work)
