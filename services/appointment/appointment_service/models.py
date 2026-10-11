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

doctor_schedule_snapshots = entity(
    "doctor_schedule_snapshots",
    ref("doctor_id", primary_key=True),
    value("accepted_revision", BigInteger),
    value("policy_snapshot", JSONB),
    ref("staff_user_id"),
    value("last_decided_proposal_revision", BigInteger),
    with_id=False,
)
schedule_proposals = entity(
    "schedule_proposals",
    ref("doctor_id"),
    value("revision", BigInteger),
    value("state"),
    UniqueConstraint("doctor_id", "revision"),
    states("state", "accepted rejected"),
    check("revision > 0", "positive_revision"),
)
slots = entity(
    "slots",
    ref("doctor_id"),
    value("schedule_revision", BigInteger),
    timestamp("starts_at"),
    timestamp("ends_at"),
    value("state"),
    UniqueConstraint("doctor_id", "starts_at", "ends_at"),
    check("ends_at > starts_at", "valid_interval"),
    check("schedule_revision > 0", "positive_revision"),
)
appointments = entity(
    "appointments",
    ref("patient_id"),
    ref("slot_id", "slots.id"),
    ref("doctor_id"),
    timestamp("starts_at"),
    timestamp("ends_at"),
    value("schedule_revision", BigInteger),
    value("state"),
    states("state", "confirmed checked_in in_consultation completed cancelled no_show"),
    check("ends_at > starts_at", "valid_interval"),
)
waitlist_entries = entity(
    "waitlist_entries",
    ref("slot_id", "slots.id"),
    ref("patient_id"),
    value("state"),
    timestamp("joined_at", default="CURRENT_TIMESTAMP"),
    ref("promoted_appointment_id", "appointments.id", nullable=True),
    value("skip_reason", String(256), nullable=True),
    states("state", "waiting promoted withdrawn skipped"),
)
patient_status_snapshots = entity(
    "patient_status_snapshots",
    ref("patient_id", primary_key=True),
    value("active", Boolean),
    value("source_version", BigInteger),
    timestamp("observed_at"),
    with_id=False,
)
checkin_links = entity(
    "checkin_links",
    ref("appointment_id", "appointments.id"),
    value("token_hash", String(64)),
    value("purpose"),
    timestamp("expires_at"),
    timestamp("consumed_at", nullable=True),
    timestamp("revoked_at", nullable=True),
    UniqueConstraint("token_hash"),
)
queue_counters = Table(
    "queue_counters",
    metadata,
    ref("doctor_id", primary_key=True),
    Column("local_date", Date, primary_key=True),
    value("next_token", BigInteger, default="1"),
    check("next_token > 0", "positive_token"),
)
queue_entries = entity(
    "queue_entries",
    ref("appointment_id", "appointments.id"),
    ref("doctor_id"),
    value("local_date", Date),
    value("token_number", BigInteger),
    value("state"),
    UniqueConstraint("appointment_id"),
    UniqueConstraint("doctor_id", "local_date", "token_number"),
    check("token_number > 0", "positive_token"),
    states("state", "waiting in_consultation completed cancelled no_show"),
)
journeys = entity(
    "journeys",
    ref("appointment_id", "appointments.id"),
    ref("patient_id"),
    value("state"),
    UniqueConstraint("appointment_id"),
)
journey_stages = entity(
    "journey_stages",
    ref("journey_id", "journeys.id", primary_key=True),
    Column("stage", String(64), primary_key=True),
    value("state"),
    ref("source_resource_id", nullable=True),
    value("source_version", BigInteger, nullable=True),
    value("source_resources", JSONB, default="'[]'::jsonb"),
    timestamp("observed_at"),
    states("state", "pending complete skipped reopened"),
    with_id=False,
)
index(
    appointments,
    "slot_id",
    unique=True,
    where="state IN ('confirmed','checked_in','in_consultation')",
    suffix="active_slot",
)
index(appointments, "patient_id", "starts_at")
index(slots, "doctor_id", "starts_at", "state")
index(
    waitlist_entries,
    "slot_id",
    "patient_id",
    unique=True,
    where="state = 'waiting'",
    suffix="one_waiting",
)
index(waitlist_entries, "slot_id", "state", "joined_at", "id")
index(
    queue_entries,
    "doctor_id",
    unique=True,
    where="state = 'in_consultation'",
    suffix="one_consultation",
)
index(queue_entries, "doctor_id", "local_date", "state")
index(journeys, "patient_id", "updated_at")
index(checkin_links, "appointment_id", "purpose")

