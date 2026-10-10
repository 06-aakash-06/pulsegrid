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
CREATE TABLE emergency_requests (
	id BIGINT NOT NULL,
	patient_id BIGINT,
	synthetic_contact VARCHAR(256),
	description TEXT NOT NULL,
	reported_urgency VARCHAR(64) NOT NULL,
	assigned_priority INTEGER,
	state VARCHAR(64) NOT NULL,
	claimed_by_user_id BIGINT,
	claim_expires_at TIMESTAMP WITH TIME ZONE,
	tracking_token_hash VARCHAR(64),
	tracking_expires_at TIMESTAMP WITH TIME ZONE,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_emergency_requests PRIMARY KEY (id),
	CONSTRAINT uq_emergency_requests_tracking_token_hash UNIQUE (tracking_token_hash),
	CONSTRAINT ck_emergency_requests_state_values CHECK (state IN ('submitted','triaged','claimed','processing','resolved','cancelled')),
	CONSTRAINT ck_emergency_requests_priority_range CHECK (assigned_priority BETWEEN 1 AND 5),
	CONSTRAINT ck_emergency_requests_tracking_pair CHECK ((tracking_token_hash IS NULL) = (tracking_expires_at IS NULL)),
	CONSTRAINT ck_emergency_requests_claim_pair CHECK ((claimed_by_user_id IS NULL) = (claim_expires_at IS NULL)),
	CONSTRAINT ck_emergency_requests_positive_version CHECK (version > 0),
	CONSTRAINT ck_emergency_requests_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_emergency_requests_patient_id_nonnegative CHECK (patient_id >= 0),
	CONSTRAINT ck_emergency_requests_claimed_by_user_id_nonnegative CHECK (claimed_by_user_id >= 0)
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
CREATE TABLE emergency_status_history (
	id BIGINT NOT NULL,
	request_id BIGINT NOT NULL,
	previous_state VARCHAR(64),
	new_state VARCHAR(64) NOT NULL,
	priority INTEGER,
	actor_user_id BIGINT,
	reason TEXT NOT NULL,
	occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_emergency_status_history PRIMARY KEY (id),
	CONSTRAINT ck_emergency_status_history_priority_range CHECK (priority BETWEEN 1 AND 5),
	CONSTRAINT fk_emergency_status_history_request_id_emergency_requests FOREIGN KEY(request_id) REFERENCES emergency_requests (id) ON DELETE RESTRICT,
	CONSTRAINT ck_emergency_status_history_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_emergency_status_history_request_id_nonnegative CHECK (request_id >= 0),
	CONSTRAINT ck_emergency_status_history_actor_user_id_nonnegative CHECK (actor_user_id >= 0)
)
""")
    op.execute("""
CREATE INDEX ix_emergency_requests_claim_expires_at ON emergency_requests (claim_expires_at)
""")
    op.execute("""
CREATE INDEX ix_emergency_requests_state_assigned_priority_created_at_id ON emergency_requests (state, assigned_priority, created_at, id)
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
CREATE INDEX ix_emergency_status_history_request_id_occurred_at ON emergency_status_history (request_id, occurred_at)
""")
    op.execute("""
REVOKE ALL ON TABLE audit_heads, audit_entries, alembic_version FROM emergency_app
""")
    op.execute("""
GRANT SELECT ON TABLE audit_heads, audit_entries, alembic_version TO emergency_app
""")


def downgrade():
    op.drop_table("emergency_status_history")
    op.drop_table("audit_entries")
    op.drop_table("outbox_events")
    op.drop_table("inbox_events")
    op.drop_table("idempotency_requests")
    op.drop_table("id_worker_state")
    op.drop_table("emergency_requests")
    op.drop_table("audit_heads")
