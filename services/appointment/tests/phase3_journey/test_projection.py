from copy import deepcopy

import pytest

from appointment_service.features.journey.projection import STAGES, project
from appointment_service.features.journey.registration import register_tables, schema_spec
from appointment_service import models as m


def fixtures():
    booking = {'id': 1, 'patient_id': 2, 'doctor_id': 3, 'state': 'confirmed'}
    workflow = {'state': 'completed'}
    hold = {'state': 'finalized', 'consultation_id': 4}
    records = {'appointment_id': '1', 'patient_id': '2', 'doctor_id': '3', 'revision': 2,
               'observed_at': '2026-01-01T00:00:00Z', 'consultation': {'id': '4', 'status': 'finalized',
               'version': 2, 'prescription': None}}
    billing = {'appointment_id': '1', 'patient_id': '2', 'revision': 2,
               'observed_at': '2026-01-01T00:00:00Z', 'invoice': {'id': '5', 'version': 2,
               'balance_minor': 0, 'charge_source_keys': [{'source_service': 'records', 'source_item_id': '4'}]}}
    return booking, workflow, hold, records, billing


def test_optional_stages_and_exact_financial_coverage():
    b, w, h, r, invoice = fixtures()
    result = project(b, w, h, r, None, invoice)
    assert tuple(s['name'] for s in result['stages']) == STAGES
    assert [s['state'] for s in result['stages']] == ['complete', 'complete', 'complete', 'skipped', 'skipped', 'complete']
    assert result['discharge_eligible']
    invoice['invoice']['charge_source_keys'] = []
    result = project(b, w, h, r, None, invoice)
    assert not result['discharge_eligible']
    assert result['stages'][-1]['pending_reason'] == 'missing_charges'


def test_incomplete_owner_and_identity_mismatch():
    b, w, h, r, invoice = fixtures()
    assert project(b, w, h, None, None, invoice)['stages'][2]['pending_reason'] == 'owner_unavailable'
    bad = deepcopy(r)
    bad['patient_id'] = '99'
    with pytest.raises(ValueError):
        project(b, w, h, bad, None, invoice)


def test_cancellation_and_unfinalized_hold_cannot_be_ready():
    b, w, h, r, invoice = fixtures()
    b['state'] = 'cancelled'
    assert not project(b, w, h, r, None, invoice)['discharge_eligible']


def test_prescription_requires_fulfillment_and_dispensing_charge_acknowledgement():
    b, w, h, r, invoice = fixtures()
    r['consultation']['prescription'] = {'id': '6', 'version': 2, 'revision': 2,
        'state': 'issued', 'items': [{'prescription_item_id': '7', 'quantity': 2}]}
    pharmacy = {'appointment_id': '1', 'patient_id': '2', 'prescription_id': '6',
        'revision': 2, 'observed_at': '2026-01-01T00:00:00Z',
        'fulfillment': {'prescription_revision': 2, 'prescription_state': 'issued',
        'version': 2, 'review_required': False,
        'items': [{'prescription_item_id': '7', 'prescribed_quantity': 2, 'dispensed_quantity': 1}],
        'reservations': [], 'dispensings': [{'source_item_ids': ['8']}]}}
    assert not project(b, w, h, r, pharmacy, invoice)['discharge_eligible']
    pharmacy['fulfillment']['items'][0]['dispensed_quantity'] = 2
    assert not project(b, w, h, r, pharmacy, invoice)['discharge_eligible']
    invoice['invoice']['charge_source_keys'].append({'source_service': 'pharmacy', 'source_item_id': '8'})
    assert project(b, w, h, r, pharmacy, invoice)['discharge_eligible']
    b['state'] = 'confirmed'
    h['state'] = 'active'
    assert not project(b, w, h, r, None, invoice)['discharge_eligible']


def test_metadata_and_manifest():
    register_tables(m.metadata)
    spec = schema_spec()
    assert {t['name'] for t in spec['tables']} >= {'journey_snapshots', 'journey_transitions'}
