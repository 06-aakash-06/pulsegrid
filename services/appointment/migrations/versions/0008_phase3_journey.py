"""Reviewed forward-only Phase 3 integration schema; no legacy row rewrites."""
from alembic import op

revision = '0008_phase3_journey'
down_revision = '0007_phase3_queue'
branch_labels = depends_on = None


def upgrade():
    op.execute("""
CREATE TABLE journey_snapshots(journey_id bigint PRIMARY KEY REFERENCES journeys(id),records_revision bigint,pharmacy_revision bigint,billing_revision bigint,expected_source_keys jsonb NOT NULL DEFAULT '[]',review_required boolean NOT NULL DEFAULT false,last_reconciled_at timestamptz,lease_token varchar(64),lease_until timestamptz,next_attempt_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,attempts integer NOT NULL DEFAULT 0 CHECK(attempts>=0),sources jsonb NOT NULL DEFAULT '{}',pending_reasons jsonb NOT NULL DEFAULT '{}',last_error varchar(64));
CREATE TABLE journey_transitions(id bigserial PRIMARY KEY,journey_id bigint NOT NULL REFERENCES journeys(id),stage varchar(64),from_state varchar(64),to_state varchar(64) NOT NULL,occurred_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,effect_key varchar(256) NOT NULL UNIQUE);
CREATE INDEX ix_journey_snapshots_next_attempt_at ON journey_snapshots(next_attempt_at);
ALTER TABLE journey_stages ALTER COLUMN observed_at DROP NOT NULL;
ALTER TABLE journeys ADD CONSTRAINT ck_journey_state CHECK(state IN ('active','ready','discharged','reopened','cancelled','no_show'));
CREATE FUNCTION journey_record_transition() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
DECLARE jid bigint; stage_name varchar(64); previous varchar(64); effect varchar(256);
BEGIN
 IF TG_OP='UPDATE' THEN previous := OLD.state; END IF;
 IF TG_OP='INSERT' OR previous IS DISTINCT FROM NEW.state THEN
  IF TG_TABLE_NAME='journeys' THEN jid := NEW.id; stage_name := NULL;
  ELSE jid := NEW.journey_id; stage_name := NEW.stage; END IF;
  effect := TG_TABLE_NAME||':'||jid::text||':'||coalesce(stage_name,'')||':'||NEW.version::text;
  INSERT INTO journey_transitions(journey_id,stage,from_state,to_state,effect_key)
   VALUES(jid,stage_name,previous,NEW.state,effect);
 END IF; RETURN NEW;
END $$;
CREATE TRIGGER journey_record_transition AFTER INSERT OR UPDATE ON journeys FOR EACH ROW EXECUTE FUNCTION journey_record_transition();
CREATE TRIGGER stage_record_transition AFTER INSERT OR UPDATE ON journey_stages FOR EACH ROW EXECUTE FUNCTION journey_record_transition();
GRANT SELECT,INSERT,UPDATE ON journey_snapshots TO appointment_app; GRANT SELECT ON journey_transitions TO appointment_app;
""")


def downgrade():
    raise RuntimeError("Forward-only; preserve workflow history")
