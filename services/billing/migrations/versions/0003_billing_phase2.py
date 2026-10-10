"""Add Phase 2 billing ledger references, constraints and append-only audit."""

from alembic import op

revision = "0003_billing_phase2"
down_revision = "0002_explicit_worker"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("ALTER TABLE invoices ALTER COLUMN journey_id DROP NOT NULL")
    # Legacy invoices cannot be assigned fabricated appointment IDs. New API writes
    # always supply appointment_id; the partial unique index permits untouched rows.
    op.execute("ALTER TABLE invoices ADD COLUMN appointment_id BIGINT")
    op.execute(
        "CREATE UNIQUE INDEX uq_invoices_appointment_id ON invoices (appointment_id) "
        "WHERE appointment_id IS NOT NULL"
    )
    op.execute("ALTER TABLE invoice_items ALTER COLUMN source_event_id DROP NOT NULL")
    op.execute("ALTER TABLE tariffs ADD COLUMN version BIGINT NOT NULL DEFAULT 1")
    op.execute("ALTER TABLE tariffs ADD CONSTRAINT ck_tariffs_positive_version CHECK (version > 0)")
    op.execute("ALTER TABLE tariffs ADD CONSTRAINT ck_tariffs_safe_range CHECK (revision <= 9007199254740991 AND unit_amount_minor <= 9007199254740991)")
    op.execute("ALTER TABLE tariffs ADD CONSTRAINT ck_tariffs_version_safe_range CHECK (version <= 9007199254740991)")
    op.execute("ALTER TABLE invoices ADD CONSTRAINT ck_invoices_appointment_nonnegative CHECK (appointment_id IS NULL OR appointment_id >= 0)")
    op.execute("ALTER TABLE invoices ADD CONSTRAINT ck_invoices_safe_range CHECK (total_minor <= 9007199254740991 AND paid_minor <= 9007199254740991)")
    op.execute("ALTER TABLE invoices ADD CONSTRAINT ck_invoices_version_safe_range CHECK (version <= 9007199254740991)")
    op.execute("ALTER TABLE invoices ADD CONSTRAINT ck_invoices_currency_inr CHECK (currency = 'INR')")
    op.execute("ALTER TABLE invoices ADD CONSTRAINT ck_invoices_status_values CHECK (status IN ('open','paid'))")
    op.execute("ALTER TABLE invoices ADD CONSTRAINT ck_invoices_paid_state_balance CHECK (status <> 'paid' OR (total_minor > 0 AND paid_minor = total_minor))")
    op.execute("ALTER TABLE tariffs ADD CONSTRAINT ck_tariffs_currency_inr CHECK (currency = 'INR')")
    op.execute("ALTER TABLE tariffs ADD CONSTRAINT ck_tariffs_charge_code_format CHECK (charge_code = 'consultation' OR charge_code ~ '^medicine:[1-9][0-9]{0,18}$')")
    op.execute("ALTER TABLE invoice_items DROP CONSTRAINT ck_invoice_items_item_bounds")
    op.execute("ALTER TABLE invoice_items ADD CONSTRAINT ck_invoice_items_item_bounds CHECK (quantity BETWEEN 1 AND 1000000 AND unit_amount_minor BETWEEN 0 AND 9007199254740991)")
    op.execute("ALTER TABLE invoice_items ADD CONSTRAINT ck_invoice_items_source_service_values CHECK (source_service IN ('records','pharmacy'))")
    op.execute("ALTER TABLE payments DROP CONSTRAINT ck_payments_status_values")
    op.execute("ALTER TABLE payments ADD CONSTRAINT ck_payments_status_values CHECK (status IN ('success','declined'))")
    op.execute("ALTER TABLE payments ADD CONSTRAINT ck_payments_currency_inr CHECK (currency = 'INR')")
    op.execute("ALTER TABLE payments ADD CONSTRAINT ck_payments_safe_range CHECK (amount_minor <= 9007199254740991)")
    op.execute("ALTER TABLE payments ADD CONSTRAINT ck_payments_version_safe_range CHECK (version <= 9007199254740991)")
    op.execute("ALTER TABLE payments ADD COLUMN request_hash VARCHAR(64)")
    op.execute("ALTER TABLE payments ADD CONSTRAINT ck_payments_request_hash CHECK (request_hash IS NULL OR request_hash ~ '^[0-9a-f]{64}$')")
    op.execute("CREATE TABLE tariff_heads (charge_code VARCHAR(128) PRIMARY KEY, last_revision BIGINT NOT NULL DEFAULT 0, CONSTRAINT ck_tariff_heads_last_revision_bounds CHECK (last_revision BETWEEN 0 AND 9007199254740991))")
    op.execute("INSERT INTO tariff_heads (charge_code,last_revision) SELECT charge_code,max(revision) FROM tariffs GROUP BY charge_code")
    op.execute("CREATE INDEX ix_invoice_items_invoice_id_created_at_id ON invoice_items (invoice_id, created_at, id)")

    op.execute("""
    CREATE FUNCTION public.billing_reject_immutable_change()
    RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      RAISE EXCEPTION 'Billing ledger rows are immutable' USING ERRCODE='55000';
    END $$
    """)
    for table_name in ("tariffs", "invoice_items", "payments"):
        op.execute(
            f"CREATE TRIGGER {table_name}_immutable BEFORE UPDATE OR DELETE ON {table_name} "
            "FOR EACH ROW EXECUTE FUNCTION public.billing_reject_immutable_change()"
        )

    op.execute("""
    CREATE FUNCTION public.billing_append_audit(p_entry_id bigint, p_metadata jsonb)
    RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
    DECLARE head public.audit_heads%ROWTYPE; canonical jsonb; calculated text;
    BEGIN
      IF p_entry_id <= 0 OR jsonb_typeof(p_metadata) <> 'object'
         OR octet_length(p_metadata::text) > 4096
         OR p_metadata->>'action' NOT IN ('tariff.create','invoice.create','invoice.charges.import','payment.attempt')
         OR p_metadata->>'result' NOT IN ('success','declined')
         OR p_metadata->>'actor_user_id' IS NULL OR p_metadata->>'resource_id' IS NULL
         OR p_metadata->>'request_id' IS NULL OR p_metadata->>'correlation_id' IS NULL
         OR p_metadata->>'occurred_at' IS NULL
         OR EXISTS(SELECT FROM jsonb_object_keys(p_metadata) k WHERE k NOT IN
           ('action','result','actor_user_id','resource_id','request_id','correlation_id','occurred_at','amount_minor','currency','item_count'))
      THEN RAISE EXCEPTION 'Invalid billing audit metadata' USING ERRCODE='22023'; END IF;
      INSERT INTO public.audit_heads(chain_id,last_sequence,last_hash)
        VALUES ('billing',0,repeat('0',64)) ON CONFLICT DO NOTHING;
      SELECT * INTO head FROM public.audit_heads WHERE chain_id='billing' FOR UPDATE;
      canonical := p_metadata || jsonb_build_object('chain_id','billing',
        'sequence',head.last_sequence+1,'entry_id',p_entry_id::text);
      calculated := encode(public.digest(convert_to(head.last_hash || canonical::text,'UTF8'),'sha256'),'hex');
      INSERT INTO public.audit_entries(chain_id,sequence,entry_id,prev_hash,entry_hash,canonical_metadata)
        VALUES('billing',head.last_sequence+1,p_entry_id,head.last_hash,calculated,canonical);
      UPDATE public.audit_heads SET last_sequence=head.last_sequence+1,last_hash=calculated WHERE chain_id='billing';
    END $$
    """)
    op.execute("REVOKE ALL ON FUNCTION public.billing_append_audit(bigint,jsonb) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION public.billing_append_audit(bigint,jsonb) TO billing_app")
    op.execute("REVOKE ALL ON FUNCTION public.billing_reject_immutable_change() FROM PUBLIC")


