"""Invalid credentials on one Doctor replica must reject503 and recover safely."""
import json,time,subprocess,sys,secrets
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_phase2 import Actor
s=json.loads(Path('/tmp/pulsegrid-phase3-live-fixture.json').read_text());a=Actor('http://127.0.0.1:8080',s['actors']['patient']);a.login()
base=['docker','compose','-f','compose.yaml','-f','services/patient/compose.auth.yaml','-f','compose.phase4.yaml']
password=Path('secrets/phase4/invalid-admission-test-password').resolve();password.write_text(secrets.token_urlsafe(48));password.chmod(0o600)
overlay=Path('/tmp/pulsegrid-phase4-invalid-admission.yaml');overlay.write_text('services:\n  doctor_replica:\n    volumes:\n    - ./secrets/phase4/invalid-admission-test-password:/run/phase4/admission-password:ro\n')
def rollout(args):
 r=subprocess.run(args+['up','-d','--no-build','--no-deps','--force-recreate','--wait','--wait-timeout','60','doctor_replica'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
 if r.returncode:raise RuntimeError(r.stderr[-1200:])
rows=[]
try:
 rollout(base+['-f',str(overlay)])
 for _ in range(8):
  time.sleep(.6);r=a.client.get('/api/v1/doctors/autocomplete?prefix=synthetic',headers={'Authorization':'Bearer '+a.token});assert r.status_code in (200,503),r.status_code
  if r.status_code==503:assert r.json()['error']['code']=='admission_unavailable' and int(r.headers['Retry-After'])>=1
  rows.append(r.status_code)
 assert 200 in rows and 503 in rows,rows
finally:rollout(base);password.unlink()
for _ in range(4):time.sleep(.6);a.call('GET','/api/v1/doctors/autocomplete?prefix=synthetic')
Path('experiments/phase4/integration/results/admission-config-failure-http.json').write_text(json.dumps({'statuses':rows,'invalid_credential_replica_rejects':503,'recovery':200,'authentication_unchanged':True,'credential_test_scope':'temporary replica-only file; original secret never edited'},indent=2));print('PASS real503 invalid-admission configuration and replica recovery200')
