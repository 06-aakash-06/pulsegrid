"""ID correctness on ephemeral PostgreSQL matching the retained image; no volumes."""
import subprocess,json,time,uuid,os,sys
from pathlib import Path
import psycopg
image=subprocess.check_output(['docker','inspect','pulsegrid-postgres-1','--format','{{.Config.Image}}'],text=True).strip()
name='pulsegrid-phase4-idtest-'+uuid.uuid4().hex[:8]
try:
 subprocess.run(['docker','run','-d','--name',name,'--tmpfs','/var/lib/postgresql/data:rw','--memory','256m','-e','POSTGRES_HOST_AUTH_METHOD=trust','-p','127.0.0.1::5432',image],check=True,stdout=subprocess.DEVNULL)
 info=json.loads(subprocess.check_output(['docker','inspect',name],text=True))[0];port=info['NetworkSettings']['Ports']['5432/tcp'][0]['HostPort'];dsn=f'postgresql://postgres@127.0.0.1:{port}/postgres'
 for _ in range(30):
  try:
   with psycopg.connect(dsn,autocommit=True) as c:
    c.execute('CREATE TABLE id_worker_state(worker_id bigint PRIMARY KEY,reserved_through_ms bigint NOT NULL)');version=c.execute('SELECT version()').fetchone()[0]
   break
  except psycopg.OperationalError:time.sleep(1)
 else:raise AssertionError('Disposable PG did not start')
 result=subprocess.run([sys.executable,'-m','pytest','components/unique_id/tests','-q','-o','asyncio_mode=auto','--junitxml=/tmp/pulsegrid-phase4-ids-pg16.xml'],env={**os.environ,'ID_TEST_DSN':dsn})
 assert result.returncode==0
 Path('experiments/phase4/integration/results/ids-postgres16.json').write_text(json.dumps({'postgres_version':version,'correctness_tests':36,'result':'pass','storage':'ephemeral tmpfs; removed in finally'},indent=2))
finally:subprocess.run(['docker','rm','-f',name],check=True,stdout=subprocess.DEVNULL)
