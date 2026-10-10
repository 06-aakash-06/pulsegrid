"""Phase 2 clinical storage, immutable revisions and constrained domain audit."""

from alembic import op

revision = "0003_clinical"
down_revision = "0002_explicit_worker"
branch_labels = depends_on = None


def upgrade():
    op.execute("ALTER TABLE consultations ALTER COLUMN journey_id DROP NOT NULL")
    op.execute("ALTER TABLE prescriptions ALTER COLUMN journey_id DROP NOT NULL")
    op.execute(
        "ALTER TABLE consultations ADD COLUMN author_user_id BIGINT, ADD COLUMN hold_version BIGINT, ADD COLUMN hold_finalized_at TIMESTAMPTZ"
    )
    op.execute(
        "ALTER TABLE consultations ADD CONSTRAINT ck_consultation_status CHECK (status IN ('draft','finalized')) NOT VALID"
    )
    op.execute(
        "ALTER TABLE prescriptions ADD CONSTRAINT ck_prescription_state CHECK (state IN ('issued','revoked')) NOT VALID"
    )
    op.execute(
        "ALTER TABLE medical_records ADD CONSTRAINT uq_record_revision UNIQUE (consultation_id,revision), ADD CONSTRAINT uq_record_supersedes UNIQUE (supersedes_id)"
    )
    op.execute(
        "ALTER TABLE prescription_items ADD CONSTRAINT uq_prescription_medicine UNIQUE (prescription_id,medicine_id), ADD CONSTRAINT ck_quantity_bound CHECK (quantity <= 1000000) NOT VALID"
    )
    # Separate from Snowflake worker allocation. Sequence survives rollbacks/restarts.
    op.execute("CREATE SEQUENCE records_domain_ids AS BIGINT MINVALUE 1 NO CYCLE")
    op.execute("""SELECT setval('records_domain_ids', GREATEST(1, COALESCE((SELECT max(id) FROM (
      SELECT id FROM consultations UNION ALL SELECT id FROM medical_records UNION ALL
      SELECT id FROM prescriptions UNION ALL SELECT id FROM prescription_items UNION ALL
      SELECT id FROM record_access_grants UNION ALL SELECT entry_id FROM audit_entries UNION ALL
      SELECT event_id FROM outbox_events) ids),0)+1),false)""")
    op.execute("""CREATE TABLE command_preparations (
      principal_scope VARCHAR(256) NOT NULL, key VARCHAR(128) NOT NULL,
      request_hash VARCHAR(64) NOT NULL, consultation_id BIGINT NOT NULL UNIQUE,
      appointment_id BIGINT NOT NULL, context JSONB NOT NULL, hold_version BIGINT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY(principal_scope,key), CHECK(consultation_id>0 AND hold_version>0))""")
    op.execute(
        "CREATE INDEX ix_consultation_author ON consultations(author_user_id,created_at,id)"
    )
    op.execute(
        "CREATE INDEX ix_consultation_patient ON consultations(patient_id,created_at,id)"
    )
    op.execute("""CREATE FUNCTION records_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      RAISE EXCEPTION 'immutable clinical history';
    END $$""")
    for table in ("medical_records", "prescription_items", "command_preparations"):
        op.execute(
            f"CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION records_immutable()"
        )
    op.execute("""CREATE FUNCTION records_freeze_consultation() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'clinical history cannot be deleted'; END IF;
      IF NEW.id<>OLD.id OR NEW.appointment_id<>OLD.appointment_id OR NEW.patient_id<>OLD.patient_id
        OR NEW.doctor_id<>OLD.doctor_id OR NEW.author_user_id IS DISTINCT FROM OLD.author_user_id
        OR NEW.hold_version IS DISTINCT FROM OLD.hold_version THEN RAISE EXCEPTION 'immutable identity'; END IF;
      IF OLD.status='finalized' AND (NEW.status<>OLD.status OR NEW.clinical_content<>OLD.clinical_content
        OR NEW.revision<>OLD.revision OR NEW.version<>OLD.version) THEN RAISE EXCEPTION 'finalized'; END IF;
      RETURN NEW;
    END $$""")
    op.execute(
        "CREATE TRIGGER freeze_consultation BEFORE UPDATE OR DELETE ON consultations FOR EACH ROW EXECUTE FUNCTION records_freeze_consultation()"
    )
    op.execute("""CREATE FUNCTION records_freeze_prescription() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'clinical history cannot be deleted'; END IF;
      IF NEW.id<>OLD.id OR NEW.consultation_id<>OLD.consultation_id OR NEW.patient_id<>OLD.patient_id
        OR NEW.journey_id IS DISTINCT FROM OLD.journey_id OR NEW.revision<>OLD.revision
        OR (OLD.state='revoked' AND NEW.state<>'revoked') THEN RAISE EXCEPTION 'immutable prescription'; END IF;
      RETURN NEW;
    END $$""")
    op.execute(
        "CREATE TRIGGER freeze_prescription BEFORE UPDATE OR DELETE ON prescriptions FOR EACH ROW EXECUTE FUNCTION records_freeze_prescription()"
    )
    op.execute("""CREATE FUNCTION records_append_audit(actor BIGINT, action TEXT, resource BIGINT,
      result TEXT, digest TEXT, request_id UUID, correlation_id UUID) RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
    DECLARE head public.audit_heads%ROWTYPE; meta JSONB; hash TEXT; stamp TEXT;
    BEGIN
      IF actor IS NULL OR resource IS NULL OR action IS NULL OR result IS NULL
        OR actor<=0 OR resource<=0 OR action NOT IN ('read','denied','created','updated','finalized','amended','issued','revoked','grant_created','grant_revoked')
        OR result NOT IN ('allowed','denied') OR (digest IS NOT NULL AND digest !~ '^[0-9a-f]{64}$')
        OR request_id IS NULL OR correlation_id IS NULL THEN RAISE EXCEPTION 'invalid audit metadata'; END IF;
      INSERT INTO public.audit_heads(chain_id,last_sequence,last_hash) VALUES('records-domain',0,repeat('0',64)) ON CONFLICT DO NOTHING;
      SELECT * INTO head FROM public.audit_heads WHERE chain_id='records-domain' FOR UPDATE;
      stamp := to_char(clock_timestamp() AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"');
      meta := jsonb_build_object('chain_id','records-domain','sequence',head.last_sequence+1,
        'actor_user_id',actor::text,'service','records','action',action,'resource_id',resource::text,
        'result',result,'occurred_at',stamp,'request_id',request_id::text,'correlation_id',correlation_id::text,
        'content_digest',digest);
      hash := encode(sha256(convert_to(head.last_hash || meta::text,'UTF8')),'hex');
      INSERT INTO public.audit_entries(chain_id,sequence,entry_id,prev_hash,entry_hash,canonical_metadata)
        VALUES('records-domain',head.last_sequence+1,nextval('public.records_domain_ids'),head.last_hash,hash,meta);
      UPDATE public.audit_heads SET last_sequence=head.last_sequence+1,last_hash=hash WHERE chain_id='records-domain';
    END $$""")
    op.execute(
        "REVOKE ALL ON FUNCTION records_append_audit(BIGINT,TEXT,BIGINT,TEXT,TEXT,UUID,UUID) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION records_append_audit(BIGINT,TEXT,BIGINT,TEXT,TEXT,UUID,UUID) TO records_app"
    )
    op.execute("GRANT USAGE, SELECT ON SEQUENCE records_domain_ids TO records_app")
    op.execute("GRANT SELECT,INSERT ON command_preparations TO records_app")
    op.execute(
        "REVOKE UPDATE,DELETE ON command_preparations,medical_records,prescription_items FROM records_app"
    )
    op.execute(
        "REVOKE DELETE ON consultations,prescriptions,record_access_grants,outbox_events FROM records_app"
    )
    op.execute("""CREATE FUNCTION records_freeze_outbox() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'immutable event'; END IF;
      IF NEW.event_id<>OLD.event_id OR NEW.aggregate_type<>OLD.aggregate_type OR NEW.aggregate_id<>OLD.aggregate_id
        OR NEW.aggregate_version<>OLD.aggregate_version OR NEW.event_type<>OLD.event_type
        OR NEW.envelope<>OLD.envelope OR NEW.created_at<>OLD.created_at THEN RAISE EXCEPTION 'immutable event'; END IF;
      RETURN NEW;
    END $$""")
    op.execute(
        "CREATE TRIGGER freeze_outbox BEFORE UPDATE OR DELETE ON outbox_events FOR EACH ROW EXECUTE FUNCTION records_freeze_outbox()"
    )
    op.execute("REVOKE ALL ON audit_heads,audit_entries FROM records_app")
    op.execute("GRANT SELECT ON audit_heads,audit_entries TO records_app")


def downgrade():
    raise RuntimeError(
        "Clinical history migration is forward-only; preserve synthetic history"
    )
