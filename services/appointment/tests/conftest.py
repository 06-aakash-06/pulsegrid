"""Disposable PostgreSQL cluster; never connects to an existing database."""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import sys
import pytest
import psycopg
from appointment_service.settings import Settings

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope='session')
def postgres_cluster():
    executable=shutil.which('initdb')
    if not executable:
        pytest.skip('BLOCKER: PostgreSQL initdb unavailable; real concurrency not verified')
    bindir=Path(executable).parent
    base=ROOT/'.test-runtime'
    base.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base) as directory:
        path=Path(directory)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0))
            port=listener.getsockname()[1]
        subprocess.run([executable,'-D',str(path/'data'),'-U','appointment_owner','-A','trust','--no-locale','--encoding=UTF8'],check=True,capture_output=True)
        subprocess.run([str(bindir/'pg_ctl'),'-D',str(path/'data'),'-l',str(path/'postgres.log'),'-o',
            f"-h 127.0.0.1 -p {port} -c unix_socket_directories=''", '-w','start'],check=True,capture_output=True)
        try:
            with psycopg.connect(host='127.0.0.1',port=port,user='appointment_owner',dbname='postgres',autocommit=True) as conn:
                conn.execute("CREATE ROLE appointment_app LOGIN PASSWORD 'isolated-test-only'")
            yield port
        finally:
            subprocess.run([str(bindir/'pg_ctl'),'-D',str(path/'data'),'-m','fast','-w','stop'],check=True,capture_output=True)
    base.rmdir()


@pytest.fixture
def database(postgres_cluster):
    import uuid
    port=postgres_cluster
    name='appointment_test_'+uuid.uuid4().hex
    with psycopg.connect(host='127.0.0.1',port=port,user='appointment_owner',dbname='postgres',autocommit=True) as conn:
        conn.execute(psycopg.sql.SQL('CREATE DATABASE {}').format(psycopg.sql.Identifier(name)))
    settings=Settings(db_host='127.0.0.1',db_port=port,db_name=name,db_user='appointment_app',
        db_password='isolated-test-only',db_pool_size=20,db_max_overflow=0,db_statement_timeout_ms=10000)
    env=dict(os.environ,PULSEGRID_APPOINTMENT_DB_HOST='127.0.0.1',PULSEGRID_APPOINTMENT_DB_PORT=str(port),
        PULSEGRID_APPOINTMENT_DB_NAME=name,PULSEGRID_APPOINTMENT_DB_USER='appointment_owner',
        PULSEGRID_APPOINTMENT_DB_PASSWORD='isolated-test-only')
    subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=ROOT,env=env,check=True,capture_output=True)
    with psycopg.connect(host='127.0.0.1',port=port,user='appointment_owner',dbname=name) as conn:
        conn.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
        conn.execute('GRANT USAGE ON SCHEMA public TO appointment_app')
        conn.execute('GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO appointment_app')
        conn.execute('REVOKE ALL ON audit_heads,audit_entries,alembic_version FROM appointment_app')
        conn.execute('GRANT SELECT ON audit_heads,audit_entries,alembic_version TO appointment_app')
    yield settings
    with psycopg.connect(host='127.0.0.1',port=port,user='appointment_owner',dbname='postgres',autocommit=True) as conn:
        conn.execute(psycopg.sql.SQL('DROP DATABASE {} WITH (FORCE)').format(psycopg.sql.Identifier(name)))
