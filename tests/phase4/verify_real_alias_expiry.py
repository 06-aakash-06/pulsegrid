"""Real wall-clock expiry via normal synthetic owner APIs; no DB time/row edits."""
import sys,json,time,uuid
from pathlib import Path
from datetime import datetime,timedelta,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_phase2 import Actor
s=json.loads(Path('artifacts/phase4/live-fixture.json').read_text());old=json.loads(Path('/tmp/pulsegrid-phase3-live-fixture.json').read_text());private=Path('artifacts/phase4/expiry-fixture.json')
d=Actor('http://127.0.0.1:8080',s['browser_doctor_actor']);d.login();time.sleep(2)
p=Actor('http://127.0.0.1:8080',old['actors']['patient']);p.login()
def call(a,method,path,body=None,et=None,codes=(200,)):
 time.sleep(.6);return a.call(method,path,body,et,str(uuid.uuid4()) if method=='POST' else None,codes)
if not private.exists():
 did=s['resources']['browser_doctor']['id'];_,et,_=call(d,'GET','/api/v1/doctors/'+did)
 rows=call(d,'GET',f'/api/v1/doctors/{did}/schedules?limit=100')[0]['items'];rev=max(x['revision'] for x in rows);accepted=max(x['revision'] for x in rows if x['status']=='accepted');previous=next(x['intervals'] for x in rows if x['status']=='accepted' and x['revision']==accepted)
 start=(datetime.now(timezone.utc)+timedelta(minutes=2)).replace(second=0,microsecond=0)
 intervals=[{'starts_at':start.isoformat(),'ends_at':(start+timedelta(minutes=5)).isoformat()}]+[{k:r[k] for k in ['starts_at','ends_at']} for r in previous]
 proposal=call(d,'POST',f'/api/v1/doctors/{did}/schedules',{'timezone':'UTC','slot_minutes':5,'intervals':intervals,'expected_revision':rev},et,(202,))[0]
 decision=call(d,'POST','/api/v1/appointments/schedule-decisions',{'doctor_id':did,'proposal_id':proposal['id'],'expected_accepted_revision':accepted},codes=(201,))[0];assert decision['state']=='accepted',decision
 _,et,_=call(d,'GET',f'/api/v1/doctors/{did}/schedules/{proposal["id"]}');call(d,'POST',f'/api/v1/doctors/{did}/schedules/{proposal["id"]}/reconcile',{},et)
 begin=start.strftime('%Y-%m-%dT%H:%M:%SZ');end=(start+timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%SZ');slot=call(p,'GET',f'/api/v1/appointments/availability?doctor_id={did}&from={begin}&to={end}')[0]['slots'][0]
 booking=call(p,'POST','/api/v1/appointments',{'patient_id':p.data['profile']['id'],'slot_id':slot['id'],'expected_schedule_revision':decision['revision']},codes=(201,))[0]
 _,et,_=call(p,'GET',f'/api/v1/appointments/{booking["id"]}/workflow');link=call(p,'POST',f'/api/v1/appointments/{booking["id"]}/short-links',{'purpose':'appointment'},et,(201,))[0]
 call(p,'GET',link['short_path']);private.write_text(json.dumps({'link':link,'initial_resolution':200},indent=2));private.chmod(0o600)
 print('PASS initial alias resolution200; waiting for actual contracted expiry',flush=True)
fixture=json.loads(private.read_text());deadline=datetime.fromisoformat(fixture['link']['expires_at'].replace('Z','+00:00'))+timedelta(seconds=2)
while datetime.now(timezone.utc)<deadline:time.sleep(min(30,max(.1,(deadline-datetime.now(timezone.utc)).total_seconds())))
p.login();path=fixture['link']['short_path']
try:call(p,'GET',path,codes=(404,))
except AssertionError as error:raise AssertionError(str(error).replace(path,'/s/<redacted>')) from None
Path('experiments/phase4/integration/results/alias-real-expiry.json').write_text(json.dumps({'initial_resolution':200,'expired_resolution':404,'actual_expires_at':fixture['link']['expires_at'],'verification':'real wall clock; no database expiry/time mutation'},indent=2));print('PASS actual wall-clock expiry404',flush=True)
