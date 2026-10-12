"""Real Traefik Phase 4 synthetic workflows, no credentials/aliases in evidence."""
import sys,json,time,uuid,secrets
from pathlib import Path
from datetime import datetime,timedelta,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_phase2 import Actor,require
ROOT=Path(__file__).resolve().parents[2]
BASE='http://127.0.0.1:8080'
old=json.loads(Path('/tmp/pulsegrid-phase3-live-fixture.json').read_text())
actors={}
private=ROOT/'artifacts/phase4/live-fixture.json'
private.parent.mkdir(parents=True,exist_ok=True)
state=json.loads(private.read_text()) if private.exists() else {'run':str(uuid.uuid4()),'resources':{}}
def save():private.write_text(json.dumps(state,indent=2));private.chmod(0o600)
checks=[]
def check(name):checks.append(name);print('PASS',name,flush=True)
def call(actor,method,path,body=None,etag=None,codes=(200,),key=None):
    time.sleep(.6)
    try:return actor.call(method,path,body,etag,key or (str(uuid.uuid4()) if method=='POST' else None),codes)
    except AssertionError as error:
        if path.startswith('/s/'):raise AssertionError(str(error).replace(path,'/s/<redacted>')) from None
        raise
for role in ('patient','other','doctor','billing_staff','receptionist'):
    time.sleep(2)
    actors[role]=Actor(BASE,old['actors'][role]);actors[role].login()
admin=Actor(BASE,json.loads(Path('/tmp/pulsegrid-phase29-live-fixture.json').read_text())['actors']['admin']);time.sleep(2);admin.login()
if 'doctor_actor' not in state:
    data={'email':f'phase4-doctor-{state["run"]}@example.test','password':secrets.token_urlsafe(24)}
    new=Actor(BASE,data)
    data['profile']=require(new.client.post('/api/v1/auth/register',json={'email':data['email'],'password':data['password'],'display_name':'Synthetic Phase4 Doctor'},headers={'Idempotency-Key':str(uuid.uuid4()),'X-Anonymous-Command-ID':secrets.token_hex(24)}),(201,))
    state['doctor_actor']=data;save()
data=state['doctor_actor']
user,uet,_=call(admin,'GET','/api/v1/patients/users/'+data['profile']['user_id'])
if 'doctor' not in user['roles']:call(admin,'PATCH','/api/v1/patients/users/'+user['id']+'/roles',{'roles':['doctor']},uet)
d=Actor(BASE,data);time.sleep(2);d.login()
actors['doctor']=d
p=actors['patient'];bill=actors['billing_staff'];other=actors['other']
def created(label,actor,path,body,etag=None,codes=(201,)):
    if label not in state['resources']:
        state['resources'][label]=call(actor,'POST',path,body,etag,codes,key=str(uuid.uuid5(uuid.UUID(state['run']),label)))[0];save()
    return state['resources'][label]
if 'doctor' not in state['resources']:
    state['resources']['doctor']=created('doctor',admin,'/api/v1/doctors',{'staff_user_id':data['profile']['user_id'],'display_name':'Synthetic Phase4 Integration Doctor','specialty_ids':[old['resources']['specialty']['id']]});save()
