"""Read-only Phase 2 Compose schema, isolation, gateway and route checks.

Run against the existing stack. Never resets tables, volumes or databases.
Route checks compare frozen method/path entries with running service OpenAPI;
they complement, rather than replace, request/response and authorization tests.
"""
import json
from pathlib import Path
import re
import subprocess
from types import SimpleNamespace
import verify_infrastructure as foundation

ROOT = Path(__file__).resolve().parents[1]
DOMAINS = foundation.DOMAINS
PREFIXES = foundation.PREFIXES

def compose(*args, code=None):
    result = subprocess.run(['docker','compose','-f','compose.yaml','-f','services/patient/compose.auth.yaml',*args],cwd=ROOT,input=code,text=True,capture_output=True,timeout=60)
    if result.returncode:
        raise RuntimeError('Compose verification failed: '+str(args[:4])+'; '+result.stderr[-1500:])
    return result.stdout.strip()

CODE = r'''
import json,sys,re
import psycopg
from sqlalchemy import create_engine,inspect,text
from alembic.config import Config
from alembic.script import ScriptDirectory
from DOMAIN_service.settings import Settings
from DOMAIN_service.models import metadata
from DOMAIN_service.main import app
s=Settings.from_env()
engine=create_engine(s.database_url,connect_args=s.connection_options,hide_parameters=True)
with engine.connect() as c:
    c.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
    assert c.scalar(text('SELECT current_user'))=='DOMAIN_app'
    assert not any(c.execute(text('SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname=current_user')).one())
    assert not c.scalar(text("SELECT has_schema_privilege(current_user,'public','CREATE')"))
    assert not c.scalar(text("SELECT has_database_privilege(current_user,current_database(),'TEMP')"))
    revision=c.scalar(text('SELECT version_num FROM alembic_version'))
    assert revision==ScriptDirectory.from_config(Config('alembic.ini')).get_current_head()
    inspector=inspect(c)
    assert set(metadata.tables).issubset(inspector.get_table_names())
    for name,table in metadata.tables.items():
        columns={x['name']:x for x in inspector.get_columns(name)}
        assert set(columns)==set(table.c.keys()),name
        for col in table.c:
            assert columns[col.name]['nullable']==col.nullable,(name,col.name)
        for fk in inspector.get_foreign_keys(name):
            assert fk['referred_table'] in metadata.tables and fk.get('referred_schema') in (None,'public')
        expected_fks={(tuple(element.parent.name for element in fk.elements),fk.elements[0].column.table.name,tuple(element.column.name for element in fk.elements),fk.ondelete) for fk in table.foreign_key_constraints}
        actual_fks={(tuple(fk['constrained_columns']),fk['referred_table'],tuple(fk['referred_columns']),fk['options'].get('ondelete')) for fk in inspector.get_foreign_keys(name)}
        assert expected_fks==actual_fks,(name,'foreign key semantics')
        primary_key=inspector.get_pk_constraint(name)['constrained_columns']
        assert primary_key==[col.name for col in table.primary_key.columns],name
        actual_indexes={index['name'] for index in inspector.get_indexes(name)}
        assert {index.name for index in table.indexes}.issubset(actual_indexes),name
        # Raw-SQL migrations and SQLAlchemy assign different constraint names.
        expected_unique={tuple(col.name for col in constraint.columns) for constraint in table.constraints if constraint.__class__.__name__=='UniqueConstraint'}
        actual_unique={tuple(constraint['column_names']) for constraint in inspector.get_unique_constraints(name)}
        for index in inspector.get_indexes(name):
            if not index['unique']:continue
            key=tuple(index['column_names'])
            # Expression indexes do not establish direct column uniqueness.
            if any(column is None for column in key):continue
            predicate=str(index.get('dialect_options',{}).get('postgresql_where','')).strip()
            # A one-column IS NOT NULL index has ordinary PostgreSQL UNIQUE
            # semantics: NULL legacy references do not conflict with each other.
            equivalent_null_filter=(len(key)==1 and predicate.strip('()')==key[0]+' IS NOT NULL')
            if not predicate or equivalent_null_filter:actual_unique.add(key)
        assert expected_unique.issubset(actual_unique),(name,'unique columns')
        expected_checks=sum(constraint.__class__.__name__=='CheckConstraint' for constraint in table.constraints)
        assert len(inspector.get_check_constraints(name))>=expected_checks,(name,'check constraints')
    for table in ('audit_entries','audit_heads','alembic_version'):
        for privilege in ('INSERT','UPDATE','DELETE','TRUNCATE'):
            assert not c.scalar(text("SELECT has_table_privilege(current_user,:table,:privilege)"),{'table':table,'privilege':privilege})
    if 'DOMAIN'=='appointment':
        constraints=set(c.scalars(text("SELECT conname FROM pg_constraint WHERE contype='x'")))
        expected={x.name for table in metadata.tables.values() for x in table.constraints if x.__class__.__name__=='ExcludeConstraint'}
        assert expected and expected.issubset(constraints)
    if 'DOMAIN'=='pharmacy':
        import hashlib
        from pharmacy_service.operations import _canonical
        for prev_hash,entry_hash,metadata_value in c.execute(text('SELECT prev_hash,entry_hash,canonical_metadata FROM audit_entries')):
            assert hashlib.sha256(prev_hash.encode('ascii')+_canonical(metadata_value)).hexdigest()==entry_hash
    else:
        invalid=c.scalar(text("SELECT count(*) FROM audit_entries WHERE entry_hash <> encode(sha256(convert_to(prev_hash || canonical_metadata::text,'UTF8')),'hex')"))
        assert invalid==0,'Audit digest mismatch'

    chains=c.execute(text("SELECT chain_id,sequence,prev_hash,entry_hash FROM audit_entries ORDER BY chain_id,sequence")).all()
    heads={x[0]:(x[1],x[2]) for x in c.execute(text('SELECT chain_id,last_sequence,last_hash FROM audit_heads'))}
    previous={}
    for chain,sequence,prev_hash,entry_hash in chains:
        last,expected=previous.get(chain,(0,'0'*64))
        assert sequence==last+1 and prev_hash==expected
        previous[chain]=(sequence,entry_hash)
    assert all(heads[chain]==value for chain,value in previous.items())
    outbox=c.scalar(text('SELECT count(*) FROM outbox_events'))
    assert outbox>0 and chains,'Expected retained synthetic workflow evidence'
    exclusions=len(list(c.scalars(text("SELECT conname FROM pg_constraint WHERE contype='x'"))))
engine.dispose()
denied=0
for other in ('patient','doctor','appointment','records','pharmacy','billing','emergency'):
    if other=='DOMAIN':continue
    try:
        with psycopg.connect(host=s.db_host,port=s.db_port,dbname=other+'_db',user=s.db_user,password=s.db_password,connect_timeout=2):
            raise AssertionError('Foreign database connection succeeded')
    except psycopg.OperationalError as e:
        assert 'permission denied for database' in str(e)
        denied+=1
normalize=lambda p:re.sub(r'\{[^}]+\}','{}',p)
actual={(method,normalize(path)) for path,spec in app.openapi()['paths'].items() for method in spec if method.upper() in ('GET','POST','PATCH','DELETE')}
required=json.loads(sys.stdin.read())
missing=[(method,path) for method,path in required if (method.lower(),normalize(path)) not in actual]
assert not missing,missing
print(json.dumps({'service':'DOMAIN','migration':revision,'tables':len(metadata.tables),'exclusions':exclusions,'foreign_connections_denied':denied,'frozen_routes_present':len(required),'audit_entries_verified':len(chains),'outbox_rows':outbox}))
'''

