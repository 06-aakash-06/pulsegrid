"""Initial documented schema; frozen DDL, with business operations deferred."""

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE TABLE audit_heads (
	chain_id VARCHAR(128) NOT NULL,
	last_sequence BIGINT DEFAULT 0 NOT NULL,
	last_hash VARCHAR(64) NOT NULL,
	CONSTRAINT pk_audit_heads PRIMARY KEY (chain_id),
	CONSTRAINT ck_audit_heads_sequence_nonnegative CHECK (last_sequence >= 0)
)
""")
    op.execute("""
CREATE TABLE id_worker_state (
	worker_id SERIAL NOT NULL,
	reserved_through_ms BIGINT NOT NULL,
	CONSTRAINT pk_id_worker_state PRIMARY KEY (worker_id),
	CONSTRAINT ck_id_worker_state_worker_range CHECK (worker_id BETWEEN 0 AND 1023),
	CONSTRAINT ck_id_worker_state_high_watermark_nonnegative CHECK (reserved_through_ms >= 0)
)
""")
    op.execute("""
CREATE TABLE idempotency_requests (
	principal_scope VARCHAR(256) NOT NULL,
	method VARCHAR(8) NOT NULL,
	route_template VARCHAR(256) NOT NULL,
	key VARCHAR(256) NOT NULL,
	request_hash VARCHAR(64) NOT NULL,
	response_code INTEGER NOT NULL,
	response JSONB NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	CONSTRAINT pk_idempotency_requests PRIMARY KEY (principal_scope, method, route_template, key),
	CONSTRAINT ck_idempotency_requests_response_code_range CHECK (response_code BETWEEN 100 AND 599)
)
""")
    op.execute("""
CREATE TABLE inbox_events (
	consumer_name VARCHAR(128) NOT NULL,
	event_id BIGINT NOT NULL,
	processed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_inbox_events PRIMARY KEY (consumer_name, event_id)
)
""")
    op.execute("""
CREATE TABLE outbox_events (
	event_id BIGINT NOT NULL,
	aggregate_type VARCHAR(64) NOT NULL,
	aggregate_id BIGINT NOT NULL,
	aggregate_version BIGINT NOT NULL,
	event_type VARCHAR(128) NOT NULL,
	envelope JSONB NOT NULL,
	published_at TIMESTAMP WITH TIME ZONE,
	attempt_count INTEGER DEFAULT 0 NOT NULL,
	next_attempt_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	claimed_by VARCHAR(128),
	lease_expires_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_outbox_events PRIMARY KEY (event_id),
	CONSTRAINT ck_outbox_events_attempt_count_nonnegative CHECK (attempt_count >= 0),
	CONSTRAINT ck_outbox_events_aggregate_version_positive CHECK (aggregate_version > 0),
	CONSTRAINT ck_outbox_events_event_id_nonnegative CHECK (event_id >= 0),
	CONSTRAINT ck_outbox_events_aggregate_id_nonnegative CHECK (aggregate_id >= 0)
)
""")
    op.execute("""
CREATE TABLE users (
	id BIGINT NOT NULL,
	email_normalized VARCHAR(320) NOT NULL,
	password_hash TEXT NOT NULL,
	account_state VARCHAR(64) NOT NULL,
	auth_version BIGINT DEFAULT 1 NOT NULL,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_users PRIMARY KEY (id),
	CONSTRAINT uq_users_email_normalized UNIQUE (email_normalized),
	CONSTRAINT ck_users_account_state_values CHECK (account_state IN ('active','disabled')),
	CONSTRAINT ck_users_positive_auth_version CHECK (auth_version > 0),
	CONSTRAINT ck_users_positive_version CHECK (version > 0),
	CONSTRAINT ck_users_id_nonnegative CHECK (id >= 0)
)
""")
    op.execute("""
CREATE TABLE audit_entries (
	chain_id VARCHAR(128) NOT NULL,
	sequence BIGINT NOT NULL,
	entry_id BIGINT NOT NULL,
	prev_hash VARCHAR(64) NOT NULL,
	entry_hash VARCHAR(64) NOT NULL,
	canonical_metadata JSONB NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_audit_entries PRIMARY KEY (chain_id, sequence),
	CONSTRAINT uq_audit_entries_entry_id UNIQUE (entry_id),
	CONSTRAINT ck_audit_entries_sequence_positive CHECK (sequence > 0),
	CONSTRAINT fk_audit_entries_chain_id_audit_heads FOREIGN KEY(chain_id) REFERENCES audit_heads (chain_id) ON DELETE RESTRICT
)
""")
    op.execute("""
