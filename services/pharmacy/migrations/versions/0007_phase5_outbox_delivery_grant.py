"""Grant Pharmacy's publisher only outbox delivery metadata updates."""
from alembic import op

revision = "0007_phase5_outbox_grants"
down_revision = "0006_phase5_event_delivery"
branch_labels = depends_on = None


def upgrade():
    op.execute(
        "GRANT UPDATE (published_at, attempt_count, next_attempt_at, claimed_by, "
        "lease_expires_at, updated_at, last_error) ON TABLE outbox_events TO pharmacy_app"
    )


def downgrade():
    raise RuntimeError("Forward-only Phase 5 event delivery permissions")
