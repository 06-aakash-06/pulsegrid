"""Phase 2 pharmacy constraints, snapshots, and append-only audit commands."""

from alembic import op

revision = "0003_phase2_pharmacy"
down_revision = "0002_explicit_worker"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE prescription_snapshots ALTER COLUMN journey_id DROP NOT NULL")
    op.execute("ALTER TABLE prescription_snapshots ADD COLUMN consultation_id BIGINT")
    op.execute("ALTER TABLE prescription_snapshots ADD COLUMN appointment_id BIGINT")
    op.execute(
        "ALTER TABLE prescription_snapshots ADD CONSTRAINT ck_prescription_snapshots_consultation_id_nonnegative CHECK (consultation_id >= 0)"
    )
    op.execute(
        "ALTER TABLE prescription_snapshots ADD CONSTRAINT ck_prescription_snapshots_appointment_id_nonnegative CHECK (appointment_id >= 0)"
    )
    op.execute(
        "ALTER TABLE prescription_snapshots ADD CONSTRAINT ck_prescription_snapshots_state_values CHECK (state IN ('issued','revoked'))"
    )

    op.execute("ALTER TABLE dispensings ADD COLUMN version BIGINT DEFAULT 1 NOT NULL")
    op.execute(
        "ALTER TABLE dispensings ADD CONSTRAINT ck_dispensings_positive_version CHECK (version > 0)"
    )

    op.execute("ALTER TABLE inventory_batches DROP CONSTRAINT ck_inventory_batches_stock_bounds")
    op.execute(
        "ALTER TABLE inventory_batches ADD CONSTRAINT ck_inventory_batches_stock_bounds CHECK (0 <= reserved AND reserved <= on_hand AND on_hand <= 1000000)"
    )
    op.execute(
        "ALTER TABLE prescription_item_snapshots DROP CONSTRAINT ck_prescription_item_snapshots_quantity_bounds"
    )
    op.execute(
        "ALTER TABLE prescription_item_snapshots ADD CONSTRAINT ck_prescription_item_snapshots_quantity_bounds CHECK (prescribed_quantity BETWEEN 0 AND 1000000 AND reserved_quantity >= 0 AND dispensed_quantity >= 0 AND reserved_quantity + dispensed_quantity <= prescribed_quantity)"
    )
    op.execute(
        "ALTER TABLE reservation_items ADD CONSTRAINT uq_reservation_items_reservation_id UNIQUE (reservation_id, item_id)"
    )
    op.execute("CREATE INDEX ix_reservations_created_at_id ON reservations (created_at, id)")
    op.execute("CREATE INDEX ix_dispensings_created_at_id ON dispensings (created_at, id)")

    op.execute("""
CREATE OR REPLACE FUNCTION public.pharmacy_lock_audit_head()
RETURNS TABLE(last_sequence BIGINT, last_hash VARCHAR(64))
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    current_sequence BIGINT;
    current_hash VARCHAR(64);
BEGIN
    INSERT INTO public.audit_heads(chain_id, last_sequence, last_hash)
    VALUES ('pharmacy', 0, repeat('0', 64))
    ON CONFLICT (chain_id) DO NOTHING;

    SELECT head.last_sequence, head.last_hash
    INTO current_sequence, current_hash
    FROM public.audit_heads AS head
    WHERE head.chain_id = 'pharmacy'
    FOR UPDATE;

    RETURN QUERY SELECT current_sequence, current_hash;
END;
$$
""")
    op.execute("""
CREATE OR REPLACE FUNCTION public.pharmacy_append_audit(
    p_entry_id BIGINT,
    p_sequence BIGINT,
    p_prev_hash VARCHAR(64),
    p_entry_hash VARCHAR(64),
    p_canonical_metadata JSONB
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    current_sequence BIGINT;
    current_hash VARCHAR(64);
    action_name TEXT;
BEGIN
    SELECT head.last_sequence, head.last_hash
    INTO current_sequence, current_hash
    FROM public.audit_heads AS head
    WHERE head.chain_id = 'pharmacy'
    FOR UPDATE;

    action_name := p_canonical_metadata->>'action';
    IF current_sequence IS NULL
        OR p_entry_id IS NULL OR p_entry_id <= 0
        OR p_sequence IS NULL OR p_sequence <> current_sequence + 1
        OR p_prev_hash IS NULL OR p_prev_hash <> current_hash
        OR p_prev_hash !~ '^[0-9a-f]{64}$'
        OR p_entry_hash IS NULL OR p_entry_hash !~ '^[0-9a-f]{64}$'
        OR p_canonical_metadata IS NULL
        OR p_canonical_metadata->>'chain_id' IS DISTINCT FROM 'pharmacy'
        OR p_canonical_metadata->>'sequence' IS DISTINCT FROM p_sequence::TEXT
        OR p_canonical_metadata->>'resource_id' IS NULL
        OR p_canonical_metadata->>'resource_id' !~ '^[0-9]+$'
        OR p_canonical_metadata->>'action_kind' IS NULL
        OR p_canonical_metadata->>'action_kind' NOT IN ('mutation', 'read')
        OR action_name IS NULL
        OR action_name NOT IN (
            'medicine.created', 'medicine.updated', 'inventory.adjusted',
            'reservation.created', 'reservation.released', 'reservation.expired',
            'reservation.dispensed', 'reservation.read', 'reservation.list',
            'reservation.release', 'reservation.revalidated', 'dispensing.read',
            'dispensing.list', 'dispensing.charge_context_read',
            'authorization.denied', 'inventory.list'
        )
        OR pg_column_size(p_canonical_metadata) > 4096
    THEN
        RAISE EXCEPTION 'invalid pharmacy audit append' USING ERRCODE = '22023';
    END IF;

    INSERT INTO public.audit_entries(
        chain_id, sequence, entry_id, prev_hash, entry_hash, canonical_metadata
    ) VALUES (
        'pharmacy', p_sequence, p_entry_id, p_prev_hash, p_entry_hash,
        p_canonical_metadata
    );

    UPDATE public.audit_heads
    SET last_sequence = p_sequence, last_hash = p_entry_hash
    WHERE chain_id = 'pharmacy';
END;
$$
""")
    op.execute("REVOKE ALL ON FUNCTION public.pharmacy_lock_audit_head() FROM PUBLIC")
    op.execute(
        "REVOKE ALL ON FUNCTION public.pharmacy_append_audit(BIGINT, BIGINT, VARCHAR, VARCHAR, JSONB) FROM PUBLIC"
    )
    op.execute("GRANT EXECUTE ON FUNCTION public.pharmacy_lock_audit_head() TO pharmacy_app")
    op.execute(
        "GRANT EXECUTE ON FUNCTION public.pharmacy_append_audit(BIGINT, BIGINT, VARCHAR, VARCHAR, JSONB) TO pharmacy_app"
    )
    op.execute("REVOKE ALL ON TABLE audit_heads, audit_entries FROM pharmacy_app")
    op.execute("GRANT SELECT ON TABLE audit_heads, audit_entries TO pharmacy_app")
    op.execute(
        "REVOKE UPDATE, DELETE ON TABLE outbox_events, stock_movements, reservation_items, dispensings, dispensing_items FROM pharmacy_app"
    )
    op.execute(
        "GRANT SELECT, INSERT ON TABLE outbox_events, stock_movements, reservation_items, dispensings, dispensing_items TO pharmacy_app"
    )