def main():
    document=(ROOT/'docs/phase-2-api-contracts.md').read_text()
    required={d:set() for d in DOMAINS}
    for line in document.splitlines():
        match=re.match(r'\| (?:(Patient|Doctor|Appointment|Records|Pharmacy|Billing|Emergency) )?(GET|POST|PATCH|DELETE) `([^`]+)`',line)
        if not match:continue
        owner,method,path=match.groups()
        if owner:domain=owner.lower()
        else:
            domain='patient' if path.startswith('/api/v1/auth/') else next(d for d in DOMAINS if path.startswith('/api/v1/'+PREFIXES[d]))
        required[domain].add((method,path))
    for domain in DOMAINS:
        # The source is fixed verification code; required route data never includes credentials.
        source=CODE.replace('DOMAIN',domain).replace('required=json.loads(sys.stdin.read())','required='+repr(sorted(required[domain])))
        print(compose('exec','-T',domain,'python','-',code=source),flush=True)
    sql="SELECT count(*) FROM pg_roles r CROSS JOIN pg_database d WHERE r.rolname ~ '^(patient|doctor|appointment|records|pharmacy|billing|emergency)_(app|migration)$' AND d.datname <> split_part(r.rolname,'_',1)||'_db' AND has_database_privilege(r.oid,d.oid,'CONNECT');"
    assert compose('exec','-T','postgres','sh','-c','psql -U "$POSTGRES_USER" -d postgres -Atc "$1"','check',sql)=='0'
    print('PASS all fourteen database roles deny foreign CONNECT',flush=True)
    phase4=compose("exec","-T","appointment","python","-c","import os; print(os.environ.get('PULSEGRID_APPOINTMENT_PHASE4_SHORT_LINKS_ENABLED','false'))")=="true"
    foundation.args=SimpleNamespace(authentication=True,short_links=phase4)
    foundation.verify_gateway()
    statuses=[json.loads(x) for x in compose('ps','--format','json').splitlines()]
    assert all(x['State']=='running' and x['Health']=='healthy' for x in statuses)
    assert len(statuses)==(17 if phase4 else 11)
    print('PASS seven APIs, PostgreSQL, Redis, RabbitMQ and Traefik healthy',flush=True)

if __name__=='__main__':main()
