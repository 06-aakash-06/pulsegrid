"""Non-destructive fictional local demo via owner APIs. Credentials stay private.
Run only against loopback development; retained data is never edited/deleted.
"""
from pathlib import Path
from datetime import datetime,timedelta,timezone
import json,secrets,sys,uuid,time
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests'))
from verify_phase2 import Actor,require
BASE='http://127.0.0.1:8080'
assert urlparse(BASE).hostname in ('localhost','127.0.0.1')
private=Path('/tmp/pulsegrid-phase9-fictional-demo.json')
state=json.loads(private.read_text()) if private.exists() else {'run':str(uuid.uuid4()),'actors':{},'resources':{}}
if state.get('demo_complete'):
    print(json.dumps({'status':'Existing completed fictional demo retained; no writes performed','private_fixture':str(private)}));sys.exit(0)
def save():private.write_text(json.dumps(state,indent=2));private.chmod(0o600)
def key(label):return str(uuid.uuid5(uuid.UUID(state['run']),label))
admin=Actor(BASE,json.loads(Path('/tmp/pulsegrid-phase29-live-fixture.json').read_text())['actors']['admin']);admin.login()
def create(label,actor,path,body,etag=None,codes=(201,)):
    if label not in state['resources']:
        state['resources'][label]=actor.call('POST',path,body,etag,key(label),codes)[0];save()
    return state['resources'][label]
def account(label,name,roles):
    data=state['actors'].setdefault(label,{'email':f'demo-{label}-{state["run"][:8]}@example.test','password':secrets.token_urlsafe(28)})
    save();a=Actor(BASE,data)
    if 'profile' not in data:
        headers={'Idempotency-Key':key('account-'+label),'X-Anonymous-Command-ID':data.setdefault('anonymous_command',secrets.token_urlsafe(32))};save()
        for attempt in range(8):
            response=a.client.post('/api/v1/auth/register',json={'email':data['email'],'password':data['password'],'display_name':name},headers=headers)
            if response.status_code!=429:break
            delay=min(60,max(1,int(response.headers.get('Retry-After','30'))));print('Registration admission limited; honoring retry deadline.',flush=True);time.sleep(delay)
        data['profile']=require(response,(201,));save()
    u,etag,_=admin.call('GET','/api/v1/patients/users/'+data['profile']['user_id'])
    if sorted(u['roles'])!=sorted(roles):admin.call('PATCH','/api/v1/patients/users/'+u['id']+'/roles',{'roles':roles},etag=etag)
    a.login();return a
people=[('Dr. Ananya Mehta','Cardiology'),('Dr. Rohan Shah','General Medicine'),('Dr. Priya Nair','Pediatrics'),('Dr. Arjun Iyer','Orthopaedics'),('Dr. Sneha Kulkarni','Dermatology'),('Dr. Vikram Rao','ENT')]
operator=account('operator','Anika Shah',['patient','hospital_admin','receptionist'])
manifest={'label':'Fictional demo hospital','doctors':{},'patients':{},'appointments':{},'specialties':[]}
for i,(name,spec) in enumerate(people):
    a=account('doctor'+str(i),name,['doctor'])
    specialty=create('specialty'+str(i),admin,'/api/v1/doctors/specialties',{'slug':'demo-'+spec.lower().replace(' ','-')+'-'+state['run'][:8],'name':spec})
    manifest['specialties'].append(specialty['id'])
    d=create('doctor'+str(i),admin,'/api/v1/doctors',{'staff_user_id':a.data['profile']['user_id'],'display_name':name,'specialty_ids':[specialty['id']]})
    if 'schedule'+str(i) not in state['resources']:
        _,etag,_=a.call('GET','/api/v1/doctors/'+d['id'])
        start=(datetime.now(timezone.utc)+timedelta(hours=2)).replace(minute=0,second=0,microsecond=0)
        create('schedule'+str(i),a,f'/api/v1/doctors/{d["id"]}/schedules',{'timezone':'UTC','slot_minutes':30,'intervals':[{'starts_at':start.isoformat(),'ends_at':(start+timedelta(hours=5)).isoformat()},{'starts_at':(start+timedelta(days=1)).isoformat(),'ends_at':(start+timedelta(days=1,hours=5)).isoformat()}],'expected_revision':0},etag,(202,))
    sch=state['resources']['schedule'+str(i)]
    create('decision'+str(i),a,'/api/v1/appointments/schedule-decisions',{'doctor_id':d['id'],'proposal_id':sch['id'],'expected_accepted_revision':0})
    _,etag,_=a.call('GET',f'/api/v1/doctors/{d["id"]}/schedules/{sch["id"]}')
    create('reconcile'+str(i),a,f'/api/v1/doctors/{d["id"]}/schedules/{sch["id"]}/reconcile',{},etag,(200,))
    manifest['doctors'][d['id']]={'portrait':i,'label':f'D{i+1:03d}'}
    pat=operator if i==0 else account('patient'+str(i),['Anika Shah','Kavya Raman','Dev Menon','Priya Sen','Arjun Kumar','Neha Roy'][i],['patient'])
    manifest['patients'][pat.data['profile']['id']]={'name':pat.data['profile']['display_name'],'label':f'P{i+1:03d}'}
    interval=sch['intervals'][0];availability,_,_=pat.call('GET',f'/api/v1/appointments/availability?doctor_id={d["id"]}&from={interval["starts_at"]}&to={interval["ends_at"]}')
    if 'appointment'+str(i) not in state['resources']:
        slot=availability['slots'][i%len(availability['slots'])]
        create('appointment'+str(i),pat,'/api/v1/appointments',{'patient_id':pat.data['profile']['id'],'slot_id':slot['id'],'expected_schedule_revision':availability['accepted_revision']})
    appointment=state['resources']['appointment'+str(i)]
    manifest['appointments'][appointment['id']]={'label':f'A{i+28:03d}'}