def downgrade():
    for table_name in ("payments", "invoice_items", "tariffs"):
        op.execute(f"DROP TRIGGER {table_name}_immutable ON {table_name}")
    op.execute("DROP FUNCTION public.billing_append_audit(bigint,jsonb)")
    op.execute("DROP FUNCTION public.billing_reject_immutable_change()")
    op.execute("DROP INDEX ix_invoice_items_invoice_id_created_at_id")
    op.execute("DROP TABLE tariff_heads")
    op.execute("ALTER TABLE payments DROP CONSTRAINT ck_payments_currency_inr")
    op.execute("ALTER TABLE payments DROP CONSTRAINT ck_payments_safe_range")
    op.execute("ALTER TABLE payments DROP CONSTRAINT ck_payments_version_safe_range")
    op.execute("ALTER TABLE payments DROP CONSTRAINT ck_payments_request_hash")
    op.execute("ALTER TABLE payments DROP COLUMN request_hash")
    op.execute("ALTER TABLE payments DROP CONSTRAINT ck_payments_status_values")
    op.execute("ALTER TABLE payments ADD CONSTRAINT ck_payments_status_values CHECK (status IN ('success','declined','reversed'))")
    op.execute("ALTER TABLE tariffs DROP CONSTRAINT ck_tariffs_charge_code_format")
    op.execute("ALTER TABLE tariffs DROP CONSTRAINT ck_tariffs_currency_inr")
    op.execute("ALTER TABLE tariffs DROP CONSTRAINT ck_tariffs_safe_range")
    op.execute("ALTER TABLE tariffs DROP CONSTRAINT ck_tariffs_version_safe_range")
    op.execute("ALTER TABLE tariffs DROP CONSTRAINT ck_tariffs_positive_version")
    op.execute("ALTER TABLE tariffs DROP COLUMN version")
    op.execute("ALTER TABLE invoice_items DROP CONSTRAINT ck_invoice_items_source_service_values")
    op.execute("ALTER TABLE invoice_items DROP CONSTRAINT ck_invoice_items_item_bounds")
    op.execute("ALTER TABLE invoice_items ADD CONSTRAINT ck_invoice_items_item_bounds CHECK (quantity > 0 AND unit_amount_minor >= 0)")
    op.execute("ALTER TABLE invoice_items ALTER COLUMN source_event_id SET NOT NULL")
    op.execute("ALTER TABLE invoices DROP CONSTRAINT ck_invoices_paid_state_balance")
    op.execute("ALTER TABLE invoices DROP CONSTRAINT ck_invoices_status_values")
    op.execute("ALTER TABLE invoices DROP CONSTRAINT ck_invoices_currency_inr")
    op.execute("ALTER TABLE invoices DROP CONSTRAINT ck_invoices_safe_range")
    op.execute("ALTER TABLE invoices DROP CONSTRAINT ck_invoices_version_safe_range")
    op.execute("ALTER TABLE invoices DROP CONSTRAINT ck_invoices_appointment_nonnegative")
    op.execute("DROP INDEX uq_invoices_appointment_id")
    op.execute("ALTER TABLE invoices DROP COLUMN appointment_id")
    op.execute("ALTER TABLE invoices ALTER COLUMN journey_id SET NOT NULL")
