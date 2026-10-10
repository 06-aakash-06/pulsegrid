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
CREATE TABLE doctor_schedule_snapshots (
	doctor_id BIGINT NOT NULL,
	accepted_revision BIGINT NOT NULL,
	policy_snapshot JSONB NOT NULL,
	staff_user_id BIGINT NOT NULL,
	last_decided_proposal_revision BIGINT NOT NULL,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_doctor_schedule_snapshots PRIMARY KEY (doctor_id),
	CONSTRAINT ck_doctor_schedule_snapshots_positive_version CHECK (version > 0),
	CONSTRAINT ck_doctor_schedule_snapshots_doctor_id_nonnegative CHECK (doctor_id >= 0),
	CONSTRAINT ck_doctor_schedule_snapshots_staff_user_id_nonnegative CHECK (staff_user_id >= 0)
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
CREATE TABLE patient_status_snapshots (
	patient_id BIGINT NOT NULL,
	active BOOLEAN NOT NULL,
	source_version BIGINT NOT NULL,
	observed_at TIMESTAMP WITH TIME ZONE NOT NULL,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_patient_status_snapshots PRIMARY KEY (patient_id),
	CONSTRAINT ck_patient_status_snapshots_positive_version CHECK (version > 0),
	CONSTRAINT ck_patient_status_snapshots_patient_id_nonnegative CHECK (patient_id >= 0)
)
""")
    op.execute("""
CREATE TABLE queue_counters (
	doctor_id BIGINT NOT NULL,
	local_date DATE NOT NULL,
	next_token BIGINT DEFAULT 1 NOT NULL,
	CONSTRAINT pk_queue_counters PRIMARY KEY (doctor_id, local_date),
	CONSTRAINT ck_queue_counters_positive_token CHECK (next_token > 0)
)
""")
    op.execute("""
CREATE TABLE schedule_proposals (
	id BIGINT NOT NULL,
	doctor_id BIGINT NOT NULL,
	revision BIGINT NOT NULL,
	state VARCHAR(64) NOT NULL,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_schedule_proposals PRIMARY KEY (id),
	CONSTRAINT uq_schedule_proposals_doctor_id UNIQUE (doctor_id, revision),
	CONSTRAINT ck_schedule_proposals_state_values CHECK (state IN ('accepted','rejected')),
	CONSTRAINT ck_schedule_proposals_positive_revision CHECK (revision > 0),
	CONSTRAINT ck_schedule_proposals_positive_version CHECK (version > 0),
	CONSTRAINT ck_schedule_proposals_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_schedule_proposals_doctor_id_nonnegative CHECK (doctor_id >= 0)
)
""")
    op.execute("""
CREATE TABLE slots (
	id BIGINT NOT NULL,
	doctor_id BIGINT NOT NULL,
	schedule_revision BIGINT NOT NULL,
	starts_at TIMESTAMP WITH TIME ZONE NOT NULL,
	ends_at TIMESTAMP WITH TIME ZONE NOT NULL,
	state VARCHAR(64) NOT NULL,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_slots PRIMARY KEY (id),
	CONSTRAINT uq_slots_doctor_id UNIQUE (doctor_id, starts_at, ends_at),
	CONSTRAINT ck_slots_valid_interval CHECK (ends_at > starts_at),
	CONSTRAINT ck_slots_positive_revision CHECK (schedule_revision > 0),
	CONSTRAINT ck_slots_positive_version CHECK (version > 0),
	CONSTRAINT ck_slots_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_slots_doctor_id_nonnegative CHECK (doctor_id >= 0)
)
""")
    op.execute("""
CREATE TABLE appointments (
	id BIGINT NOT NULL,
	patient_id BIGINT NOT NULL,
	slot_id BIGINT NOT NULL,
	doctor_id BIGINT NOT NULL,
	starts_at TIMESTAMP WITH TIME ZONE NOT NULL,
	ends_at TIMESTAMP WITH TIME ZONE NOT NULL,
	schedule_revision BIGINT NOT NULL,
	state VARCHAR(64) NOT NULL,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_appointments PRIMARY KEY (id),
	CONSTRAINT ck_appointments_state_values CHECK (state IN ('confirmed','checked_in','in_consultation','completed','cancelled','no_show')),
	CONSTRAINT ck_appointments_valid_interval CHECK (ends_at > starts_at),
	CONSTRAINT ck_appointments_positive_version CHECK (version > 0),
	CONSTRAINT fk_appointments_slot_id_slots FOREIGN KEY(slot_id) REFERENCES slots (id) ON DELETE RESTRICT,
	CONSTRAINT ck_appointments_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_appointments_patient_id_nonnegative CHECK (patient_id >= 0),
	CONSTRAINT ck_appointments_slot_id_nonnegative CHECK (slot_id >= 0),
	CONSTRAINT ck_appointments_doctor_id_nonnegative CHECK (doctor_id >= 0)
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
CREATE TABLE checkin_links (
	id BIGINT NOT NULL,
	appointment_id BIGINT NOT NULL,
	token_hash VARCHAR(64) NOT NULL,
	purpose VARCHAR(64) NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	consumed_at TIMESTAMP WITH TIME ZONE,
	revoked_at TIMESTAMP WITH TIME ZONE,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_checkin_links PRIMARY KEY (id),
	CONSTRAINT uq_checkin_links_token_hash UNIQUE (token_hash),
	CONSTRAINT ck_checkin_links_positive_version CHECK (version > 0),
	CONSTRAINT fk_checkin_links_appointment_id_appointments FOREIGN KEY(appointment_id) REFERENCES appointments (id) ON DELETE RESTRICT,
	CONSTRAINT ck_checkin_links_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_checkin_links_appointment_id_nonnegative CHECK (appointment_id >= 0)
)
""")
    op.execute("""
CREATE TABLE journeys (
	id BIGINT NOT NULL,
	appointment_id BIGINT NOT NULL,
	patient_id BIGINT NOT NULL,
	state VARCHAR(64) NOT NULL,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_journeys PRIMARY KEY (id),
	CONSTRAINT uq_journeys_appointment_id UNIQUE (appointment_id),
	CONSTRAINT ck_journeys_positive_version CHECK (version > 0),
	CONSTRAINT fk_journeys_appointment_id_appointments FOREIGN KEY(appointment_id) REFERENCES appointments (id) ON DELETE RESTRICT,
	CONSTRAINT ck_journeys_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_journeys_appointment_id_nonnegative CHECK (appointment_id >= 0),
	CONSTRAINT ck_journeys_patient_id_nonnegative CHECK (patient_id >= 0)
)
""")
    op.execute("""
CREATE TABLE queue_entries (
	id BIGINT NOT NULL,
	appointment_id BIGINT NOT NULL,
	doctor_id BIGINT NOT NULL,
	local_date DATE NOT NULL,
	token_number BIGINT NOT NULL,
	state VARCHAR(64) NOT NULL,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_queue_entries PRIMARY KEY (id),
	CONSTRAINT uq_queue_entries_appointment_id UNIQUE (appointment_id),
	CONSTRAINT uq_queue_entries_doctor_id UNIQUE (doctor_id, local_date, token_number),
	CONSTRAINT ck_queue_entries_positive_token CHECK (token_number > 0),
	CONSTRAINT ck_queue_entries_state_values CHECK (state IN ('waiting','in_consultation','completed','cancelled','no_show')),
	CONSTRAINT ck_queue_entries_positive_version CHECK (version > 0),
	CONSTRAINT fk_queue_entries_appointment_id_appointments FOREIGN KEY(appointment_id) REFERENCES appointments (id) ON DELETE RESTRICT,
	CONSTRAINT ck_queue_entries_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_queue_entries_appointment_id_nonnegative CHECK (appointment_id >= 0),
	CONSTRAINT ck_queue_entries_doctor_id_nonnegative CHECK (doctor_id >= 0)
)
""")
    op.execute("""
CREATE TABLE waitlist_entries (
	id BIGINT NOT NULL,
	slot_id BIGINT NOT NULL,
	patient_id BIGINT NOT NULL,
	state VARCHAR(64) NOT NULL,
	joined_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	promoted_appointment_id BIGINT,
	skip_reason VARCHAR(256),
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_waitlist_entries PRIMARY KEY (id),
	CONSTRAINT ck_waitlist_entries_state_values CHECK (state IN ('waiting','promoted','withdrawn','skipped')),
	CONSTRAINT ck_waitlist_entries_positive_version CHECK (version > 0),
	CONSTRAINT fk_waitlist_entries_slot_id_slots FOREIGN KEY(slot_id) REFERENCES slots (id) ON DELETE RESTRICT,
	CONSTRAINT fk_waitlist_entries_promoted_appointment_id_appointments FOREIGN KEY(promoted_appointment_id) REFERENCES appointments (id) ON DELETE RESTRICT,
	CONSTRAINT ck_waitlist_entries_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_waitlist_entries_slot_id_nonnegative CHECK (slot_id >= 0),
	CONSTRAINT ck_waitlist_entries_patient_id_nonnegative CHECK (patient_id >= 0),
	CONSTRAINT ck_waitlist_entries_promoted_appointment_id_nonnegative CHECK (promoted_appointment_id >= 0)
)
""")
    op.execute("""
CREATE TABLE journey_stages (
	journey_id BIGINT NOT NULL,
	stage VARCHAR(64) NOT NULL,
	state VARCHAR(64) NOT NULL,
	source_resource_id BIGINT,
	source_version BIGINT,
	source_resources JSONB DEFAULT '[]'::jsonb NOT NULL,
	observed_at TIMESTAMP WITH TIME ZONE NOT NULL,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_journey_stages PRIMARY KEY (journey_id, stage),
	CONSTRAINT ck_journey_stages_state_values CHECK (state IN ('pending','complete','skipped','reopened')),
	CONSTRAINT ck_journey_stages_positive_version CHECK (version > 0),
	CONSTRAINT fk_journey_stages_journey_id_journeys FOREIGN KEY(journey_id) REFERENCES journeys (id) ON DELETE RESTRICT,
	CONSTRAINT ck_journey_stages_journey_id_nonnegative CHECK (journey_id >= 0),
	CONSTRAINT ck_journey_stages_source_resource_id_nonnegative CHECK (source_resource_id >= 0)
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
CREATE INDEX ix_slots_doctor_id_starts_at_state ON slots (doctor_id, starts_at, state)
""")
    op.execute("""
CREATE UNIQUE INDEX ix_appointments_active_slot ON appointments (slot_id) WHERE state IN ('confirmed','checked_in','in_consultation')
""")
    op.execute("""
CREATE INDEX ix_appointments_patient_id_starts_at ON appointments (patient_id, starts_at)
""")
    op.execute("""
CREATE INDEX ix_checkin_links_appointment_id_purpose ON checkin_links (appointment_id, purpose)
""")
    op.execute("""
CREATE INDEX ix_journeys_patient_id_updated_at ON journeys (patient_id, updated_at)
""")
    op.execute("""
CREATE INDEX ix_queue_entries_doctor_id_local_date_state ON queue_entries (doctor_id, local_date, state)
""")
    op.execute("""
CREATE UNIQUE INDEX ix_queue_entries_one_consultation ON queue_entries (doctor_id) WHERE state = 'in_consultation'
""")
    op.execute("""
CREATE UNIQUE INDEX ix_waitlist_entries_one_waiting ON waitlist_entries (slot_id, patient_id) WHERE state = 'waiting'
""")
    op.execute("""
CREATE INDEX ix_waitlist_entries_slot_id_state_joined_at_id ON waitlist_entries (slot_id, state, joined_at, id)
""")
    op.execute("""
REVOKE ALL ON TABLE audit_heads, audit_entries, alembic_version FROM appointment_app
""")
    op.execute("""
GRANT SELECT ON TABLE audit_heads, audit_entries, alembic_version TO appointment_app
""")


def downgrade():
    op.drop_table("journey_stages")
    op.drop_table("waitlist_entries")
    op.drop_table("queue_entries")
    op.drop_table("journeys")
    op.drop_table("checkin_links")
    op.drop_table("audit_entries")
    op.drop_table("appointments")
    op.drop_table("slots")
    op.drop_table("schedule_proposals")
    op.drop_table("queue_counters")
    op.drop_table("patient_status_snapshots")
    op.drop_table("outbox_events")
    op.drop_table("inbox_events")
    op.drop_table("idempotency_requests")
    op.drop_table("id_worker_state")
    op.drop_table("doctor_schedule_snapshots")
    op.drop_table("audit_heads")
