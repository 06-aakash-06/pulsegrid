"""Service-owned SQLAlchemy schema. No runtime schema creation or cross-domain FKs."""

from sqlalchemy import (
    MetaData,
    Table,
    Column,
    BigInteger,
    Integer,
    String,
    Text,
    Boolean,
    Date,
    DateTime,
    CheckConstraint,
    ForeignKey,
    PrimaryKeyConstraint,
    UniqueConstraint,
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)


def ref(name, target=None, nullable=False, primary_key=False):
    args = [name, BigInteger]
    if target:
        args.append(ForeignKey(target, ondelete="RESTRICT"))
    return Column(
        *args, nullable=nullable, primary_key=primary_key, autoincrement=False
    )


def value(name, kind=String(64), nullable=False, default=None):
    return Column(
        name,
        kind,
        nullable=nullable,
        server_default=text(default) if default is not None else None,
    )


def timestamp(name, nullable=False, default=None):
    return value(name, DateTime(timezone=True), nullable, default)


def check(expression, name):
    return CheckConstraint(expression, name=name)


def states(column, values):
    return check(
        column + " IN (" + ",".join(repr(v) for v in values.split()) + ")",
        column + "_values",
    )


def entity(name, *items, with_id=True, version=True):
    columns = [ref("id", primary_key=True)] if with_id else []
    columns.extend(items)
    if version:
        columns.extend(
            [
                value("version", BigInteger, default="1"),
                check("version > 0", "positive_version"),
            ]
        )
    columns.extend(
        [
            timestamp("created_at", default="CURRENT_TIMESTAMP"),
            timestamp("updated_at", default="CURRENT_TIMESTAMP"),
        ]
    )
    table = Table(name, metadata, *columns)
    for col in table.columns:
        if isinstance(col.type, BigInteger) and (
            col.name == "id" or col.name.endswith("_id")
        ):
            table.append_constraint(
                check(f"{col.name} >= 0", f"{col.name}_nonnegative")
            )
    return table


def index(table, *columns, unique=False, where=None, suffix=None):
    name = "ix_" + table.name + "_" + (suffix or "_".join(columns))
    return Index(
        name,
        *(table.c[c] for c in columns),
        unique=unique,
        postgresql_where=text(where) if where else None,
    )


