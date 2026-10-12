"""Add diagnostics and a selected-event claim index to Pharmacy outbox."""
from alembic import op

revision = "0006_phase5_event_delivery"
down_revision = "0005_phase4_catalog_revision"
branch_labels = depends_on = None


def upgrade():
    op.execute("ALTER TABLE outbox_events ADD COLUMN last_error varchar(128)")
    op.execute(
        "CREATE INDEX ix_outbox_events_phase5_due "
        "ON outbox_events(event_type,next_attempt_at,event_id) "
        "WHERE published_at IS NULL"
    )


def downgrade():
    raise RuntimeError("Forward-only Phase 5 event delivery")