CREATE TABLE patient_profiles (
	id BIGINT NOT NULL,
	user_id BIGINT NOT NULL,
	display_name VARCHAR(200) NOT NULL,
	date_of_birth DATE,
	synthetic_contact VARCHAR(256),
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_patient_profiles PRIMARY KEY (id),
	CONSTRAINT uq_patient_profiles_user_id UNIQUE (user_id),
	CONSTRAINT ck_patient_profiles_positive_version CHECK (version > 0),
	CONSTRAINT fk_patient_profiles_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT,
	CONSTRAINT ck_patient_profiles_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_patient_profiles_user_id_nonnegative CHECK (user_id >= 0)
)
""")
    op.execute("""
CREATE TABLE refresh_sessions (
	id BIGINT NOT NULL,
	user_id BIGINT NOT NULL,
	family_id BIGINT NOT NULL,
	token_hash VARCHAR(64) NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	family_expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	revoked_at TIMESTAMP WITH TIME ZONE,
	replaced_by_id BIGINT,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_refresh_sessions PRIMARY KEY (id),
	CONSTRAINT uq_refresh_sessions_token_hash UNIQUE (token_hash),
	CONSTRAINT ck_refresh_sessions_family_expiry_bound CHECK (expires_at <= family_expires_at),
	CONSTRAINT ck_refresh_sessions_positive_version CHECK (version > 0),
	CONSTRAINT fk_refresh_sessions_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT,
	CONSTRAINT fk_refresh_sessions_replaced_by_id_refresh_sessions FOREIGN KEY(replaced_by_id) REFERENCES refresh_sessions (id) ON DELETE RESTRICT,
	CONSTRAINT ck_refresh_sessions_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_refresh_sessions_user_id_nonnegative CHECK (user_id >= 0),
	CONSTRAINT ck_refresh_sessions_family_id_nonnegative CHECK (family_id >= 0),
	CONSTRAINT ck_refresh_sessions_replaced_by_id_nonnegative CHECK (replaced_by_id >= 0)
)
""")
    op.execute("""
CREATE TABLE role_assignments (
	id BIGINT NOT NULL,
	user_id BIGINT NOT NULL,
	role VARCHAR(64) NOT NULL,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_role_assignments PRIMARY KEY (id),
	CONSTRAINT uq_role_assignments_user_id UNIQUE (user_id, role),
	CONSTRAINT ck_role_assignments_role_values CHECK (role IN ('patient','doctor','receptionist','pharmacist','billing_staff','emergency_staff','hospital_admin','ops')),
	CONSTRAINT ck_role_assignments_positive_version CHECK (version > 0),
	CONSTRAINT fk_role_assignments_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT,
	CONSTRAINT ck_role_assignments_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_role_assignments_user_id_nonnegative CHECK (user_id >= 0)
)
""")
    op.execute("""
CREATE INDEX ix_idempotency_requests_expires_at ON idempotency_requests (expires_at)
""")
    op.execute("""
CREATE INDEX ix_inbox_events_processed_at ON inbox_events (processed_at)
""")
    op.execute("""
CREATE INDEX ix_outbox_events_unpublished ON outbox_events (next_attempt_at, event_id) WHERE published_at IS NULL
""")
    op.execute("""
CREATE INDEX ix_refresh_sessions_expires_at ON refresh_sessions (expires_at)
""")
    op.execute("""
CREATE INDEX ix_refresh_sessions_family_id_user_id ON refresh_sessions (family_id, user_id)
""")
    op.execute("""
REVOKE ALL ON TABLE audit_heads, audit_entries, alembic_version FROM patient_app
""")
    op.execute("""
GRANT SELECT ON TABLE audit_heads, audit_entries, alembic_version TO patient_app
""")


def downgrade():
    op.drop_table("role_assignments")
    op.drop_table("refresh_sessions")
    op.drop_table("patient_profiles")
    op.drop_table("audit_entries")
    op.drop_table("users")
    op.drop_table("outbox_events")
    op.drop_table("inbox_events")
    op.drop_table("idempotency_requests")
    op.drop_table("id_worker_state")
    op.drop_table("audit_heads")
