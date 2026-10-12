"""Permit provider row locking with only version-column UPDATE privilege."""
from alembic import op
revision='0006_phase4_provider_lock_grant'
down_revision='0005_phase4_insurance'
branch_labels=depends_on=None

def upgrade():
    op.execute('GRANT UPDATE(version) ON insurance_providers TO billing_app')

def downgrade():
    op.execute('REVOKE UPDATE(version) ON insurance_providers FROM billing_app')
