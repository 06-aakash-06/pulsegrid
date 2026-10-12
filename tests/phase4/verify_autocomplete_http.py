"""Real gateway trie vs bounded memory fallback; restore original deployment."""
import json,time,subprocess,statistics,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_phase2 import Actor
base=['docker','compose','-f','compose.yaml','-f','services/patient/compose.auth.yaml','-f','compose.phase4.yaml']
s=json.loads(Path('/tmp/pulsegrid-phase3-live-fixture.json').read_text());actor=Actor('http://127.0.0.1:8080',s['actors']['patient']);actor.login()
paths={'doctor':'/api/v1/doctors/autocomplete?prefix=synthetic&kinds=doctor,specialty&limit=10','pharmacy':'/api/v1/pharmacy/medicines/autocomplete?prefix=synthetic&limit=10'}
results=[];expected={}
def measure(mode):
 for owner,path in paths.items():
  samples=[]
  for i in range(12):
   time.sleep(.6);t=time.perf_counter();body,_,_=actor.call('GET',path);samples.append((time.perf_counter()-t)*1000)
   assert body['source']==mode,(owner,body)
   if owner not in expected:expected[owner]=body['items']
   assert body['items']==expected[owner]
  results.append({'owner':owner,'source':mode,'requests':len(samples),'errors':0,'mean_ms':statistics.mean(samples),'p50_ms':statistics.median(samples),'p95_ms':sorted(samples)[-1],'items':len(expected[owner]),'samples_ms':samples})
def deploy(cmd):
 subprocess.run(cmd+['up','-d','--no-deps','--no-build','--force-recreate','doctor','doctor_replica','pharmacy'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 time.sleep(12)
measure('trie')
overlay=Path('/tmp/pulsegrid-phase4-index-fallback.yaml');overlay.write_text('services:\n  doctor:\n    environment:\n      PULSEGRID_DOCTOR_PHASE4_AUTOCOMPLETE_MAX_BYTES: "1024"\n  doctor_replica:\n    environment:\n      PULSEGRID_DOCTOR_PHASE4_AUTOCOMPLETE_MAX_BYTES: "1024"\n  pharmacy:\n    environment:\n      PULSEGRID_PHARMACY_PHASE4_AUTOCOMPLETE_MAX_BYTES: "1024"\n')
try:
 deploy(base+['-f',str(overlay)]);measure('database')
finally:deploy(base)
measure('trie')
Path('experiments/phase4/integration/results/autocomplete-http.json').write_text(json.dumps({'measurements':results,'budget_normal_bytes':67108864,'budget_forced_bytes':1024,'limitations':['12 paced authenticated endpoint samples per condition, not a saturation benchmark.','Fallback is forced by lowering the budget, not by disabling correctness safeguards.']},indent=2))
print('PASS real Doctor/Pharmacy bounded fallback and recovery; identical authorized suggestions')
