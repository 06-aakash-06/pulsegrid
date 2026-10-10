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
CREATE TABLE insurance_providers (
	id BIGINT NOT NULL,
	synthetic_slug VARCHAR(128) NOT NULL,
	allowlisted_url TEXT NOT NULL,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_insurance_providers PRIMARY KEY (id),
	CONSTRAINT uq_insurance_providers_synthetic_slug UNIQUE (synthetic_slug),
	CONSTRAINT ck_insurance_providers_positive_version CHECK (version > 0),
	CONSTRAINT ck_insurance_providers_id_nonnegative CHECK (id >= 0)
)
""")
    op.execute("""
CREATE TABLE invoices (
	id BIGINT NOT NULL,
	journey_id BIGINT NOT NULL,
	patient_id BIGINT NOT NULL,
	currency VARCHAR(3) NOT NULL,
	status VARCHAR(64) NOT NULL,
	total_minor BIGINT DEFAULT 0 NOT NULL,
	paid_minor BIGINT DEFAULT 0 NOT NULL,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_invoices PRIMARY KEY (id),
	CONSTRAINT uq_invoices_journey_id UNIQUE (journey_id),
	CONSTRAINT ck_invoices_money_bounds CHECK (total_minor >= 0 AND paid_minor >= 0 AND paid_minor <= total_minor),
	CONSTRAINT ck_invoices_currency_code CHECK (currency ~ '^[A-Z]{3}$'),
	CONSTRAINT ck_invoices_positive_version CHECK (version > 0),
	CONSTRAINT ck_invoices_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_invoices_journey_id_nonnegative CHECK (journey_id >= 0),
	CONSTRAINT ck_invoices_patient_id_nonnegative CHECK (patient_id >= 0)
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
CREATE TABLE tariffs (
	id BIGINT NOT NULL,
	charge_code VARCHAR(128) NOT NULL,
	revision BIGINT NOT NULL,
	unit_amount_minor BIGINT NOT NULL,
	currency VARCHAR(3) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_tariffs PRIMARY KEY (id),
	CONSTRAINT uq_tariffs_charge_code UNIQUE (charge_code, revision),
	CONSTRAINT ck_tariffs_tariff_bounds CHECK (revision > 0 AND unit_amount_minor >= 0),
	CONSTRAINT ck_tariffs_currency_code CHECK (currency ~ '^[A-Z]{3}$'),
	CONSTRAINT ck_tariffs_id_nonnegative CHECK (id >= 0)
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
CREATE TABLE crawler_runs (
	id BIGINT NOT NULL,
	provider_id BIGINT NOT NULL,
	fetched_at TIMESTAMP WITH TIME ZONE,
	state VARCHAR(64) NOT NULL,
	content_hash VARCHAR(64),
	error_code VARCHAR(128),
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_crawler_runs PRIMARY KEY (id),
	CONSTRAINT ck_crawler_runs_positive_version CHECK (version > 0),
	CONSTRAINT fk_crawler_runs_provider_id_insurance_providers FOREIGN KEY(provider_id) REFERENCES insurance_providers (id) ON DELETE RESTRICT,
	CONSTRAINT ck_crawler_runs_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_crawler_runs_provider_id_nonnegative CHECK (provider_id >= 0)
)
""")
    op.execute("""
CREATE TABLE invoice_adjustments (
	id BIGINT NOT NULL,
	invoice_id BIGINT NOT NULL,
	amount_minor BIGINT NOT NULL,
	reason TEXT NOT NULL,
	source_adjustment_id BIGINT NOT NULL,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_invoice_adjustments PRIMARY KEY (id),
	CONSTRAINT uq_invoice_adjustments_source_adjustment_id UNIQUE (source_adjustment_id),
	CONSTRAINT ck_invoice_adjustments_positive_version CHECK (version > 0),
	CONSTRAINT fk_invoice_adjustments_invoice_id_invoices FOREIGN KEY(invoice_id) REFERENCES invoices (id) ON DELETE RESTRICT,
	CONSTRAINT ck_invoice_adjustments_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_invoice_adjustments_invoice_id_nonnegative CHECK (invoice_id >= 0),
	CONSTRAINT ck_invoice_adjustments_source_adjustment_id_nonnegative CHECK (source_adjustment_id >= 0)
)
""")
    op.execute("""
CREATE TABLE invoice_items (
	id BIGINT NOT NULL,
	invoice_id BIGINT NOT NULL,
	source_service VARCHAR(64) NOT NULL,
	source_event_id BIGINT NOT NULL,
	source_item_id BIGINT NOT NULL,
	tariff_id BIGINT NOT NULL,
	quantity INTEGER NOT NULL,
	unit_amount_minor BIGINT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_invoice_items PRIMARY KEY (id),
	CONSTRAINT uq_invoice_items_source_service UNIQUE (source_service, source_item_id),
	CONSTRAINT ck_invoice_items_item_bounds CHECK (quantity > 0 AND unit_amount_minor >= 0),
	CONSTRAINT fk_invoice_items_invoice_id_invoices FOREIGN KEY(invoice_id) REFERENCES invoices (id) ON DELETE RESTRICT,
	CONSTRAINT fk_invoice_items_tariff_id_tariffs FOREIGN KEY(tariff_id) REFERENCES tariffs (id) ON DELETE RESTRICT,
	CONSTRAINT ck_invoice_items_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_invoice_items_invoice_id_nonnegative CHECK (invoice_id >= 0),
	CONSTRAINT ck_invoice_items_source_event_id_nonnegative CHECK (source_event_id >= 0),
	CONSTRAINT ck_invoice_items_source_item_id_nonnegative CHECK (source_item_id >= 0),
	CONSTRAINT ck_invoice_items_tariff_id_nonnegative CHECK (tariff_id >= 0)
)
""")
    op.execute("""
CREATE TABLE payments (
	id BIGINT NOT NULL,
	invoice_id BIGINT NOT NULL,
	idempotency_key VARCHAR(256) NOT NULL,
	amount_minor BIGINT NOT NULL,
	currency VARCHAR(3) NOT NULL,
	status VARCHAR(64) NOT NULL,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_payments PRIMARY KEY (id),
	CONSTRAINT uq_payments_invoice_id UNIQUE (invoice_id, idempotency_key),
	CONSTRAINT ck_payments_positive_amount CHECK (amount_minor > 0),
	CONSTRAINT ck_payments_currency_code CHECK (currency ~ '^[A-Z]{3}$'),
	CONSTRAINT ck_payments_status_values CHECK (status IN ('success','declined','reversed')),
	CONSTRAINT ck_payments_positive_version CHECK (version > 0),
	CONSTRAINT fk_payments_invoice_id_invoices FOREIGN KEY(invoice_id) REFERENCES invoices (id) ON DELETE RESTRICT,
	CONSTRAINT ck_payments_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_payments_invoice_id_nonnegative CHECK (invoice_id >= 0)
)
""")
    op.execute("""
CREATE TABLE insurance_rules (
	id BIGINT NOT NULL,
	provider_id BIGINT NOT NULL,
	source_run_id BIGINT NOT NULL,
	revision BIGINT NOT NULL,
	effective_from TIMESTAMP WITH TIME ZONE NOT NULL,
	rule_data JSONB NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_insurance_rules PRIMARY KEY (id),
	CONSTRAINT uq_insurance_rules_provider_id UNIQUE (provider_id, revision),
	CONSTRAINT ck_insurance_rules_positive_revision CHECK (revision > 0),
	CONSTRAINT fk_insurance_rules_provider_id_insurance_providers FOREIGN KEY(provider_id) REFERENCES insurance_providers (id) ON DELETE RESTRICT,
	CONSTRAINT fk_insurance_rules_source_run_id_crawler_runs FOREIGN KEY(source_run_id) REFERENCES crawler_runs (id) ON DELETE RESTRICT,
	CONSTRAINT ck_insurance_rules_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_insurance_rules_provider_id_nonnegative CHECK (provider_id >= 0),
	CONSTRAINT ck_insurance_rules_source_run_id_nonnegative CHECK (source_run_id >= 0)
)
""")
    op.execute("""
CREATE TABLE insurance_estimates (
	id BIGINT NOT NULL,
	invoice_id BIGINT NOT NULL,
	rules_id BIGINT NOT NULL,
	estimate_minor BIGINT NOT NULL,
	calculated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	freshness_state VARCHAR(64) NOT NULL,
	version BIGINT DEFAULT 1 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT pk_insurance_estimates PRIMARY KEY (id),
	CONSTRAINT ck_insurance_estimates_nonnegative_estimate CHECK (estimate_minor >= 0),
	CONSTRAINT ck_insurance_estimates_positive_version CHECK (version > 0),
	CONSTRAINT fk_insurance_estimates_invoice_id_invoices FOREIGN KEY(invoice_id) REFERENCES invoices (id) ON DELETE RESTRICT,
	CONSTRAINT fk_insurance_estimates_rules_id_insurance_rules FOREIGN KEY(rules_id) REFERENCES insurance_rules (id) ON DELETE RESTRICT,
	CONSTRAINT ck_insurance_estimates_id_nonnegative CHECK (id >= 0),
	CONSTRAINT ck_insurance_estimates_invoice_id_nonnegative CHECK (invoice_id >= 0),
	CONSTRAINT ck_insurance_estimates_rules_id_nonnegative CHECK (rules_id >= 0)
)
""")
    op.execute("""
CREATE INDEX ix_idempotency_requests_expires_at ON idempotency_requests (expires_at)
""")
    op.execute("""
CREATE INDEX ix_inbox_events_processed_at ON inbox_events (processed_at)
""")
    op.execute("""
CREATE INDEX ix_invoices_patient_id_status_created_at ON invoices (patient_id, status, created_at)
""")
    op.execute("""
CREATE INDEX ix_outbox_events_unpublished ON outbox_events (next_attempt_at, event_id) WHERE published_at IS NULL
""")
    op.execute("""
CREATE INDEX ix_crawler_runs_provider_id_created_at ON crawler_runs (provider_id, created_at)
""")
    op.execute("""
CREATE INDEX ix_payments_invoice_id_created_at ON payments (invoice_id, created_at)
""")
    op.execute("""
CREATE INDEX ix_insurance_estimates_invoice_id_calculated_at ON insurance_estimates (invoice_id, calculated_at)
""")
    op.execute("""
REVOKE ALL ON TABLE audit_heads, audit_entries, alembic_version FROM billing_app
""")
    op.execute("""
GRANT SELECT ON TABLE audit_heads, audit_entries, alembic_version TO billing_app
""")


def downgrade():
    op.drop_table("insurance_estimates")
    op.drop_table("insurance_rules")
    op.drop_table("payments")
    op.drop_table("invoice_items")
    op.drop_table("invoice_adjustments")
    op.drop_table("crawler_runs")
    op.drop_table("audit_entries")
    op.drop_table("tariffs")
    op.drop_table("outbox_events")
    op.drop_table("invoices")
    op.drop_table("insurance_providers")
    op.drop_table("inbox_events")
    op.drop_table("idempotency_requests")
    op.drop_table("id_worker_state")
    op.drop_table("audit_heads")
