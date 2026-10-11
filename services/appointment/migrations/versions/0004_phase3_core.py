"""G0 shared workflow storage; no enrollment/backfill or feature activation."""
from alembic import op

revision = '0004_phase3_core'
down_revision = '0003_booking'
branch_labels = depends_on = None


def upgrade():
    # Dormant legacy feature data has no reviewed Phase 3 interpretation.
    op.execute("""
    DO $$ BEGIN
      IF EXISTS (SELECT FROM waitlist_entries) OR EXISTS (SELECT FROM checkin_links)
        OR EXISTS (SELECT FROM queue_counters) OR EXISTS (SELECT FROM queue_entries)
        OR EXISTS (SELECT FROM journeys) OR EXISTS (SELECT FROM journey_stages) THEN
        RAISE EXCEPTION 'Unexpected dormant feature data: explicit review required';
      END IF;
    END $$;
    CREATE TABLE appointment_workflows (
      appointment_id bigint PRIMARY KEY REFERENCES appointments(id) ON DELETE RESTRICT,
      journey_id bigint NOT NULL UNIQUE REFERENCES journeys(id) ON DELETE RESTRICT,
      patient_id bigint NOT NULL, doctor_id bigint NOT NULL,
      slot_id bigint NOT NULL REFERENCES slots(id) ON DELETE RESTRICT,
      schedule_revision bigint NOT NULL,
      schedule_fingerprint varchar(64) NOT NULL,
      state varchar(32) NOT NULL,
      window_starts_at timestamptz NOT NULL, window_ends_at timestamptz NOT NULL,
      queue_entry_id bigint UNIQUE REFERENCES queue_entries(id) ON DELETE RESTRICT,
      version bigint NOT NULL DEFAULT 1,
      created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
      CONSTRAINT ck_appointment_workflows_appointment_id_nonnegative CHECK (appointment_id>=0),
      CONSTRAINT ck_appointment_workflows_journey_id_nonnegative CHECK (journey_id>=0),
      CONSTRAINT ck_appointment_workflows_patient_id_nonnegative CHECK (patient_id>=0),
      CONSTRAINT ck_appointment_workflows_doctor_id_nonnegative CHECK (doctor_id>=0),
      CONSTRAINT ck_appointment_workflows_slot_id_nonnegative CHECK (slot_id>=0),
      CONSTRAINT ck_appointment_workflows_queue_entry_id_nonnegative CHECK (queue_entry_id>=0),
      CONSTRAINT ck_appointment_workflows_positive_version CHECK (version>0),
      CONSTRAINT ck_appointment_workflows_safe_version CHECK (version<=9007199254740991),
      CONSTRAINT ck_appointment_workflows_positive_schedule_revision CHECK (schedule_revision>0),
      CONSTRAINT ck_appointment_workflows_fingerprint CHECK (schedule_fingerprint ~ '^[0-9a-f]{64}$'),
      CONSTRAINT ck_appointment_workflows_valid_window CHECK (window_ends_at>window_starts_at),
      CONSTRAINT ck_appointment_workflows_state_values CHECK
        (state IN ('booked','checked_in','in_consultation','completed','cancelled','no_show')),
      CONSTRAINT ck_appointment_workflows_queue_required CHECK
        (state NOT IN ('checked_in','in_consultation','completed') OR queue_entry_id IS NOT NULL)
    );
    GRANT SELECT,INSERT,UPDATE ON appointment_workflows TO appointment_app;
    CREATE FUNCTION public.appointment_workflow_binding() RETURNS trigger LANGUAGE plpgsql
      SET search_path=pg_catalog,public AS $$
    DECLARE w public.appointment_workflows%ROWTYPE; a public.appointments%ROWTYPE; j public.journeys%ROWTYPE; q public.queue_entries%ROWTYPE;
    BEGIN
      SELECT * INTO w FROM public.appointment_workflows WHERE appointment_id=NEW.appointment_id;
      SELECT * INTO a FROM public.appointments WHERE id=w.appointment_id;
      SELECT * INTO j FROM public.journeys WHERE id=w.journey_id;
      IF a.id IS NULL OR j.id IS NULL OR
        (w.patient_id,w.doctor_id,w.slot_id,w.schedule_revision)
          IS DISTINCT FROM (a.patient_id,a.doctor_id,a.slot_id,a.schedule_revision) OR
        (j.appointment_id,j.patient_id) IS DISTINCT FROM (a.id,a.patient_id) OR
        w.window_starts_at IS DISTINCT FROM a.starts_at - interval '30 minutes' OR
        w.window_ends_at IS DISTINCT FROM a.starts_at + interval '15 minutes' THEN
        RAISE EXCEPTION 'Workflow binding mismatch' USING ERRCODE='23514', CONSTRAINT='workflow_binding';
      END IF;
      IF w.queue_entry_id IS NOT NULL THEN
        SELECT * INTO q FROM public.queue_entries WHERE id=w.queue_entry_id;
        IF q.id IS NULL OR (q.appointment_id,q.doctor_id) IS DISTINCT FROM (a.id,a.doctor_id) THEN
          RAISE EXCEPTION 'Workflow queue mismatch' USING ERRCODE='23514', CONSTRAINT='workflow_queue_binding';
        END IF;
      END IF;
      RETURN NEW;
    END $$;
    CREATE CONSTRAINT TRIGGER workflow_binding AFTER INSERT OR UPDATE ON appointment_workflows
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.appointment_workflow_binding();
    -- Validate final parent state too: direct parent SQL must not orphan/misbind
    -- an existing workflow. Deferred checks allow atomic reschedule updates.
    CREATE FUNCTION public.appointment_workflow_parent_binding() RETURNS trigger LANGUAGE plpgsql
      SET search_path=pg_catalog,public AS $$
    BEGIN
      IF EXISTS (
        SELECT FROM public.appointment_workflows w
        JOIN public.appointments a ON a.id=w.appointment_id
        JOIN public.journeys j ON j.id=w.journey_id
        LEFT JOIN public.queue_entries q ON q.id=w.queue_entry_id
        WHERE ((TG_TABLE_NAME='appointments' AND a.id=NEW.id)
          OR (TG_TABLE_NAME='journeys' AND j.id=NEW.id)
          OR (TG_TABLE_NAME='queue_entries' AND w.queue_entry_id=NEW.id))
          AND ((w.patient_id,w.doctor_id,w.slot_id,w.schedule_revision)
              IS DISTINCT FROM (a.patient_id,a.doctor_id,a.slot_id,a.schedule_revision)
            OR (j.appointment_id,j.patient_id) IS DISTINCT FROM (a.id,a.patient_id)
            OR w.window_starts_at IS DISTINCT FROM a.starts_at - interval '30 minutes'
            OR w.window_ends_at IS DISTINCT FROM a.starts_at + interval '15 minutes'
            OR (w.queue_entry_id IS NOT NULL AND
               (q.appointment_id,q.doctor_id) IS DISTINCT FROM (a.id,a.doctor_id)))
      ) THEN
        RAISE EXCEPTION 'Workflow parent binding mismatch' USING ERRCODE='23514', CONSTRAINT='workflow_parent_binding';
      END IF;
      RETURN NEW;
    END $$;
    CREATE CONSTRAINT TRIGGER workflow_parent_binding AFTER UPDATE ON appointments
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.appointment_workflow_parent_binding();
    CREATE CONSTRAINT TRIGGER workflow_parent_binding AFTER UPDATE ON journeys
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.appointment_workflow_parent_binding();
    CREATE CONSTRAINT TRIGGER workflow_parent_binding AFTER UPDATE ON queue_entries
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.appointment_workflow_parent_binding();
    CREATE FUNCTION public.appointment_append_phase3_audit(p_entry_id bigint,p_metadata jsonb)
      RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
    DECLARE head public.audit_heads%ROWTYPE; canonical jsonb; calculated text;
    BEGIN
      IF p_entry_id IS NULL OR p_entry_id<=0 OR jsonb_typeof(p_metadata) IS DISTINCT FROM 'object'
        OR octet_length(p_metadata::text)>4096 OR p_metadata->>'result' IS DISTINCT FROM 'success'
        OR p_metadata->>'action' IS NULL OR p_metadata->>'action' NOT IN
          ('waitlist_joined','waitlist_withdrawn','waitlist_skipped','waitlist_promoted',
           'workflow_enrolled','workflow_checked_in','workflow_consultation_started',
           'workflow_completed','workflow_no_show','workflow_cancelled',
           'journey_created','journey_updated','journey_discharged','journey_reopened','workflow_read')
        OR p_metadata->>'resource_id' IS NULL OR (p_metadata->>'resource_id') !~ '^[1-9][0-9]{0,18}$'
        OR p_metadata->>'request_id' IS NULL OR (p_metadata->>'request_id') !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        OR p_metadata->>'correlation_id' IS NULL OR (p_metadata->>'correlation_id') !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        OR p_metadata->>'occurred_at' IS NULL OR (p_metadata->>'occurred_at') !~ '^[0-9TZ:.+-]+$'
        OR length(p_metadata->>'occurred_at')>40
        OR ((p_metadata ? 'actor_user_id') = (p_metadata ? 'actor_service'))
        OR (p_metadata ? 'actor_user_id' AND (p_metadata->>'actor_user_id' IS NULL OR (p_metadata->>'actor_user_id') !~ '^[1-9][0-9]{0,18}$'))
        OR (p_metadata ? 'actor_service' AND (p_metadata->>'actor_service') IS DISTINCT FROM 'appointment')
        OR (p_metadata ? 'reason_digest' AND (p_metadata->>'reason_digest' IS NULL OR (p_metadata->>'reason_digest') !~ '^[0-9a-f]{64}$'))
        OR EXISTS (SELECT FROM jsonb_object_keys(p_metadata) k WHERE k NOT IN
          ('action','result','actor_user_id','actor_service','resource_id','request_id','correlation_id','occurred_at','reason_digest')) THEN
        RAISE EXCEPTION 'Invalid Phase 3 audit metadata' USING ERRCODE='22023';
      END IF;
      INSERT INTO public.audit_heads VALUES ('appointment',0,repeat('0',64)) ON CONFLICT DO NOTHING;
      SELECT * INTO head FROM public.audit_heads WHERE chain_id='appointment' FOR UPDATE;
      canonical:=p_metadata || jsonb_build_object('chain_id','appointment','sequence',head.last_sequence+1,'entry_id',p_entry_id::text);
      calculated:=encode(public.digest(convert_to(head.last_hash || canonical::text,'UTF8'),'sha256'),'hex');
      INSERT INTO public.audit_entries(chain_id,sequence,entry_id,prev_hash,entry_hash,canonical_metadata)
        VALUES ('appointment',head.last_sequence+1,p_entry_id,head.last_hash,calculated,canonical);
      UPDATE public.audit_heads SET last_sequence=head.last_sequence+1,last_hash=calculated WHERE chain_id='appointment';
    END $$;
    REVOKE ALL ON FUNCTION public.appointment_append_phase3_audit(bigint,jsonb) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION public.appointment_append_phase3_audit(bigint,jsonb) TO appointment_app;
    """)


def downgrade():
    raise RuntimeError('Phase 3 core is forward-only; preserve episode history')
