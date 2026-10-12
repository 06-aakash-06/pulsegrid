"""Forward migrations and safe downgrade refusal on invocation-owned empty databases."""
import os,sys,tempfile,subprocess,socket,json
from pathlib import Path
import psycopg
from psycopg import sql
ROOT=Path(__file__).resolve().parents[2]
bases={'doctor':'0004_phase3_schedule','pharmacy':'0004_phase3_stock','appointment':'0009_phase3_workflow','billing':'0004_phase3_workflow'}
# Resolve the reviewed actual Phase 3 heads from the new chain, not guessed aliases.
from alembic.config import Config
from alembic.script import ScriptDirectory
for owner in bases:
 cfg=Config(str(ROOT/'services'/owner/'alembic.ini'));cfg.set_main_option('script_location',str(ROOT/'services'/owner/'migrations'))
 script=ScriptDirectory.from_config(cfg);new=next(r for r in script.walk_revisions() if str(r.revision).startswith('0010_' if owner=='appointment' else '0005_'));bases[owner]=new.down_revision
results=[]
with tempfile.TemporaryDirectory(prefix='pulsegrid-phase4-migrations-') as t:
 path=Path(t)
 with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
 subprocess.run(['initdb','-D',str(path/'data'),'-A','trust','--no-locale','--encoding=UTF8'],check=True,stdout=subprocess.DEVNULL)
 subprocess.run(['pg_ctl','-D',str(path/'data'),'-l',str(path/'log'),'-o',f"-h 127.0.0.1 -p {port} -k ''",'-w','start'],check=True,stdout=subprocess.DEVNULL)
 try:
  for owner,base in bases.items():
   name=owner+'_roundtrip'
   with psycopg.connect(host='127.0.0.1',port=port,dbname='postgres',autocommit=True) as c:
    c.execute(sql.SQL('CREATE ROLE {} LOGIN').format(sql.Identifier(owner+'_migration')));c.execute(sql.SQL('CREATE ROLE {} LOGIN').format(sql.Identifier(owner+'_app')));c.execute(sql.SQL('GRANT {} TO {}').format(sql.Identifier(owner+'_app'),sql.Identifier(owner+'_migration')));c.execute(sql.SQL('CREATE DATABASE {} OWNER {}').format(sql.Identifier(name),sql.Identifier(owner+'_migration')))
   env={k:v for k,v in os.environ.items() if not k.startswith('PULSEGRID_')};env.update({f'PULSEGRID_{owner.upper()}_{k}':str(v) for k,v in {'DB_HOST':'127.0.0.1','DB_PORT':port,'DB_NAME':name,'DB_USER':owner+'_migration','DB_PASSWORD':'roundtrip'}.items()})
   for op,rev in [('upgrade',base),('upgrade','head')]:
    subprocess.run([sys.executable,'-m','alembic',op,rev],cwd=ROOT/'services'/owner,env=env,check=True,stdout=subprocess.DEVNULL)
   with psycopg.connect(host='127.0.0.1',port=port,dbname=name) as c:head=c.execute('SELECT version_num FROM alembic_version').fetchone()[0]
   refused=subprocess.run([sys.executable,'-m','alembic','downgrade',base],cwd=ROOT/'services'/owner,env=env,text=True,capture_output=True)
   assert refused.returncode and 'Forward-only' in refused.stderr
   with psycopg.connect(host='127.0.0.1',port=port,dbname=name) as c:assert c.execute('SELECT version_num FROM alembic_version').fetchone()[0]==head
   subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=ROOT/'services'/owner,env=env,check=True,stdout=subprocess.DEVNULL)
   results.append({'owner':owner,'phase3_head':base,'phase4_head':head,'forward':'pass','downgrade':'safely refused; durable history forward-only','head_preserved':True,'database':'disposable empty'})
 finally:subprocess.run(['pg_ctl','-D',str(path/'data'),'-m','fast','-w','stop'],check=True,stdout=subprocess.DEVNULL)
Path('experiments/phase4/integration/results/migrations.json').write_text(json.dumps(results,indent=2));print('PASS four disposable forward chains and atomic downgrade refusal')