def downgrade():
    op.execute("REVOKE ALL ON FUNCTION public.pharmacy_append_audit(BIGINT, BIGINT, VARCHAR, VARCHAR, JSONB) FROM pharmacy_app")
    op.execute("REVOKE ALL ON FUNCTION public.pharmacy_lock_audit_head() FROM pharmacy_app")
    op.execute("DROP FUNCTION public.pharmacy_append_audit(BIGINT, BIGINT, VARCHAR, VARCHAR, JSONB)")
    op.execute("DROP FUNCTION public.pharmacy_lock_audit_head()")
    op.execute("DROP INDEX ix_dispensings_created_at_id")
    op.execute("DROP INDEX ix_reservations_created_at_id")
    op.execute("ALTER TABLE reservation_items DROP CONSTRAINT uq_reservation_items_reservation_id")
    op.execute("ALTER TABLE prescription_item_snapshots DROP CONSTRAINT ck_prescription_item_snapshots_quantity_bounds")
    op.execute(
        "ALTER TABLE prescription_item_snapshots ADD CONSTRAINT ck_prescription_item_snapshots_quantity_bounds CHECK (prescribed_quantity >= 0 AND reserved_quantity >= 0 AND dispensed_quantity >= 0 AND reserved_quantity + dispensed_quantity <= prescribed_quantity)"
    )
    op.execute("ALTER TABLE inventory_batches DROP CONSTRAINT ck_inventory_batches_stock_bounds")
    op.execute(
        "ALTER TABLE inventory_batches ADD CONSTRAINT ck_inventory_batches_stock_bounds CHECK (0 <= reserved AND reserved <= on_hand)"
    )
    op.execute("ALTER TABLE dispensings DROP CONSTRAINT ck_dispensings_positive_version")
    op.execute("ALTER TABLE dispensings DROP COLUMN version")
    op.execute("ALTER TABLE prescription_snapshots DROP CONSTRAINT ck_prescription_snapshots_state_values")
    op.execute("ALTER TABLE prescription_snapshots DROP CONSTRAINT ck_prescription_snapshots_appointment_id_nonnegative")
    op.execute("ALTER TABLE prescription_snapshots DROP CONSTRAINT ck_prescription_snapshots_consultation_id_nonnegative")
    op.execute("ALTER TABLE prescription_snapshots DROP COLUMN appointment_id")
    op.execute("ALTER TABLE prescription_snapshots DROP COLUMN consultation_id")
    op.execute("ALTER TABLE prescription_snapshots ALTER COLUMN journey_id SET NOT NULL")
