"""Synthetic Emergency lifecycle after Phase 4 isolated admission activation."""
import json,sys,time,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_phase2 import Actor
s=json.loads(Path('/tmp/pulsegrid-phase29-live-fixture.json').read_text());actors={}
for role in ['patient','other','emergency_staff']:
 time.sleep(2);actors[role]=Actor('http://127.0.0.1:8080',s['actors'][role]);actors[role].login()
p,o,e=[actors[x] for x in ['patient','other','emergency_staff']]
def call(a,method,path,body=None,et=None,codes=(200,)):
 time.sleep(.6);return a.call(method,path,body,et,str(uuid.uuid4()) if method=='POST' else None,codes)
v,et,_=call(p,'POST','/api/v1/emergencies',{'patient_id':p.data['profile']['id'],'description':'Synthetic Phase4 verification','reported_urgency':'urgent'},codes=(201,));path='/api/v1/emergencies/'+v['id']
_,et,_=call(p,'GET',path);call(o,'GET',path,codes=(404,));call(p,'PATCH',path+'/priority',{'assigned_priority':1,'reason':'Synthetic denial'},et,(403,))
_,et,_=call(e,'PATCH',path+'/priority',{'assigned_priority':3,'reason':'Synthetic staff priority'},et)
_,et,_=call(e,'POST',path+'/claim',{},et)
_,et,_=call(e,'POST',path+'/transitions',{'state':'processing','reason':'Synthetic processing'},et)
v,_,_=call(e,'POST',path+'/transitions',{'state':'resolved','reason':'Synthetic resolved'},et);assert v['state']=='resolved'
Path('experiments/phase4/integration/results/emergency-http.json').write_text(json.dumps({'submission':201,'wrong_owner':404,'patient_priority_change':403,'staff_claim_processing_resolution':'pass'},indent=2));print('PASS real Emergency submission, ownership, staff triage/claim/processing/resolution')
