"""Retained synthetic 0003 upgrade and dormant-data stop, in isolated DBs only."""
import os
from contextlib import contextmanager
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def retained_database(port):
    name = 'appointment_upgrade_' + uuid4().hex
    kwargs = dict(host='127.0.0.1',port=port,user='appointment_owner',dbname=name)
    with psycopg.connect(**{**kwargs,'dbname':'postgres'},autocommit=True) as conn:
        conn.execute(psycopg.sql.SQL('CREATE DATABASE {}').format(psycopg.sql.Identifier(name)))
    env = dict(os.environ, PULSEGRID_APPOINTMENT_DB_HOST='127.0.0.1',
        PULSEGRID_APPOINTMENT_DB_PORT=str(port), PULSEGRID_APPOINTMENT_DB_NAME=name,
        PULSEGRID_APPOINTMENT_DB_USER='appointment_owner', PULSEGRID_APPOINTMENT_DB_PASSWORD='isolated-test-only')
    def migrate(revision):
        return subprocess.run([sys.executable,'-m','alembic','upgrade',revision],
                              cwd=ROOT,env=env,capture_output=True,text=True)
    try:
        result=migrate('0003_booking')
        assert result.returncode==0,result.stderr
        with psycopg.connect(**kwargs) as conn:
            conn.execute("""INSERT INTO doctor_schedule_snapshots
              (doctor_id,accepted_revision,policy_snapshot,staff_user_id,last_decided_proposal_revision)
              VALUES (1,1,'{}',101,1)""")
            conn.execute("""INSERT INTO slots(id,doctor_id,schedule_revision,starts_at,ends_at,state)
              VALUES (1,1,1,now()+interval '2 days',now()+interval '2 days 30 minutes','bookable')""")
            conn.execute("""INSERT INTO appointments(id,patient_id,slot_id,doctor_id,doctor_user_id,
              starts_at,ends_at,schedule_revision,state)
              SELECT 100,11,id,doctor_id,101,starts_at,ends_at,schedule_revision,'confirmed' FROM slots""")
            conn.execute("""SELECT appointment_append_audit(101,jsonb_build_object(
              'action','booked','result','success','actor_user_id','11','resource_id','100',
              'request_id',%s::text,'correlation_id',%s::text,'occurred_at','2026-10-11T00:00:00Z'))""",(str(uuid4()),str(uuid4())))
            conn.execute("""INSERT INTO outbox_events(event_id,aggregate_type,aggregate_id,aggregate_version,event_type,envelope)
              VALUES (102,'appointment',100,1,'appointment.booked.v1','{}')""")
            conn.execute("""INSERT INTO idempotency_requests VALUES
              ('user:11','POST','/api/v1/appointments','synthetic-key-0001','hash',201,'{}',now()+interval '1 day')""")
        yield kwargs,migrate
    finally:
        with psycopg.connect(**{**kwargs,'dbname':'postgres'},autocommit=True) as conn:
            conn.execute(psycopg.sql.SQL('DROP DATABASE {} WITH (FORCE)').format(psycopg.sql.Identifier(name)))


def snapshot(conn):
    return {table: conn.execute(psycopg.sql.SQL('SELECT * FROM {} ORDER BY 1').format(
        psycopg.sql.Identifier(table))).fetchall() for table in
        ('appointments','slots','doctor_schedule_snapshots','audit_heads','audit_entries',
         'outbox_events','idempotency_requests')}


def test_retained_upgrade_preserves_all_history(postgres_cluster):
    with retained_database(postgres_cluster) as (kwargs,migrate):
        with psycopg.connect(**kwargs) as conn:
            before=snapshot(conn)
        result=migrate('head')
        assert result.returncode==0,result.stderr
        with psycopg.connect(**kwargs) as conn:
            assert snapshot(conn)==before
            assert conn.execute('SELECT version_num FROM alembic_version').fetchone()==('0008_phase3_journey',)
            assert conn.execute('SELECT count(*) FROM appointment_workflows').fetchone()==(0,)
            assert conn.execute("SELECT has_table_privilege('appointment_app','appointment_workflows','INSERT')").fetchone()==(True,)
            constraints=conn.execute("SELECT conname FROM pg_constraint WHERE conrelid='appointments'::regclass").fetchall()
            assert ('appointments_patient_overlap',) in constraints


@pytest.mark.parametrize('table', ['waitlist_entries','checkin_links','queue_counters','queue_entries','journeys','journey_stages'])
def test_unexpected_dormant_data_blocks_upgrade_without_deletion(postgres_cluster,table):
    with retained_database(postgres_cluster) as (kwargs,migrate):
        with psycopg.connect(**kwargs) as conn:
            sql={
                'waitlist_entries': "INSERT INTO waitlist_entries(id,slot_id,patient_id,state) VALUES (200,1,12,'waiting')",
                'checkin_links': "INSERT INTO checkin_links(id,appointment_id,token_hash,purpose,expires_at) VALUES (200,100,repeat('a',64),'check_in',now()+interval '1 day')",
                'queue_counters': "INSERT INTO queue_counters(doctor_id,local_date) VALUES (1,current_date)",
                'queue_entries': "INSERT INTO queue_entries(id,appointment_id,doctor_id,local_date,token_number,state) VALUES (200,100,1,current_date,1,'waiting')",
                'journeys': "INSERT INTO journeys(id,appointment_id,patient_id,state) VALUES (200,100,11,'active')",
                'journey_stages': "INSERT INTO journeys(id,appointment_id,patient_id,state) VALUES (200,100,11,'active'); INSERT INTO journey_stages(journey_id,stage,state,observed_at) VALUES (200,'appointment','complete',now())",
            }
            conn.execute(sql[table])
            before=snapshot(conn)
        result=migrate('head')
        assert result.returncode!=0 and 'Unexpected dormant feature data' in result.stderr
        with psycopg.connect(**kwargs) as conn:
            assert snapshot(conn)==before
            assert conn.execute('SELECT version_num FROM alembic_version').fetchone()==('0003_booking',)
            assert conn.execute("SELECT to_regclass('appointment_workflows')").fetchone()==(None,)
            assert conn.execute(psycopg.sql.SQL('SELECT count(*) FROM {}').format(psycopg.sql.Identifier(table))).fetchone()==(1,)
