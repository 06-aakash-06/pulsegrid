"""Prepare resumable fictional Phase 10 fixtures in the verified audit project only.

Credentials remain in ignored secrets/phase10/. No retained database is touched.
"""
from pathlib import Path
from datetime import datetime,timedelta,timezone
import sys,json,secrets,uuid,time,subprocess
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests'))
from verify_phase2 import Actor,require
BASE='http://127.0.0.1:18880';PROJECT='pulsegrid-audit-20261025'

def isolated():
 ids=subprocess.check_output(['docker','ps','-aq','--filter','label=com.docker.compose.project='+PROJECT],text=True).split()
 assert ids,'Preserved isolated project not found'
 own=json.loads(subprocess.check_output(['docker','inspect',*ids]));foreign_ids=subprocess.check_output(['docker','ps','-aq','--filter','label=com.docker.compose.project=pulsegrid'],text=True).split();foreign=json.loads(subprocess.check_output(['docker','inspect',*foreign_ids]))
 volumes=lambda xs:{m['Name']for x in xs for m in x['Mounts']if m['Type']=='volume'}
 assert not volumes(own)&volumes(foreign)
 assert all(not m.get('RW')for x in own for m in x['Mounts']if m['Type']=='bind')
 assert all(n.startswith(PROJECT+'_')for x in own for n in x['NetworkSettings']['Networks'])

class AcceptanceActor(Actor):
 def login(self):
  csrf=require(self.client.get('/api/v1/auth/csrf'))['csrf_token']
  for attempt in range(20):
   response=self.client.post('/api/v1/auth/login',json={'email':self.data['email'],'password':self.data['password']},headers={'X-CSRF-Token':csrf})
   if response.status_code!=429:break
   time.sleep(min(30,float(response.headers.get('Retry-After','2'))))
  self.token=require(response)['access_token']

 def call(self,method,path,body=None,etag=None,key=None,codes=(200,)):
  time.sleep(.2)
  for attempt in range(4):
   headers={'Authorization':'Bearer '+self.token}
   if etag is not None:headers['If-Match']=etag
   if key is not None:headers['Idempotency-Key']=key
   response=self.client.request(method,path,json=body,headers=headers)
   if response.status_code!=429 or 429 in codes:break
   time.sleep(min(5,float(response.headers.get('Retry-After','1'))))
  return require(response,codes),response.headers.get('etag'),response.status_code

