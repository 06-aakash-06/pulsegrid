"""Real synthetic crawler/estimate gateway verification after hospital journey."""
import sys,json,time,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_phase2 import Actor
s=json.loads(Path('/tmp/pulsegrid-phase3-live-fixture.json').read_text())
actors={}
for role in ['billing_staff','patient','other']:
 time.sleep(2);actors[role]=Actor('http://127.0.0.1:8080',s['actors'][role]);actors[role].login()
bill,p,other=[actors[role] for role in ['billing_staff','patient','other']]
def call(a,method,path,body=None,etag=None,codes=(200,)):
 time.sleep(.6);return a.call(method,path,body,etag,str(uuid.uuid4()) if method=='POST' else None,codes)
providers,_,_=call(bill,'GET','/api/v1/billing/insurance/providers');assert len(providers['items'])==3
run,_,_=call(bill,'POST','/api/v1/billing/insurance/providers/4101/refresh',{},'"1"',codes=(202,))
for _ in range(15):
 time.sleep(2)
 status,_,_=call(bill,'GET',f'/api/v1/billing/insurance/runs/{run["run_id"]}')
 if status['state'] in ('complete','partial','failed'):break
assert status['state']=='complete',status
invoice=s['resources']['full_invoice']['id']
before,et,_=call(p,'GET',f'/api/v1/billing/invoices/{invoice}')
history,_,_=call(p,'GET',f'/api/v1/billing/invoices/{invoice}/payments')
e,_,_=call(p,'POST',f'/api/v1/billing/invoices/{invoice}/insurance-estimates',{'provider_id':'4101','policy_code':'DEMO'},et,codes=(201,))
after,_,_=call(p,'GET',f'/api/v1/billing/invoices/{invoice}')
history_after,_,_=call(p,'GET',f'/api/v1/billing/invoices/{invoice}/payments')
assert before==after and history==history_after and e['is_simulated'] and e['estimate_minor']==0
call(other,'GET',f'/api/v1/billing/invoices/{invoice}/insurance-estimates',codes=(404,))
call(p,'POST','/api/v1/billing/insurance/providers/4101/refresh',{},'"1"',codes=(403,))
print('PASS fixture_crawl_complete_estimate_provenance_paid_invoice_and_payments_unchanged_owner_scope')
Path('artifacts/phase4/insurance-http.json').write_text(json.dumps({'run_id':run['run_id'],'state':status['state'],'pages_processed':status['pages_processed'],'estimate_minor':e['estimate_minor'],'rule_revision':e['rule_revision'],'invoice_unchanged':True,'payments_unchanged':True},indent=2))
