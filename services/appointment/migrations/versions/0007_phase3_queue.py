"""Reviewed forward-only Phase 3 integration schema; no legacy row rewrites."""
from alembic import op

revision = '0007_phase3_queue'
down_revision = '0006_phase3_checkin'
branch_labels = depends_on = None


def upgrade():
    op.execute("""
DO $$ BEGIN IF EXISTS(SELECT FROM queue_entries) THEN RAISE EXCEPTION 'Review dormant queue entries before ranking upgrade'; END IF; END $$;
ALTER TABLE queue_entries ADD COLUMN position integer;
ALTER TABLE queue_entries DROP CONSTRAINT ck_queue_entries_state_values;
ALTER TABLE queue_entries ADD CONSTRAINT ck_queue_entries_state_values CHECK(state IN ('waiting','skipped','in_consultation','completed','cancelled','no_show'));
ALTER TABLE queue_entries ADD CONSTRAINT ck_queue_entries_position CHECK((state='waiting' AND position IS NOT NULL AND position>0) OR (state<>'waiting' AND position IS NULL)), ADD CONSTRAINT ck_queue_entries_safe_token CHECK(token_number BETWEEN 1 AND 9007199254740991), ADD CONSTRAINT ck_queue_entries_safe_version CHECK(version BETWEEN 1 AND 9007199254740991);
CREATE TABLE queue_snapshots(doctor_id bigint NOT NULL REFERENCES doctor_schedule_snapshots(doctor_id),local_date date NOT NULL,version bigint NOT NULL DEFAULT 1 CHECK(version BETWEEN 1 AND 9007199254740991),created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(doctor_id,local_date));
CREATE INDEX ix_queue_entries_waiting_fifo ON queue_entries(doctor_id,local_date,token_number,id) WHERE state='waiting';
CREATE TABLE queue_transitions(id bigserial PRIMARY KEY,entry_id bigint NOT NULL REFERENCES queue_entries(id),from_state varchar(32),to_state varchar(32) NOT NULL,occurred_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,version bigint NOT NULL,UNIQUE(entry_id,version));
CREATE FUNCTION queue_record_transition() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$ BEGIN
 IF TG_OP='INSERT' OR OLD.state IS DISTINCT FROM NEW.state THEN INSERT INTO queue_transitions(entry_id,from_state,to_state,version) VALUES (NEW.id,CASE WHEN TG_OP='UPDATE' THEN OLD.state ELSE NULL END,NEW.state,NEW.version); END IF; RETURN NEW; END $$;
CREATE TRIGGER queue_record_transition AFTER INSERT OR UPDATE ON queue_entries FOR EACH ROW EXECUTE FUNCTION queue_record_transition();
GRANT SELECT,INSERT,UPDATE ON queue_snapshots TO appointment_app; GRANT SELECT ON queue_transitions TO appointment_app;
""")


def downgrade():
    raise RuntimeError("Forward-only; preserve workflow history")
