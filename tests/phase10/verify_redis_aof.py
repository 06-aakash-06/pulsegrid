"""Docker regression for persisted Lua effects with the generated admission ACL.

Uses two dedicated containers/volumes, no ports or network. Preserves volumes.
The disabled default identity must replay AOF transactions without authenticating.
"""
from pathlib import Path
import subprocess,tempfile,secrets,time,json,uuid
ROOT=Path(__file__).resolve().parents[2]
IMAGE='redis:7-alpine@sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499'
LUA="redis.call('HSET',KEYS[1],'state','SURGE','version','1');redis.call('PEXPIRE',KEYS[1],600000);return 1"
KEY='pg:admission:v1:aof-regression'

def run(args,**kwargs):return subprocess.run(args,capture_output=True,text=True,check=True,timeout=20,**kwargs).stdout.strip()
def case(default_rule,label):
 suffix=uuid.uuid4().hex[:8];name='pulsegrid-p10-aof-'+label+'-'+suffix;volume=name+'-data';password=secrets.token_hex(24)
 private=ROOT/'secrets/phase10/aof';private.mkdir(parents=True,exist_ok=True);acl=private/(name+'.acl')
 acl.write_text(default_rule+'\nuser admission on >'+password+' ~pg:admission:v1:* +ping +hset +hmget +pexpire +pttl +evalsha +script|load\n');acl.chmod(0o600)
 run(['docker','volume','create',volume])
 shell='cp /run/aof.acl /tmp/phase4.acl && chown redis:redis /tmp/phase4.acl && chmod 400 /tmp/phase4.acl && exec /usr/local/bin/docker-entrypoint.sh redis-server --appendonly yes --aclfile /tmp/phase4.acl --save ""'
 run(['docker','run','-d','--name',name,'--network','none','--mount','type=volume,src='+volume+',dst=/data','--mount','type=bind,src='+str(acl)+',dst=/run/aof.acl,readonly',IMAGE,'sh','-c',shell])
 def cli(*args,body=''):
  return run(['docker','exec','-i',name,'sh','-c','IFS= read -r REDISCLI_AUTH; export REDISCLI_AUTH; exec redis-cli --raw --user admission "$@"','sh',*args],input=password+'\n'+body)
 try:
  for _ in range(30):
   if cli('PING')=='PONG':break
   time.sleep(.1)
  sha=cli('-x','SCRIPT','LOAD',body=LUA);assert len(sha)==40,sha
  assert cli('EVALSHA',sha,'1',KEY)=='1'
  before=cli('HMGET',KEY,'state','version');assert before=='SURGE\n1',before
  ttl_before=int(cli('PTTL',KEY));assert 0<ttl_before<=600000
  assert 'NOPERM'in cli('HSET','outside-admission-namespace','field','value')
  run(['docker','stop','-t','5',name]);run(['docker','start',name])
  for _ in range(30):
   if cli('PING')=='PONG':break
   time.sleep(.1)
  after=cli('HMGET',KEY,'state','version');ttl_after=int(cli('PTTL',KEY));logs=run(['docker','logs',name]);obj=json.loads(run(['docker','inspect',name]))[0]
  # NOAUTH/default-disabled stays enforced even when offline replay is allowed.
  unauth=run(['docker','exec',name,'redis-cli','--raw','PING']);default_auth=run(['docker','exec',name,'redis-cli','--raw','AUTH','default','irrelevant'])
  assert 'NOAUTH'in unauth and 'WRONGPASS'in default_auth
  return {'case':label,'state_before':before.splitlines(),'state_after':after.splitlines(),'persisted':after==before,'ttl_before_ms':ttl_before,'ttl_after_ms':ttl_after,'expiry_preserved':0<ttl_after<=ttl_before,'aof_acl_errors':logs.count('AOF-loading-client'),'unauthenticated_denied':True,'default_login_denied':True,'outside_namespace_denied':True,'container':name,'volume_preserved':volume,'restart_count':obj['RestartCount']}
 finally:run(['docker','stop','-t','3',name])

def main():
 source=(ROOT/'infra/phase4/init_config.py').read_text();start=source.index("f'user default ")+2;default=source[start:source.index('\\n',start)]
 baseline=case('user default off','previous')
 current=case(default,'current')
 result={'baseline':baseline,'current':current,'no_retained_stack_mutation':True,'no_volume_deletion':True}
 (ROOT/'docs/phase-10/evidence/redis-aof-regression.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result,indent=2));assert current['persisted']and current['expiry_preserved']and current['aof_acl_errors']==0,'Admission Lua state must survive AOF replay'
if __name__=='__main__':main()
