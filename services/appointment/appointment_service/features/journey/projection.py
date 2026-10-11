"""Pure stage decisions from complete, identity-bound owner snapshots."""
from datetime import datetime, timezone

STAGES = ('appointment', 'check_in', 'consultation', 'prescription', 'pharmacy', 'billing')


def _stage(name, state='pending', reason='awaiting_source', sources=(), observed_at=None):
    return dict(name=name, state=state, pending_reason=reason if state == 'pending' else None,
                sources=list(sources), observed_at=observed_at)


def _source(owner, kind, resource, version, observed_at):
    return dict(owner=owner, resource_type=kind, resource_id=str(resource),
                version=version, observed_at=observed_at)


def project(booking, workflow, hold, records=None, pharmacy=None, billing=None):
    """No missing owner is interpreted as an empty source or a paid invoice."""
    aid, pid = str(booking['id']), str(booking['patient_id'])
    for snapshot in (records, pharmacy, billing):
        if snapshot is not None and (str(snapshot['appointment_id']), str(snapshot['patient_id'])) != (aid, pid):
            raise ValueError('Owner snapshot identity mismatch')
    observed = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    cancelled = booking['state'] == 'cancelled' or workflow['state'] in ('cancelled', 'no_show')
    stages = [_stage('appointment', 'complete' if not cancelled else 'skipped', None),
              _stage('check_in', 'complete' if workflow['state'] in ('checked_in', 'in_consultation', 'completed') else 'pending',
                     'awaiting_source')]
    consultation = records.get('consultation') if records else None
    finalized = bool(consultation and consultation['status'] == 'finalized' and
                     hold and hold['state'] == 'finalized' and
                     str(consultation['id']) == str(hold['consultation_id']) and
                     str(records['doctor_id']) == str(booking['doctor_id']))
    sources = [_source('records', 'consultation', consultation['id'], consultation['version'], records['observed_at'])] if finalized else []
    stages.append(_stage('consultation', 'complete' if finalized else 'pending',
                         'awaiting_source' if records else 'owner_unavailable', sources,
                         records['observed_at'] if records else None))
    prescription = consultation.get('prescription') if finalized else None
    if not finalized:
        stages.extend((_stage('prescription', reason='owner_unavailable' if records is None else 'awaiting_source'),
                       _stage('pharmacy', reason='owner_unavailable' if pharmacy is None else 'awaiting_source')))
    elif prescription is None:
        stages.extend((_stage('prescription', 'skipped', None, observed_at=records['observed_at']),
                       _stage('pharmacy', 'skipped', None, observed_at=records['observed_at'])))
    else:
        p_source = [_source('records', 'prescription', prescription['id'], prescription['version'], records['observed_at'])]
        issued = prescription['state'] == 'issued'
        stages.append(_stage('prescription', 'complete' if issued else 'pending',
                             'review_required', p_source, records['observed_at']))
        matching = pharmacy and str(pharmacy['prescription_id']) == str(prescription['id'])
        fulfillment = pharmacy.get('fulfillment') if matching else None
        compatible = fulfillment and fulfillment['prescription_revision'] == prescription['revision'] and fulfillment['prescription_state'] == prescription['state']
        items = fulfillment['items'] if compatible else []
        full = compatible and {str(i['prescription_item_id']) for i in items} == {str(i['prescription_item_id']) for i in prescription['items']} and all(i['dispensed_quantity'] == i['prescribed_quantity'] for i in items)
        active = compatible and any(r['state'] == 'reserved' for r in fulfillment['reservations'])
        dispensed = compatible and any(i['dispensed_quantity'] for i in items)
        skipped = compatible and not issued and not active and not dispensed
        state = 'complete' if issued and full else 'skipped' if skipped else 'pending'
        reason = 'owner_unavailable' if pharmacy is None else 'source_changed' if not compatible else 'review_required' if not issued or fulfillment['review_required'] else 'unfilled'
        f_source = [_source('pharmacy', 'fulfillment', prescription['id'], fulfillment['version'], pharmacy['observed_at'])] if compatible else []
        stages.append(_stage('pharmacy', state, reason, f_source, pharmacy['observed_at'] if pharmacy else None))
    expected = {('records', str(consultation['id']))} if finalized else set()
    if prescription and pharmacy and pharmacy.get('fulfillment') and pharmacy['fulfillment']['prescription_revision'] == prescription['revision']:
        for dispensing in pharmacy['fulfillment']['dispensings']:
            expected.update(('pharmacy', str(item)) for item in dispensing['source_item_ids'])
    invoice = billing.get('invoice') if billing else None
    actual = {(key['source_service'], str(key['source_item_id'])) for key in invoice['charge_source_keys']} if invoice else set()
    coverage = bool(finalized and billing and invoice and (prescription is None or pharmacy and pharmacy.get('fulfillment')) and
                    actual == expected and invoice['balance_minor'] == 0)
    billing_reason = ('owner_unavailable' if billing is None else 'missing_invoice' if invoice is None else
                      'missing_charges' if actual != expected else 'unpaid' if invoice['balance_minor'] else 'awaiting_source')
    b_sources = [_source('billing', 'invoice', invoice['id'], invoice['version'], billing['observed_at'])] if invoice else []
    stages.append(_stage('billing', 'complete' if coverage else 'pending', billing_reason,
                         b_sources, billing['observed_at'] if billing else None))
    review = bool(prescription and prescription['state'] == 'revoked' and
                  not (pharmacy and pharmacy.get('fulfillment') and stages[4]['state'] == 'skipped'))
    review |= bool(pharmacy and pharmacy.get('fulfillment') and pharmacy['fulfillment']['review_required'])
    ready = not cancelled and not review and all(s['state'] in ('complete', 'skipped') for s in stages)
    return dict(stages=stages, expected_sources=sorted(expected), review_required=review,
                discharge_eligible=ready, observed_at=observed)