outbox_events = entity(
    "outbox_events",
    ref("event_id", primary_key=True),
    value("aggregate_type"),
    ref("aggregate_id"),
    value("aggregate_version", BigInteger),
    value("event_type", String(128)),
    value("envelope", JSONB),
    timestamp("published_at", nullable=True),
    value("attempt_count", Integer, default="0"),
    timestamp("next_attempt_at", default="CURRENT_TIMESTAMP"),
    value("claimed_by", String(128), nullable=True),
    timestamp("lease_expires_at", nullable=True),
    check("attempt_count >= 0", "attempt_count_nonnegative"),
    check("aggregate_version > 0", "aggregate_version_positive"),
    with_id=False,
    version=False,
)
index(
    outbox_events,
    "next_attempt_at",
    "event_id",
    where="published_at IS NULL",
    suffix="unpublished",
)
inbox_events = Table(
    "inbox_events",
    metadata,
    value("consumer_name", String(128)),
    ref("event_id"),
    timestamp("processed_at", default="CURRENT_TIMESTAMP"),
    PrimaryKeyConstraint("consumer_name", "event_id"),
)
index(inbox_events, "processed_at")
idempotency_requests = Table(
    "idempotency_requests",
    metadata,
    value("principal_scope", String(256)),
    value("method", String(8)),
    value("route_template", String(256)),
    value("key", String(256)),
    value("request_hash", String(64)),
    value("response_code", Integer),
    value("response", JSONB),
    timestamp("expires_at"),
    PrimaryKeyConstraint("principal_scope", "method", "route_template", "key"),
    check("response_code BETWEEN 100 AND 599", "response_code_range"),
)
index(idempotency_requests, "expires_at")
audit_heads = Table(
    "audit_heads",
    metadata,
    Column("chain_id", String(128), primary_key=True),
    value("last_sequence", BigInteger, default="0"),
    value("last_hash", String(64)),
    check("last_sequence >= 0", "sequence_nonnegative"),
)
audit_entries = Table(
    "audit_entries",
    metadata,
    Column(
        "chain_id",
        String(128),
        ForeignKey("audit_heads.chain_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    value("sequence", BigInteger),
    ref("entry_id"),
    value("prev_hash", String(64)),
    value("entry_hash", String(64)),
    value("canonical_metadata", JSONB),
    timestamp("created_at", default="CURRENT_TIMESTAMP"),
    PrimaryKeyConstraint("chain_id", "sequence"),
    UniqueConstraint("entry_id"),
    check("sequence > 0", "sequence_positive"),
)
id_worker_state = Table(
    "id_worker_state",
    metadata,
    Column("worker_id", Integer, primary_key=True, autoincrement=False),
    value("reserved_through_ms", BigInteger),
    check("worker_id BETWEEN 0 AND 1023", "worker_range"),
    check("reserved_through_ms >= 0", "high_watermark_nonnegative"),
)

tariffs = entity(
    "tariffs",
    value("charge_code", String(128)),
    value("revision", BigInteger),
    value("unit_amount_minor", BigInteger),
    value("currency", String(3)),
    UniqueConstraint("charge_code", "revision"),
    check("revision > 0 AND unit_amount_minor >= 0", "tariff_bounds"),
    check("currency ~ '^[A-Z]{3}$'", "currency_code"),
    version=False,
)
invoices = entity(
    "invoices",
    ref("journey_id"),
    ref("patient_id"),
    value("currency", String(3)),
    value("status"),
    value("total_minor", BigInteger, default="0"),
    value("paid_minor", BigInteger, default="0"),
    UniqueConstraint("journey_id"),
    check(
        "total_minor >= 0 AND paid_minor >= 0 AND paid_minor <= total_minor",
        "money_bounds",
    ),
    check("currency ~ '^[A-Z]{3}$'", "currency_code"),
)
invoice_items = entity(
    "invoice_items",
    ref("invoice_id", "invoices.id"),
    value("source_service"),
    ref("source_event_id"),
    ref("source_item_id"),
    ref("tariff_id", "tariffs.id"),
    value("quantity", Integer),
    value("unit_amount_minor", BigInteger),
    UniqueConstraint("source_service", "source_item_id"),
    check("quantity > 0 AND unit_amount_minor >= 0", "item_bounds"),
    version=False,
)
invoice_adjustments = entity(
    "invoice_adjustments",
    ref("invoice_id", "invoices.id"),
    value("amount_minor", BigInteger),
    value("reason", Text),
    ref("source_adjustment_id"),
    UniqueConstraint("source_adjustment_id"),
)
payments = entity(
    "payments",
    ref("invoice_id", "invoices.id"),
    value("idempotency_key", String(256)),
    value("amount_minor", BigInteger),
    value("currency", String(3)),
    value("status"),
    UniqueConstraint("invoice_id", "idempotency_key"),
    check("amount_minor > 0", "positive_amount"),
    check("currency ~ '^[A-Z]{3}$'", "currency_code"),
    states("status", "success declined reversed"),
)
insurance_providers = entity(
    "insurance_providers",
    value("synthetic_slug", String(128)),
    value("allowlisted_url", Text),
    UniqueConstraint("synthetic_slug"),
)
crawler_runs = entity(
    "crawler_runs",
    ref("provider_id", "insurance_providers.id"),
    timestamp("fetched_at", nullable=True),
    value("state"),
    value("content_hash", String(64), nullable=True),
    value("error_code", String(128), nullable=True),
)
insurance_rules = entity(
    "insurance_rules",
    ref("provider_id", "insurance_providers.id"),
    ref("source_run_id", "crawler_runs.id"),
    value("revision", BigInteger),
    timestamp("effective_from"),
    value("rule_data", JSONB),
    UniqueConstraint("provider_id", "revision"),
    check("revision > 0", "positive_revision"),
    version=False,
)
insurance_estimates = entity(
    "insurance_estimates",
    ref("invoice_id", "invoices.id"),
    ref("rules_id", "insurance_rules.id"),
    value("estimate_minor", BigInteger),
    timestamp("calculated_at"),
    value("freshness_state"),
    check("estimate_minor >= 0", "nonnegative_estimate"),
)
index(invoices, "patient_id", "status", "created_at")
index(payments, "invoice_id", "created_at")
index(crawler_runs, "provider_id", "created_at")
index(insurance_estimates, "invoice_id", "calculated_at")
