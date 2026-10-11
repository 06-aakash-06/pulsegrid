"""Local episode revision for bounded Records workflow snapshots."""

from alembic import op

revision = "0005_phase3_workflow"
down_revision = "0004_clinical_integrity"
branch_labels = depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE records_episode_revisions (
            appointment_id BIGINT PRIMARY KEY CHECK (appointment_id > 0),
            patient_id BIGINT NOT NULL CHECK (patient_id > 0),
            revision BIGINT NOT NULL CHECK (revision >= 2)
        )
    """)
    op.execute("""
        INSERT INTO records_episode_revisions (appointment_id, patient_id, revision)
        SELECT appointment_id, patient_id, 2 FROM consultations
    """)
    op.execute("GRANT SELECT ON records_episode_revisions TO records_app")
    op.execute("""
        CREATE FUNCTION records_bump_episode() RETURNS trigger LANGUAGE plpgsql
        SECURITY DEFINER SET search_path = pg_catalog, public AS $$
        DECLARE episode BIGINT; patient BIGINT;
        BEGIN
            IF TG_TABLE_NAME = 'consultations' THEN
                episode := NEW.appointment_id; patient := NEW.patient_id;
            ELSIF TG_TABLE_NAME = 'medical_records' OR TG_TABLE_NAME = 'prescriptions' THEN
                SELECT appointment_id, patient_id INTO episode, patient
                FROM consultations WHERE id = NEW.consultation_id;
            ELSE
                SELECT c.appointment_id, c.patient_id INTO episode, patient
                FROM prescriptions p JOIN consultations c ON c.id = p.consultation_id
                WHERE p.id = NEW.prescription_id;
            END IF;
            IF episode IS NOT NULL THEN
                INSERT INTO records_episode_revisions VALUES (episode, patient, 2)
                ON CONFLICT (appointment_id) DO UPDATE
                SET revision = records_episode_revisions.revision + 1
                WHERE records_episode_revisions.patient_id = EXCLUDED.patient_id;
            END IF;
            RETURN NEW;
        END $$
    """)
    for table in ("consultations", "medical_records", "prescriptions", "prescription_items"):
        events = "INSERT OR UPDATE" if table in ("consultations", "prescriptions") else "INSERT"
        op.execute(f"CREATE TRIGGER bump_records_episode AFTER {events} ON {table} FOR EACH ROW EXECUTE FUNCTION records_bump_episode()")
    op.execute("""
        DO $migration$
        DECLARE definition TEXT;
        BEGIN
            SELECT pg_get_functiondef('public.records_append_audit(BIGINT,TEXT,BIGINT,TEXT,TEXT,UUID,UUID)'::regprocedure)
            INTO definition;
            IF position('actor<=0' IN definition) = 0 THEN
                RAISE EXCEPTION 'Records audit policy changed; review migration';
            END IF;
            definition := replace(definition, 'actor<=0',
                '(actor<=0 AND NOT (actor=0 AND action=''workflow_snapshot_read''))');
            definition := replace(definition, '''grant_revoked'')',
                '''grant_revoked'', ''workflow_snapshot_read'')');
            EXECUTE definition;
        END $migration$
    """)


def downgrade():
    raise RuntimeError("Episode revisions are forward-only; preserve clinical history")
