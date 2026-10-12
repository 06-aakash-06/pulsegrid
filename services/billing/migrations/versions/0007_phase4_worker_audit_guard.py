"""Reject missing worker audit identity even under SQL three-valued logic."""
from alembic import op
revision='0007_phase4_worker_audit_guard'
down_revision='0006_phase4_provider_lock_grant'
branch_labels=depends_on=None

def upgrade():
    op.execute("""DO $$ DECLARE definition text; BEGIN
      definition:=pg_get_functiondef('public.billing_append_insurance_audit(bigint,jsonb)'::regprocedure);
      definition:=replace(definition, 'OR NOT ((p_metadata', 'OR NOT COALESCE(((p_metadata');
      definition:=replace(definition, $old$'insurance.source_revision_conflict')))$old$, $new$'insurance.source_revision_conflict'))),false)$new$);
      EXECUTE definition;
    END $$;""")

def downgrade():
    raise RuntimeError('Forward-only audit guard')
