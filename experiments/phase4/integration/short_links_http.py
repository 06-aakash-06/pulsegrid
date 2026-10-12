"""Real Traefik/JWT/PostgreSQL/Snowflake/owner-effect endpoint comparisons.

One synthetic future booking, actual admission policies unchanged. Thirty-two
legitimate temporary client sources, no published ports or database access.
"""
import sys,json,time,uuid,subprocess,statistics,math,hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'tests'))
from verify_phase2 import Actor
fixture=json.loads(Path('/tmp/pulsegrid-phase3-live-fixture.json').read_text())
actor=Actor('http://127.0.0.1:8080',fixture['actors']['patient']);actor.login()
# Browser fixture retains the real booking created and rescheduled through UI.
bookings=actor.call('GET','/api/v1/appointments?limit=100')[0]['items']
booking=next(x for x in bookings if x['doctor_id']==json.loads(Path('artifacts/phase4/live-fixture.json').read_text())['resources']['browser_doctor']['id'] and x['starts_at']>__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat().replace('+00:00','Z') and x['state']=='confirmed')
aid=booking['id'];workflow,etag,_=actor.call('GET',f'/api/v1/appointments/{aid}/workflow')
image=subprocess.check_output(['docker','inspect','pulsegrid-doctor-1','--format','{{.Config.Image}}'],text=True).strip();prefix='pulsegrid-phase4-load-'+uuid.uuid4().hex[:8];nodes=[];all_rows=[];summary=[]
program=r'''import sys,json,time,uuid,urllib.request,urllib.error,hashlib
cfg=json.load(sys.stdin);rows=[];seen=[]
for warm in [True,False]:
 start=time.monotonic();end=start+(5 if warm else 30);next_at=start
 while time.monotonic()<end:
  request_time=time.perf_counter();headers={'Authorization':'Bearer '+cfg['token']}
  if cfg['mode']=='creation':
   headers.update({'If-Match':cfg['etag'],'Idempotency-Key':str(uuid.uuid4()),'Content-Type':'application/json'});data=json.dumps({'purpose':'appointment'}).encode();method='POST'
  else:data=None;method='GET'
  req=urllib.request.Request('http://traefik:8080'+cfg['path'],data=data,headers=headers,method=method)
  try:
   try:r=urllib.request.urlopen(req,timeout=5)
   except urllib.error.HTTPError as error:r=error
   with r:
    payload=json.load(r);status=r.status;retry=r.headers.get('Retry-After');code=payload.get('error',{}).get('code')
    valid=(status==429 and code=='rate_limited' and retry is not None) or (status in (200,201) and ((payload.get('appointment_id')==cfg['appointment_id']) if cfg['mode']!='baseline' else payload.get('appointment_id')==cfg['appointment_id']))
    if status==201:
     valid=valid and ((int(payload['id'])>>12)&1023)==256 and payload['short_path'].startswith('/s/');seen.append(payload['id'])
   error_type=None
  except Exception as error:status=0;retry=None;code=None;valid=False;error_type=type(error).__name__
  elapsed=(time.perf_counter()-request_time)*1000
  if not warm:rows.append({'status':status,'ms':elapsed,'retry_after':retry,'code':code,'correct':valid,'error_type':error_type})
  next_at+=1;time.sleep(max(0,min(next_at-time.monotonic(),end-time.monotonic())))
print(json.dumps({'samples':rows,'created_ids':seen}))
'''
def drive(index,cfg):
 r=subprocess.run(['docker','exec','-i',nodes[index],'python','-c',program],input=json.dumps(cfg),text=True,capture_output=True,check=True);return json.loads(r.stdout)
try:
 for i in range(32):
  name=prefix+'-'+str(i);subprocess.run(['docker','run','-d','--name',name,'--network','pulsegrid_edge','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--memory','64m','--cpus','.1','--user','10001:10001','--entrypoint','python',image,'-c','import time;time.sleep(1800)'],check=True,stdout=subprocess.DEVNULL);nodes.append(name)
 for level,clients in [('low',1),('medium',8),('high',32)]:
  actor.login()
  for trial in range(3):
   modes=['baseline','resolution','creation'] if trial%2==0 else ['creation','resolution','baseline']
   for mode in modes:
    # A new alias before a resolution-only trial; no concurrent reissue404 noise.
    if mode=='resolution':
     time.sleep(6);link=actor.call('POST',f'/api/v1/appointments/{aid}/short-links',{'purpose':'appointment'},etag,str(uuid.uuid4()),(201,))[0];path=link['short_path']
    elif mode=='creation':path=f'/api/v1/appointments/{aid}/short-links'
    else:path=f'/api/v1/appointments/{aid}/workflow'
    time.sleep(6);cfg={'token':actor.token,'path':path,'mode':mode,'etag':etag,'appointment_id':aid};start=time.perf_counter()
    with ThreadPoolExecutor(max_workers=clients) as pool:batches=list(pool.map(lambda i:drive(i,cfg),range(clients)))
    wall=time.perf_counter()-start;rows=[row for batch in batches for row in batch['samples']];ids=[x for batch in batches for x in batch['created_ids']];assert len(ids)==len(set(ids))
    success=[r['ms'] for r in rows if r['status'] in (200,201)];limited=sum(r['status']==429 for r in rows);errors=sum(r['status'] not in (200,201,429) for r in rows);assert all(r['correct'] for r in rows),{'level':level,'mode':mode,'statuses':sorted(set(r['status'] for r in rows))}
    for row in rows:all_rows.append({'level':level,'trial':trial+1,'operation':mode,**row})
    measured_wall=30.;summary.append({'level':level,'clients':clients,'trial':trial+1,'operation':mode,'attempted':len(rows),'admitted':len(success),'limited':limited,'errors':errors,'error_rate':errors/len(rows),'all_mean_ms':statistics.mean(r['ms'] for r in rows),'success_mean_ms':statistics.mean(success) if success else None,'success_p50_ms':statistics.median(success) if success else None,'success_p95_ms':sorted(success)[math.ceil(.95*len(success))-1] if success else None,'all_p95_ms':sorted(r['ms'] for r in rows)[math.ceil(.95*len(rows))-1],'successful_throughput':len(success)/measured_wall,'attempted_throughput':len(rows)/measured_wall,'correctness_ratio':sum(r['correct'] for r in rows)/len(rows),'worker256_collisions':0,'total_worker_seconds_including5s_warmup':wall})
    print(json.dumps(summary[-1]),flush=True)
    Path('artifacts/phase4/short-links/http-samples.json').write_text(json.dumps(all_rows))
    Path('experiments/phase4/integration/results/short-links-http.json').write_text(json.dumps({'seed':404,'warmup_seconds':5,'measurement_seconds':30,'repeats':3,'rows':summary,'limitations':['Actual hospital alias cardinality is small; the separate50k adapter workload investigates pool saturation.','Admission quotas remain active: high429 responses are policy rejection, not server errors.','One existing API process; client sources are real temporary containers.','Creation/resolution/baseline measured separately; request latency excludes client pacing.']},indent=2))
finally:
 for name in nodes:subprocess.run(['docker','rm','-f',name],check=True,stdout=subprocess.DEVNULL)
print('PASS authenticated short-link endpoint matrix; load clients removed')
