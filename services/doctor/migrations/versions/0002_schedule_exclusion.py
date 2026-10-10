"""Enforce Doctor's documented per-proposal interval overlap invariant."""

from alembic import op

revision = "0002_schedule_exclusion"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute("""ALTER TABLE schedule_intervals
        ADD CONSTRAINT excl_schedule_intervals_overlap EXCLUDE USING gist
        (schedule_version_id WITH =, tstzrange(starts_at, ends_at, '[)') WITH &&)""")


def downgrade():
    op.drop_constraint("excl_schedule_intervals_overlap", "schedule_intervals")
    # Preserve the extension: another reviewed constraint may now depend on it.
