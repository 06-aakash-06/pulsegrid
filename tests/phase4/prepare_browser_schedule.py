"""Create authorized isolated synthetic staff/schedule for manual browser booking."""
import json,sys,time,uuid,secrets
from pathlib import Path
from datetime import datetime,timedelta,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_phase2 import Actor,require
p=Path('artifacts/phase4/live-fixture.json');s=json.loads(p.read_text())
def save():p.write_text(json.dumps(s,indent=2));p.chmod(0o600)
admin=Actor('http://127.0.0.1:8080',json.loads(Path('/tmp/pulsegrid-phase29-live-fixture.json').read_text())['actors']['admin']);admin.login();time.sleep(2)
if 'browser_doctor_actor' not in s:
 data={'email':'phase4-browser-doctor-'+uuid.uuid4().hex+'@example.test','password':secrets.token_urlsafe(24)}
 a=Actor('http://127.0.0.1:8080',data)
 data['profile']=require(a.client.post('/api/v1/auth/register',json={**data,'display_name':'Synthetic Phase4 Browser Doctor'},headers={'Idempotency-Key':str(uuid.uuid4()),'X-Anonymous-Command-ID':secrets.token_hex(24)}),(201,))
 user,et,_=admin.call('GET','/api/v1/patients/users/'+data['profile']['user_id']);admin.call('PATCH','/api/v1/patients/users/'+user['id']+'/roles',{'roles':['doctor']},et)
 s['browser_doctor_actor']=data;save()
data=s['browser_doctor_actor']
if 'browser_doctor' not in s['resources']:
 specialty=json.loads(Path('/tmp/pulsegrid-phase3-live-fixture.json').read_text())['resources']['specialty']['id']
 s['resources']['browser_doctor']=admin.call('POST','/api/v1/doctors',{'staff_user_id':data['profile']['user_id'],'display_name':'Synthetic Phase4 Browser Doctor','specialty_ids':[specialty]},None,str(uuid.uuid4()),(201,))[0];save()
a=Actor('http://127.0.0.1:8080',data);time.sleep(2);a.login();did=s['resources']['browser_doctor']['id']
if 'accepted_browser_schedule' not in s['resources']:
 _,et,_=a.call('GET','/api/v1/doctors/'+did)
 start=(datetime.now(timezone.utc)+timedelta(days=1)).replace(hour=4,minute=0,second=0,microsecond=0)
 body={'timezone':'UTC','slot_minutes':5,'intervals':[{'starts_at':start.isoformat(),'ends_at':(start+timedelta(minutes=30)).isoformat()}],'expected_revision':0}
 proposal=a.call('POST',f'/api/v1/doctors/{did}/schedules',body,et,str(uuid.uuid4()),(202,))[0]
 time.sleep(1);decision=a.call('POST','/api/v1/appointments/schedule-decisions',{'doctor_id':did,'proposal_id':proposal['id'],'expected_accepted_revision':0},None,str(uuid.uuid4()),(201,))[0];assert decision['state']=='accepted',decision
 _,et,_=a.call('GET',f'/api/v1/doctors/{did}/schedules/{proposal["id"]}')
 a.call('POST',f'/api/v1/doctors/{did}/schedules/{proposal["id"]}/reconcile',{},et,str(uuid.uuid4()))
 s['resources']['accepted_browser_schedule']=proposal;save()
print('PASS authorized future schedule prepared; existing doctors/appointments retained')
