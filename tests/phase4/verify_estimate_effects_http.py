"""Real gateway estimates must persist distinct owner effect identities."""
import json,time,subprocess,sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_phase2 import Actor
s=json.loads(Path('/tmp/pulsegrid-phase3-live-fixture.json').read_text());a=Actor('http://127.0.0.1:8080',s['actors']['patient']);a.login();invoice=s['resources']['full_invoice']['id'];time.sleep(1);_,et,_=a.call('GET','/api/v1/billing/invoices/'+invoice);ids=[]
for _ in range(2):
 time.sleep(1);v=a.call('POST',f'/api/v1/billing/invoices/{invoice}/insurance-estimates',{'provider_id':'4101','policy_code':'DEMO'},et,str(uuid.uuid4()),(201,))[0];ids.append(v['id'])
code="""import sys,json,psycopg
from billing_service.settings import Settings
ids=json.load(sys.stdin);s=Settings.from_env();dsn=s.database_url.render_as_string(hide_password=False).replace('postgresql+psycopg://','postgresql://')
with psycopg.connect(dsn) as c:
 rows=c.execute("SELECT aggregate_type,aggregate_id,aggregate_version,envelope->'payload'->>'estimate_id' FROM outbox_events WHERE event_type='billing.insurance.estimate_created.v1' AND envelope->'payload'->>'estimate_id'=ANY(%s)",(ids,)).fetchall()
assert len(rows)==2 and all(t=='insurance_estimate' and str(i)==eid and v==1 for t,i,v,eid in rows)
assert len(set(row[1] for row in rows))==2
print('PASS two distinct estimate effect identities')
"""
subprocess.run(['docker','exec','-i','pulsegrid-billing-1','python','-c',code],input=json.dumps(ids),text=True,check=True)
Path('experiments/phase4/integration/results/estimate-effects-http.json').write_text(json.dumps({'created_estimates':2,'distinct_aggregate_identities':2,'type':'insurance_estimate','version':1,'verification':'gateway commands and Billing-owned outbox'},indent=2))