def main():
 isolated();private=ROOT/'secrets/phase10';private.mkdir(mode=0o700,parents=True,exist_ok=True);fixture=private/'fixture.json';state=json.loads(fixture.read_text())if fixture.exists()else {'run':str(uuid.uuid4()),'actors':{},'resources':{},'checks':[]}
 def save():fixture.write_text(json.dumps(state,indent=2));fixture.chmod(0o600)
 def key(label):return str(uuid.uuid5(uuid.UUID(state['run']),label))
 operator=AcceptanceActor(BASE,json.loads((ROOT/'secrets/final-audit/admin.json').read_text())['actors']['admin']);operator.login();actors={}
 for role in ('patient','other','third','doctor','alternate_doctor','receptionist','pharmacist','billing_staff','emergency_staff','hospital_admin','ops'):
  data=state['actors'].setdefault(role,{'email':f'p10-{role}-{state["run"]}@example.test','password':secrets.token_urlsafe(24)})
  save();a=AcceptanceActor(BASE,data);actors[role]=a
  if 'profile'not in data:
   for attempt in range(12):
    time.sleep(.5)
    response=a.client.post('/api/v1/auth/register',json={'email':data['email'],'password':data['password'],'display_name':'Phase10 Fictional '+role},headers={'Idempotency-Key':key('register-'+role),'X-Anonymous-Command-ID':key('anon-'+role).replace('-','')+'A'*12})
    if response.status_code!=429:break
    time.sleep(min(30,float(response.headers.get('Retry-After','2'))))
   data['profile']=require(response,(201,));save()
  if role not in ('patient','other','third'):
   user,et,_=operator.call('GET','/api/v1/patients/users/'+data['profile']['user_id']);expected='doctor'if role=='alternate_doctor'else role
   if user['roles']!=[expected]:operator.call('PATCH','/api/v1/patients/users/'+user['id']+'/roles',{'roles':[expected]},et)
  a.login()
 r=state['resources']
 def create(label,a,path,body,etag=None,codes=(201,)):
  if label not in r:r[label]=a.call('POST',path,body,etag,key(label),codes)[0];save()
  return r[label]
 specialty=create('specialty',operator,'/api/v1/doctors/specialties',{'slug':'phase10-'+state['run'][:8],'name':'Phase10 Acceptance Care'})
 for role in ('doctor','alternate_doctor'):
  create(role,operator,'/api/v1/doctors',{'staff_user_id':actors[role].data['profile']['user_id'],'display_name':'Phase10 Acceptance '+role.replace('_',' '),'specialty_ids':[specialty['id']]})
 d=r['doctor'];doctor=actors['doctor']
 if 'schedule'not in r:
  _,et,_=doctor.call('GET','/api/v1/doctors/'+d['id']);start=(datetime.now(timezone.utc)+timedelta(minutes=10)).replace(second=0,microsecond=0)
  create('schedule',doctor,f'/api/v1/doctors/{d["id"]}/schedules',{'timezone':'UTC','slot_minutes':5,'intervals':[{'starts_at':start.isoformat(),'ends_at':(start+timedelta(hours=4)).isoformat()}],'expected_revision':0},et,(202,))
 schedule=r['schedule'];create('decision',doctor,'/api/v1/appointments/schedule-decisions',{'doctor_id':d['id'],'proposal_id':schedule['id'],'expected_accepted_revision':0})
 _,et,_=doctor.call('GET',f'/api/v1/doctors/{d["id"]}/schedules/{schedule["id"]}');create('schedule_reconcile',doctor,f'/api/v1/doctors/{d["id"]}/schedules/{schedule["id"]}/reconcile',{},et,(200,))
 start=datetime.fromisoformat(schedule['intervals'][0]['starts_at'].replace('Z','+00:00'));end=datetime.fromisoformat(schedule['intervals'][-1]['ends_at'].replace('Z','+00:00'))
 available=actors['patient'].call('GET',f'/api/v1/appointments/availability?doctor_id={d["id"]}&from={start.strftime("%Y-%m-%dT%H:%M:%SZ")}&to={end.strftime("%Y-%m-%dT%H:%M:%SZ")}')[0]
 if 'slots'not in r:r['slots']=available['slots'];save()
 for i,label in enumerate(('camera_booking','clinical_rx_booking','clinical_no_rx_booking','reception_booking','cancel_booking','reschedule_booking','queue_skip_booking','queue_recall_booking','waitlist_booking')):
  a=actors['other']if label=='waitlist_booking'else actors['patient'];create(label,a,'/api/v1/appointments',{'patient_id':a.data['profile']['id'],'slot_id':r['slots'][i]['id'],'expected_schedule_revision':r['decision']['revision']})
 medicine=create('medicine',actors['pharmacist'],'/api/v1/pharmacy/medicines',{'sku':'P10-'+state['run'][:8],'name':'Phase10 Synthetic Medicine'})
 create('stock',actors['pharmacist'],'/api/v1/pharmacy/inventory-adjustments',{'medicine_id':medicine['id'],'batch_code':'P10-LOT','expires_on':(start.date()+timedelta(days=40)).isoformat(),'delta':60,'reason':'Fictional Phase10 acceptance stock','expected_batch_version':0})
 tariffs=actors['billing_staff'].call('GET','/api/v1/billing/tariffs')[0]['items']
 if not any(x['charge_code']=='consultation'for x in tariffs):create('consultation_tariff',actors['billing_staff'],'/api/v1/billing/tariffs',{'charge_code':'consultation','unit_amount_minor':10000,'currency':'INR'})
 create('medicine_tariff',actors['billing_staff'],'/api/v1/billing/tariffs',{'charge_code':'medicine:'+medicine['id'],'unit_amount_minor':2500,'currency':'INR'})
 (ROOT/'docs/phase-10/evidence/fixture-summary.json').write_text(json.dumps({'isolated_project':PROJECT,'actor_roles':list(actors),'doctor_id':d['id'],'patient_id':actors['patient'].data['profile']['id'],'medicine_id':medicine['id'],'synthetic_appointments':9,'schedule_from':start.isoformat(),'schedule_to':end.isoformat(),'mutations_used':'owner public APIs','secrets_recorded':False},indent=2)+'\n')
 print('PASS Phase10 fictional actors, schedules, nine bookings, medicine/stock and tariffs prepared',flush=True)

if __name__=='__main__':main()
