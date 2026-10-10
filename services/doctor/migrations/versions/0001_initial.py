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
CREATE TABLE doctors (
	id BIGINT NOT NULL,
	staff_user_id BIGINT NOT NULL,
	display_name VARCHAR(200) NOT NULL,
	active BOOLEAN DEFAULT true NOT NULL,
	profile_version BIGINT DEFAULT 1 NOT NULL,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_doctors PRIMARY KEY (id),
	CONSTRAINT uq_doctors_staff_user_id UNIQUE (staff_user_id),
	CONSTRAINT ck_doctors_positive_profile_version CHECK (profile_version > 0),
	CONSTRAINT ck_doctors_positive_version CHECK (version > 0),
	CONSTRAINT ck_doctors_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_doctors_staff_user_id_nonnegative CHECK (staff_user_id >= 0)
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
CREATE TABLE specialties (
	id BIGINT NOT NULL,
	slug VARCHAR(128) NOT NULL,
	name VARCHAR(200) NOT NULL,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_specialties PRIMARY KEY (id),
	CONSTRAINT uq_specialties_slug UNIQUE (slug),
	CONSTRAINT ck_specialties_positive_version CHECK (version > 0),
	CONSTRAINT ck_specialties_id_nonnegative CHECK (id >= 0)
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
CREATE TABLE doctor_specialties (
	doctor_id BIGINT NOT NULL,
	specialty_id BIGINT NOT NULL,
	CONSTRAINT pk_doctor_specialties PRIMARY KEY (doctor_id, specialty_id),
	CONSTRAINT fk_doctor_specialties_doctor_id_doctors FOREIGN KEY(doctor_id) REFERENCES doctors (id) ON DELETE RESTRICT,
	CONSTRAINT fk_doctor_specialties_specialty_id_specialties FOREIGN KEY(specialty_id) REFERENCES specialties (id) ON DELETE RESTRICT
)
""")
    op.execute("""
CREATE TABLE schedule_versions (
	id BIGINT NOT NULL,
	doctor_id BIGINT NOT NULL,
	revision BIGINT NOT NULL,
	timezone VARCHAR(128) NOT NULL,
	slot_minutes INTEGER NOT NULL,
	effective_from TIMESTAMP WITH TIME ZONE NOT NULL,
	status VARCHAR(64) NOT NULL,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_schedule_versions PRIMARY KEY (id),
	CONSTRAINT uq_schedule_versions_doctor_id UNIQUE (doctor_id, revision),
	CONSTRAINT ck_schedule_versions_positive_policy CHECK (revision > 0 AND slot_minutes > 0),
	CONSTRAINT ck_schedule_versions_status_values CHECK (status IN ('pending','accepted','rejected')),
	CONSTRAINT ck_schedule_versions_positive_version CHECK (version > 0),
	CONSTRAINT fk_schedule_versions_doctor_id_doctors FOREIGN KEY(doctor_id) REFERENCES doctors (id) ON DELETE RESTRICT,
	CONSTRAINT ck_schedule_versions_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_schedule_versions_doctor_id_nonnegative CHECK (doctor_id >= 0)
)
""")
    op.execute("""
CREATE TABLE schedule_acknowledgements (
	id BIGINT NOT NULL,
	schedule_version_id BIGINT NOT NULL,
	accepted BOOLEAN NOT NULL,
	operational_version BIGINT,
	reason TEXT,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_schedule_acknowledgements PRIMARY KEY (id),
	CONSTRAINT uq_schedule_acknowledgements_schedule_version_id UNIQUE (schedule_version_id),
	CONSTRAINT fk_schedule_acknowledgements_schedule_version_id_schedu_875f FOREIGN KEY(schedule_version_id) REFERENCES schedule_versions (id) ON DELETE RESTRICT,
	CONSTRAINT ck_schedule_acknowledgements_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_schedule_acknowledgements_schedule_version_id_nonnegative CHECK (schedule_version_id >= 0)
)
""")
    op.execute("""
CREATE TABLE schedule_intervals (
	id BIGINT NOT NULL,
	schedule_version_id BIGINT NOT NULL,
	starts_at TIMESTAMP WITH TIME ZONE NOT NULL,
	ends_at TIMESTAMP WITH TIME ZONE NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_schedule_intervals PRIMARY KEY (id),
	CONSTRAINT ck_schedule_intervals_valid_interval CHECK (ends_at > starts_at),
	CONSTRAINT fk_schedule_intervals_schedule_version_id_schedule_versions FOREIGN KEY(schedule_version_id) REFERENCES schedule_versions (id) ON DELETE RESTRICT,
	CONSTRAINT ck_schedule_intervals_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_schedule_intervals_schedule_version_id_nonnegative CHECK (schedule_version_id >= 0)
)
""")
    op.execute("""
CREATE INDEX ix_doctors_active ON doctors (active)
""")
    op.execute("""
CREATE INDEX ix_doctors_name_prefix ON doctors (display_name varchar_pattern_ops)
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
CREATE INDEX ix_doctor_specialties_specialty_id_doctor_id ON doctor_specialties (specialty_id, doctor_id)
""")
    op.execute("""
CREATE UNIQUE INDEX ix_schedule_versions_one_pending ON schedule_versions (doctor_id) WHERE status = 'pending'
""")
    op.execute("""
CREATE INDEX ix_schedule_intervals_schedule_version_id_starts_at ON schedule_intervals (schedule_version_id, starts_at)
""")
    op.execute("""
REVOKE ALL ON TABLE audit_heads, audit_entries, alembic_version FROM doctor_app
""")
    op.execute("""
GRANT SELECT ON TABLE audit_heads, audit_entries, alembic_version TO doctor_app
""")


def downgrade():
    op.drop_table("schedule_intervals")
    op.drop_table("schedule_acknowledgements")
    op.drop_table("schedule_versions")
    op.drop_table("doctor_specialties")
    op.drop_table("audit_entries")
    op.drop_table("specialties")
    op.drop_table("outbox_events")
    op.drop_table("inbox_events")
    op.drop_table("idempotency_requests")
    op.drop_table("id_worker_state")
    op.drop_table("doctors")
    op.drop_table("audit_heads")
