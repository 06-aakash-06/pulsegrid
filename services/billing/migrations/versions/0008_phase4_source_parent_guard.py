"""Explicit source-observation parent bound, retaining immutable rules."""
from alembic import op
revision='0008_phase4_source_parent_guard'
down_revision='0007_phase4_worker_audit_guard'
branch_labels=depends_on=None

def upgrade():
    op.execute('ALTER TABLE insurance_source_versions ADD CONSTRAINT ck_phase4_source_provider_positive CHECK(provider_id>0)')

def downgrade():
    raise RuntimeError('Forward-only source provenance')
