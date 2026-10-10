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
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, ExcludeConstraint

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

doctors = entity(
    "doctors",
    ref("staff_user_id"),
    value("display_name", String(200)),
    value("active", Boolean, default="true"),
    value("profile_version", BigInteger, default="1"),
    UniqueConstraint("staff_user_id"),
    check("profile_version > 0", "positive_profile_version"),
    check("length(btrim(display_name)) BETWEEN 1 AND 200", "display_name_nonempty"),
)
specialties = entity(
    "specialties",
    value("slug", String(128)),
    value("name", String(200)),
    UniqueConstraint("slug"),
    check(
        "slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$' AND length(slug) BETWEEN 1 AND 128",
        "slug_format",
    ),
    check("length(btrim(name)) BETWEEN 1 AND 200", "name_nonempty"),
)
doctor_specialties = Table(
    "doctor_specialties",
    metadata,
    ref("doctor_id", "doctors.id", primary_key=True),
    ref("specialty_id", "specialties.id", primary_key=True),
)
schedule_versions = entity(
    "schedule_versions",
    ref("doctor_id", "doctors.id"),
    value("revision", BigInteger),
    value("timezone", String(128)),
    value("slot_minutes", Integer),
    timestamp("effective_from"),
    value("status"),
    UniqueConstraint("doctor_id", "revision"),
    check("revision > 0 AND slot_minutes > 0", "positive_policy"),
    check("slot_minutes BETWEEN 5 AND 120", "slot_minutes_range"),
    states("status", "pending accepted rejected"),
)
schedule_intervals = entity(
    "schedule_intervals",
    ref("schedule_version_id", "schedule_versions.id"),
    timestamp("starts_at"),
    timestamp("ends_at"),
    check("ends_at > starts_at", "valid_interval"),
    version=False,
)
schedule_acknowledgements = entity(
    "schedule_acknowledgements",
    ref("schedule_version_id", "schedule_versions.id"),
    value("accepted", Boolean),
    value("operational_version", BigInteger, nullable=True),
    value("reason", Text, nullable=True),
    Column("conflicts", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    UniqueConstraint("schedule_version_id"),
    check("jsonb_typeof(conflicts) = 'array'", "conflicts_array"),
    version=False,
)
index(
    schedule_versions,
    "doctor_id",
    unique=True,
    where="status = 'pending'",
    suffix="one_pending",
)
index(schedule_intervals, "schedule_version_id", "starts_at")
Index(
    "ix_doctors_name_prefix",
    doctors.c.display_name,
    postgresql_ops={"display_name": "varchar_pattern_ops"},
)
index(doctors, "active")
index(doctor_specialties, "specialty_id", "doctor_id")
Index("ix_doctors_created_id", doctors.c.created_at, doctors.c.id)
Index(
    "ix_doctors_active_created_id",
    doctors.c.active,
    doctors.c.created_at,
    doctors.c.id,
)
Index(
    "ix_doctors_lower_display_name_prefix",
    func.lower(doctors.c.display_name),
    postgresql_ops={"lower": "text_pattern_ops"},
)
Index("ix_specialties_created_id", specialties.c.created_at, specialties.c.id)
Index(
    "ix_schedule_versions_doctor_created_id",
    schedule_versions.c.doctor_id,
    schedule_versions.c.created_at,
    schedule_versions.c.id,
)

# Doctor's documented overlap invariant is local; Appointment's exclusions
# remain explicitly deferred until booking/schedule-acceptance implementation.
schedule_intervals.append_constraint(
    ExcludeConstraint(
        (schedule_intervals.c.schedule_version_id, "="),
        (text("tstzrange(starts_at, ends_at, '[)')"), "&&"),
        name="excl_schedule_intervals_overlap",
        using="gist",
    )
)
