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
CREATE TABLE medicines (
	id BIGINT NOT NULL,
	sku VARCHAR(128) NOT NULL,
	name VARCHAR(200) NOT NULL,
	normalized_name VARCHAR(200) NOT NULL,
	active BOOLEAN DEFAULT true NOT NULL,
	catalog_version BIGINT DEFAULT 1 NOT NULL,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_medicines PRIMARY KEY (id),
	CONSTRAINT uq_medicines_sku UNIQUE (sku),
	CONSTRAINT ck_medicines_positive_catalog_version CHECK (catalog_version > 0),
	CONSTRAINT ck_medicines_positive_version CHECK (version > 0),
	CONSTRAINT ck_medicines_id_nonnegative CHECK (id >= 0)
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
CREATE TABLE prescription_snapshots (
	prescription_id BIGINT NOT NULL,
	patient_id BIGINT NOT NULL,
	journey_id BIGINT NOT NULL,
	revision BIGINT NOT NULL,
	state VARCHAR(64) NOT NULL,
	source_version BIGINT NOT NULL,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_prescription_snapshots PRIMARY KEY (prescription_id),
	CONSTRAINT ck_prescription_snapshots_positive_version CHECK (version > 0),
	CONSTRAINT ck_prescription_snapshots_prescription_id_nonnegative CHECK (prescription_id >= 0),
	CONSTRAINT ck_prescription_snapshots_patient_id_nonnegative CHECK (patient_id >= 0),
	CONSTRAINT ck_prescription_snapshots_journey_id_nonnegative CHECK (journey_id >= 0)
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
CREATE TABLE inventory_batches (
	id BIGINT NOT NULL,
	medicine_id BIGINT NOT NULL,
	batch_code VARCHAR(128) NOT NULL,
	expires_on DATE NOT NULL,
	on_hand INTEGER NOT NULL,
	reserved INTEGER DEFAULT 0 NOT NULL,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_inventory_batches PRIMARY KEY (id),
	CONSTRAINT uq_inventory_batches_medicine_id UNIQUE (medicine_id, batch_code),
	CONSTRAINT ck_inventory_batches_stock_bounds CHECK (0 <= reserved AND reserved <= on_hand),
	CONSTRAINT ck_inventory_batches_positive_version CHECK (version > 0),
	CONSTRAINT fk_inventory_batches_medicine_id_medicines FOREIGN KEY(medicine_id) REFERENCES medicines (id) ON DELETE RESTRICT,
	CONSTRAINT ck_inventory_batches_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_inventory_batches_medicine_id_nonnegative CHECK (medicine_id >= 0)
)
""")
    op.execute("""
CREATE TABLE prescription_item_snapshots (
	item_id BIGINT NOT NULL,
	prescription_id BIGINT NOT NULL,
	medicine_id BIGINT NOT NULL,
	prescribed_quantity INTEGER NOT NULL,
	reserved_quantity INTEGER DEFAULT 0 NOT NULL,
	dispensed_quantity INTEGER DEFAULT 0 NOT NULL,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_prescription_item_snapshots PRIMARY KEY (item_id),
	CONSTRAINT ck_prescription_item_snapshots_quantity_bounds CHECK (prescribed_quantity >= 0 AND reserved_quantity >= 0 AND dispensed_quantity >= 0 AND reserved_quantity + dispensed_quantity <= prescribed_quantity),
	CONSTRAINT ck_prescription_item_snapshots_positive_version CHECK (version > 0),
	CONSTRAINT fk_prescription_item_snapshots_prescription_id_prescrip_4682 FOREIGN KEY(prescription_id) REFERENCES prescription_snapshots (prescription_id) ON DELETE RESTRICT,
	CONSTRAINT fk_prescription_item_snapshots_medicine_id_medicines FOREIGN KEY(medicine_id) REFERENCES medicines (id) ON DELETE RESTRICT,
	CONSTRAINT ck_prescription_item_snapshots_item_id_nonnegative CHECK (item_id >= 0),
	CONSTRAINT ck_prescription_item_snapshots_prescription_id_nonnegative CHECK (prescription_id >= 0),
	CONSTRAINT ck_prescription_item_snapshots_medicine_id_nonnegative CHECK (medicine_id >= 0)
)
""")
    op.execute("""
CREATE TABLE reservations (
	id BIGINT NOT NULL,
	prescription_id BIGINT NOT NULL,
	patient_id BIGINT NOT NULL,
	state VARCHAR(64) NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_reservations PRIMARY KEY (id),
	CONSTRAINT ck_reservations_state_values CHECK (state IN ('reserved','expired','released','dispensed')),
	CONSTRAINT ck_reservations_positive_version CHECK (version > 0),
	CONSTRAINT fk_reservations_prescription_id_prescription_snapshots FOREIGN KEY(prescription_id) REFERENCES prescription_snapshots (prescription_id) ON DELETE RESTRICT,
	CONSTRAINT ck_reservations_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_reservations_prescription_id_nonnegative CHECK (prescription_id >= 0),
	CONSTRAINT ck_reservations_patient_id_nonnegative CHECK (patient_id >= 0)
)
""")
    op.execute("""
CREATE TABLE dispensings (
	id BIGINT NOT NULL,
	reservation_id BIGINT NOT NULL,
	staff_user_id BIGINT NOT NULL,
	completed_at TIMESTAMP WITH TIME ZONE NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_dispensings PRIMARY KEY (id),
	CONSTRAINT uq_dispensings_reservation_id UNIQUE (reservation_id),
	CONSTRAINT fk_dispensings_reservation_id_reservations FOREIGN KEY(reservation_id) REFERENCES reservations (id) ON DELETE RESTRICT,
	CONSTRAINT ck_dispensings_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_dispensings_reservation_id_nonnegative CHECK (reservation_id >= 0),
	CONSTRAINT ck_dispensings_staff_user_id_nonnegative CHECK (staff_user_id >= 0)
)
""")
    op.execute("""
CREATE TABLE reservation_items (
	id BIGINT NOT NULL,
	reservation_id BIGINT NOT NULL,
	item_id BIGINT NOT NULL,
	batch_id BIGINT NOT NULL,
	quantity INTEGER NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_reservation_items PRIMARY KEY (id),
	CONSTRAINT ck_reservation_items_positive_quantity CHECK (quantity > 0),
	CONSTRAINT fk_reservation_items_reservation_id_reservations FOREIGN KEY(reservation_id) REFERENCES reservations (id) ON DELETE RESTRICT,
	CONSTRAINT fk_reservation_items_item_id_prescription_item_snapshots FOREIGN KEY(item_id) REFERENCES prescription_item_snapshots (item_id) ON DELETE RESTRICT,
	CONSTRAINT fk_reservation_items_batch_id_inventory_batches FOREIGN KEY(batch_id) REFERENCES inventory_batches (id) ON DELETE RESTRICT,
	CONSTRAINT ck_reservation_items_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_reservation_items_reservation_id_nonnegative CHECK (reservation_id >= 0),
	CONSTRAINT ck_reservation_items_item_id_nonnegative CHECK (item_id >= 0),
	CONSTRAINT ck_reservation_items_batch_id_nonnegative CHECK (batch_id >= 0)
)
""")
    op.execute("""
CREATE TABLE stock_movements (
	id BIGINT NOT NULL,
	batch_id BIGINT NOT NULL,
	delta INTEGER NOT NULL,
	reason VARCHAR(128) NOT NULL,
	source_id BIGINT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_stock_movements PRIMARY KEY (id),
	CONSTRAINT uq_stock_movements_batch_id UNIQUE (batch_id, reason, source_id),
	CONSTRAINT ck_stock_movements_nonzero_delta CHECK (delta <> 0),
	CONSTRAINT fk_stock_movements_batch_id_inventory_batches FOREIGN KEY(batch_id) REFERENCES inventory_batches (id) ON DELETE RESTRICT,
	CONSTRAINT ck_stock_movements_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_stock_movements_batch_id_nonnegative CHECK (batch_id >= 0),
	CONSTRAINT ck_stock_movements_source_id_nonnegative CHECK (source_id >= 0)
)
""")
    op.execute("""
CREATE TABLE dispensing_items (
	id BIGINT NOT NULL,
	dispensing_id BIGINT NOT NULL,
	reservation_item_id BIGINT NOT NULL,
	quantity INTEGER NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_dispensing_items PRIMARY KEY (id),
	CONSTRAINT uq_dispensing_items_reservation_item_id UNIQUE (reservation_item_id),
	CONSTRAINT ck_dispensing_items_positive_quantity CHECK (quantity > 0),
	CONSTRAINT fk_dispensing_items_dispensing_id_dispensings FOREIGN KEY(dispensing_id) REFERENCES dispensings (id) ON DELETE RESTRICT,
	CONSTRAINT fk_dispensing_items_reservation_item_id_reservation_items FOREIGN KEY(reservation_item_id) REFERENCES reservation_items (id) ON DELETE RESTRICT,
	CONSTRAINT ck_dispensing_items_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_dispensing_items_dispensing_id_nonnegative CHECK (dispensing_id >= 0),
	CONSTRAINT ck_dispensing_items_reservation_item_id_nonnegative CHECK (reservation_item_id >= 0)
)
""")
    op.execute("""
CREATE INDEX ix_idempotency_requests_expires_at ON idempotency_requests (expires_at)
""")
    op.execute("""
CREATE INDEX ix_inbox_events_processed_at ON inbox_events (processed_at)
""")
    op.execute("""
CREATE INDEX ix_medicines_name_prefix ON medicines (normalized_name varchar_pattern_ops)
""")
    op.execute("""
CREATE INDEX ix_outbox_events_unpublished ON outbox_events (next_attempt_at, event_id) WHERE published_at IS NULL
""")
    op.execute("""
CREATE INDEX ix_inventory_batches_medicine_id_expires_on ON inventory_batches (medicine_id, expires_on)
""")
    op.execute("""
CREATE INDEX ix_prescription_item_snapshots_prescription_id ON prescription_item_snapshots (prescription_id)
""")
    op.execute("""
CREATE INDEX ix_reservations_expires_at_state ON reservations (expires_at, state)
""")
    op.execute("""
CREATE INDEX ix_reservations_patient_id_prescription_id ON reservations (patient_id, prescription_id)
""")
    op.execute("""
CREATE INDEX ix_reservation_items_reservation_id ON reservation_items (reservation_id)
""")
    op.execute("""
REVOKE ALL ON TABLE audit_heads, audit_entries, alembic_version FROM pharmacy_app
""")
    op.execute("""
GRANT SELECT ON TABLE audit_heads, audit_entries, alembic_version TO pharmacy_app
""")


def downgrade():
    op.drop_table("dispensing_items")
    op.drop_table("stock_movements")
    op.drop_table("reservation_items")
    op.drop_table("dispensings")
    op.drop_table("reservations")
    op.drop_table("prescription_item_snapshots")
    op.drop_table("inventory_batches")
    op.drop_table("audit_entries")
    op.drop_table("prescription_snapshots")
    op.drop_table("outbox_events")
    op.drop_table("medicines")
    op.drop_table("inbox_events")
    op.drop_table("idempotency_requests")
    op.drop_table("id_worker_state")
    op.drop_table("audit_heads")
