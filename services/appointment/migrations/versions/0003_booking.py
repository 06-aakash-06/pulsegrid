"""Phase 2.3 overlap safety, slot copies, clinical holds and constrained audit."""
from alembic import op

revision = '0003_booking'
down_revision = '0002_explicit_worker'
branch_labels = depends_on = None


def upgrade():
    op.execute('CREATE EXTENSION IF NOT EXISTS btree_gist')
    op.execute('CREATE EXTENSION IF NOT EXISTS pgcrypto')
    op.execute("""
    ALTER TABLE slots ADD CONSTRAINT slots_doctor_overlap EXCLUDE USING gist
      (doctor_id WITH =, tstzrange(starts_at,ends_at,'[)') WITH &&) WHERE (state <> 'retired');
    ALTER TABLE slots ADD CONSTRAINT slots_phase2_state CHECK (state IN ('bookable','retired'));
    ALTER TABLE appointments ADD CONSTRAINT appointments_patient_overlap EXCLUDE USING gist
      (patient_id WITH =, tstzrange(starts_at,ends_at,'[)') WITH &&)
      WHERE (state IN ('confirmed','checked_in','in_consultation'));
    ALTER TABLE appointments ADD COLUMN doctor_user_id bigint;
    UPDATE appointments a SET doctor_user_id=s.staff_user_id FROM doctor_schedule_snapshots s WHERE a.doctor_id=s.doctor_id;
    ALTER TABLE appointments ALTER COLUMN doctor_user_id SET NOT NULL;
    ALTER TABLE appointments ADD CONSTRAINT appointments_doctor_user_positive CHECK (doctor_user_id>0);
    ALTER TABLE schedule_proposals ADD COLUMN reason_code varchar(64);
    ALTER TABLE schedule_proposals ADD COLUMN conflicting_appointment_ids jsonb NOT NULL DEFAULT '[]';
    ALTER TABLE schedule_proposals ADD COLUMN staff_user_id bigint;
    UPDATE schedule_proposals p SET staff_user_id=s.staff_user_id FROM doctor_schedule_snapshots s WHERE p.doctor_id=s.doctor_id;
    ALTER TABLE schedule_proposals ALTER COLUMN staff_user_id SET NOT NULL;
    CREATE TABLE clinical_holds (
      appointment_id bigint PRIMARY KEY REFERENCES appointments(id) ON DELETE RESTRICT,
      consultation_id bigint NOT NULL UNIQUE CHECK (consultation_id>0),
      state varchar(16) NOT NULL CHECK (state IN ('active','finalized'))
    );
    GRANT SELECT,INSERT,UPDATE ON clinical_holds TO appointment_app;
    CREATE FUNCTION public.appointment_check_copy() RETURNS trigger LANGUAGE plpgsql
      SET search_path=pg_catalog,public AS $$
    DECLARE s public.slots%ROWTYPE; d public.doctor_schedule_snapshots%ROWTYPE;
    BEGIN
      IF TG_OP='INSERT' OR (NEW.slot_id,NEW.doctor_id,NEW.starts_at,NEW.ends_at,NEW.schedule_revision,NEW.doctor_user_id)
          IS DISTINCT FROM (OLD.slot_id,OLD.doctor_id,OLD.starts_at,OLD.ends_at,OLD.schedule_revision,OLD.doctor_user_id) THEN
        SELECT * INTO s FROM public.slots WHERE id=NEW.slot_id;
        SELECT * INTO d FROM public.doctor_schedule_snapshots WHERE doctor_id=s.doctor_id;
        IF s.id IS NULL OR d.doctor_id IS NULL OR s.state <> 'bookable' OR s.starts_at <= statement_timestamp()
          OR (NEW.doctor_id,NEW.starts_at,NEW.ends_at,NEW.schedule_revision,NEW.doctor_user_id)
            IS DISTINCT FROM (s.doctor_id,s.starts_at,s.ends_at,s.schedule_revision,d.staff_user_id)
          OR s.schedule_revision <> d.accepted_revision THEN
          RAISE EXCEPTION 'Invalid slot copy' USING ERRCODE='23514', CONSTRAINT='appointment_slot_copy';
        END IF;
      END IF;
      IF TG_OP='UPDATE' THEN
        IF OLD.state='cancelled' AND NEW.state<>'cancelled' THEN
          RAISE EXCEPTION 'Invalid transition' USING ERRCODE='23514', CONSTRAINT='appointment_transition';
        END IF;
        IF (NEW.slot_id IS DISTINCT FROM OLD.slot_id OR NEW.state='cancelled' AND OLD.state<>'cancelled')
          AND EXISTS (SELECT FROM public.clinical_holds WHERE appointment_id=OLD.id) THEN
          RAISE EXCEPTION 'Clinical hold' USING ERRCODE='23514', CONSTRAINT='appointment_clinical_hold';
        END IF;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER appointment_copy BEFORE INSERT OR UPDATE ON appointments
      FOR EACH ROW EXECUTE FUNCTION public.appointment_check_copy();
    CREATE FUNCTION public.appointment_append_audit(p_entry_id bigint,p_metadata jsonb)
      RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
    DECLARE head public.audit_heads%ROWTYPE; canonical jsonb; calculated text;
    BEGIN
      IF p_entry_id IS NULL OR p_entry_id<=0 OR jsonb_typeof(p_metadata) IS DISTINCT FROM 'object' OR octet_length(p_metadata::text)>4096
        OR p_metadata->>'action' IS NULL OR p_metadata->>'result' IS DISTINCT FROM 'success'
        OR p_metadata->>'action' NOT IN ('booked','cancelled','rescheduled','schedule_accepted','schedule_rejected','clinical_hold','hold_finalized','read')
        OR (p_metadata->>'actor_user_id') IS NULL OR (p_metadata->>'resource_id') IS NULL
        OR (p_metadata->>'actor_user_id') !~ '^[1-9][0-9]{0,18}$'
        OR (p_metadata->>'resource_id') !~ '^[1-9][0-9]{0,18}$'
        OR (p_metadata->>'request_id') IS NULL OR (p_metadata->>'correlation_id') IS NULL
        OR (p_metadata->>'request_id') !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        OR (p_metadata->>'correlation_id') !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        OR (p_metadata->>'occurred_at') IS NULL OR length(p_metadata->>'occurred_at')>40
        OR (p_metadata->>'occurred_at') !~ '^[0-9TZ:.+-]+$'
        OR (p_metadata ? 'reason_digest' AND (p_metadata->>'reason_digest') !~ '^[0-9a-f]{64}$')
        OR EXISTS (SELECT FROM jsonb_object_keys(p_metadata) k WHERE k NOT IN
          ('action','result','actor_user_id','resource_id','request_id','correlation_id','occurred_at','reason_digest')) THEN
        RAISE EXCEPTION 'Invalid audit metadata' USING ERRCODE='22023';
      END IF;
      INSERT INTO public.audit_heads VALUES ('appointment',0,repeat('0',64)) ON CONFLICT DO NOTHING;
      SELECT * INTO head FROM public.audit_heads WHERE chain_id='appointment' FOR UPDATE;
      canonical:=p_metadata || jsonb_build_object('chain_id','appointment','sequence',head.last_sequence+1,'entry_id',p_entry_id::text);
      calculated:=encode(public.digest(convert_to(head.last_hash || canonical::text,'UTF8'),'sha256'),'hex');
      INSERT INTO public.audit_entries(chain_id,sequence,entry_id,prev_hash,entry_hash,canonical_metadata)
        VALUES ('appointment',head.last_sequence+1,p_entry_id,head.last_hash,calculated,canonical);
      UPDATE public.audit_heads SET last_sequence=head.last_sequence+1,last_hash=calculated WHERE chain_id='appointment';
    END $$;
    REVOKE ALL ON FUNCTION public.appointment_append_audit(bigint,jsonb) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION public.appointment_append_audit(bigint,jsonb) TO appointment_app;
    """)


def downgrade():
    op.execute('DROP FUNCTION public.appointment_append_audit(bigint,jsonb)')
    op.execute('DROP TRIGGER appointment_copy ON appointments')
    op.execute('DROP FUNCTION public.appointment_check_copy()')
    op.drop_table('clinical_holds')
    for name in ('reason_code','conflicting_appointment_ids','staff_user_id'):
        op.drop_column('schedule_proposals',name)
    op.drop_column('appointments','doctor_user_id')
    op.execute('ALTER TABLE appointments DROP CONSTRAINT appointments_patient_overlap')
    op.execute('ALTER TABLE slots DROP CONSTRAINT slots_doctor_overlap, DROP CONSTRAINT slots_phase2_state')