# Add a near-term accepted interval to this run's new doctor only, retaining all booked intervals.
a=Actor(BASE,state['actors']['doctor0']);a.login();d=state['resources']['doctor0'];sch=state['resources']['schedule0']
if 'near-schedule' not in state['resources']:
    start=(datetime.now(timezone.utc)+timedelta(minutes=10)).replace(second=0,microsecond=0)
    _,etag,_=a.call('GET','/api/v1/doctors/'+d['id'])
    intervals=sorted(sch['intervals']+[{'starts_at':start.isoformat(),'ends_at':(start+timedelta(minutes=30)).isoformat()}],key=lambda x:x['starts_at'])
    create('near-schedule',a,f'/api/v1/doctors/{d["id"]}/schedules',{'timezone':'UTC','slot_minutes':30,'intervals':intervals,'expected_revision':1},etag,(202,))
near=state['resources']['near-schedule']
create('near-decision',a,'/api/v1/appointments/schedule-decisions',{'doctor_id':d['id'],'proposal_id':near['id'],'expected_accepted_revision':1})
_,etag,_=a.call('GET',f'/api/v1/doctors/{d["id"]}/schedules/{near["id"]}')
create('near-reconciled',a,f'/api/v1/doctors/{d["id"]}/schedules/{near["id"]}/reconcile',{},etag,(200,))
interval=near['intervals'][0]
if 'near-appointment' not in state['resources']:
    available,_,_=operator.call('GET',f'/api/v1/appointments/availability?doctor_id={d["id"]}&from={interval["starts_at"]}&to={interval["ends_at"]}')
    slot=available['slots'][0]
    create('near-appointment',operator,'/api/v1/appointments',{'patient_id':operator.data['profile']['id'],'slot_id':slot['id'],'expected_schedule_revision':available['accepted_revision']})
app=state['resources']['near-appointment'];manifest['appointments'][app['id']]={'label':'A034'}
if 'qr-redeemed' not in state['resources']:
    _,etag,_=operator.call('GET','/api/v1/appointments/'+app['id']+'/workflow')
    token=create('qr',operator,'/api/v1/appointments/'+app['id']+'/check-in-links',{},etag)
    _,workflow_etag,_=operator.call('GET','/api/v1/appointments/'+app['id']+'/workflow')
    create('qr-redeemed',operator,'/api/v1/appointments/'+app['id']+'/check-in',{'token':token['token']},workflow_etag,(200,))
# Real catalog examples, with stock controlled by Pharmacy; no React records.
pharmacist=Actor(BASE,json.loads(Path('/tmp/pulsegrid-phase29-live-fixture.json').read_text())['actors']['pharmacist']);pharmacist.login()
for i,name in enumerate(['Paracetamol 650 mg','Pantoprazole 40 mg','Cetirizine 10 mg']):
    med=create('medicine'+str(i),pharmacist,'/api/v1/pharmacy/medicines',{'sku':f'DEMO-{i+1:03d}-{state["run"][:8]}','name':name})
    create('stock'+str(i),pharmacist,'/api/v1/pharmacy/inventory-adjustments',{'medicine_id':med['id'],'batch_code':'DEMO-LOT','expires_on':(datetime.now(timezone.utc).date()+timedelta(days=180)).isoformat(),'delta':100,'reason':'Fictional local demonstration','expected_batch_version':0})
state['demo_complete']=True;save()
folder=ROOT/'frontend/.demo';folder.mkdir(exist_ok=True)
(folder/'hospital.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps({'doctors':len(manifest['doctors']),'specialties':len(manifest['specialties']),'patients':len(manifest['patients']),'appointments':len(manifest['appointments']),'private_fixture':str(private)}))
