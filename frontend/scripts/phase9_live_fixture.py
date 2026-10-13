"""Create isolated synthetic Phase 9 browser data through existing owner HTTP APIs.

Uses the retained approved operator fixture. Never resets databases, edits a
retained appointment, starts containers, or prints credentials. Private state
is held outside Git with mode 0600. Re-running reuses the same command keys.
"""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import argparse
import json
import secrets
import sys
import uuid
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests'))
from verify_phase2 import Actor, require

def seed(base,fixture):
    state=json.loads(fixture.read_text()) if fixture.exists() else {'run':str(uuid.uuid4()),'actors':{},'resources':{},'checks':[]}
    def save():
        fixture.write_text(json.dumps(state,indent=2));fixture.chmod(0o600)
    def key(label):return str(uuid.uuid5(uuid.UUID(state['run']),label))
    original=json.loads(Path('/tmp/pulsegrid-phase29-live-fixture.json').read_text())['actors']
    p3=json.loads(Path('/tmp/pulsegrid-phase3-live-fixture.json').read_text())['actors']
    for role in ['admin','pharmacist','billing_staff','emergency_staff']:
        state['actors'].setdefault(role,original[role])
    state['actors'].setdefault('receptionist',p3['receptionist'])
    admin=Actor(base,state['actors']['admin']);admin.login()
    actors={}
    for role in ['doctor','patient']:
        data=state['actors'].setdefault(role,{'email':f'p9-{role}-{state["run"]}@example.test','password':secrets.token_urlsafe(28)})
        save();actor=Actor(base,data);actors[role]=actor
        if 'profile' not in data:
            data['profile']=require(actor.client.post('/api/v1/auth/register',json={'email':data['email'],'password':data['password'],'display_name':'Synthetic Phase 9 '+role.title()},headers={'Idempotency-Key':key('register-'+role),'X-Anonymous-Command-ID':secrets.token_urlsafe(32)}),(201,));save()
        if role=='doctor':
            user,etag,_=admin.call('GET','/api/v1/patients/users/'+data['profile']['user_id'])
            if user['roles']!=['doctor']:admin.call('PATCH','/api/v1/patients/users/'+user['id']+'/roles',{'roles':['doctor']},etag=etag)
        actor.login()
    r=state['resources'];doctor=actors['doctor'];patient=actors['patient']
    def create(label,actor,path,body,etag=None,codes=(201,)):
        if label not in r:r[label]=actor.call('POST',path,body,etag,key(label),codes)[0];save()
        return r[label]
    specialty=create('specialty',admin,'/api/v1/doctors/specialties',{'slug':'phase9-'+state['run'][:8],'name':'Synthetic Phase 9 Care'})
    d=create('doctor',admin,'/api/v1/doctors',{'staff_user_id':doctor.data['profile']['user_id'],'display_name':'Synthetic Phase 9 Doctor','specialty_ids':[specialty['id']]})
    if 'schedule' not in r:
        _,etag,_=doctor.call('GET','/api/v1/doctors/'+d['id'])
        start=(datetime.now(timezone.utc)+timedelta(minutes=20)).replace(second=0,microsecond=0)
        create('schedule',doctor,f'/api/v1/doctors/{d["id"]}/schedules',{'timezone':'UTC','slot_minutes':5,'intervals':[{'starts_at':start.isoformat(),'ends_at':(start+timedelta(minutes=60)).isoformat()}],'expected_revision':0},etag,(202,))
    schedule=r['schedule']
    create('decision',doctor,'/api/v1/appointments/schedule-decisions',{'doctor_id':d['id'],'proposal_id':schedule['id'],'expected_accepted_revision':0})
    _,etag,_=doctor.call('GET',f'/api/v1/doctors/{d["id"]}/schedules/{schedule["id"]}')
    create('reconciled',doctor,f'/api/v1/doctors/{d["id"]}/schedules/{schedule["id"]}/reconcile',{},etag,(200,))
    start=datetime.fromisoformat(schedule['intervals'][0]['starts_at'].replace('Z','+00:00'));end=datetime.fromisoformat(schedule['intervals'][-1]['ends_at'].replace('Z','+00:00'))
    availability,_,_=patient.call('GET',f'/api/v1/appointments/availability?doctor_id={d["id"]}&from={start.strftime("%Y-%m-%dT%H:%M:%SZ")}&to={end.strftime("%Y-%m-%dT%H:%M:%SZ")}')
    r['slots']=availability['slots'];save()
    pharmacist=Actor(base,state['actors']['pharmacist']);pharmacist.login()
    billing=Actor(base,state['actors']['billing_staff']);billing.login()
    med=create('medicine',pharmacist,'/api/v1/pharmacy/medicines',{'sku':'P9-'+state['run'][:8],'name':'Synthetic Phase 9 medicine'})
    create('stock',pharmacist,'/api/v1/pharmacy/inventory-adjustments',{'medicine_id':med['id'],'batch_code':'P9-LOT','expires_on':(start.date()+timedelta(days=30)).isoformat(),'delta':20,'reason':'Synthetic Phase 9 UI verification','expected_batch_version':0})
    create('tariff',billing,'/api/v1/billing/tariffs',{'charge_code':'medicine:'+med['id'],'unit_amount_minor':2500,'currency':'INR'})
    for label in ['isolated synthetic registration','role-authorized doctor profile','accepted future slots','synthetic medicine stock and tariff']:
        if label not in state['checks']:state['checks'].append(label)
    save()
    print(json.dumps({'doctor_id':d['id'],'patient_id':patient.data['profile']['id'],'medicine_id':med['id'],'from':start.isoformat(),'to':end.isoformat(),'slots':len(r['slots'])}))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--base-url',default='http://127.0.0.1:5173');parser.add_argument('--fixture',type=Path,default=Path('/tmp/pulsegrid-phase9-live-fixture.json'));a=parser.parse_args();seed(a.base_url,a.fixture)
