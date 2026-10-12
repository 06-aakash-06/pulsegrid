"""Non-executable migration handoff for Appointment short links."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    text,
)


_SCHEMA_SPEC: dict[str, Any] = {
    "revision": "0010_phase4_short_links",
    "tables": [
        {
            "name": "short_links",
            "owner": "appointment",
            "purpose": "reusable navigation alias; never a check-in credential",
        }
    ],
    "columns": [
        {"table": "short_links", "name": "id", "type": "BIGINT", "nullable": False},
        {"table": "short_links", "name": "appointment_id", "type": "BIGINT", "nullable": False},
        {"table": "short_links", "name": "purpose", "type": "VARCHAR(16)", "nullable": False},
        {"table": "short_links", "name": "token_hash", "type": "VARCHAR(64)", "nullable": False},
        {"table": "short_links", "name": "expires_at", "type": "TIMESTAMPTZ", "nullable": False},
        {"table": "short_links", "name": "revoked_at", "type": "TIMESTAMPTZ", "nullable": True},
        {"table": "short_links", "name": "workflow_version", "type": "BIGINT", "nullable": False},
        {"table": "short_links", "name": "schedule_fingerprint", "type": "VARCHAR(64)", "nullable": False},
        {"table": "short_links", "name": "version", "type": "BIGINT", "nullable": False, "default": "1"},
        {"table": "short_links", "name": "created_at", "type": "TIMESTAMPTZ", "nullable": False, "default": "CURRENT_TIMESTAMP"},
        {"table": "short_links", "name": "updated_at", "type": "TIMESTAMPTZ", "nullable": False, "default": "CURRENT_TIMESTAMP"},
    ],
    "indexes": [
        {"name": "uq_short_links_token_hash", "table": "short_links", "unique": True, "columns": ["token_hash"]},
        {
            "name": "uq_short_links_live_appointment_purpose",
            "table": "short_links",
            "unique": True,
            "columns": ["appointment_id", "purpose"],
            "where": "revoked_at IS NULL",
        },
        {"name": "ix_short_links_appointment_id", "table": "short_links", "unique": False, "columns": ["appointment_id"]},
    ],
    "constraints": [
        {"name": "fk_short_links_appointment_id_appointments", "table": "short_links", "expression": "appointment_id REFERENCES appointments(id) ON DELETE RESTRICT"},
        {"name": "ck_short_links_id_positive", "table": "short_links", "expression": "id BETWEEN 1 AND 9223372036854775807"},
        {"name": "ck_short_links_appointment_id_positive", "table": "short_links", "expression": "appointment_id > 0"},
        {"name": "ck_short_links_purpose", "table": "short_links", "expression": "purpose IN ('appointment','check_in')"},
        {"name": "ck_short_links_token_hash_sha256", "table": "short_links", "expression": "token_hash ~ '^[0-9a-f]{64}$'"},
        {"name": "ck_short_links_workflow_version_safe", "table": "short_links", "expression": "workflow_version BETWEEN 1 AND 9007199254740991"},
        {"name": "ck_short_links_schedule_fingerprint_sha256", "table": "short_links", "expression": "schedule_fingerprint ~ '^[0-9a-f]{64}$'"},
        {"name": "ck_short_links_version_safe", "table": "short_links", "expression": "version BETWEEN 1 AND 9007199254740991"},
    ],
    "preflight": [
        "Create only as the forward Appointment revision 0010_phase4_short_links; do not edit or recreate the applied Phase 3 history.",
        "Confirm the appointments primary key and existing appointment_app schema grants before adding the local foreign key.",
        "The partial unique index covers all unrevoked aliases, including expired rows; reissue revokes the prior row before insert.",
        "No alias, QR credential, or patient data is backfilled. token_hash stores SHA-256 of the 22-character alias only.",
    ],
    "runtime_grants": [
        {"role": "appointment_app", "table": "short_links", "privileges": ["SELECT", "INSERT", "UPDATE"]}
    ],
    "audit_actions": ["short_link_created", "short_link_revoked"],
}

_TABLE: Table | None = None


def schema_spec() -> dict[str, Any]:
    """Return an independent JSON-compatible schema handoff."""
    return json.loads(json.dumps(_SCHEMA_SPEC))


def register_tables(metadata: MetaData) -> None:
    """Attach only the feature table to Appointment metadata; never execute DDL."""
    global _TABLE
    from ... import models

    if metadata is not models.metadata:
        raise ValueError("Appointment metadata required")
    existing = metadata.tables.get("short_links")
    if existing is not None:
        if _TABLE is not None and existing is not _TABLE:
            raise ValueError("Short-link table identity changed")
        _TABLE = existing
        return

    _TABLE = Table(
        "short_links",
        metadata,
        Column("id", BigInteger, primary_key=True, autoincrement=False),
        Column("appointment_id", BigInteger, ForeignKey("appointments.id", ondelete="RESTRICT"), nullable=False),
        Column("purpose", String(16), nullable=False),
        Column("token_hash", String(64), nullable=False),
        Column("expires_at", DateTime(timezone=True), nullable=False),
        Column("revoked_at", DateTime(timezone=True), nullable=True),
        Column("workflow_version", BigInteger, nullable=False),
        Column("schedule_fingerprint", String(64), nullable=False),
        Column("version", BigInteger, nullable=False, server_default=text("1")),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
        Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
        UniqueConstraint("token_hash", name="uq_short_links_token_hash"),
        CheckConstraint("id BETWEEN 1 AND 9223372036854775807", name="short_links_id_positive"),
        CheckConstraint("appointment_id > 0", name="short_links_appointment_id_positive"),
        CheckConstraint("purpose IN ('appointment','check_in')", name="short_links_purpose"),
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="short_links_token_hash_sha256"),
        CheckConstraint("workflow_version BETWEEN 1 AND 9007199254740991", name="short_links_workflow_version_safe"),
        CheckConstraint("schedule_fingerprint ~ '^[0-9a-f]{64}$'", name="short_links_schedule_fingerprint_sha256"),
        CheckConstraint("version BETWEEN 1 AND 9007199254740991", name="short_links_version_safe"),
    )
    Index(
        "uq_short_links_live_appointment_purpose",
        _TABLE.c.appointment_id,
        _TABLE.c.purpose,
        unique=True,
        postgresql_where=text("revoked_at IS NULL"),
    )
    Index("ix_short_links_appointment_id", _TABLE.c.appointment_id)


def table_for(metadata: MetaData | None = None) -> Table:
    """Resolve the registered owner table without creating a database schema."""
    from ... import models

    owner_metadata = metadata or models.metadata
    register_tables(owner_metadata)
    assert _TABLE is not None
    return _TABLE
