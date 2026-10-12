"""Bounded outage/topology rollout on Phase 4-owned cache nodes; always recover."""
import json,subprocess,sys,time,statistics
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_phase2 import Actor
COMPOSE=['docker','compose','-f','compose.yaml','-f','services/patient/compose.auth.yaml','-f','compose.phase4.yaml']
s=json.loads(Path('/tmp/pulsegrid-phase3-live-fixture.json').read_text())
a=Actor('http://127.0.0.1:8080',s['actors']['patient']);a.login()
config_path=Path('secrets/phase4/cache.json');initial=json.loads(config_path.read_text());results=[]
def read(label,count=6):
 lat=[]
 for _ in range(count):
  time.sleep(.6);start=time.perf_counter();value,_,_=a.call('GET','/api/v1/doctors?limit=20');lat.append((time.perf_counter()-start)*1000)
  assert value==expected
 results.append({'scenario':label,'requests':count,'errors':0,'mean_ms':statistics.mean(lat),'p95_ms':max(lat)})
def rollout(config):
 config_path.write_text(json.dumps(config));config_path.chmod(0o600)
 subprocess.run(COMPOSE+['up','-d','--no-build','--no-deps','--force-recreate','doctor','doctor_replica'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 for _ in range(30):
  try:
   r=a.client.get('/api/v1/doctors/health/ready')
   if r.status_code==200:time.sleep(2);return
  except Exception:pass
  time.sleep(1)
 raise RuntimeError('Doctor recovery did not finish')
expected=a.call('GET','/api/v1/doctors?limit=20')[0]
try:
 read('warm_cache')
 # Both nodes are newly introduced cache-only resources; PostgreSQL untouched.
 subprocess.run(COMPOSE+['stop','-t','1','cache_a','cache_b'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 read('cache_outage_owner_fallback',3)
 subprocess.run(COMPOSE+['start','cache_a','cache_b'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 time.sleep(2);read('restart_cold_refill')
 removed={'epoch':initial['epoch']+1,'nodes':{'cache_b':initial['nodes']['cache_b']}}
 rollout(removed);read('node_removed_epoch_refill')
 restored={'epoch':initial['epoch']+2,'nodes':initial['nodes']}
 rollout(restored);read('node_added_new_epoch_refill')
finally:
 subprocess.run(COMPOSE+['start','cache_a','cache_b'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 # Epoch never rolls backwards, even if a test failed.
 current=json.loads(config_path.read_text())
 if current['nodes']!=initial['nodes']:rollout({'epoch':current['epoch']+1,'nodes':initial['nodes']})
Path('experiments/phase4/integration/results/cache-http.json').write_text(json.dumps({'catalog_size':len(expected['items']),'final_epoch':json.loads(config_path.read_text())['epoch'],'measurements':results,'limits':['Six-request endpoint sanity measurements, not frozen-duration performance trials.','Cache placement provides no replication/HA.']},indent=2))
print('PASS',len(results),'real cache endpoint scenarios; PostgreSQL parity preserved')
