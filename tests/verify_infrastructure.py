"""Real Compose checks; --failure briefly stops PostgreSQL and always restores it.

Run only against this synthetic development stack. No domain rows are created.
"""

from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DOMAINS = (
    "patient",
    "doctor",
    "appointment",
    "records",
    "pharmacy",
    "billing",
    "emergency",
)
PREFIXES = dict(
    zip(
        DOMAINS,
        (
            "patients",
            "doctors",
            "appointments",
            "records",
            "pharmacy",
            "billing",
            "emergencies",
        ),
    )
)


def compose(*args, code=None):
    result = subprocess.run(
        ["docker", "compose", *args],
        cwd=ROOT,
        input=code,
        text=True,
        capture_output=True,
        timeout=180,
    )
    if result.returncode:
        # Do not relay database exceptions/URLs containing private credentials.
        raise RuntimeError(f"Compose command failed: {' '.join(args)}")
    return result.stdout.strip()


def gateway_url():
    port = os.environ.get("GATEWAY_PORT")
    if not port:
        values = dict(
            line.split("=", 1)
            for line in (ROOT / ".env").read_text().splitlines()
            if line and not line.startswith("#")
        )
        port = values.get("GATEWAY_PORT", "8080")
    return f"http://127.0.0.1:{port}"


def request(path, headers=None):
    try:
        with urlopen(
            Request(gateway_url() + path, headers=headers or {}), timeout=6
        ) as response:
            return response.status, json.load(response), response.headers
    except HTTPError as response:
        raw = response.read()
        try:
            body = json.loads(raw)
        except ValueError:
            body = {}
        return response.code, body, response.headers


def wait_readiness(status, timeout=60):
    deadline = time.monotonic() + timeout
    pending = set(DOMAINS)
    while pending and time.monotonic() < deadline:
        for domain in tuple(pending):
            try:
                code, body, _ = request(f"/api/v1/{PREFIXES[domain]}/health/ready")
                if code == status and body.get("service") == domain:
                    pending.remove(domain)
            except (URLError, TimeoutError):
                pass
        if pending:
            time.sleep(1)
    assert not pending, f"Readiness did not reach {status}: {sorted(pending)}"


