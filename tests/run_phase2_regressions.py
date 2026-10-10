"""Run colocated suites against disposable local PostgreSQL, never Compose DBs.

Requires installed service test extras plus local initdb/pg_ctl. Appointment and
Records retain their own isolated cluster fixtures. No persistent data reset.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
DOMAINS = ('patient', 'doctor', 'appointment', 'records', 'pharmacy', 'billing', 'emergency')


def main():
    bindir = Path(shutil.which('initdb') or '')
    if not bindir.is_file():
        raise SystemExit('initdb unavailable: PostgreSQL verification not performed')
    bindir = bindir.parent
    with tempfile.TemporaryDirectory(prefix='pulsegrid-phase29-tests-') as temporary:
        path = Path(temporary)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        subprocess.run([str(bindir/'initdb'), '-D', str(path/'data'), '-A', 'trust', '--no-locale', '--encoding=UTF8'], check=True, stdout=subprocess.DEVNULL)
        subprocess.run([str(bindir/'pg_ctl'), '-D', str(path/'data'), '-l', str(path/'postgres.log'), '-o', f"-h 127.0.0.1 -p {port} -k ''", '-w', 'start'], check=True, stdout=subprocess.DEVNULL)
        env = {k:v for k,v in os.environ.items() if not k.startswith('PULSEGRID_')}
        env['PYTHONPATH'] = os.pathsep.join(str(ROOT/'services'/d) for d in DOMAINS)
        env['PATH'] = str(bindir)+os.pathsep+env['PATH']
        database_names = {'patient':'patient_management_test','doctor':'pulsegrid_doctor_test_phase29','pharmacy':'pharmacy_phase29_test','billing':'billing_phase29_test','emergency':'emergency_phase29_test'}
        variable_names = {'patient':'PULSEGRID_PATIENT_MANAGEMENT_TEST_DB_URL','doctor':'PULSEGRID_DOCTOR_TEST_DATABASE_URL','pharmacy':'PULSEGRID_PHARMACY_TEST_DATABASE_URL','billing':'PULSEGRID_BILLING_TEST_DATABASE_URL','emergency':'PULSEGRID_EMERGENCY_TEST_DATABASE_URL'}
        try:
            for domain,name in database_names.items():
                with psycopg.connect(host='127.0.0.1',port=port,dbname='postgres',autocommit=True) as connection:
                    for suffix,password in [('migration','migration-test'),('app','runtime-test')]:
                        connection.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(domain+'_'+suffix),sql.Literal(password)))
                    connection.execute(sql.SQL('GRANT {} TO {}').format(sql.Identifier(domain+'_app'),sql.Identifier(domain+'_migration')))
                    connection.execute(sql.SQL('CREATE DATABASE {} OWNER {}').format(sql.Identifier(name),sql.Identifier(domain+'_migration')))
                with psycopg.connect(host='127.0.0.1',port=port,dbname=name,autocommit=True) as connection:
                    connection.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
                    connection.execute(sql.SQL('GRANT USAGE,CREATE ON SCHEMA public TO {}').format(sql.Identifier(domain+'_migration')))
                    connection.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(sql.Identifier(domain+'_app')))
                    connection.execute(sql.SQL('ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO {}').format(sql.Identifier(domain+'_migration'),sql.Identifier(domain+'_app')))
                migration_env = {**env, **{f'PULSEGRID_{domain.upper()}_{key}':str(value) for key,value in {'DB_HOST':'127.0.0.1','DB_PORT':port,'DB_NAME':name,'DB_USER':domain+'_migration','DB_PASSWORD':'migration-test'}.items()}}
                subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=ROOT/'services'/domain,env=migration_env,check=True)
                with psycopg.connect(host='127.0.0.1',port=port,dbname=name,autocommit=True) as connection:
                    connection.execute(sql.SQL('REVOKE ALL ON audit_heads,audit_entries,alembic_version FROM {}').format(sql.Identifier(domain+'_app')))
                    connection.execute(sql.SQL('GRANT SELECT ON audit_heads,audit_entries,alembic_version TO {}').format(sql.Identifier(domain+'_app')))
                # Some agent fixture seed/cleanup engines require the owner role;
                # Billing/Emergency explicitly exercise the runtime role.
                runtime = domain in {'billing','emergency'}
                user = domain+('_app' if runtime else '_migration')
                password = 'runtime-test' if runtime else 'migration-test'
                env[variable_names[domain]] = f'postgresql://{user}:{password}@127.0.0.1:{port}/{name}'
            env['PULSEGRID_AUTH_INTEGRATION'] = '1'
            env['PULSEGRID_PATIENT_AUTH_TEST_DATABASE_URL'] = f'postgresql://patient_app:runtime-test@127.0.0.1:{port}/patient_management_test'
            result = subprocess.run([sys.executable,'-m','pytest',str(ROOT/'services'),'-q','-ra','-o','addopts=','--junitxml=/tmp/pulsegrid-phase29-backend.xml',*sys.argv[1:]],cwd=ROOT,env=env)
            # Records requires its service-local path-verified isolated cluster.
            records = subprocess.run([sys.executable,'tests/run_isolated.py','-q','-ra','-o','addopts=','--junitxml=/tmp/pulsegrid-phase29-records.xml'],cwd=ROOT/'services/records',env=env)
            return result.returncode or records.returncode
        finally:
            subprocess.run([str(bindir/'pg_ctl'),'-D',str(path/'data'),'-m','fast','-w','stop'],check=True,stdout=subprocess.DEVNULL)


if __name__ == '__main__':
    raise SystemExit(main())
