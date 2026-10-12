"""Feature schema handoff; DDL remains owned by the Billing coordinator."""

from __future__ import annotations

from typing import Any


def register_tables(metadata: Any) -> None:
    """Register only the crawler-owned source-version table; never call create_all."""
    if "insurance_source_versions" in metadata.tables:
        return
    from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, ForeignKey, Index, String, Table

    table = Table(
        "insurance_source_versions",
        metadata,
        Column(
            "provider_id",
            BigInteger,
            ForeignKey("insurance_providers.id", ondelete="RESTRICT"),
            nullable=False,
            primary_key=True,
        ),
        Column("source_id", String(128), nullable=False, primary_key=True),
        Column("source_path", String(2048), nullable=False, primary_key=True),
        Column("source_version", BigInteger, nullable=False),
        Column("content_hash", String(64), nullable=False),
        Column("observed_run_id", BigInteger, ForeignKey("crawler_runs.id", ondelete="RESTRICT"), nullable=False),
        Column("observed_at", DateTime(timezone=True), nullable=False),
        CheckConstraint("provider_id > 0", name="provider_positive"),
        CheckConstraint("source_version > 0", name="source_version_positive"),
        CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="content_hash_sha256"),
    )
    Index("ix_insurance_source_versions_provider_observed", table.c.provider_id, table.c.observed_at)


def schema_spec() -> dict[str, Any]:
    """Return a JSON-compatible migration, preflight, grants, and audit manifest."""
    return {
        "tables": {
            "insurance_source_versions": {
                "ownership": "billing",
                "columns": {
                    "provider_id": "BIGINT NOT NULL REFERENCES insurance_providers(id) ON DELETE RESTRICT",
                    "source_id": "VARCHAR(128) NOT NULL; configured synthetic source identity",
                    "source_path": "VARCHAR(2048) NOT NULL; path only, no query, fragment, or full URL",
                    "source_version": "BIGINT NOT NULL; increments when the observed page content hash changes",
                    "content_hash": "CHAR(64) NOT NULL; SHA256 of decompressed page bytes",
                    "observed_run_id": "BIGINT NOT NULL REFERENCES crawler_runs(id) ON DELETE RESTRICT",
                    "observed_at": "TIMESTAMPTZ NOT NULL",
                },
                "primary_key": ["provider_id", "source_id", "source_path"],
                "constraints": [
                    "provider_id > 0",
                    "source_version > 0",
                    "content_hash is lowercase SHA256 hex",
                    "no raw page body or patient fields are stored",
                ],
                "indexes": [["provider_id", "observed_at"]],
            },
            "crawler_runs": {
                "columns_to_add": {
                    "pages_processed": "INTEGER NOT NULL DEFAULT 0 CHECK >= 0",
                    "pages_retrieved": "INTEGER NOT NULL DEFAULT 0 CHECK >= 0",
                    "pages_failed": "INTEGER NOT NULL DEFAULT 0 CHECK >= 0",
                    "pages_invalid": "INTEGER NOT NULL DEFAULT 0 CHECK >= 0",
                    "pages_deduplicated": "INTEGER NOT NULL DEFAULT 0 CHECK >= 0",
                    "policies_accepted": "INTEGER NOT NULL DEFAULT 0 CHECK >= 0",
                    "policies_quarantined": "INTEGER NOT NULL DEFAULT 0 CHECK >= 0",
                    "lease_owner": "VARCHAR(128) NULL",
                    "lease_until": "TIMESTAMPTZ NULL",
                    "fencing_version": "BIGINT NOT NULL DEFAULT 0 CHECK >= 0",
                    "attempt_count": "INTEGER NOT NULL DEFAULT 0 CHECK BETWEEN 0 AND 3",
                    "next_attempt_at": "TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP",
                },
                "indexes": [
                    "partial unique provider_id WHERE state IN ('pending','running')",
                    "claim due pending/expired rows by next_attempt_at, created_at with FOR UPDATE SKIP LOCKED",
                ],
            },
            "insurance_rules": {
                "columns_to_add": {
                    "policy_code": "VARCHAR(64) NOT NULL after reviewed dormant-row preflight",
                    "content_hash": "CHAR(64) NOT NULL after reviewed backfill",
                    "effective_to": "TIMESTAMPTZ NOT NULL after reviewed backfill",
                },
                "constraints": [
                    "preserve provider_id,revision uniqueness for storage revisions",
                    "unique source policy revision by provider_id, policy_code, (rule_data->'policy'->>'revision')::BIGINT",
                    "same source policy revision with different content is quarantined, never updated",
                    "accepted rule rows are immutable to runtime credentials",
                    "rule_data contains exact PolicyRule plus source_id, source_version, observed_at",
                ],
            },
            "insurance_estimates": {
                "columns_to_add": {
                    "invoice_version": "BIGINT NOT NULL",
                    "provider_id": "BIGINT NOT NULL REFERENCES insurance_providers(id)",
                    "source_run_id": "BIGINT NOT NULL REFERENCES crawler_runs(id)",
                    "rule_revision": "BIGINT NOT NULL; source policy revision",
                    "currency": "CHAR(3) NOT NULL CHECK currency = INR",
                    "eligible_minor": "BIGINT NOT NULL CHECK 0..9007199254740991",
                    "version": "BIGINT NOT NULL DEFAULT 1",
                },
                "constraints": [
                    "estimate_minor is nonnegative and within safe integer range",
                    "estimate rows never update invoice totals, payments, or journey predicates",
                ],
            },
        },
        "preflight": [
            "Inspect dormant provider, run, rule, and estimate rows; unexpected mappings stop migration for review.",
            "Do not delete or reset rows and do not guess policy codes, source revisions, or effective_to backfills.",
            "Retain the existing unique insurance_rules(provider_id, revision) storage-revision constraint.",
            "Prove the new partial active-run uniqueness and source-revision uniqueness against retained rows before applying constraints.",
        ],
        "runtime_grants": [
            "billing_app may read configured synthetic providers and source versions.",
            "billing_app may insert source observations, append runs/rules/estimates, and update only run lease/state/counters.",
            "billing_app may not update or delete accepted insurance_rules rows.",
            "No crawler credential can read Records or Patient data or another service database.",
        ],
        "audit_actions": [
            "insurance.refresh_requested",
            "insurance.crawl_completed",
            "insurance.rule_accepted",
            "insurance.source_revision_conflict",
            "insurance.estimate_created",
        ],
        "outbox_event": "billing.insurance.crawl_completed.v1; retained locally until a separately authorized publisher exists",
        "limits": {
            "global_concurrency": 4,
            "per_host_concurrency": 2,
            "request_timeout_seconds": 1,
            "run_deadline_seconds": 30,
            "pages_per_run": 100,
            "depth": 2,
            "redirects": 2,
            "response_bytes_decompressed": 262144,
            "retries": 2,
            "lease_seconds": 30,
            "claim_batch": 4,
            "freshness_seconds": 86400,
        },
    }
