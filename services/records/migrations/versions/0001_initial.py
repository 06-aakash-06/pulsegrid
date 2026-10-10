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
CREATE TABLE consultations (
	id BIGINT NOT NULL,
	appointment_id BIGINT NOT NULL,
	journey_id BIGINT NOT NULL,
	patient_id BIGINT NOT NULL,
	doctor_id BIGINT NOT NULL,
	status VARCHAR(64) NOT NULL,
	revision BIGINT NOT NULL,
	clinical_content JSONB NOT NULL,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_consultations PRIMARY KEY (id),
	CONSTRAINT uq_consultations_appointment_id UNIQUE (appointment_id),
	CONSTRAINT ck_consultations_positive_revision CHECK (revision > 0),
	CONSTRAINT ck_consultations_positive_version CHECK (version > 0),
	CONSTRAINT ck_consultations_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_consultations_appointment_id_nonnegative CHECK (appointment_id >= 0),
	CONSTRAINT ck_consultations_journey_id_nonnegative CHECK (journey_id >= 0),
	CONSTRAINT ck_consultations_patient_id_nonnegative CHECK (patient_id >= 0),
	CONSTRAINT ck_consultations_doctor_id_nonnegative CHECK (doctor_id >= 0)
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
CREATE TABLE record_access_grants (
	id BIGINT NOT NULL,
	patient_id BIGINT NOT NULL,
	grantee_user_id BIGINT NOT NULL,
	scope VARCHAR(64) NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	revoked_at TIMESTAMP WITH TIME ZONE,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_record_access_grants PRIMARY KEY (id),
	CONSTRAINT ck_record_access_grants_scope_values CHECK (scope IN ('records:read','prescriptions:read')),
	CONSTRAINT ck_record_access_grants_positive_version CHECK (version > 0),
	CONSTRAINT ck_record_access_grants_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_record_access_grants_patient_id_nonnegative CHECK (patient_id >= 0),
	CONSTRAINT ck_record_access_grants_grantee_user_id_nonnegative CHECK (grantee_user_id >= 0)
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
CREATE TABLE medical_records (
	id BIGINT NOT NULL,
	consultation_id BIGINT NOT NULL,
	patient_id BIGINT NOT NULL,
	author_user_id BIGINT NOT NULL,
	content JSONB NOT NULL,
	revision BIGINT NOT NULL,
	supersedes_id BIGINT,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_medical_records PRIMARY KEY (id),
	CONSTRAINT ck_medical_records_positive_revision CHECK (revision > 0),
	CONSTRAINT ck_medical_records_positive_version CHECK (version > 0),
	CONSTRAINT fk_medical_records_consultation_id_consultations FOREIGN KEY(consultation_id) REFERENCES consultations (id) ON DELETE RESTRICT,
	CONSTRAINT fk_medical_records_supersedes_id_medical_records FOREIGN KEY(supersedes_id) REFERENCES medical_records (id) ON DELETE RESTRICT,
	CONSTRAINT ck_medical_records_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_medical_records_consultation_id_nonnegative CHECK (consultation_id >= 0),
	CONSTRAINT ck_medical_records_patient_id_nonnegative CHECK (patient_id >= 0),
	CONSTRAINT ck_medical_records_author_user_id_nonnegative CHECK (author_user_id >= 0),
	CONSTRAINT ck_medical_records_supersedes_id_nonnegative CHECK (supersedes_id >= 0)
)
""")
    op.execute("""
CREATE TABLE prescriptions (
	id BIGINT NOT NULL,
	consultation_id BIGINT NOT NULL,
	patient_id BIGINT NOT NULL,
	journey_id BIGINT NOT NULL,
	revision BIGINT NOT NULL,
	state VARCHAR(64) NOT NULL,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_prescriptions PRIMARY KEY (id),
	CONSTRAINT uq_prescriptions_consultation_id UNIQUE (consultation_id, revision),
	CONSTRAINT ck_prescriptions_positive_revision CHECK (revision > 0),
	CONSTRAINT ck_prescriptions_positive_version CHECK (version > 0),
	CONSTRAINT fk_prescriptions_consultation_id_consultations FOREIGN KEY(consultation_id) REFERENCES consultations (id) ON DELETE RESTRICT,
	CONSTRAINT ck_prescriptions_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_prescriptions_consultation_id_nonnegative CHECK (consultation_id >= 0),
	CONSTRAINT ck_prescriptions_patient_id_nonnegative CHECK (patient_id >= 0),
	CONSTRAINT ck_prescriptions_journey_id_nonnegative CHECK (journey_id >= 0)
)
""")
    op.execute("""
CREATE TABLE prescription_items (
	id BIGINT NOT NULL,
	prescription_id BIGINT NOT NULL,
	medicine_id BIGINT NOT NULL,
	medicine_snapshot JSONB NOT NULL,
	dosage TEXT NOT NULL,
	instructions TEXT NOT NULL,
	quantity INTEGER NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_prescription_items PRIMARY KEY (id),
	CONSTRAINT ck_prescription_items_positive_quantity CHECK (quantity > 0),
	CONSTRAINT fk_prescription_items_prescription_id_prescriptions FOREIGN KEY(prescription_id) REFERENCES prescriptions (id) ON DELETE RESTRICT,
	CONSTRAINT ck_prescription_items_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_prescription_items_prescription_id_nonnegative CHECK (prescription_id >= 0),
	CONSTRAINT ck_prescription_items_medicine_id_nonnegative CHECK (medicine_id >= 0)
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
CREATE INDEX ix_record_access_grants_active_grants ON record_access_grants (patient_id, grantee_user_id) WHERE revoked_at IS NULL
""")
    op.execute("""
CREATE INDEX ix_medical_records_consultation_id_revision ON medical_records (consultation_id, revision)
""")
    op.execute("""
CREATE INDEX ix_medical_records_patient_id_created_at ON medical_records (patient_id, created_at)
""")
    op.execute("""
CREATE INDEX ix_prescriptions_patient_id_created_at ON prescriptions (patient_id, created_at)
""")
    op.execute("""
CREATE INDEX ix_prescription_items_prescription_id ON prescription_items (prescription_id)
""")
    op.execute("""
REVOKE ALL ON TABLE audit_heads, audit_entries, alembic_version FROM records_app
""")
    op.execute("""
GRANT SELECT ON TABLE audit_heads, audit_entries, alembic_version TO records_app
""")


def downgrade():
    op.drop_table("prescription_items")
    op.drop_table("prescriptions")
    op.drop_table("medical_records")
    op.drop_table("audit_entries")
    op.drop_table("record_access_grants")
    op.drop_table("outbox_events")
    op.drop_table("inbox_events")
    op.drop_table("idempotency_requests")
    op.drop_table("id_worker_state")
    op.drop_table("consultations")
    op.drop_table("audit_heads")
