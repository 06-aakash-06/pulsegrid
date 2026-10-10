"""Worker identity is allocated explicitly, never by a PostgreSQL sequence."""

from alembic import op

revision = "0003_explicit_worker"
down_revision = "0002_schedule_exclusion"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE id_worker_state ALTER COLUMN worker_id DROP DEFAULT")
    op.execute("DROP SEQUENCE IF EXISTS id_worker_state_worker_id_seq")


def downgrade():
    op.execute(
        "CREATE SEQUENCE id_worker_state_worker_id_seq OWNED BY id_worker_state.worker_id"
    )
    op.execute(
        "ALTER TABLE id_worker_state ALTER COLUMN worker_id SET DEFAULT nextval('id_worker_state_worker_id_seq')"
    )
    op.execute(
        "SELECT setval('id_worker_state_worker_id_seq', COALESCE((SELECT max(worker_id) FROM id_worker_state), 0) + 1, false)"
    )
