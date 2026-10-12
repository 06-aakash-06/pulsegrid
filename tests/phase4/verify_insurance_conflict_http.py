"""Bounded synthetic source equivocation; restore configured fixture in finally."""
import json,sys,time,uuid,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_phase2 import Actor
s=json.loads(Path('/tmp/pulsegrid-phase3-live-fixture.json').read_text())
b=Actor('http://127.0.0.1:8080',s['actors']['billing_staff']);b.login();time.sleep(2)
p=Actor('http://127.0.0.1:8080',s['actors']['patient']);p.login()
base=['docker','compose','-f','compose.yaml','-f','services/patient/compose.auth.yaml','-f','compose.phase4.yaml']
def call(a,method,path,body=None,et=None,codes=(200,)):
 time.sleep(.6);return a.call(method,path,body,et,str(uuid.uuid4()) if method=='POST' else None,codes)
def refresh():
 value,_,_=call(b,'POST','/api/v1/billing/insurance/providers/4101/refresh',{},'"1"',(202,))
 for _ in range(20):
  time.sleep(2);v,_,_=call(b,'GET','/api/v1/billing/insurance/runs/'+value['run_id'])
  if v['state'] in ('complete','partial','failed'):return v
 raise AssertionError('Crawler failed to finish')
invoice=s['resources']['full_invoice']['id'];before,et,_=call(p,'GET','/api/v1/billing/invoices/'+invoice)
overlay=Path('/tmp/pulsegrid-phase4-fixture-conflict.yaml');overlay.write_text('services:\n  fixture_1:\n    environment:\n      POLICY_REVISION: "2"\n      COVERAGE_BPS: "6000"\n')
try:
 subprocess.run(base+['-f',str(overlay),'up','-d','--no-deps','--no-build','--force-recreate','fixture_1'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 v=refresh();assert v['error_code']=='source_revision_conflict',v
 error,_,_=call(p,'POST',f'/api/v1/billing/invoices/{invoice}/insurance-estimates',{'provider_id':'4101','policy_code':'DEMO'},et,(409,));assert error['error']['code']=='source_revision_conflict'
finally:
 subprocess.run(base+['up','-d','--no-deps','--no-build','--force-recreate','fixture_1'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 recovered=refresh();assert recovered['state']=='complete',recovered
value,_,_=call(p,'POST',f'/api/v1/billing/invoices/{invoice}/insurance-estimates',{'provider_id':'4101','policy_code':'DEMO'},et,(201,));assert value['rule_revision']==2
call(p,'POST',f'/api/v1/billing/invoices/{invoice}/insurance-estimates',{'provider_id':'4101','policy_code':'DEMO','url':'http://example.com'},et,(422,))
after,_,_=call(p,'GET','/api/v1/billing/invoices/'+invoice);assert after==before
Path('experiments/phase4/integration/results/insurance-conflict-http.json').write_text(json.dumps({'conflict_error':v['error_code'],'estimate_rejected':409,'recovered_run_state':recovered['state'],'recovered_rule_revision':value['rule_revision'],'arbitrary_url_rejected':422,'invoice_unchanged':True},indent=2))
print('PASS source equivocation quarantined, estimate409, configured fixture recovered, invoice immutable')
