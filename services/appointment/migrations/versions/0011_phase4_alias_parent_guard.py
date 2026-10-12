"""Explicit positive alias parent invariant, in addition to the local FK."""
from alembic import op
revision='0011_phase4_alias_parent_guard'
down_revision='0010_phase4_short_links'
branch_labels=depends_on=None

def upgrade():
    op.execute('ALTER TABLE short_links ADD CONSTRAINT ck_short_links_parent_positive CHECK(appointment_id>0)')

def downgrade():
    raise RuntimeError('Forward-only alias history')