DATABASE_CODE = """
import json
import asyncio
from types import SimpleNamespace
import psycopg
from sqlalchemy import create_engine, inspect, text, CheckConstraint, UniqueConstraint
from sqlalchemy.exc import IntegrityError
from DOMAIN_service.settings import Settings
from DOMAIN_service.models import metadata
from DOMAIN_service.database import Database, get_database_session
s=Settings.from_env()
engine=create_engine(s.database_url,connect_args=s.connection_options,hide_parameters=True)
with engine.connect() as c:
    assert c.scalar(text('SELECT current_database()')) == 'DOMAIN_db'
    assert c.scalar(text('SELECT current_user')) == 'DOMAIN_app'
    assert c.scalar(text('SELECT 1')) == 1
    flags=c.execute(text('SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname=current_user')).one()
    assert not any(flags)
    assert not c.scalar(text("SELECT has_schema_privilege(current_user,'public','CREATE')"))
    assert not c.scalar(text("SELECT has_database_privilege(current_user,current_database(),'TEMP')"))
    assert c.scalar(text('SELECT version_num FROM alembic_version')) == ('0003_explicit_worker' if 'DOMAIN' == 'doctor' else '0002_explicit_worker')
    inspector=inspect(c)
    assert set(inspector.get_table_names()) == set(metadata.tables) | {'alembic_version'}
    assert inspector.get_sequence_names()==[], 'Worker/domain IDs must not use database sequences'
    assert next(col for col in inspector.get_columns('id_worker_state') if col['name']=='worker_id')['default'] is None
    counts={}
    for t in metadata.sorted_tables:
        cols={col['name']:col for col in inspector.get_columns(t.name)}
        assert set(cols) == set(t.c.keys()), t.name
        for col in t.c:
            assert cols[col.name]['nullable'] == col.nullable, (t.name,col.name)
            assert str(cols[col.name]['type'].compile(dialect=engine.dialect)) == str(col.type.compile(dialect=engine.dialect)), (t.name,col.name)
        assert inspector.get_pk_constraint(t.name)['constrained_columns'] == [col.name for col in t.primary_key.columns],t.name
        fks=inspector.get_foreign_keys(t.name)
        assert len(fks) == len(t.foreign_key_constraints),t.name
        for fk in fks:
            assert fk['referred_table'] in metadata.tables
            assert fk.get('referred_schema') in (None,'public')
            assert fk['options'].get('ondelete') == 'RESTRICT'
        assert len(inspector.get_check_constraints(t.name)) == sum(isinstance(x,CheckConstraint) for x in t.constraints),t.name
        assert len(inspector.get_unique_constraints(t.name)) == sum(isinstance(x,UniqueConstraint) for x in t.constraints),t.name
        exclusions=set(c.scalars(text("SELECT conname FROM pg_constraint WHERE contype='x' AND conrelid=CAST(:table AS regclass)"),{'table':t.name}))
        assert exclusions == {x.name for x in t.constraints if x.__class__.__name__=='ExcludeConstraint'},t.name
        actual={i['name']:i for i in inspector.get_indexes(t.name) if not i.get('duplicates_constraint') and i['name'] not in exclusions}
        assert set(actual) == {i.name for i in t.indexes},t.name
        for i in t.indexes:
            assert actual[i.name]['unique'] == i.unique
            assert actual[i.name]['column_names'] == [col.name for col in i.columns]
            assert bool(actual[i.name].get('dialect_options',{}).get('postgresql_where')) == (i.dialect_options['postgresql']['where'] is not None)
        assert c.scalar(text('SELECT count(*) FROM "'+t.name+'"')) == 0, 'Verifier expects an empty foundation database'
        counts[t.name]=len(cols)
    for table in ('audit_entries','audit_heads','alembic_version'):
        for privilege in ('INSERT','UPDATE','DELETE','TRUNCATE'):
            assert not c.scalar(text("SELECT has_table_privilege(current_user,:table,:privilege)"),{'table':table,'privilege':privilege})
    for table in set(metadata.tables)-{'audit_entries','audit_heads'}:
        for privilege in ('SELECT','INSERT','UPDATE','DELETE'):
            assert c.scalar(text("SELECT has_table_privilege(current_user,:table,:privilege)"),{'table':table,'privilege':privilege})
# Exercise the documented Doctor exclusion with rolled-back synthetic fixtures.
    if 'DOMAIN' == 'doctor':
        c.execute(text("INSERT INTO doctors(id,staff_user_id,display_name) VALUES (1,1,'Constraint test')"))
        c.execute(text("INSERT INTO schedule_versions(id,doctor_id,revision,timezone,slot_minutes,effective_from,status) VALUES (2,1,1,'UTC',15,CURRENT_TIMESTAMP,'pending')"))
        c.execute(text("INSERT INTO schedule_intervals(id,schedule_version_id,starts_at,ends_at) VALUES (3,2,'2030-01-01T10:00:00Z','2030-01-01T11:00:00Z')"))
        try:
            with c.begin_nested():
                c.execute(text("INSERT INTO schedule_intervals(id,schedule_version_id,starts_at,ends_at) VALUES (4,2,'2030-01-01T10:30:00Z','2030-01-01T11:30:00Z')"))
            raise AssertionError('Doctor overlap unexpectedly accepted')
        except IntegrityError as error:
            assert error.orig.sqlstate == '23P01'
        c.rollback()
        assert c.scalar(text('SELECT count(*) FROM doctors'))==0
engine.dispose()
async def session_cleanup():
    db=Database(s)
    await db.start()
    try:
        dependency=get_database_session(SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(database=db))))
        session=await anext(dependency)
        assert await session.scalar(text('SELECT 1'))==1
        await session.execute(text('INSERT INTO id_worker_state(worker_id,reserved_through_ms) VALUES (0,0)'))
        await dependency.aclose()  # Request cleanup must roll back uncommitted work.
        async with db.session_factory() as fresh:
            assert await fresh.scalar(text('SELECT count(*) FROM id_worker_state'))==0
    finally:
        await db.close()
    assert db.engine is None and db.session_factory is None
asyncio.run(session_cleanup())
denied=0
for other in ('patient','doctor','appointment','records','pharmacy','billing','emergency'):
    if other == 'DOMAIN':
        continue
    try:
        with psycopg.connect(host=s.db_host,port=s.db_port,dbname=other+'_db',user=s.db_user,password=s.db_password,connect_timeout=2):
            raise AssertionError('Cross-service connection unexpectedly succeeded')
    except psycopg.OperationalError as error:
        assert 'permission denied for database' in str(error), 'Connection failed for a reason other than isolation'
        denied+=1
print(json.dumps({'service':'DOMAIN','tables':len(counts),'denied_connections':denied,'schema_constraints':'verified'}))
"""


