"""Short admission-only Redis outage with recovery; no application data reset."""
import json,time,subprocess,sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_phase2 import Actor
s=json.loads(Path('/tmp/pulsegrid-phase3-live-fixture.json').read_text());a=Actor('http://127.0.0.1:8080',s['actors']['patient']);a.login();time.sleep(3)
rows=[]
try:
 subprocess.run(['docker','stop','-t','1','pulsegrid-redis-1'],check=True,stdout=subprocess.DEVNULL)
 for _ in range(20):
  r=a.client.get('/api/v1/doctors/autocomplete?prefix=synthetic',headers={'Authorization':'Bearer '+a.token})
  assert r.status_code in (200,429),r.status_code
  if r.status_code==429:assert r.json()['error']['code']=='rate_limited' and int(r.headers['Retry-After'])>=1
  rows.append(r.status_code)
finally:subprocess.run(['docker','start','pulsegrid-redis-1'],check=True,stdout=subprocess.DEVNULL)
time.sleep(3)
a.call('GET','/api/v1/doctors/autocomplete?prefix=synthetic')
assert 200 in rows and 429 in rows,rows
Path('experiments/phase4/integration/results/admission-outage-http.json').write_text(json.dumps({'requests':20,'statuses':rows,'fallback':'per-process conservative divided quota; approximate','recovery':200,'duration_scope':'twenty requests, Redis always restarted in finally'},indent=2))
print('PASS conservative admission fallback429 and Redis restart recovery200')
