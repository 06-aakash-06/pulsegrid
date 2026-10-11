"""Reviewed forward-only Phase 3 integration schema; no legacy row rewrites."""
from alembic import op

revision = '0005_phase3_waitlist'
down_revision = '0004_phase3_core'
branch_labels = depends_on = None


def upgrade():
    op.execute("""
CREATE TABLE promotion_jobs(slot_id bigint PRIMARY KEY REFERENCES slots(id) ON DELETE RESTRICT,version bigint NOT NULL DEFAULT 1 CHECK(version>0),attempt_count integer NOT NULL DEFAULT 0 CHECK(attempt_count>=0),next_attempt_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,lease_token varchar(64),lease_expires_at timestamptz,pending boolean NOT NULL DEFAULT true,updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,CHECK((lease_token IS NULL)=(lease_expires_at IS NULL)));
CREATE INDEX ix_promotion_jobs_due ON promotion_jobs(next_attempt_at,slot_id) WHERE pending;
CREATE UNIQUE INDEX ix_waitlist_promoted_unique ON waitlist_entries(promoted_appointment_id) WHERE promoted_appointment_id IS NOT NULL;
ALTER TABLE waitlist_entries ADD CONSTRAINT ck_waitlist_outcome CHECK ((state='promoted')=(promoted_appointment_id IS NOT NULL) AND (state='skipped')=(skip_reason IS NOT NULL) AND (skip_reason IS NULL OR skip_reason IN ('inactive_patient','patient_overlap','slot_retired','window_closed','offer_expired')));
ALTER TABLE patient_status_snapshots ADD CONSTRAINT ck_patient_status_source CHECK(source_version>=0 AND (source_version>0 OR NOT active));
CREATE TABLE waitlist_offers(id bigint PRIMARY KEY CHECK(id>0),entry_id bigint NOT NULL REFERENCES waitlist_entries(id) ON DELETE RESTRICT,slot_id bigint NOT NULL REFERENCES slots(id) ON DELETE RESTRICT,patient_id bigint NOT NULL CHECK(patient_id>0),state varchar(16) NOT NULL CHECK(state IN ('pending','accepted','declined','expired','revoked')),expires_at timestamptz NOT NULL,appointment_id bigint REFERENCES appointments(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,version bigint NOT NULL DEFAULT 1 CHECK(version BETWEEN 1 AND 9007199254740991),created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,CHECK((state='accepted')=(appointment_id IS NOT NULL)));
CREATE UNIQUE INDEX uq_offer_slot_pending ON waitlist_offers(slot_id) WHERE state='pending';
CREATE UNIQUE INDEX uq_offer_entry_pending ON waitlist_offers(entry_id) WHERE state='pending';
CREATE FUNCTION appointment_offer_binding() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$ BEGIN
 PERFORM id FROM slots WHERE id=NEW.slot_id FOR UPDATE;
 IF NOT EXISTS(SELECT FROM waitlist_entries WHERE id=NEW.entry_id AND slot_id=NEW.slot_id AND patient_id=NEW.patient_id) THEN RAISE EXCEPTION 'Offer binding mismatch' USING ERRCODE='23514'; END IF;
 IF NEW.state='pending' AND EXISTS(SELECT FROM appointments WHERE slot_id=NEW.slot_id AND state IN ('confirmed','checked_in','in_consultation')) THEN RAISE EXCEPTION 'Slot occupied' USING ERRCODE='23514'; END IF;
 RETURN NEW; END $$;
CREATE TRIGGER offer_binding BEFORE INSERT OR UPDATE ON waitlist_offers FOR EACH ROW EXECUTE FUNCTION appointment_offer_binding();
CREATE FUNCTION appointment_offer_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$ BEGIN
 PERFORM id FROM slots WHERE id=NEW.slot_id FOR UPDATE;
 IF NEW.state IN ('confirmed','checked_in','in_consultation') AND EXISTS(SELECT FROM waitlist_offers WHERE slot_id=NEW.slot_id AND state='pending') THEN RAISE EXCEPTION 'Slot has pending offer' USING ERRCODE='23514'; END IF; RETURN NEW; END $$;
CREATE TRIGGER offer_guard BEFORE INSERT OR UPDATE ON appointments FOR EACH ROW EXECUTE FUNCTION appointment_offer_guard();
GRANT SELECT,INSERT,UPDATE ON promotion_jobs,waitlist_offers TO appointment_app;
DO $$ DECLARE definition text; BEGIN
 definition := pg_get_functiondef('public.appointment_append_phase3_audit(bigint,jsonb)'::regprocedure);
 definition := replace(definition, '''waitlist_joined''', '''offer_pending'',''offer_accepted'',''offer_declined'',''offer_expired'',''offer_revoked'',''queue_skipped'',''queue_recalled'',''workflow_link_issued'',''waitlist_joined''');
 EXECUTE definition;
END $$;
""")


def downgrade():
    raise RuntimeError("Forward-only; preserve workflow history")