# Phase 2 additions; historic migration revisions remain frozen.
from sqlalchemy.dialects.postgresql import ExcludeConstraint
slots.append_constraint(ExcludeConstraint(
    ('doctor_id', '='), (text("tstzrange(starts_at,ends_at,'[)')"), '&&'),
    where=text("state <> 'retired'"), name='slots_doctor_overlap', using='gist'))
slots.append_constraint(check("state IN ('bookable','retired')", 'slots_phase2_state'))
appointments.append_constraint(ExcludeConstraint(
    ('patient_id', '='), (text("tstzrange(starts_at,ends_at,'[)')"), '&&'),
    where=text("state IN ('confirmed','checked_in','in_consultation')"),
    name='appointments_patient_overlap', using='gist'))
appointments.append_column(ref('doctor_user_id'))
appointments.append_constraint(check('doctor_user_id>0', 'appointments_doctor_user_positive'))
schedule_proposals.append_column(value('reason_code', nullable=True))
schedule_proposals.append_column(value('conflicting_appointment_ids', JSONB, default="'[]'::jsonb"))
schedule_proposals.append_column(ref('staff_user_id'))
clinical_holds = Table('clinical_holds', metadata,
    ref('appointment_id', 'appointments.id', primary_key=True),
    ref('consultation_id'), value('state', String(16)),
    UniqueConstraint('consultation_id'), check('consultation_id>0', 'consultation_positive'),
    states('state', 'active finalized'))

# G0 shared operational aggregate. Legacy appointments are never backfilled.
appointment_workflows = entity(
    'appointment_workflows',
    ref('appointment_id', 'appointments.id', primary_key=True),
    ref('journey_id', 'journeys.id'),
    ref('patient_id'), ref('doctor_id'), ref('slot_id', 'slots.id'),
    value('schedule_revision', BigInteger),
    value('schedule_fingerprint', String(64)),
    value('state', String(32)),
    timestamp('window_starts_at'), timestamp('window_ends_at'),
    ref('queue_entry_id', 'queue_entries.id', nullable=True),
    UniqueConstraint('journey_id'), UniqueConstraint('queue_entry_id'),
    states('state', 'booked checked_in in_consultation completed cancelled no_show'),
    check('schedule_revision > 0', 'positive_schedule_revision'),
    check('version <= 9007199254740991', 'safe_version'),
    check('window_ends_at > window_starts_at', 'valid_window'),
    check("schedule_fingerprint ~ '^[0-9a-f]{64}$'", 'fingerprint'),
    check("state NOT IN ('checked_in','in_consultation','completed') OR queue_entry_id IS NOT NULL", 'queue_required'),
    with_id=False,
)

# G2 reviewed feature schema. All DDL remains in owner migrations 0005-0008.
checkin_links.append_column(value('workflow_version', BigInteger))
checkin_links.append_column(value('schedule_fingerprint', String(64)))
queue_entries.append_column(value('position', Integer, nullable=True))
queue_snapshots = Table('queue_snapshots', metadata,
    ref('doctor_id', 'doctor_schedule_snapshots.doctor_id', primary_key=True),
    Column('local_date', Date, primary_key=True),
    value('version', BigInteger, default='1'),
    timestamp('created_at', default='CURRENT_TIMESTAMP'),
    timestamp('updated_at', default='CURRENT_TIMESTAMP'))
waitlist_offers = entity('waitlist_offers',
    ref('entry_id', 'waitlist_entries.id'), ref('slot_id', 'slots.id'), ref('patient_id'),
    value('state', String(16)), timestamp('expires_at'),
    ref('appointment_id', 'appointments.id', nullable=True))
journey_snapshots = Table('journey_snapshots', metadata,
    ref('journey_id', 'journeys.id', primary_key=True),
    value('records_revision', BigInteger, nullable=True),
    value('pharmacy_revision', BigInteger, nullable=True),
    value('billing_revision', BigInteger, nullable=True),
    value('expected_source_keys', JSONB, default="'[]'::jsonb"),
    value('review_required', Boolean, default='false'),
    timestamp('last_reconciled_at', nullable=True),
    value('lease_token', String(64), nullable=True), timestamp('lease_until', nullable=True),
    timestamp('next_attempt_at', default='CURRENT_TIMESTAMP'),
    value('attempts', Integer, default='0'), value('sources', JSONB, default="'{}'::jsonb"),
    value('pending_reasons', JSONB, default="'{}'::jsonb"),
    value('last_error', String(64), nullable=True))
journey_stages.c.observed_at.nullable = True
