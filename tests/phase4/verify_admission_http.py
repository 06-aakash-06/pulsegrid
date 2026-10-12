"""Real Traefik burst across two Doctor replicas, with legitimate loopback sources."""
import json,time,math,statistics,uuid,subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import httpx
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_phase2 import Actor
s=json.loads(Path('/tmp/pulsegrid-phase3-live-fixture.json').read_text())
a=Actor('http://127.0.0.1:8080',s['actors']['patient']);a.login()
time.sleep(6)
containers=['pulsegrid-patient-1','pulsegrid-doctor-1','pulsegrid-doctor_replica-1','pulsegrid-records-1','pulsegrid-pharmacy-1','pulsegrid-billing-1','pulsegrid-appointment-1','pulsegrid-emergency-1']
program="""import sys,json,time,urllib.request,urllib.error
config=json.load(sys.stdin);rows=[]
for i in range(config['count']):
 start=time.perf_counter()
 req=urllib.request.Request('http://traefik:8080/api/v1/doctors/autocomplete?prefix=synthetic',headers={'Authorization':'Bearer '+config['token'],'X-Forwarded-For':'198.51.100.'+str(i+1)})
 try:r=urllib.request.urlopen(req,timeout=5)
 except urllib.error.HTTPError as error:r=error
 data=json.load(r)
 rows.append({'status':r.status,'ms':(time.perf_counter()-start)*1000,'retry_after':r.headers.get('Retry-After'),'code':data.get('error',{}).get('code')})
print(json.dumps(rows))
"""
def request(i):
 result=subprocess.run(['docker','exec','-i',containers[i],'python','-c',program],input=json.dumps({'token':a.token,'count':13 if i<4 else 12}),text=True,capture_output=True,check=True)
 return json.loads(result.stdout)
def metrics():
 result={}
 code="import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/metrics').read().decode())"
 for node in ['pulsegrid-doctor-1','pulsegrid-doctor_replica-1']:
  raw=subprocess.check_output(['docker','exec',node,'python','-c',code],text=True)
  counts={}
  for line in raw.splitlines():
   if line.startswith('pulsegrid_http_admission_requests_total{') and 'policy="doctor_directory_search_directory"' in line:
    labels=dict(__import__('re').findall(r'([a-z_]+)="([^"]*)"',line));counts[labels['outcome']]=float(line.rsplit(' ',1)[1])
  result[node]=counts
 return result
before_metrics=metrics()
started=time.perf_counter()
with ThreadPoolExecutor(max_workers=8) as pool:rows=[row for batch in pool.map(request,range(8)) for row in batch]
elapsed=time.perf_counter()-started
after_metrics=metrics()
metric_deltas={node:{outcome:after_metrics[node].get(outcome,0)-before_metrics[node].get(outcome,0) for outcome in ['accepted','limited','unavailable']} for node in after_metrics}
accepted=sum(r['status']==200 for r in rows);limited=sum(r['status']==429 for r in rows)
assert accepted and limited and accepted+limited==100, {r['status'] for r in rows}
assert accepted<=math.floor(60+elapsed*10), (accepted,elapsed)
assert all(r['code']=='rate_limited' and int(r['retry_after'])>=1 for r in rows if r['status']==429)
assert sum(v['accepted'] for v in metric_deltas.values())==accepted
assert sum(v['limited'] for v in metric_deltas.values())==limited
assert all(v['accepted']+v['limited']>0 for v in metric_deltas.values())
# Search overload does not touch Emergency's own principal/aggregate partitions.
r=a.client.post('/api/v1/emergencies',json={},headers={'Authorization':'Bearer '+a.token,'Idempotency-Key':str(uuid.uuid4())});assert r.status_code==422,r.status_code

result={'replica_final_http_metric_deltas':metric_deltas,'attempted':100,'admitted':accepted,'limited':limited,'errors':0,'elapsed_seconds':elapsed,'attempted_throughput':100/elapsed,'successful_throughput':accepted/elapsed,'all_mean_ms':statistics.mean(r['ms'] for r in rows),'all_p95_ms':sorted(r['ms'] for r in rows)[94],'emergency_business_validation_after_search_overload':422,'spoofed_x_forwarded_for_cannot_expand_principal_quota':True}
out=Path('experiments/phase4/integration/results');out.mkdir(parents=True,exist_ok=True);(out/'admission-http.json').write_text(json.dumps(result,indent=2));(out/'admission-http-samples.json').write_text(json.dumps(rows,indent=2));print(json.dumps(result))
