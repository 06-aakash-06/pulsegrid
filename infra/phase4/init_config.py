"""Generate only missing ignored Phase 4 credentials/config; never rotate existing secrets.
Run from repository root using Python with PyYAML installed. No DB/network mutation.
"""
from pathlib import Path
import json,secrets,yaml
owners='patient doctor appointment records pharmacy billing emergency'.split()
secretpath=Path('secrets/phase4');secretpath.mkdir(parents=True,exist_ok=True)
for name in ['admission-password','admission-hmac','cache-password']:
 p=secretpath/name
 if not p.exists():p.write_text(secrets.token_hex(32));p.chmod(0o600)
admission=(secretpath/'admission-password').read_text().strip();cache=(secretpath/'cache-password').read_text().strip()
# Redis replays Lua effects as the disabled default user during AOF loading.
# Permit only those persisted effects; the default identity cannot log in.
# Runtime callers retain their separate, namespace-scoped admission identity.
(secretpath/'admission.acl').write_text(f'user default off ~pg:admission:v1:* +select +hset +pexpireat +del\nuser admission on >{admission} ~pg:admission:v1:* +ping +time +type +hmget +hset +pexpire +evalsha +script|load\n')
(secretpath/'cache.acl').write_text(f'user default off\nuser doctor on >{cache} ~pg:cache:v1:doctor:* +ping +get +set +del\n')
for name in ['admission.acl','cache.acl']:(secretpath/name).chmod(0o600)
if not (secretpath/'cache.json').exists(): (secretpath/'cache.json').write_text(json.dumps({'epoch':1,'nodes':{n:f'redis://doctor:{cache}@{n}:6379/0' for n in ['cache_a','cache_b']}}));(secretpath/'cache.json').chmod(0o600)
sources=[{'provider_id':str(4101+i),'source_id':f'provider:{4101+i}','base_url':f'http://fixture_{i+1}:8000/','allowed_ips':[f'172.29.44.{11+i}']} for i in range(3)]
if not (secretpath/'sources.json').exists(): (secretpath/'sources.json').write_text(json.dumps(sources));(secretpath/'sources.json').chmod(0o600)
