"""Monotonic local Billing episode revisions and metadata read audit."""
from alembic import op
revision='0004_phase3_workflow'
down_revision='0003_billing_phase2'
branch_labels=depends_on=None


def upgrade():
    op.execute("""
    CREATE TABLE billing_episode_revisions(appointment_id bigint PRIMARY KEY CHECK(appointment_id>0),
      patient_id bigint NOT NULL CHECK(patient_id>0),revision bigint NOT NULL CHECK(revision>=2));
    INSERT INTO billing_episode_revisions SELECT appointment_id,patient_id,2 FROM invoices WHERE appointment_id IS NOT NULL;
    GRANT SELECT ON billing_episode_revisions TO billing_app;
    CREATE FUNCTION billing_bump_episode() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
    DECLARE episode bigint; patient bigint;
    BEGIN
      IF TG_TABLE_NAME='invoices' THEN episode:=NEW.appointment_id;patient:=NEW.patient_id;
      ELSE SELECT appointment_id,patient_id INTO episode,patient FROM invoices WHERE id=NEW.invoice_id; END IF;
      IF episode IS NOT NULL THEN
       INSERT INTO billing_episode_revisions VALUES(episode,patient,2)
       ON CONFLICT(appointment_id) DO UPDATE SET revision=billing_episode_revisions.revision+1
       WHERE billing_episode_revisions.patient_id=EXCLUDED.patient_id;
      END IF; RETURN NEW;
    END $$;
    CREATE TRIGGER bump_billing_episode AFTER INSERT OR UPDATE ON invoices FOR EACH ROW EXECUTE FUNCTION billing_bump_episode();
    CREATE TRIGGER bump_billing_items AFTER INSERT OR UPDATE ON invoice_items FOR EACH ROW EXECUTE FUNCTION billing_bump_episode();
    CREATE TRIGGER bump_billing_payments AFTER INSERT OR UPDATE ON payments FOR EACH ROW EXECUTE FUNCTION billing_bump_episode();
    CREATE TRIGGER bump_billing_adjustments AFTER INSERT OR UPDATE ON invoice_adjustments FOR EACH ROW EXECUTE FUNCTION billing_bump_episode();
    DO $$ DECLARE definition text; BEGIN
      definition:=pg_get_functiondef('public.billing_append_audit(bigint,jsonb)'::regprocedure);
      definition:=replace(definition, '''tariff.create''', '''invoice.workflow_snapshot_read'',''tariff.create''');
      EXECUTE definition;
    END $$;
    """)


def downgrade():
    raise RuntimeError('Forward-only financial history')
