"""Real synthetic Phase 2 workflows through Traefik, retaining all history.

Temporarily enable the existing auth-test PostgreSQL port for the explicit
Patient-owned first-admin bootstrap. All hospital dependencies use owner HTTP
APIs. Secrets/credentials are kept only in a private ignored /tmp fixture file.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import secrets
import sys
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = 'http://127.0.0.1:5173'


def require(response, codes=(200,)):
    if response.status_code not in codes:
        try: code = response.json().get('error',{}).get('code','unknown')
        except ValueError: code = 'non_json'
        raise AssertionError(f'{response.request.method} {response.request.url.path}: {response.status_code} {code}; expected {codes}')
    return response.json() if response.status_code != 204 else None


class Actor:
    def __init__(self, base, data):
        self.data=data
        self.client=httpx.Client(base_url=base,headers={'Origin':ORIGIN},timeout=15,trust_env=False)
        self.token=None

    def login(self):
        csrf=require(self.client.get('/api/v1/auth/csrf'))['csrf_token']
        result=require(self.client.post('/api/v1/auth/login',json={'email':self.data['email'],'password':self.data['password']},headers={'X-CSRF-Token':csrf}))
        self.token=result['access_token']

    def call(self, method, path, body=None, etag=None, key=None, codes=(200,)):
        headers={'Authorization':'Bearer '+self.token}
        if etag is not None: headers['If-Match']=etag
        if key is not None: headers['Idempotency-Key']=key
        response=self.client.request(method,path,json=body,headers=headers)
        data=require(response,codes)
        return data,response.headers.get('etag'),response.status_code


def bootstrap(data):
    # Existing owner CLI/function: this is an explicit operator operation, not
    # an HTTP auth bypass or business-service access to a foreign database.
    for line in (ROOT/'.env').read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            key,value=line.split('=',1)
            os.environ.setdefault(key,value.strip().strip('"').strip("'"))
    sys.path.insert(0,str(ROOT/'services/patient'))
    from patient_service.settings import Settings
    from patient_service.bootstrap_admin import bootstrap_first_admin
    bootstrap_first_admin(data['email'],Settings(environment='development',db_host='127.0.0.1',db_port=55433,db_name='patient_db',db_user='patient_app',db_password=os.environ['PATIENT_DB_PASSWORD']))


def verify(base, fixture):
    if fixture.exists(): state=json.loads(fixture.read_text())
    else: state={'run':str(uuid.uuid4()),'actors':{},'resources':{},'checks':[]}
    def save():
        fixture.write_text(json.dumps(state,indent=2));fixture.chmod(0o600)
    def key(label):return str(uuid.uuid5(uuid.UUID(state['run']),label))
    actors={}
    for role in ['admin','doctor','alternate_doctor','pharmacist','billing_staff','emergency_staff','patient','other']:
        data=state['actors'].setdefault(role,{'email':f'p29-{role}-{state["run"]}@example.test','password':secrets.token_urlsafe(24)})
        save(); actor=Actor(base,data);actors[role]=actor
        if 'profile' not in data:
            response=actor.client.post('/api/v1/auth/register',json={'email':data['email'],'password':data['password'],'display_name':'Synthetic Phase29 '+role},headers={'Idempotency-Key':key('register-'+role),'X-Anonymous-Command-ID':key('anonymous-'+role).replace('-','')+'A'*12})
            data['profile']=require(response,(201,));save()
    admin=actors['admin']
    if not state.get('admin_bootstrapped'):
        bootstrap(admin.data);state['admin_bootstrapped']=True;save()
    admin.login()
    for role in ['doctor','alternate_doctor','pharmacist','billing_staff','emergency_staff']:
        expected_role='doctor' if role=='alternate_doctor' else role
        actor=actors[role];uid=actor.data['profile']['user_id']
        user,etag,_=admin.call('GET','/api/v1/patients/users/'+uid)
        if user['roles'] != [expected_role]:admin.call('PATCH','/api/v1/patients/users/'+uid+'/roles',{'roles':[expected_role]},etag=etag)
    for actor in actors.values():actor.login()
    def checked(name):
        if name not in state['checks']:state['checks'].append(name)
        save();print('PASS',name,flush=True)
    resources=state['resources']
    def create(name, actor, method, path, body, etag=None,codes=(201,)):
        if name not in resources:
            resources[name]=actor.call(method,path,body,etag,key(name),codes)[0];save()
        return resources[name]
    patient=actors['patient'];other=actors['other'];doctor=actors['doctor'];pharmacist=actors['pharmacist'];billing=actors['billing_staff'];emergency=actors['emergency_staff']
    profile,etag,_=patient.call('GET','/api/v1/patients/me')
    patient.call('PATCH','/api/v1/patients/me',{'synthetic_contact':'Synthetic contact only'},etag=etag)
    checked('patient_profile_read_update')
    specialty=create('specialty',admin,'POST','/api/v1/doctors/specialties',{'slug':'phase29-'+state['run'][:8],'name':'Synthetic General Care'})
    d=create('doctor',admin,'POST','/api/v1/doctors',{'staff_user_id':doctor.data['profile']['user_id'],'display_name':'Synthetic Phase29 Doctor','specialty_ids':[specialty['id']]})
    _,de,_=doctor.call('GET','/api/v1/doctors/'+d['id'])
    start=(datetime.now(timezone.utc)+timedelta(days=2)).replace(hour=4,minute=0,second=0,microsecond=0)
    start_text=start.isoformat();end_text=(start+timedelta(hours=2)).isoformat()
    schedule=create('schedule',doctor,'POST',f'/api/v1/doctors/{d["id"]}/schedules',{'timezone':'Asia/Kolkata','slot_minutes':15,'intervals':[{'starts_at':start_text,'ends_at':end_text}],'expected_revision':0},de,(202,))
    decision=create('decision',doctor,'POST','/api/v1/appointments/schedule-decisions',{'doctor_id':d['id'],'proposal_id':schedule['id'],'expected_accepted_revision':0})
    assert decision['state']=='accepted'
    proposal,pe,_=doctor.call('GET',f'/api/v1/doctors/{d["id"]}/schedules/{schedule["id"]}')
    if proposal['status']=='pending':
        doctor.call('POST',f'/api/v1/doctors/{d["id"]}/schedules/{schedule["id"]}/reconcile',{},pe,key('reconcile'))
    availability,_,_=patient.call('GET',f'/api/v1/appointments/availability?doctor_id={d["id"]}&from={start.strftime("%Y-%m-%dT%H:%M:%SZ")}&to={(start+timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")}')
    slots=availability['slots'];assert len(slots)>=4
    revision=availability['accepted_revision']
    checked('doctor_schedule_accept_reconcile_availability')
    appointment=create('appointment',patient,'POST','/api/v1/appointments',{'patient_id':profile['id'],'slot_id':slots[0]['id'],'expected_schedule_revision':revision})
    if not state.get('rescheduled'):
        ap,ae,_=patient.call('GET','/api/v1/appointments/'+appointment['id'])
        patient.call('POST',f'/api/v1/appointments/{ap["id"]}/reschedule',{'target_slot_id':slots[1]['id'],'expected_schedule_revision':revision},ae,key('reschedule'))
        state['rescheduled']=True;save()
    cancel=create('cancel_booking',patient,'POST','/api/v1/appointments',{'patient_id':profile['id'],'slot_id':slots[2]['id'],'expected_schedule_revision':revision})
    cancellable,ce,_=patient.call('GET','/api/v1/appointments/'+cancel['id'])
    if cancellable['state']=='confirmed':
        patient.call('POST',f'/api/v1/appointments/{cancel["id"]}/cancel',{'reason':'Synthetic cancellation'},ce,key('cancel'))
    other.call('GET','/api/v1/appointments/'+appointment['id'],codes=(404,))
    checked('book_reschedule_cancel_and_other_patient_denial')
    # Race two distinct registered patients via real gateway/API/PostgreSQL.
    if 'concurrency' not in resources:
        body=lambda actor:{'patient_id':actor.data['profile']['id'],'slot_id':slots[3]['id'],'expected_schedule_revision':revision}
        def compete(actor):
            return actor.call('POST','/api/v1/appointments',body(actor),key=key('race-'+actor.data['profile']['id']),codes=(201,409))[2]
        with ThreadPoolExecutor(max_workers=2) as pool:statuses=list(pool.map(compete,[patient,other]))
        assert sorted(statuses)==[201,409],statuses
        resources['concurrency']={'requests':2,'statuses':statuses,'exclusive_successes':1};save()
    checked('gateway_same_slot_concurrency_one_winner')
    medicine=create('medicine',pharmacist,'POST','/api/v1/pharmacy/medicines',{'sku':'P29-'+state['run'],'name':'Synthetic medicine'})
    create('stock',pharmacist,'POST','/api/v1/pharmacy/inventory-adjustments',{'medicine_id':medicine['id'],'batch_code':'P29-LOT','expires_on':(start.date()+timedelta(days=30)).isoformat(),'delta':10,'reason':'Synthetic initial stock','expected_batch_version':0})
    content={'summary':'Synthetic consultation','assessment':'Educational fixture only','plan':'Synthetic follow-up'}
    actors['alternate_doctor'].call('POST','/api/v1/records/consultations',{'appointment_id':appointment['id'],'clinical_content':content},key=key('unassigned-doctor'),codes=(404,))
    consultation=create('consultation',doctor,'POST','/api/v1/records/consultations',{'appointment_id':appointment['id'],'clinical_content':content})
    _,coet,_=doctor.call('GET','/api/v1/records/consultations/'+consultation['id'])
    final=create('finalize',doctor,'POST',f'/api/v1/records/consultations/{consultation["id"]}/finalize',{'prescription_items':[{'medicine_id':medicine['id'],'quantity':2,'dosage':'Synthetic dose','instructions':'Educational fixture'}]},coet,(200,))
    prescription=final['prescription'];record=final['record'];assert prescription is not None
    patient.call('GET','/api/v1/records/'+record['id'])
    patient.call('GET','/api/v1/records/patients/'+profile['id'])
    other.call('GET','/api/v1/records/'+record['id'],codes=(404,))
    other.call('GET','/api/v1/records/prescriptions/'+prescription['id'],codes=(404,))
    _,ae,_=patient.call('GET','/api/v1/appointments/'+appointment['id'])
    patient.call('POST',f'/api/v1/appointments/{appointment["id"]}/cancel',{'reason':'Clinical hold denial fixture'},ae,key('hold-cancel-denied'),(409,))
    checked('assigned_doctor_finalize_history_prescription_and_access_denial')
    reservation=create('reservation',pharmacist,'POST','/api/v1/pharmacy/reservations',{'prescription_id':prescription['id'],'items':[{'prescription_item_id':prescription['items'][0]['id'],'quantity':2}]})
    other.call('GET','/api/v1/pharmacy/reservations/'+reservation['id'],codes=(404,))
    _,re,_=pharmacist.call('GET','/api/v1/pharmacy/reservations/'+reservation['id'])
    dispensing=create('dispense',pharmacist,'POST',f'/api/v1/pharmacy/reservations/{reservation["id"]}/dispense',{},re)
    _,newre,_=pharmacist.call('GET','/api/v1/pharmacy/reservations/'+reservation['id'])
    duplicate=create('dispense-again',pharmacist,'POST',f'/api/v1/pharmacy/reservations/{reservation["id"]}/dispense',{},newre)
    assert duplicate['id']==dispensing['id']
    inv,_,_=pharmacist.call('GET','/api/v1/pharmacy/inventory?medicine_id='+medicine['id'])
    assert inv['items'][0]['on_hand']==8 and inv['items'][0]['reserved']==0
    checked('prescription_fulfillment_inventory_and_duplicate_dispense')
    create('consultation_tariff',billing,'POST','/api/v1/billing/tariffs',{'charge_code':'consultation','unit_amount_minor':10000,'currency':'INR'})
    create('medicine_tariff',billing,'POST','/api/v1/billing/tariffs',{'charge_code':'medicine:'+medicine['id'],'unit_amount_minor':2500,'currency':'INR'})
    invoice=create('invoice',billing,'POST','/api/v1/billing/invoices',{'appointment_id':appointment['id'],'currency':'INR'})
    _,ie,_=billing.call('GET','/api/v1/billing/invoices/'+invoice['id'])
    charged=create('charges',billing,'POST',f'/api/v1/billing/invoices/{invoice["id"]}/charges',{'consultation_id':consultation['id'],'dispensing_ids':[dispensing['id']]},ie,(200,))
    assert charged['total_minor']==15000 and len(charged['items'])==2
    _,ie,_=billing.call('GET','/api/v1/billing/invoices/'+invoice['id'])
    if state.get('paid'):
        same=billing.call('GET','/api/v1/billing/invoices/'+invoice['id'])[0]
    else:
        same=create('reimport',billing,'POST',f'/api/v1/billing/invoices/{invoice["id"]}/charges',{'consultation_id':consultation['id'],'dispensing_ids':[dispensing['id']]},ie,(200,))
    assert same['total_minor']==15000 and len(same['items'])==2
    _,ie,_=patient.call('GET','/api/v1/billing/invoices/'+invoice['id'])
    if not state.get('paid'):
        declined=patient.call('POST',f'/api/v1/billing/invoices/{invoice["id"]}/payments',{'amount_minor':15000,'currency':'INR','simulated_outcome':'decline'},ie,key('decline'),(201,))[0]
        assert declined['status']=='declined'
        unpaid,ie,_=patient.call('GET','/api/v1/billing/invoices/'+invoice['id']);assert unpaid['paid_minor']==0
        paid=patient.call('POST',f'/api/v1/billing/invoices/{invoice["id"]}/payments',{'amount_minor':15000,'currency':'INR','simulated_outcome':'success'},ie,key('pay'),(201,))[0]
        assert paid['status']=='success';state['paid']=True;save()
    paid_invoice,_,_=patient.call('GET','/api/v1/billing/invoices/'+invoice['id']);assert paid_invoice['paid_minor']==15000 and paid_invoice['balance_minor']==0
    other.call('GET','/api/v1/billing/invoices/'+invoice['id'],codes=(404,))
    checked('invoice_consultation_medicine_import_dedup_decline_and_payment')
    e=create('emergency',patient,'POST','/api/v1/emergencies',{'patient_id':profile['id'],'description':'Synthetic emergency verification','reported_urgency':'urgent'})
    _,ee,_=patient.call('GET','/api/v1/emergencies/'+e['id'])
    patient.call('PATCH',f'/api/v1/emergencies/{e["id"]}/priority',{'assigned_priority':1,'reason':'Must be denied'},ee,codes=(403,))
    if not state.get('emergency_resolved'):
        triaged,ee,_=emergency.call('PATCH',f'/api/v1/emergencies/{e["id"]}/priority',{'assigned_priority':3,'reason':'Synthetic staff priority'},ee)
        _,ee,_=emergency.call('POST',f'/api/v1/emergencies/{e["id"]}/claim',{},ee,key('claim'))
        _,ee,_=emergency.call('POST',f'/api/v1/emergencies/{e["id"]}/transitions',{'state':'processing','reason':'Synthetic processing'},ee,key('processing'))
        resolved,_,_=emergency.call('POST',f'/api/v1/emergencies/{e["id"]}/transitions',{'state':'resolved','reason':'Synthetic resolved'},ee,key('resolved'))
        assert resolved['state']=='resolved';state['emergency_resolved']=True;save()
    checked('emergency_patient_submission_staff_claim_processing_resolution')
    prescription,pre,_=doctor.call('GET','/api/v1/records/prescriptions/'+prescription['id'])
    if prescription['state']=='issued':doctor.call('POST',f'/api/v1/records/prescriptions/{prescription["id"]}/revoke',{'reason':'Synthetic revocation'},pre,key('revoke'))
    pharmacist.call('POST','/api/v1/pharmacy/reservations',{'prescription_id':prescription['id'],'items':[{'prescription_item_id':prescription['items'][0]['id'],'quantity':1}]},key=key('revoked-reserve'),codes=(409,))
    checked('revoked_prescription_rejects_new_fulfillment')
    # A second unfilled reservation exercises the explicit revocation recovery workflow.
    ra=create('revocation_appointment',patient,'POST','/api/v1/appointments',{'patient_id':profile['id'],'slot_id':slots[-1]['id'],'expected_schedule_revision':revision})
    rc=create('revocation_consultation',doctor,'POST','/api/v1/records/consultations',{'appointment_id':ra['id'],'clinical_content':content})
    _,rce,_=doctor.call('GET','/api/v1/records/consultations/'+rc['id'])
    rf=create('revocation_finalize',doctor,'POST',f'/api/v1/records/consultations/{rc["id"]}/finalize',{'prescription_items':[{'medicine_id':medicine['id'],'quantity':1,'dosage':'Synthetic dose','instructions':'Revocation fixture'}]},rce,(200,))
    rp=rf['prescription']
    rr=create('revocation_reservation',pharmacist,'POST','/api/v1/pharmacy/reservations',{'prescription_id':rp['id'],'items':[{'prescription_item_id':rp['items'][0]['id'],'quantity':1}]})
    current,rpe,_=doctor.call('GET','/api/v1/records/prescriptions/'+rp['id'])
    if current['state']=='issued':doctor.call('POST',f'/api/v1/records/prescriptions/{rp["id"]}/revoke',{'reason':'Synthetic unfilled revocation'},rpe,key('revoke-unfilled'))
    _,rre,_=pharmacist.call('GET','/api/v1/pharmacy/reservations/'+rr['id'])
    pharmacist.call('POST',f'/api/v1/pharmacy/reservations/{rr["id"]}/dispense',{},rre,key('denied-revoked-dispense'),(409,))
    released=create('revalidate',pharmacist,'POST',f'/api/v1/pharmacy/reservations/{rr["id"]}/revalidate',{},rre,(200,))
    assert released['state']=='released'
    _,rre,_=pharmacist.call('GET','/api/v1/pharmacy/reservations/'+rr['id'])
    again=create('revalidate-again',pharmacist,'POST',f'/api/v1/pharmacy/reservations/{rr["id"]}/revalidate',{},rre,(200,))
    assert again['state']=='released'
    inv,_,_=pharmacist.call('GET','/api/v1/pharmacy/inventory?medicine_id='+medicine['id'])
    assert inv['items'][0]['on_hand']==8 and inv['items'][0]['reserved']==0
    checked('revocation_revalidation_releases_unfilled_stock_once')
    for path in ['/api/v1/patients/me','/api/v1/doctors','/api/v1/appointments','/api/v1/records/prescriptions','/api/v1/pharmacy/reservations','/api/v1/billing/invoices','/api/v1/emergencies']:
        require(httpx.get(base+path,trust_env=False),(401,))
    checked('all_seven_domains_reject_unauthenticated_access')
    print('COMPLETE',len(state['checks']),'real HTTP workflow groups; private fixture retained for browser verification',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://127.0.0.1:8080')
    parser.add_argument('--fixture',type=Path,default=Path('/tmp/pulsegrid-phase29-live-fixture.json'))
    args=parser.parse_args();verify(args.base_url,args.fixture)
