"""Paced authenticated endpoint baseline/cold/warm samples, private cache only."""
import json,time,statistics,sys,subprocess,asyncio,argparse
from pathlib import Path
from redis.asyncio import Redis
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_phase2 import Actor
base=['docker','compose','-f','compose.yaml','-f','services/patient/compose.auth.yaml','-f','compose.phase4.yaml']
s=json.loads(Path('/tmp/pulsegrid-phase3-live-fixture.json').read_text());a=Actor('http://127.0.0.1:8080',s['actors']['patient']);a.login()
expected=a.call('GET','/api/v1/doctors?limit=20')[0];results=[]
parser=argparse.ArgumentParser();parser.add_argument('--full-duration',action='store_true');options=parser.parse_args()
def deploy(args):
 subprocess.run(args+['up','-d','--no-build','--no-deps','--force-recreate','doctor','doctor_replica'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);time.sleep(12)
def cold():
 # Remove only the newly owned Doctor cache namespace, never admission or DB data.
 code="""import asyncio,json,os,psycopg
from redis.asyncio import Redis
from doctor_service.settings import Settings
from doctor_service.features.directory_cache import DirectoryFilters
from pulsegrid_consistent_hashing import HashRing,RingSnapshot
from pulsegrid_key_value_cache import Cache
async def main():
 cfg=json.load(open(os.environ['PULSEGRID_DOCTOR_PHASE4_CACHE_CONFIG_FILE']))
 settings=Settings.from_env()
 dsn=settings.database_url.render_as_string(hide_password=False).replace('postgresql+psycopg://','postgresql://')
 with psycopg.connect(dsn) as conn:revision=conn.execute('SELECT revision FROM directory_revision WHERE singleton').fetchone()[0]
 clients={node:Redis.from_url(url) for node,url in cfg['nodes'].items()}
 cache=Cache(HashRing(RingSnapshot(cfg['epoch'],128,tuple(cfg['nodes']))),clients)
 client,key=cache._target(DirectoryFilters('synthetic-hospital','patient',limit=20).key(revision))
 await client.delete(key)
 assert await client.get(key) is None
 await cache.close()
asyncio.run(main())"""
 subprocess.run(['docker','exec','pulsegrid-doctor-1','python','-c',code],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
def measure(mode):
 for trial in range(3 if options.full_duration else 1):
  if options.full_duration:
   end=time.monotonic()+5
   while time.monotonic()<end:
    time.sleep(.6);a.call('GET','/api/v1/doctors?limit=20')
  lat=[];start=time.perf_counter()
  while (time.perf_counter()-start<30 if options.full_duration else len(lat)<30):
   if mode=='cold_cache':cold()
   time.sleep(.6);t=time.perf_counter();v,_,_=a.call('GET','/api/v1/doctors?limit=20');lat.append((time.perf_counter()-t)*1000);assert v==expected
  elapsed=time.perf_counter()-start
  results.append({'scenario':mode,'trial':trial+1,'requests':len(lat),'errors':0,'mean_ms':statistics.mean(lat),'p50_ms':statistics.median(lat),'p95_ms':sorted(lat)[__import__('math').ceil(.95*len(lat))-1],'samples_ms':lat,'concurrency':1,'elapsed_seconds':elapsed,'successful_throughput_including_pacing_and_reset':len(lat)/elapsed,'latency_excludes_pacing_and_cache_reset':True})
overlay=Path('/tmp/pulsegrid-phase4-no-cache.yaml');overlay.write_text('services:\n  doctor:\n    environment:\n      PULSEGRID_DOCTOR_PHASE4_CACHE_ENABLED: "false"\n  doctor_replica:\n    environment:\n      PULSEGRID_DOCTOR_PHASE4_CACHE_ENABLED: "false"\n')
try:deploy(base+['-f',str(overlay)]);measure('uncached_owner_database')
finally:deploy(base)
measure('cold_cache');measure('warm_cache')
(Path('experiments/phase4/integration/results')/('cache-endpoint-full.json' if options.full_duration else 'cache-endpoint-benchmark.json')).write_text(json.dumps({'catalog_size':len(expected['items']),'measurements':results,'limits':['Paced authenticated endpoint comparisons; 5s warmup/30s x3 with --full-duration. Throughput includes pacing and cold reset; no saturation claim.','Low/medium/high adapter trials are separate retained component evidence.']},indent=2));print('PASS uncached/cold/warm real endpoint parity and measurements')