def verify_databases():
    for domain in DOMAINS:
        print(
            compose(
                "exec",
                "-T",
                domain,
                "python",
                "-",
                code=DATABASE_CODE.replace("DOMAIN", domain),
            )
        )
    # Both runtime and migration users must lack cross-database CONNECT.
    # PostgreSQL image has no Python; use SQL directly, no credentials in argv.
    sql = "SELECT count(*) FROM pg_roles r CROSS JOIN pg_database d WHERE r.rolname ~ '^(patient|doctor|appointment|records|pharmacy|billing|emergency)_(app|migration)$' AND d.datname <> split_part(r.rolname,'_',1)||'_db' AND has_database_privilege(r.oid,d.oid,'CONNECT');"
    assert (
        compose(
            "exec",
            "-T",
            "postgres",
            "sh",
            "-c",
            'psql -U "$POSTGRES_USER" -d postgres -Atc "$1"',
            "check",
            sql,
        )
        == "0"
    )
    print(
        "PASS: all 14 runtime/migration roles have CONNECT only to their owned database"
    )


def verify_gateway():
    for domain in DOMAINS:
        for kind in ("live", "ready"):
            status, body, headers = request(f"/api/v1/{PREFIXES[domain]}/health/{kind}")
            assert status == 200 and body["service"] == domain
            assert headers["x-request-id"] and headers["x-correlation-id"]
        # The prefix must match its complete path segment.
        assert request(f"/api/v1/{PREFIXES[domain]}-collision/health/live")[0] == 404
    # Reserved paths route to their future owner, which returns the safe API envelope.
    for path in ("/api/v1/auth/login", "/s/reserved"):
        status, body, _ = request(path)
        assert status == 404 and "error" in body
    for path in (
        "/internal/v1/anything",
        "/dashboard/",
        "/api/rawdata",
        "/docs",
        "/health/live",
    ):
        status, body, _ = request(path)
        assert status == 404 and "error" not in body
    assert (
        request("/api/v1/patients/health/live", {"X_Forwarded_Host": "spoof.example"})[
            0
        ]
        == 400
    )
    assert (
        request(
            "/api/v1/patients/health/live/",
            {"X-Forwarded-Proto": "https", "X-Forwarded-Host": "spoof.example"},
        )[0]
        == 200
    )
    print(
        "PASS: seven gateway routes, preserved health paths, reserved auth/short-link routes, collision/admin/internal rejection"
    )


def failure_test():
    started = time.monotonic()
    try:
        compose("stop", "postgres")
        wait_readiness(503)
        for domain in DOMAINS:
            status, body, _ = request(f"/api/v1/{PREFIXES[domain]}/health/ready")
            assert (
                status == 503
                and body["dependencies"]["database"]["status"] == "unavailable"
            )
            assert request(f"/api/v1/{PREFIXES[domain]}/health/live")[0] == 200
        print(
            "PASS: all seven readiness checks return 503 during PostgreSQL outage; liveness remains 200"
        )
    finally:
        compose("start", "postgres")
        wait_readiness(200)
    print(
        f"PASS: PostgreSQL restored and seven pools recovered; controlled test duration {time.monotonic()-started:.1f}s; volumes preserved"
    )


def shutdown_test():
    since = datetime.now(timezone.utc).isoformat()
    try:
        compose("stop", *DOMAINS)
        for domain in DOMAINS:
            container = compose("ps", "-aq", domain)
            result = subprocess.run(
                ["docker", "inspect", container, "--format", "{{.State.ExitCode}}"],
                capture_output=True,
                text=True,
                check=True,
            )
            assert result.stdout.strip() in ("0", "143"), domain
            logs = compose("logs", "--no-color", "--since", since, domain)
            assert "Application shutdown complete" in logs, domain
            assert "Traceback" not in logs, domain
            print(
                f"PASS: {domain} application shutdown complete; container exit {result.stdout.strip()}"
            )
    finally:
        compose("up", "-d")
        wait_readiness(200)
    print("PASS: seven services restarted and ready; volumes preserved")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--failure",
        action="store_true",
        help="Stop only development PostgreSQL temporarily, then restore it",
    )
    parser.add_argument(
        "--shutdown",
        action="store_true",
        help="Stop/restart the seven development API containers and verify graceful shutdown",
    )
    args = parser.parse_args()
    wait_readiness(200)
    verify_databases()
    verify_gateway()
    if args.failure:
        failure_test()
        verify_databases()
    if args.shutdown:
        shutdown_test()
        verify_gateway()
    print("Infrastructure verification passed")
