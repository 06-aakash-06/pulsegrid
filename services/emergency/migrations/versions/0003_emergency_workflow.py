"""Emergency workflow constraints and constrained audit append capability."""

from alembic import op
import sqlalchemy as sa

revision = "0003_emergency_workflow"
down_revision = "0002_explicit_worker"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "id_worker_state",
        sa.Column("last_sequence", sa.Integer(), server_default=sa.text("-1"), nullable=False),
    )
    op.create_check_constraint(
        "sequence_range",
        "id_worker_state",
        "last_sequence BETWEEN -1 AND 4095",
    )
    op.create_check_constraint(
        "reported_urgency_values",
        "emergency_requests",
        "reported_urgency IN ('unspecified','urgent')",
    )
    op.create_check_constraint(
        "description_length",
        "emergency_requests",
        "char_length(btrim(description)) BETWEEN 1 AND 4000",
    )
    op.drop_constraint(
        "claim_pair", "emergency_requests", type_="check"
    )
    op.create_check_constraint(
        "claim_state",
        "emergency_requests",
        "(state IN ('claimed','processing')) = (claimed_by_user_id IS NOT NULL) "
        "AND (state = 'claimed') = (claim_expires_at IS NOT NULL)",
    )

    # pgcrypto is a trusted, PostgreSQL-provided extension. The function is
    # SECURITY DEFINER so the runtime role can append a hash-chain entry while
    # retaining no direct UPDATE/DELETE permission on audit storage.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(
        r"""
CREATE FUNCTION append_emergency_audit(
    p_entry_id BIGINT,
    p_canonical_metadata JSONB
)
RETURNS TABLE(audit_sequence BIGINT, previous_hash VARCHAR, current_hash VARCHAR)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    v_head public.audit_heads%ROWTYPE;
    v_sequence BIGINT;
    v_prev_hash VARCHAR(64);
    v_entry_hash VARCHAR(64);
BEGIN
    IF p_entry_id IS NULL OR p_entry_id <= 0
       OR p_canonical_metadata IS NULL
       OR jsonb_typeof(p_canonical_metadata) <> 'object' THEN
        RAISE EXCEPTION 'invalid emergency audit entry' USING ERRCODE = '22023';
    END IF;

    INSERT INTO public.audit_heads(chain_id, last_sequence, last_hash)
    VALUES ('emergency', 0, repeat('0', 64))
    ON CONFLICT (chain_id) DO NOTHING;

    SELECT * INTO v_head
    FROM public.audit_heads
    WHERE chain_id = 'emergency'
    FOR UPDATE;

    v_sequence := v_head.last_sequence + 1;
    v_prev_hash := v_head.last_hash;
    v_entry_hash := encode(
        public.digest(
            convert_to(v_prev_hash || p_canonical_metadata::text, 'UTF8'),
            'sha256'
        ),
        'hex'
    );

    INSERT INTO public.audit_entries(
        chain_id, sequence, entry_id, prev_hash, entry_hash,
        canonical_metadata, created_at
    ) VALUES (
        'emergency', v_sequence, p_entry_id, v_prev_hash, v_entry_hash,
        p_canonical_metadata, statement_timestamp()
    );

    UPDATE public.audit_heads
    SET last_sequence = v_sequence, last_hash = v_entry_hash
    WHERE chain_id = 'emergency';

    audit_sequence := v_sequence;
    previous_hash := v_prev_hash;
    current_hash := v_entry_hash;
    RETURN NEXT;
END
$function$
"""
    )
    op.execute(
        "REVOKE ALL ON FUNCTION append_emergency_audit(BIGINT, JSONB) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION append_emergency_audit(BIGINT, JSONB) TO emergency_app"
    )
    op.execute(
        "REVOKE UPDATE, DELETE, TRUNCATE ON TABLE emergency_status_history FROM emergency_app"
    )
    op.execute(
        "GRANT SELECT, INSERT ON TABLE emergency_status_history TO emergency_app"
    )
    op.execute(
        "REVOKE DELETE, TRUNCATE ON TABLE emergency_requests FROM emergency_app"
    )


def downgrade():
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE emergency_requests TO emergency_app"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE emergency_status_history TO emergency_app"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION append_emergency_audit(BIGINT, JSONB) FROM emergency_app"
    )
    op.execute("DROP FUNCTION append_emergency_audit(BIGINT, JSONB)")
    op.drop_constraint(
        "claim_state", "emergency_requests", type_="check"
    )
    op.create_check_constraint(
        "claim_pair",
        "emergency_requests",
        "(claimed_by_user_id IS NULL) = (claim_expires_at IS NULL)",
    )
    op.drop_constraint(
        "description_length",
        "emergency_requests",
        type_="check",
    )
    op.drop_constraint(
        "reported_urgency_values",
        "emergency_requests",
        type_="check",
    )
    op.drop_constraint(
        "sequence_range", "id_worker_state", type_="check"
    )
    op.drop_column("id_worker_state", "last_sequence")
