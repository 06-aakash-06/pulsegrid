"""Local episode revision for bounded Pharmacy workflow snapshots."""

from alembic import op

revision = "0004_phase3_workflow"
down_revision = "0003_phase2_pharmacy"
branch_labels = depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE pharmacy_episode_revisions (
            appointment_id BIGINT PRIMARY KEY CHECK (appointment_id > 0),
            patient_id BIGINT NOT NULL CHECK (patient_id > 0),
            prescription_id BIGINT NOT NULL UNIQUE CHECK (prescription_id > 0),
            revision BIGINT NOT NULL CHECK (revision >= 2)
        )
    """)
    op.execute("""
        INSERT INTO pharmacy_episode_revisions
        SELECT appointment_id, patient_id, prescription_id, 2
        FROM prescription_snapshots WHERE appointment_id IS NOT NULL
    """)
    op.execute("GRANT SELECT ON pharmacy_episode_revisions TO pharmacy_app")
    op.execute("""
        CREATE FUNCTION pharmacy_bump_episode() RETURNS trigger LANGUAGE plpgsql
        SECURITY DEFINER SET search_path = pg_catalog, public AS $$
        DECLARE prescription BIGINT; episode BIGINT; patient BIGINT;
        BEGIN
            IF TG_TABLE_NAME = 'prescription_snapshots' THEN
                prescription := NEW.prescription_id;
            ELSIF TG_TABLE_NAME = 'prescription_item_snapshots' OR TG_TABLE_NAME = 'reservations' THEN
                prescription := NEW.prescription_id;
            ELSIF TG_TABLE_NAME = 'dispensings' THEN
                SELECT prescription_id INTO prescription FROM reservations WHERE id = NEW.reservation_id;
            ELSE
                SELECT r.prescription_id INTO prescription FROM reservation_items ri
                JOIN reservations r ON r.id = ri.reservation_id
                WHERE ri.id = NEW.reservation_item_id;
            END IF;
            SELECT appointment_id, patient_id INTO episode, patient
            FROM prescription_snapshots WHERE prescription_id = prescription;
            IF episode IS NOT NULL THEN
                INSERT INTO pharmacy_episode_revisions VALUES (episode, patient, prescription, 2)
                ON CONFLICT (appointment_id) DO UPDATE
                SET revision = pharmacy_episode_revisions.revision + 1
                WHERE pharmacy_episode_revisions.patient_id = EXCLUDED.patient_id
                  AND pharmacy_episode_revisions.prescription_id = EXCLUDED.prescription_id;
            END IF;
            RETURN NEW;
        END $$
    """)
    for table in ("prescription_snapshots", "prescription_item_snapshots", "reservations", "dispensings", "dispensing_items"):
        events = "INSERT OR UPDATE" if table != "dispensing_items" else "INSERT"
        op.execute(f"CREATE TRIGGER bump_pharmacy_episode AFTER {events} ON {table} FOR EACH ROW EXECUTE FUNCTION pharmacy_bump_episode()")
    op.execute("""
        DO $migration$
        DECLARE definition TEXT;
        BEGIN
            SELECT pg_get_functiondef('public.pharmacy_append_audit(BIGINT,BIGINT,VARCHAR,VARCHAR,JSONB)'::regprocedure)
            INTO definition;
            IF position('''authorization.denied'', ''inventory.list''' IN definition) = 0 THEN
                RAISE EXCEPTION 'Pharmacy audit allowlist changed; review migration';
            END IF;
            definition := replace(definition,
                '''authorization.denied'', ''inventory.list''',
                '''authorization.denied'', ''inventory.list'', ''prescription.fulfillment_read'', ''prescription.workflow_snapshot_read''');
            EXECUTE definition;
        END $migration$
    """)


def downgrade():
    raise RuntimeError("Episode revisions are forward-only; preserve fulfillment history")
