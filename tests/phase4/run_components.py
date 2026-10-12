"""Run component storage tests only on a cluster owned by this invocation."""
import os,sys,socket,subprocess,tempfile
from pathlib import Path
import psycopg
ROOT=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='pulsegrid-phase4-components-') as temp:
    path=Path(temp)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    subprocess.run(['initdb','-D',str(path/'data'),'-A','trust','--no-locale','--encoding=UTF8'],check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['pg_ctl','-D',str(path/'data'),'-l',str(path/'postgres.log'),'-o',f"-h 127.0.0.1 -p {port} -k ''",'-w','start'],check=True,stdout=subprocess.DEVNULL)
    try:
        dsn=f'postgresql://127.0.0.1:{port}/postgres'
        with psycopg.connect(dsn,autocommit=True) as c:
            c.execute('CREATE TABLE id_worker_state(worker_id bigint PRIMARY KEY,reserved_through_ms bigint NOT NULL)')
        env={**os.environ,'ID_TEST_DSN':dsn}
        result=subprocess.run([sys.executable,'-m','pytest','components','--import-mode=importlib','-q','-o','asyncio_mode=auto','--junitxml=/tmp/pulsegrid-phase4-components.xml'],env=env,cwd=ROOT)
    finally:
        subprocess.run(['pg_ctl','-D',str(path/'data'),'-m','fast','-w','stop'],check=True,stdout=subprocess.DEVNULL)
    raise SystemExit(result.returncode)
