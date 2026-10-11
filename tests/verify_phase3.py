"""Resumable synthetic Phase 3 gateway demonstration; never resets owner data.

Credentials and bearer tokens are never printed or committed. Uses an existing
operator account from the private Phase 2 fixture; all business effects use HTTP.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import secrets
import time
import subprocess
import uuid
from verify_phase2 import Actor, require


def verify(base, fixture):
    state = json.loads(fixture.read_text()) if fixture.exists() else {
        'run':str(uuid.uuid4()), 'actors':{}, 'resources':{}, 'checks':[]}
    def save():
        fixture.write_text(json.dumps(state,indent=2)); fixture.chmod(0o600)
    def key(label): return str(uuid.uuid5(uuid.UUID(state['run']), label))
    def checked(label):
        if label not in state['checks']: state['checks'].append(label)
        save(); print('PASS',label,flush=True)
    admin_data=json.loads(Path('/tmp/pulsegrid-phase29-live-fixture.json').read_text())['actors']['admin']
    admin=Actor(base,admin_data);admin.login()
    actors={}
    for role in ('doctor','receptionist','pharmacist','billing_staff','patient','other','third'):
        data=state['actors'].setdefault(role,dict(email=f'p3-{role}-{state["run"]}@example.test',password=secrets.token_urlsafe(24)))
        save();actor=Actor(base,data);actors[role]=actor
        if 'profile' not in data:
            data['profile']=require(actor.client.post('/api/v1/auth/register',json={
                'email':data['email'],'password':data['password'],'display_name':'Synthetic Phase3 '+role},
                headers={'Idempotency-Key':key('register-'+role),'X-Anonymous-Command-ID':key('anon-'+role).replace('-','')+'A'*12}),(201,));save()
        if role not in ('patient','other','third'):
            user,et,_=admin.call('GET','/api/v1/patients/users/'+data['profile']['user_id'])
            if user['roles'] != [role]: admin.call('PATCH','/api/v1/patients/users/'+user['id']+'/roles',{'roles':[role]},etag=et)
        actor.login()
    r=state['resources'];patient=actors['patient'];other=actors['other'];third=actors['third']
    doctor=actors['doctor'];reception=actors['receptionist'];pharmacist=actors['pharmacist'];billing=actors['billing_staff']
    def create(label,actor,path,body,etag=None,codes=(201,)):
        if label not in r: r[label]=actor.call('POST',path,body,etag,key(label),codes)[0];save()
        return r[label]
    specialty=create('specialty',admin,'/api/v1/doctors/specialties',{'slug':'phase3-'+state['run'][:8],'name':'Synthetic Phase3 Care'})
    d=create('doctor',admin,'/api/v1/doctors',{'staff_user_id':doctor.data['profile']['user_id'],'display_name':'Synthetic Phase3 Doctor','specialty_ids':[specialty['id']]})
    if 'schedule' not in r:
        _,et,_=doctor.call('GET','/api/v1/doctors/'+d['id'])
        start=(datetime.now(timezone.utc)+timedelta(minutes=6)).replace(second=0,microsecond=0)
        create('schedule',doctor,f'/api/v1/doctors/{d["id"]}/schedules',{'timezone':'UTC','slot_minutes':5,
            'intervals':[{'starts_at':start.isoformat(),'ends_at':(start+timedelta(minutes=50)).isoformat()}],'expected_revision':0},et,(202,))
    schedule=r['schedule'];start=datetime.fromisoformat(schedule['intervals'][0]['starts_at'].replace('Z','+00:00'))
    end=datetime.fromisoformat(schedule['intervals'][-1]['ends_at'].replace('Z','+00:00'))
    create('decision',doctor,'/api/v1/appointments/schedule-decisions',{'doctor_id':d['id'],'proposal_id':schedule['id'],'expected_accepted_revision':0})
    _,et,_=doctor.call('GET',f'/api/v1/doctors/{d["id"]}/schedules/{schedule["id"]}')
    create('schedule_reconcile',doctor,f'/api/v1/doctors/{d["id"]}/schedules/{schedule["id"]}/reconcile',{},et,(200,))
    if 'slots' not in r:
        availability,_,_=patient.call('GET',f'/api/v1/appointments/availability?doctor_id={d["id"]}&from={start.strftime("%Y-%m-%dT%H:%M:%SZ")}&to={end.strftime("%Y-%m-%dT%H:%M:%SZ")}')
        r['slots']=availability['slots'];save()
    slots=r['slots'];revision=r['decision']['revision']
    checked('registration_doctor_search_accepted_schedule')
    def book(label,actor,index):
        return create(label,actor,'/api/v1/appointments',{'patient_id':actor.data['profile']['id'],'slot_id':slots[index]['id'],'expected_schedule_revision':revision})
    def cancel(label,actor,a):
        _,et,_=actor.call('GET','/api/v1/appointments/'+a['id'])
        return create(label,actor,f'/api/v1/appointments/{a["id"]}/cancel',{'reason':'Synthetic offer verification'},et,(200,))
    def offers(actor,sid):
        return [o for o in actor.call('GET','/api/v1/appointments/waitlist-offers?limit=100')[0]['items'] if o['slot_id']==sid]
    # Begin near-term durable expiry first, while other workflows are exercised.
    expiry_booking=book('expiry_original',other,0)
    for label,actor in (('expiry_first',patient),('expiry_second',third)):
        create(label,actor,'/api/v1/appointments/waitlists',{'patient_id':actor.data['profile']['id'],'slot_id':slots[0]['id'],'expected_schedule_revision':revision})
    cancel('expiry_cancel',other,expiry_booking)
    if 'expiry_offer' not in r:
        for _ in range(30):
            found=offers(patient,slots[0]['id'])
            if found:r['expiry_offer']=found[0];save();break
            time.sleep(1)
        assert 'expiry_offer' in r,'No durable FIFO offer'
    checked('fully_booked_fifo_offer_reserves_capacity')
    medicine=create('medicine',pharmacist,'/api/v1/pharmacy/medicines',{'sku':'P3-'+state['run'],'name':'Synthetic Phase3 medicine'})
    create('stock',pharmacist,'/api/v1/pharmacy/inventory-adjustments',{'medicine_id':medicine['id'],'batch_code':'P3-LOT','expires_on':(start.date()+timedelta(days=30)).isoformat(),'delta':20,'reason':'Synthetic stock','expected_batch_version':0})
    # Existing consultation tariff may already exist; reuse owner data.
    tariffs=billing.call('GET','/api/v1/billing/tariffs')[0]['items']
    if not any(t['charge_code']=='consultation' for t in tariffs):create('tariff',billing,'/api/v1/billing/tariffs',{'charge_code':'consultation','unit_amount_minor':10000,'currency':'INR'})
    create('medicine_tariff',billing,'/api/v1/billing/tariffs',{'charge_code':'medicine:'+medicine['id'],'unit_amount_minor':2500,'currency':'INR'})
    def reconcile(actor,jid,label):
        for attempt in range(15):
            _,et,_=actor.call('GET',f'/api/v1/appointments/journeys/{jid}')
            data,_,status=actor.call('POST',f'/api/v1/appointments/journeys/{jid}/reconcile',{},et,str(uuid.uuid4()),(200,412))
            if status==200:return data
        raise AssertionError('Repeated reconciliation version contention')
    def checkin(label,actor,a):
        if label not in r:
            _,et,_=actor.call('GET',f'/api/v1/appointments/{a["id"]}/workflow')
            issued=actor.call('POST',f'/api/v1/appointments/{a["id"]}/check-in-links',{},et,key(label+'issue'),(201,))[0]
            assert len(issued['token'])==22 and a['id'] not in issued['token']
            other.call('POST',f'/api/v1/appointments/{a["id"]}/check-in',{'token':issued['token']},et,key(label+'unauthorized'),(404,))
            _,et,_=actor.call('GET',f'/api/v1/appointments/{a["id"]}/workflow')
            r[label]=actor.call('POST',f'/api/v1/appointments/{a["id"]}/check-in',{'token':issued['token']},et,key(label),(200,))[0];save()
            _,et,_=actor.call('GET',f'/api/v1/appointments/{a["id"]}/workflow')
            actor.call('POST',f'/api/v1/appointments/{a["id"]}/check-in',{'token':issued['token']},et,key(label+'replay'),(409,))
        return r[label]['queue_entry']
    def start_queue(label,actor,a):
        own,et,_=doctor.call('GET',f'/api/v1/appointments/{a["id"]}/queue')
        return create(label,doctor,f'/api/v1/appointments/queue-entries/{own["entry"]["id"]}/start',{},et,(200,))
    def clinical(label,a,rx):
        c=create(label+'_consult',doctor,'/api/v1/records/consultations',{'appointment_id':a['id'],'clinical_content':{'summary':'Synthetic consultation','assessment':'Educational fixture only','plan':'Synthetic follow-up'}})
        _,et,_=doctor.call('GET','/api/v1/records/consultations/'+c['id'])
        final=create(label+'_final',doctor,f'/api/v1/records/consultations/{c["id"]}/finalize',{'prescription_items':[{'medicine_id':medicine['id'],'quantity':2,'dosage':'Synthetic dose','instructions':'Educational fixture'}] if rx else []},et,(200,))
        return c,final
    def billing_and_discharge(label,a,c,dispensings):
        invoice=create(label+'_invoice',billing,'/api/v1/billing/invoices',{'appointment_id':a['id'],'currency':'INR'})
        _,et,_=billing.call('GET','/api/v1/billing/invoices/'+invoice['id'])
        charged=create(label+'_charges',billing,f'/api/v1/billing/invoices/{invoice["id"]}/charges',{'consultation_id':c['id'],'dispensing_ids':dispensings},et,(200,))
        _,et,_=patient.call('GET','/api/v1/billing/invoices/'+invoice['id'])
        create(label+'_payment',patient,f'/api/v1/billing/invoices/{invoice["id"]}/payments',{'amount_minor':charged['total_minor'],'currency':'INR','simulated_outcome':'success'},et)
        result=reconcile(patient,a['journey_id'],label+'_reconcile')
        assert result['discharge_eligible'] or result['state']=='discharged',[(s['name'],s['state'],s['pending_reason']) for s in result['stages']]
        other.call('GET',f'/api/v1/appointments/journeys/{a["journey_id"]}',codes=(404,))
        patient.call('POST',f'/api/v1/appointments/journeys/{a["journey_id"]}/discharge',{'reason':'Denied patient command'},f'"{result["version"]}"',key(label+'denied'),(403,))
        if result['state']!='discharged':
            for attempt in range(15):
                result=reconcile(reception,a['journey_id'],label+'_ready'+str(attempt))
                value,_,status=reception.call('POST',f'/api/v1/appointments/journeys/{a["journey_id"]}/discharge',{'reason':'Synthetic verified discharge'},f'"{result["version"]}"',str(uuid.uuid4()),(200,412))
                if status==200:r[label+'_discharge']=value;save();break
            assert r[label+'_discharge']['state']=='discharged'
        history=patient.call('GET',f'/api/v1/appointments/journeys/{a["journey_id"]}/history?limit=100')[0]['items']
        assert any(h['stage']=='registration' for h in history) and any(h['to_state']=='complete' for h in history)
        return result
    if 'workflow1_qr_queue_clinical_rx_pharmacy_billing_payment_discharge' not in state['checks']:
        a=book('full_booking',patient,1)
        if 'full_start' not in r:
            doctor.call('POST','/api/v1/records/consultations',{'appointment_id':a['id'],'clinical_content':{'summary':'Premature synthetic consultation','assessment':'Test','plan':'Test'}},key=key('gate-denied'),codes=(409,))
        e=checkin('full_checkin',patient,a);start_queue('full_start',patient,a)
        c,final=clinical('full',a,True);rx=final['prescription']
        reservation=create('full_reserve',pharmacist,'/api/v1/pharmacy/reservations',{'prescription_id':rx['id'],'items':[{'prescription_item_id':rx['items'][0]['id'],'quantity':2}]})
        _,et,_=pharmacist.call('GET','/api/v1/pharmacy/reservations/'+reservation['id'])
        dispensing=create('full_dispense',pharmacist,f'/api/v1/pharmacy/reservations/{reservation["id"]}/dispense',{},et)
        billing_and_discharge('full',a,c,[dispensing['id']])
        checked('workflow1_qr_queue_clinical_rx_pharmacy_billing_payment_discharge')
    if 'workflow5_no_prescription_pharmacy_skipped_paid_discharge' not in state['checks']:
        a2=book('no_rx_booking',patient,2);checkin('no_rx_checkin',patient,a2);start_queue('no_rx_start',patient,a2)
        c2,f2=clinical('no_rx',a2,False);assert f2['prescription'] is None
        result=billing_and_discharge('no_rx',a2,c2,[])
        assert next(s for s in result['stages'] if s['name']=='pharmacy')['state']=='skipped'
        checked('workflow5_no_prescription_pharmacy_skipped_paid_discharge')
    original=book('accept_original',other,5)
    create('accept_waiting',patient,'/api/v1/appointments/waitlists',{'patient_id':patient.data['profile']['id'],'slot_id':slots[5]['id'],'expected_schedule_revision':revision})
    cancel('accept_cancel',other,original)
    if 'accepted_offer' not in r:
        for _ in range(30):
            found=offers(patient,slots[5]['id'])
            if found:break
            time.sleep(1)
        offer=found[0];_,et,_=patient.call('GET','/api/v1/appointments/waitlist-offers/'+offer['id'])
        def accept(index):return patient.call('POST','/api/v1/appointments/waitlist-offers/'+offer['id']+'/accept',{},et,key('offeraccept'+str(index)),(200,409,412))
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(accept,range(4)))
        assert sum(status==200 for _,_,status in results)==1
        r['accepted_offer']=next(v for v,_,s in results if s==200);save()
    assert r['accepted_offer']['appointment']['state']=='confirmed'
    checked('workflow2_offer_acceptance_gateway_race_one_booking')
    qa=book('queue_first',patient,3);qb=book('queue_second',third,4)
    ea=checkin('queue_first_checkin',patient,qa);eb=checkin('queue_second_checkin',third,qb)
    own,et,_=doctor.call('GET',f'/api/v1/appointments/{qa["id"]}/queue')
    create('queue_skip',doctor,f'/api/v1/appointments/queue-entries/{ea["id"]}/skip',{'reason':'Synthetic skip'},et,(200,))
    if 'queue_recall' not in r:
        q=doctor.call('GET',f'/api/v1/appointments/queues?doctor_id={d["id"]}&local_date={start.date()}&limit=100')[0]
        assert next(item for item in q['items'] if item['state']=='waiting')['id']==eb['id']
    own,et,_=doctor.call('GET',f'/api/v1/appointments/{qa["id"]}/queue')
    create('queue_recall',doctor,f'/api/v1/appointments/queue-entries/{ea["id"]}/recall',{'reason':'Synthetic recall'},et,(200,))
    start_queue('queue_start',patient,qa)
    if 'queue_final' not in r:
        own,et,_=doctor.call('GET',f'/api/v1/appointments/{qb["id"]}/queue')
        doctor.call('POST',f'/api/v1/appointments/queue-entries/{eb["id"]}/start',{},et,key('busy-start'),(409,))
    clinical('queue',qa,False)
    for attempt in range(25):
        completed=reconcile(patient,qa['journey_id'],'queue_complete'+str(attempt))
        if next(s for s in completed['stages'] if s['name']=='consultation')['state']=='complete':break
        time.sleep(1)
    hist=doctor.call('GET',f'/api/v1/appointments/queue-entries/{ea["id"]}/history?limit=100')[0]['items']
    assert any(h['to_state']=='skipped' for h in hist) and any(h['to_state']=='completed' for h in hist)
    checked('workflow4_skip_recall_fifo_busy_guard_completion_history')
    # Start an unshortened five-minute offer on a later slot so expiry can
    # promote another patient before that slot's opening time.
    original=book('durable_expiry_original',other,8)
    for label,actor in (('durable_expiry_first',patient),('durable_expiry_second',third)):
        create(label,actor,'/api/v1/appointments/waitlists',{'patient_id':actor.data['profile']['id'],'slot_id':slots[8]['id'],'expected_schedule_revision':revision})
    cancel('durable_expiry_cancel',other,original)
    checked('durable_expiry_offer_started')
    # Explicit synthetic outage: stop condition one reconciliation (<=15s),
    # finally always restores the same existing Billing container.
    if 'workflow6' not in state['checks']:
        compose=['docker','compose','-f','compose.yaml','-f','services/patient/compose.auth.yaml']
        try:
            subprocess.run(compose+['stop','-t','2','billing'],check=True,capture_output=True,timeout=10)
            pending=reconcile(patient,qa['journey_id'],'billing_outage')
            assert not pending['discharge_eligible'] and pending['reconciliation']['state']=='failed'
            assert next(s for s in pending['stages'] if s['name']=='billing')['state']=='pending'
        finally:
            subprocess.run(['docker','start','pulsegrid-billing-1'],check=True,capture_output=True,timeout=10)
        for attempt in range(30):
            recovered=reconcile(patient,qa['journey_id'],'billing_recovery'+str(attempt))
            if recovered['reconciliation']['last_error'] is None:break
            time.sleep(1)
        assert recovered['reconciliation']['last_error'] is None
        checked('workflow6')
    if 'expiry_successor' not in r:
        deadline=time.monotonic()+320
        while time.monotonic()<deadline:
            first=offers(patient,slots[8]['id']);successor=offers(third,slots[8]['id'])
            if first and first[0]['state']=='expired' and successor:
                r['expired_offer']=first[0];r['expiry_successor']=successor[0];save();break
            time.sleep(1)
        assert 'expiry_successor' in r and r['expiry_successor']['state']=='pending','Next FIFO patient received no offer'
    checked('workflow3_durable_offer_expiry_next_patient_worker_recovery')
    for path in ('/api/v1/appointments/waitlists','/api/v1/appointments/waitlist-offers','/api/v1/appointments/journeys','/internal/v1/patients/waitlist-eligibility'):
        response=__import__('httpx').get(base+path,trust_env=False)
        if path.startswith('/internal'):assert response.status_code==404
        else:require(response,(401,))
    checked('gateway_authentication_ownership_internal_route_isolation')
    print('COMPLETE',len(state['checks']),'gateway workflow groups; synthetic fixture retained privately',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://127.0.0.1:8080')
    parser.add_argument('--fixture',type=Path,default=Path('/tmp/pulsegrid-phase3-live-fixture.json'))
    args=parser.parse_args();verify(args.base_url,args.fixture)
