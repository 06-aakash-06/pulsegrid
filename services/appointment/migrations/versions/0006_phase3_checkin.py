"""Reviewed forward-only Phase 3 integration schema; no legacy row rewrites."""
from alembic import op

revision = '0006_phase3_checkin'
down_revision = '0005_phase3_waitlist'
branch_labels = depends_on = None


def upgrade():
    op.execute("""
DO $$ BEGIN IF EXISTS(SELECT FROM checkin_links) THEN RAISE EXCEPTION 'Review existing check-in credentials before binding upgrade'; END IF; END $$;
ALTER TABLE checkin_links ADD COLUMN workflow_version bigint NOT NULL, ADD COLUMN schedule_fingerprint varchar(64) NOT NULL;
ALTER TABLE checkin_links ADD CONSTRAINT ck_checkin_links_workflow_version_safe CHECK(workflow_version BETWEEN 1 AND 9007199254740991), ADD CONSTRAINT ck_checkin_links_schedule_fingerprint_sha256 CHECK(schedule_fingerprint ~ '^[0-9a-f]{64}$'), ADD CONSTRAINT ck_checkin_links_token_hash_sha256 CHECK(token_hash ~ '^[0-9a-f]{64}$'), ADD CONSTRAINT ck_checkin_links_check_in_purpose CHECK(purpose='check_in');
CREATE UNIQUE INDEX uq_checkin_links_live_appointment_purpose ON checkin_links(appointment_id,purpose) WHERE consumed_at IS NULL AND revoked_at IS NULL;
""")


def downgrade():
    raise RuntimeError("Forward-only; preserve workflow history")
