"""Spoofed forwarded headers cannot create authentication source identities."""
import json,time,math,uuid,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_phase2 import Actor
import httpx
c=httpx.Client(base_url='http://127.0.0.1:8080',headers={'Origin':'http://127.0.0.1:5173'},timeout=10,trust_env=False)
csrf=c.get('/api/v1/auth/csrf').json()['csrf_token'];rows=[];start=time.perf_counter()
for i in range(20):
 t=time.perf_counter();r=c.post('/api/v1/auth/login',json={'email':f'synthetic-absent-{uuid.uuid4()}@example.test','password':'Synthetic-invalid-password-only'},headers={'X-CSRF-Token':csrf,'X-Forwarded-For':f'198.51.100.{i+1}'})
 assert r.status_code in (401,429),r.status_code
 rows.append({'status':r.status_code,'ms':(time.perf_counter()-t)*1000,'retry_after':r.headers.get('Retry-After')})
 if r.status_code==429:assert r.json()['error']['code']=='rate_limited' and int(r.headers['Retry-After'])>=1
elapsed=time.perf_counter()-start;admitted=sum(x['status']==401 for x in rows);assert admitted<=math.floor(10+elapsed*.5) and admitted<20,(admitted,elapsed)
Path('experiments/phase4/integration/results/proxy-http.json').write_text(json.dumps({'requests':20,'admitted_invalid_logins':admitted,'limited':20-admitted,'elapsed_seconds':elapsed,'forwarded_header_spoof_does_not_bypass_source_quota':True,'samples':rows},indent=2));print('PASS authentication source quota despite20 spoofed forwarding identities')
