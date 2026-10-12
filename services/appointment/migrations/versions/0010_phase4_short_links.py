"""Add navigation aliases without changing appointments or QR credentials."""
from alembic import op
revision='0010_phase4_short_links'
down_revision='0009_phase3_registration_history'
branch_labels=depends_on=None

def upgrade():
    op.execute("""
    CREATE TABLE short_links(
      id bigint PRIMARY KEY CHECK(id>0), appointment_id bigint NOT NULL REFERENCES appointments(id) ON DELETE RESTRICT,
      purpose varchar(16) NOT NULL CHECK(purpose IN ('appointment','check_in')),
      token_hash varchar(64) NOT NULL CONSTRAINT uq_short_links_token_hash UNIQUE CHECK(token_hash ~ '^[0-9a-f]{64}$'),
      expires_at timestamptz NOT NULL, revoked_at timestamptz,
      workflow_version bigint NOT NULL CHECK(workflow_version BETWEEN 1 AND 9007199254740991),
      schedule_fingerprint varchar(64) NOT NULL CHECK(schedule_fingerprint ~ '^[0-9a-f]{64}$'),
      version bigint NOT NULL DEFAULT 1 CHECK(version BETWEEN 1 AND 9007199254740991),
      created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE UNIQUE INDEX uq_short_links_live_appointment_purpose ON short_links(appointment_id,purpose) WHERE revoked_at IS NULL;
    CREATE INDEX ix_short_links_appointment_id ON short_links(appointment_id);
    REVOKE ALL ON short_links FROM appointment_app;
    GRANT SELECT,INSERT,UPDATE ON short_links TO appointment_app;
    DO $$ DECLARE definition text; BEGIN
      definition:=pg_get_functiondef('public.appointment_append_phase3_audit(bigint,jsonb)'::regprocedure);
      definition:=replace(definition, $old$'workflow_link_issued'$old$, $new$'short_link_created','short_link_revoked','workflow_link_issued'$new$);
      EXECUTE definition;
    END $$;
    """)

def downgrade():
    raise RuntimeError('Forward-only alias/audit history')