time.sleep(6)  # Allow the documented five-second replica refresh after source creation.
items,_,_=call(p,'GET','/api/v1/doctors/autocomplete?prefix=synthetic');assert items['items'] and items['source']=='trie'
meds,_,_=call(p,'GET','/api/v1/pharmacy/medicines/autocomplete?prefix=synthetic');assert meds['items'] and meds['source']=='trie'
empty,_,_=call(p,'GET','/api/v1/doctors/autocomplete?prefix=zzzzz-no-match');assert empty['items']==[]
a,_,_=call(p,'GET','/api/v1/doctors?limit=20');b,_,_=call(p,'GET','/api/v1/doctors?limit=20');assert a==b
check('authenticated_directory_autocomplete_cache_parity_empty')
# Use existing synthetic doctor identity with a new future schedule, preserving old history.
did=state['resources']['doctor']['id']
profile,et,_=call(d,'GET',f'/api/v1/doctors/{did}')
schedules,_,_=call(d,'GET',f'/api/v1/doctors/{did}/schedules?limit=100')
revision=max((row['revision'] for row in schedules['items']),default=0)
start=datetime.fromisoformat(state['resources']['schedule']['intervals'][0]['starts_at'].replace('Z','+00:00')) if 'schedule' in state['resources'] else (datetime.now(timezone.utc)+timedelta(minutes=8)).replace(second=0,microsecond=0)
proposal=created('schedule',d,f'/api/v1/doctors/{did}/schedules',{'timezone':'UTC','slot_minutes':5,'intervals':[{'starts_at':start.isoformat(),'ends_at':(start+timedelta(minutes=30)).isoformat()}],'expected_revision':revision},et,codes=(202,))
# Current operational accepted revision remains the last accepted proposal revision.
accepted=max((row['revision'] for row in schedules['items'] if row['status']=='accepted'),default=0)
decision=created('decision',d,'/api/v1/appointments/schedule-decisions',{'doctor_id':did,'proposal_id':proposal['id'],'expected_accepted_revision':accepted},codes=(201,))
_,et,_=call(d,'GET',f'/api/v1/doctors/{did}/schedules/{proposal["id"]}')
created('reconcile',d,f'/api/v1/doctors/{did}/schedules/{proposal["id"]}/reconcile',{},et,codes=(200,))
avail,_,_=call(p,'GET',f'/api/v1/appointments/availability?doctor_id={did}&from={start.strftime("%Y-%m-%dT%H:%M:%SZ")}&to={(start+timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")}')
slot=avail['slots'][0]
booking=created('booking',p,'/api/v1/appointments',{'patient_id':p.data['profile']['id'],'slot_id':slot['id'],'expected_schedule_revision':decision['revision']},codes=(201,))
aid=booking['id'];workflow,et,_=call(p,'GET',f'/api/v1/appointments/{aid}/workflow')
key=str(uuid.uuid4())
link,_,_=call(p,'POST',f'/api/v1/appointments/{aid}/short-links',{'purpose':'appointment'},et,codes=(201,),key=key)
resolved,_,_=call(p,'GET',link['short_path']);assert resolved['appointment_id']==aid
call(other,'GET',link['short_path'],codes=(404,))
call(p,'POST',f'/api/v1/appointments/{aid}/short-links',{'purpose':'appointment'},et,codes=(409,),key=key)
response=p.client.get(link['short_path'],headers={'Accept':'text/html'});assert response.status_code==303 and response.headers['location'].startswith('/short-link#alias=')
check('booking_snowflake_alias_scope_static_navigation_sanitized_replay')
qr,_,_=call(p,'POST',f'/api/v1/appointments/{aid}/check-in-links',{},et,codes=(201,))
# First QR issuance retains version; QR reissue increments it and safely invalidates aliases.
current_wf,_,_=call(p,'GET',f'/api/v1/appointments/{aid}/workflow')
call(p,'GET',link['short_path'],codes=((404,) if current_wf['version'] != workflow['version'] else (200,)))
workflow,et,_=call(p,'GET',f'/api/v1/appointments/{aid}/workflow')
checkin,_,_=call(p,'POST',f'/api/v1/appointments/{aid}/check-in',{'token':qr['token']},et)
check('original_explicit_qr_checkin_after_alias_creation')
# Another appointment demonstrates lifecycle revocation without disturbing checked-in patient.
book2=created('other_booking',other,'/api/v1/appointments',{'patient_id':other.data['profile']['id'],'slot_id':avail['slots'][1]['id'],'expected_schedule_revision':decision['revision']},codes=(201,))
wf,et,_=call(other,'GET',f'/api/v1/appointments/{book2["id"]}/workflow')
link2,_,_=call(other,'POST',f'/api/v1/appointments/{book2["id"]}/short-links',{'purpose':'appointment'},et,codes=(201,))
_,bet,_=call(other,'GET',f'/api/v1/appointments/{book2["id"]}')
call(other,'POST',f'/api/v1/appointments/{book2["id"]}/cancel',{'reason':'Synthetic Phase 4 lifecycle verification'},bet)
call(other,'GET',link2['short_path'],codes=(404,))
check('cancel_revokes_alias_transactionally')
providers,_,_=call(bill,'GET','/api/v1/billing/insurance/providers');assert len(providers['items'])==3
run,_,_=call(bill,'POST','/api/v1/billing/insurance/providers/4101/refresh',{},'"1"',codes=(202,))
for _ in range(15):
    time.sleep(2)
    status,_,_=call(bill,'GET',f'/api/v1/billing/insurance/runs/{run["run_id"]}')
    if status['state'] in ('complete','partial','failed'):break
assert status['state']=='complete',status
invoice_id=old['resources']['full_invoice']['id']
before,iet,_=call(p,'GET',f'/api/v1/billing/invoices/{invoice_id}')
estimate,_,_=call(p,'POST',f'/api/v1/billing/invoices/{invoice_id}/insurance-estimates',{'provider_id':'4101','policy_code':'DEMO'},iet,codes=(201,))
after,_,_=call(p,'GET',f'/api/v1/billing/invoices/{invoice_id}');assert before==after
assert estimate['is_simulated'] and estimate['estimate_minor']==0
call(other,'GET',f'/api/v1/billing/invoices/{invoice_id}/insurance-estimates',codes=(404,))
check('crawler_fixture_ingestion_estimate_paid_invoice_unchanged_scope')
# Keep only opaque business IDs in private resume state, never aliases/QR/auth tokens.
resume={'appointment_id':aid,'doctor_id':did,'invoice_id':invoice_id,'checks':checks}
path=ROOT/'artifacts/phase4/http.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(resume,indent=2));path.chmod(0o600)
print('HTTP workflow groups:',len(checks))
