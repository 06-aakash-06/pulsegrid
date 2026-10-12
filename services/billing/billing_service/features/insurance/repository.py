"""Billing-owned SQL persistence adapter for insurance runs and rule provenance.

The coordinator supplies Billing's session factory, ID allocator, and transactional
audit/outbox callback. This module never constructs a connection pool or runs DDL.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlsplit

from .contracts import ValidatedPolicyExport
from .crawler import CrawlOutcome, CrawlSource, SourceObservation

RUN_LEASE_SECONDS = 30
MAX_RUN_ATTEMPTS = 3
CLAIM_BATCH_MAX = 4


class SQLAlchemyInsuranceRepository:
    """SQLAlchemy 2 async adapter using only Billing's owned schema/session."""

    def __init__(
        self,
        read_session: Callable[[], Any],
        allocate_id: Callable[[], Any],
        *,
        audit_outbox: Callable[..., Any],
        worker_id: str = "billing-insurance-worker",
    ) -> None:
        if not worker_id or len(worker_id) > 128:
            raise ValueError("worker_id must be a bounded configured identifier")
        self._read_session = read_session
        self._allocate_id = allocate_id
        self._audit_outbox = audit_outbox
        self.worker_id = worker_id

    async def get_provider(self, provider_id: str) -> Mapping[str, Any] | None:
        from sqlalchemy import select

        from ...models import insurance_providers

        async with self._read_session() as session:
            result = await session.execute(
                select(insurance_providers).where(insurance_providers.c.id == int(provider_id))
            )
            row = result.mappings().first()
            return dict(row) if row is not None else None

    async def list_sources(self, provider_id: str) -> tuple[CrawlSource, ...]:
        provider = await self.get_provider(provider_id)
        if provider is None:
            return ()
        configured_url = provider.get("allowlisted_url")
        if not isinstance(configured_url, str):
            return ()
        path = urlsplit(configured_url).path or "/"
        if not path.endswith("/"):
            path += "/"
        return (CrawlSource(source_id=f"provider:{provider_id}", start_path=path),)

    async def begin_run(self, provider_id: str) -> Mapping[str, Any]:
        allocated_id=await self._allocate_id()
        async with self._read_session() as session:
            async with session.begin():
                return await self.enqueue_run(session, provider_id, allocated_id=allocated_id)

    async def enqueue_run(self, session: Any, provider_id: str, *, allocated_id: int) -> Mapping[str, Any]:
        from sqlalchemy import select

        from ...models import crawler_runs, insurance_providers

        provider = (
            await session.execute(
                select(insurance_providers)
                .where(insurance_providers.c.id == int(provider_id))
                .with_for_update()
            )
        ).mappings().first()
        if provider is None:
            raise KeyError("provider_not_found")
        active = (
            await session.execute(
                select(crawler_runs)
                .where(
                    crawler_runs.c.provider_id == int(provider_id),
                    crawler_runs.c.state.in_(("pending", "running")),
                )
                .order_by(crawler_runs.c.created_at.desc())
                .limit(1)
                .with_for_update()
            )
        ).mappings().first()
        if active is not None:
            return dict(active)
        run_id = int(allocated_id)
        await session.execute(
            crawler_runs.insert().values(
                id=run_id,
                provider_id=int(provider_id),
                state="pending",
                error_code=None,
            )
        )
        await self._call_audit_outbox(
            session,
            action="insurance.refresh_requested",
            run_id=run_id,
            version=1,
            payload={"provider_id": provider_id, "run_id": str(run_id)},
        )
        return {"id": run_id, "provider_id": int(provider_id), "state": "pending", "version": 1}

    async def read_source_version(
        self, provider_id: str, source_id: str, path: str
    ) -> Mapping[str, Any] | None:
        from sqlalchemy import text

        async with self._read_session() as session:
            result = await session.execute(
                text(
                    "SELECT source_version, content_hash FROM insurance_source_versions "
                    "WHERE provider_id=:provider_id AND source_id=:source_id AND source_path=:path"
                ),
                {"provider_id": int(provider_id), "source_id": source_id, "path": path},
            )
            row = result.mappings().first()
            return dict(row) if row is not None else None

    async def commit_run(
        self,
        run_id: str,
        fencing_version: int | None,
        outcome: CrawlOutcome,
        policies: Sequence[ValidatedPolicyExport],
        observations: Sequence[SourceObservation],
    ) -> Mapping[str, Any]:
        """Finalize source versions, accepted rules, run counts, audit, and outbox atomically."""
        from sqlalchemy import select, text

        from ...models import crawler_runs, insurance_providers

        reserved_rule_ids=iter([int(await self._allocate_id()) for _ in policies])
        accepted = 0
        duplicates = 0
        quarantined = 0
        changed = 0
        async with self._read_session() as session:
            async with session.begin():
                provider = (
                    await session.execute(
                        select(insurance_providers)
                        .where(insurance_providers.c.id == int(outcome.provider_id))
                        .with_for_update()
                    )
                ).mappings().first()
                if provider is None:
                    return {"lease_owned": False}
                run_result = await session.execute(
                    text(
                        "SELECT state, version, fencing_version, lease_until, attempt_count "
                        "FROM crawler_runs WHERE id=:run_id AND provider_id=:provider_id FOR UPDATE"
                    ),
                    {"run_id": int(run_id), "provider_id": int(outcome.provider_id)},
                )
                run = run_result.mappings().first()
                if run is None:
                    return {"lease_owned": False}
                if fencing_version is None:
                    if run["state"] not in {"pending", "running"}:
                        return {"lease_owned": False}
                elif (
                    run["state"] != "running"
                    or int(run["fencing_version"]) != fencing_version
                    or run["lease_until"] is None
                ):
                    return {"lease_owned": False}
                if fencing_version is not None:
                    lease_ok = await session.execute(
                        text("SELECT :lease_until > CURRENT_TIMESTAMP"),
                        {"lease_until": run["lease_until"]},
                    )
                    if not lease_ok.scalar_one():
                        return {"lease_owned": False}

                audit_sequence = int(run["version"])
                if outcome.policies_quarantined:
                    audit_sequence += 1
                    await self._call_audit_outbox(
                        session,
                        action="insurance.source_revision_conflict",
                        run_id=int(run_id),
                        version=audit_sequence,
                        payload={
                            "provider_id": outcome.provider_id,
                            "run_id": run_id,
                            "conflict_count": outcome.policies_quarantined,
                            "reason": "same_run_revision_conflict",
                        },
                    )

                effective_versions: dict[tuple[str, str], int] = {}
                for observation in observations:
                    old_result = await session.execute(
                        text(
                            "SELECT source_version, content_hash FROM insurance_source_versions "
                            "WHERE provider_id=:provider_id AND source_id=:source_id AND source_path=:path FOR UPDATE"
                        ),
                        {
                            "provider_id": int(outcome.provider_id),
                            "source_id": observation.source_id,
                            "path": observation.path,
                        },
                    )
                    old = old_result.mappings().first()
                    if old is None:
                        version = 1
                        await session.execute(
                            text(
                                "INSERT INTO insurance_source_versions "
                                "(provider_id,source_id,source_path,source_version,content_hash,observed_run_id,observed_at) "
                                "VALUES (:provider_id,:source_id,:path,:source_version,:content_hash,:run_id,:observed_at) "
                                "ON CONFLICT (provider_id,source_id,source_path) DO NOTHING"
                            ),
                            {
                                "provider_id": int(outcome.provider_id),
                                "source_id": observation.source_id,
                                "path": observation.path,
                                "source_version": version,
                                "content_hash": observation.content_hash,
                                "run_id": int(run_id),
                                "observed_at": observation.observed_at,
                            },
                        )
                        # Serialize a first-observation race and use the committed version.
                        verify = await session.execute(
                            text(
                                "SELECT source_version, content_hash FROM insurance_source_versions "
                                "WHERE provider_id=:provider_id AND source_id=:source_id AND source_path=:path FOR UPDATE"
                            ),
                            {
                                "provider_id": int(outcome.provider_id),
                                "source_id": observation.source_id,
                                "path": observation.path,
                            },
                        )
                        current = verify.mappings().one()
                        version = int(current["source_version"])
                    elif old["content_hash"] == observation.content_hash:
                        version = int(old["source_version"])
                        await session.execute(
                            text(
                                "UPDATE insurance_source_versions SET observed_run_id=:run_id, observed_at=:observed_at "
                                "WHERE provider_id=:provider_id AND source_id=:source_id AND source_path=:path"
                            ),
                            {
                                "provider_id": int(outcome.provider_id),
                                "source_id": observation.source_id,
                                "path": observation.path,
                                "run_id": int(run_id),
                                "observed_at": observation.observed_at,
                            },
                        )
                    else:
                        version = int(old["source_version"]) + 1
                        changed += 1
                        await session.execute(
                            text(
                                "UPDATE insurance_source_versions SET source_version=:source_version, content_hash=:content_hash, "
                                "observed_run_id=:run_id, observed_at=:observed_at "
                                "WHERE provider_id=:provider_id AND source_id=:source_id AND source_path=:path"
                            ),
                            {
                                "provider_id": int(outcome.provider_id),
                                "source_id": observation.source_id,
                                "path": observation.path,
                                "source_version": version,
                                "content_hash": observation.content_hash,
                                "run_id": int(run_id),
                                "observed_at": observation.observed_at,
                            },
                        )
                    effective_versions[(observation.source_id, observation.path)] = version

                for policy in policies:
                    source_version = effective_versions.get((policy.source_id, policy.source_path), policy.source_version)
                    rule = policy.rule
                    existing_result = await session.execute(
                        text(
                            "SELECT content_hash FROM insurance_rules WHERE provider_id=:provider_id "
                            "AND policy_code=:policy_code "
                            "AND (rule_data->'policy'->>'revision')::bigint=:source_revision"
                        ),
                        {
                            "provider_id": int(outcome.provider_id),
                            "policy_code": rule.policy_code,
                            "source_revision": rule.revision,
                        },
                    )
                    existing = existing_result.mappings().first()
                    if existing is not None:
                        if existing["content_hash"] == policy.content_hash:
                            duplicates += 1
                        else:
                            quarantined += 1
                            audit_sequence += 1
                            await self._call_audit_outbox(
                                session,
                                action="insurance.source_revision_conflict",
                                run_id=int(run_id),
                                version=audit_sequence,
                                payload={
                                    "provider_id": outcome.provider_id,
                                    "policy_code": rule.policy_code,
                                    "rule_revision": rule.revision,
                                    "source_run_id": run_id,
                                },
                            )
                        continue
                    storage_revision_result = await session.execute(
                        text("SELECT COALESCE(MAX(revision),0)+1 FROM insurance_rules WHERE provider_id=:provider_id"),
                        {"provider_id": int(outcome.provider_id)},
                    )
                    storage_revision = int(storage_revision_result.scalar_one())
                    rule_id = next(reserved_rule_ids)
                    rule_data = {
                        "policy": rule.to_dict(),
                        "source": {
                            "source_id": policy.source_id,
                            "source_path": policy.source_path,
                            "source_version": source_version,
                            "source_run_id": policy.source_run_id,
                            "observed_at": policy.observed_at,
                        },
                    }
                    await session.execute(
                        text(
                            "INSERT INTO insurance_rules "
                            "(id,provider_id,source_run_id,revision,policy_code,content_hash,effective_from,effective_to,rule_data) "
                            "VALUES (:id,:provider_id,:run_id,:storage_revision,:policy_code,:content_hash,:effective_from,:effective_to,CAST(:rule_data AS jsonb))"
                        ),
                        {
                            "id": rule_id,
                            "provider_id": int(outcome.provider_id),
                            "run_id": int(run_id),
                            "storage_revision": storage_revision,
                            "policy_code": rule.policy_code,
                            "content_hash": policy.content_hash,
                            "effective_from": rule.effective_from,
                            "effective_to": rule.effective_to,
                            "rule_data": json.dumps(rule_data, separators=(",", ":")),
                        },
                    )
                    accepted += 1
                    audit_sequence += 1
                    await self._call_audit_outbox(
                        session,
                        action="insurance.rule_accepted",
                        run_id=int(run_id),
                        version=audit_sequence,
                        payload={
                            "provider_id": outcome.provider_id,
                            "policy_code": rule.policy_code,
                            "rule_revision": rule.revision,
                            "rules_id": str(rule_id),
                            "source_run_id": run_id,
                        },
                    )

                if quarantined:
                    state = "partial"
                    error_code = "source_revision_conflict"
                else:
                    state = outcome.state
                    error_code = outcome.error_code
                content_manifest = {
                    "pages": sorted(
                        (o.source_id, o.path, o.content_hash, effective_versions.get((o.source_id, o.path), o.source_version))
                        for o in observations
                    ),
                    "rules": sorted((p.rule.policy_code, p.rule.revision, p.content_hash) for p in policies),
                }
                content_hash = hashlib.sha256(
                    json.dumps(content_manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest()
                retry_seconds = min(30, 2 ** max(1, int(run["attempt_count"])))
                await session.execute(
                    text(
                        "UPDATE crawler_runs SET state=:state, fetched_at=CURRENT_TIMESTAMP, content_hash=:content_hash, "
                        "error_code=:error_code, pages_processed=:pages_processed, pages_retrieved=:pages_retrieved, "
                        "pages_failed=:pages_failed, pages_invalid=:pages_invalid, pages_deduplicated=:pages_deduplicated, "
                        "policies_accepted=:policies_accepted, policies_quarantined=:policies_quarantined, "
                        "next_attempt_at=CURRENT_TIMESTAMP + (:retry_seconds * INTERVAL '1 second'), "
                        "lease_owner=NULL, lease_until=NULL, version=version+1 "
                        "WHERE id=:run_id"
                    ),
                    {
                        "state": state,
                        "content_hash": content_hash,
                        "error_code": error_code,
                        "pages_processed": outcome.pages_processed,
                        "pages_retrieved": outcome.pages_retrieved,
                        "pages_failed": outcome.pages_failed,
                        "pages_invalid": outcome.pages_invalid,
                        "pages_deduplicated": outcome.pages_deduplicated,
                        "policies_accepted": accepted,
                        "policies_quarantined": outcome.policies_quarantined + quarantined,
                        "retry_seconds": retry_seconds,
                        "run_id": int(run_id),
                    },
                )
                await self._call_audit_outbox(
                    session,
                    action="insurance.crawl_completed",
                    run_id=int(run_id),
                    version=audit_sequence + 1,
                    payload={
                        "provider_id": outcome.provider_id,
                        "run_id": run_id,
                        "state": state,
                        "pages_processed": outcome.pages_processed,
                        "pages_failed": outcome.pages_failed,
                        "policies_accepted": accepted,
                        "policies_quarantined": outcome.policies_quarantined + quarantined,
                    },
                )
                return {
                    "lease_owned": True,
                    "state": state,
                    "policies_accepted": accepted,
                    "policies_deduplicated": duplicates,
                    "policies_quarantined": quarantined,
                    "changed_pages": changed,
                    "error_code": error_code,
                }

    async def claim_runs(self, session: Any, now: datetime, limit: int) -> tuple[dict[str, Any], ...]:
        """Claim a bounded due batch with SKIP LOCKED; caller commits before fetching."""
        from sqlalchemy import text

        if type(limit) is not int or not 1 <= limit <= CLAIM_BATCH_MAX:
            raise ValueError("claim limit exceeds the reviewed bound")
        exhausted_result = await session.execute(
            text(
                "SELECT id,provider_id,version,fencing_version FROM crawler_runs "
                "WHERE state='running' AND lease_until<=:now AND attempt_count>=:max_attempts "
                "ORDER BY lease_until,created_at,id FOR UPDATE SKIP LOCKED"
            ),
            {"now": now, "max_attempts": MAX_RUN_ATTEMPTS},
        )
        for exhausted in exhausted_result.mappings().all():
            updated = await session.execute(
                text(
                    "UPDATE crawler_runs SET state='failed',error_code='retry_exhausted',"
                    "fetched_at=CURRENT_TIMESTAMP,lease_owner=NULL,lease_until=NULL,version=version+1 "
                    "WHERE id=:run_id AND state='running' AND fencing_version=:fencing_version "
                    "AND lease_until<=:now AND attempt_count>=:max_attempts"
                ),
                {
                    "run_id": exhausted["id"],
                    "fencing_version": exhausted["fencing_version"],
                    "now": now,
                    "max_attempts": MAX_RUN_ATTEMPTS,
                },
            )
            if updated.rowcount:
                await self._call_audit_outbox(
                    session,
                    action="insurance.crawl_completed",
                    run_id=int(exhausted["id"]),
                    version=int(exhausted["version"]) + 1,
                    payload={
                        "provider_id": str(exhausted["provider_id"]),
                        "run_id": str(exhausted["id"]),
                        "state": "failed",
                        "error_code": "retry_exhausted",
                    },
                )
        query = text(
            "WITH candidates AS ("
            " SELECT r.id FROM crawler_runs r WHERE ("
            " (r.state='pending' AND r.next_attempt_at<=:now) OR "
            " (r.state IN ('failed','partial') AND r.next_attempt_at<=:now AND r.attempt_count<:max_attempts) OR "
            " (r.state='running' AND r.lease_until<=:now AND r.attempt_count<:max_attempts)) "
            " AND NOT EXISTS (SELECT 1 FROM crawler_runs active WHERE active.provider_id=r.provider_id "
            "   AND active.id<>r.id AND active.state IN ('pending','running')) "
            " AND NOT EXISTS (SELECT 1 FROM crawler_runs earlier WHERE earlier.provider_id=r.provider_id "
            "   AND earlier.id<>r.id AND earlier.next_attempt_at<=:now AND earlier.attempt_count<:max_attempts "
            "   AND (earlier.state='pending' OR earlier.state IN ('failed','partial') OR "
            "     (earlier.state='running' AND earlier.lease_until<=:now)) "
            "   AND NOT EXISTS (SELECT 1 FROM crawler_runs active_earlier WHERE active_earlier.provider_id=earlier.provider_id "
            "     AND active_earlier.id<>earlier.id AND active_earlier.state IN ('pending','running')) "
            "   AND (earlier.next_attempt_at,earlier.created_at,earlier.id)<(r.next_attempt_at,r.created_at,r.id)) "
            " ORDER BY r.next_attempt_at,r.created_at,r.id FOR UPDATE SKIP LOCKED LIMIT :limit"
            ") UPDATE crawler_runs r SET state='running', lease_owner=:worker_id, "
            "lease_until=:lease_until, fencing_version=r.fencing_version+1, attempt_count=r.attempt_count+1, "
            "version=r.version+1 FROM candidates c WHERE r.id=c.id RETURNING r.id,r.provider_id,r.fencing_version,r.version"
        )
        result = await session.execute(
            query,
            {
                "now": now,
                "lease_until": now + timedelta(seconds=RUN_LEASE_SECONDS),
                "limit": limit,
                "max_attempts": MAX_RUN_ATTEMPTS,
                "worker_id": self.worker_id,
            },
        )
        return tuple(dict(row) for row in result.mappings().all())

    async def list_providers(self, session: Any, cursor: str | None, limit: int) -> dict[str, Any]:
        from sqlalchemy import text

        after_id = 0
        if cursor is not None:
            from .contracts import validate_id

            after_id = int(validate_id(cursor, name="cursor"))
        result = await session.execute(
            text(
                "SELECT p.id,p.version,p.synthetic_slug,MAX(r.fetched_at) FILTER (WHERE r.state='complete') AS last_success_at "
                "FROM insurance_providers p LEFT JOIN crawler_runs r ON r.provider_id=p.id "
                "WHERE p.id>:after_id GROUP BY p.id,p.version,p.synthetic_slug ORDER BY p.id LIMIT :limit"
            ),
            {"after_id": after_id, "limit": limit + 1},
        )
        rows = result.mappings().all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = [
            {
                "id": str(row["id"]),
                "synthetic_slug": row["synthetic_slug"],
                "version": int(row["version"]),
                "last_success_at": row["last_success_at"].astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                if row["last_success_at"] is not None
                else None,
            }
            for row in rows
        ]
        return {"items": items, "next_cursor": str(rows[-1]["id"]) if has_more and rows else None}

    async def get_run(self, session: Any, run_id: str) -> dict[str, Any] | None:
        from sqlalchemy import text

        result = await session.execute(
            text("SELECT id,provider_id,state,pages_processed,error_code,version FROM crawler_runs WHERE id=:id"),
            {"id": int(run_id)},
        )
        row = result.mappings().first()
        if row is None:
            return None
        state = row["state"] if row["state"] in {"pending", "running", "complete", "partial", "failed"} else "failed"
        return {
            "id": str(row["id"]),
            "provider_id": str(row["provider_id"]),
            "state": state,
            "pages_processed": int(row["pages_processed"]),
            "error_code": row["error_code"],
            "version": int(row["version"]),
        }

    async def latest_run_state(self) -> str | None:
        """Read recent health state without making crawler status Billing readiness."""
        from sqlalchemy import text

        async with self._read_session() as session:
            result = await session.execute(
                text(
                    "SELECT state FROM crawler_runs "
                    "WHERE fetched_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours' "
                    "ORDER BY fetched_at DESC,id DESC LIMIT 1"
                )
            )
            return result.scalar_one_or_none()

    async def policy_for_estimate(
        self, session: Any, provider_id: str, policy_code: str, now: datetime | None = None
    ) -> dict[str, Any] | None:
        import re

        from sqlalchemy import text

        from .contracts import export_validated_policy, rule_content_hash, validate

        if not isinstance(policy_code, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", policy_code):
            return None
        latest=(await session.execute(text("SELECT error_code FROM crawler_runs WHERE provider_id=:provider_id AND fetched_at IS NOT NULL ORDER BY fetched_at DESC,id DESC LIMIT 1"),{'provider_id':int(provider_id)})).scalar_one_or_none()
        if latest=='source_revision_conflict':
            from .contracts import InsuranceValidationError
            raise InsuranceValidationError('source_revision_conflict')
        result = await session.execute(
            text(
                "SELECT r.id,r.provider_id,r.source_run_id,r.rule_data,r.content_hash,run.fetched_at,CURRENT_TIMESTAMP AS database_now "
                "FROM insurance_rules r JOIN crawler_runs run ON run.id=r.source_run_id "
                "WHERE r.provider_id=:provider_id AND r.policy_code=:policy_code "
                "AND r.effective_from<=CURRENT_TIMESTAMP AND r.effective_to>CURRENT_TIMESTAMP AND run.state IN ('complete','partial') "
                "ORDER BY (r.rule_data->'policy'->>'revision')::bigint DESC,r.revision DESC LIMIT 1"
            ),
            {"provider_id": int(provider_id), "policy_code": policy_code},
        )
        row = result.mappings().first()
        if row is None or row["fetched_at"] is None:
            return None
        data = row["rule_data"]
        if isinstance(data, str):
            data = json.loads(data)
        if not isinstance(data, dict) or set(data) != {"policy", "source"}:
            return None
        source = data["source"]
        try:
            rule = validate(data["policy"])
            content_hash = rule_content_hash(rule)
            policy = export_validated_policy(
                provider_id=str(row["provider_id"]),
                source_id=source["source_id"],
                source_path=source["source_path"],
                source_run_id=str(source["source_run_id"]),
                source_version=source["source_version"],
                content_hash=content_hash,
                observed_at=source["observed_at"],
                rule=rule,
            )
        except (KeyError, TypeError, ValueError):
            return None
        if row["content_hash"] != content_hash:
            return None
        return {
            "rules_id": str(row["id"]),
            "policy_export": policy,
            "source_fetched_at": row["fetched_at"],
            "database_now": row["database_now"],
        }

    async def create_estimate(self, session: Any, result: Mapping[str, Any]) -> None:
        from sqlalchemy import text

        await session.execute(
            text(
                "INSERT INTO insurance_estimates "
                "(id,invoice_id,rules_id,provider_id,source_run_id,invoice_version,rule_revision,currency,eligible_minor,estimate_minor,calculated_at,freshness_state,version) "
                "VALUES (:id,:invoice_id,:rules_id,:provider_id,:source_run_id,:invoice_version,:rule_revision,:currency,:eligible_minor,:estimate_minor,:calculated_at,:freshness_state,:version)"
            ),
            {
                "id": int(result["id"]),
                "invoice_id": int(result["invoice_id"]),
                "rules_id": int(result["rules_id"]),
                "provider_id": int(result["provider_id"]),
                "source_run_id": int(result["source_run_id"]),
                "invoice_version": result["invoice_version"],
                "rule_revision": result["rule_revision"],
                "currency": result["currency"],
                "eligible_minor": result["eligible_minor"],
                "estimate_minor": result["estimate_minor"],
                "calculated_at": result["calculated_at"],
                "freshness_state": result["freshness_state"],
                "version": result["version"],
            },
        )
        await self._call_audit_outbox(
            session,
            action="insurance.estimate_created",
            run_id=int(result["source_run_id"]),
            version=int(result["version"]),
            payload={
                "invoice_id": result["invoice_id"],
                "estimate_id": result["id"],
                "provider_id": result["provider_id"],
                "policy_code": result["policy_code"],
                "estimate_minor": result["estimate_minor"],
                "currency": "INR",
            },
        )

    async def list_estimates(self, session: Any, invoice_id: str, cursor: str | None, limit: int) -> dict[str, Any]:
        from sqlalchemy import text

        after_id = 0
        if cursor is not None:
            from .contracts import validate_id

            after_id = int(validate_id(cursor, name="cursor"))
        result = await session.execute(
            text(
                "SELECT e.id,e.invoice_id,e.invoice_version,e.provider_id,e.rules_id,e.source_run_id,e.rule_revision,"
                "e.currency,e.eligible_minor,e.estimate_minor,e.calculated_at,e.freshness_state,e.version,"
                "r.policy_code,run.fetched_at,i.version AS current_invoice_version,"
                "CURRENT_TIMESTAMP - run.fetched_at > INTERVAL '24 hours' AS source_is_stale "
                "FROM insurance_estimates e JOIN insurance_rules r ON r.id=e.rules_id "
                "JOIN crawler_runs run ON run.id=e.source_run_id JOIN invoices i ON i.id=e.invoice_id "
                "WHERE e.invoice_id=:invoice_id AND e.id>:after_id ORDER BY e.id LIMIT :limit"
            ),
            {"invoice_id": int(invoice_id), "after_id": after_id, "limit": limit + 1},
        )
        rows = result.mappings().all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        items: list[dict[str, Any]] = []
        for row in rows:
            calculated = row["calculated_at"].astimezone(timezone.utc)
            stale = (
                row["current_invoice_version"] != row["invoice_version"]
                or bool(row["source_is_stale"])
            )
            items.append(
                {
                    "id": str(row["id"]),
                    "invoice_id": str(row["invoice_id"]),
                    "invoice_version": int(row["invoice_version"]),
                    "provider_id": str(row["provider_id"]),
                    "policy_code": row["policy_code"],
                    "rules_id": str(row["rules_id"]),
                    "rule_revision": int(row["rule_revision"]),
                    "source_run_id": str(row["source_run_id"]),
                    "currency": row["currency"],
                    "eligible_minor": int(row["eligible_minor"]),
                    "estimate_minor": int(row["estimate_minor"]),
                    "calculated_at": calculated.isoformat().replace("+00:00", "Z"),
                    "freshness_state": "stale" if stale else "fresh",
                    "is_simulated": True,
                    "version": int(row["version"]),
                }
            )
        return {"items": items, "next_cursor": str(rows[-1]["id"]) if has_more and rows else None}

    async def fail_claim(self, claim: Mapping[str, Any], error_code: str) -> None:
        from sqlalchemy import text

        safe_codes = {
            "provider_not_found",
            "source_not_configured",
            "source_not_allowlisted",
            "source_resolution_failed",
            "worker_error",
            "invalid_lease_version",
        }
        safe_code = error_code if error_code in safe_codes else "worker_error"
        async with self._read_session() as session:
            async with session.begin():
                result = await session.execute(
                    text(
                        "UPDATE crawler_runs SET state='failed',error_code=:error_code,fetched_at=CURRENT_TIMESTAMP,"
                        "next_attempt_at=CURRENT_TIMESTAMP + INTERVAL '2 seconds',lease_owner=NULL,lease_until=NULL,version=version+1 "
                        "WHERE id=:run_id AND provider_id=:provider_id AND state='running' AND fencing_version=:fencing_version "
                        "AND lease_until>CURRENT_TIMESTAMP"
                    ),
                    {
                        "error_code": safe_code,
                        "run_id": int(claim.get("id", claim.get("run_id"))),
                        "provider_id": int(claim["provider_id"]),
                        "fencing_version": int(claim.get("fencing_version", claim.get("lease_version"))),
                    },
                )
                if result.rowcount:
                    await self._call_audit_outbox(
                        session,
                        action="insurance.crawl_completed",
                        run_id=int(claim.get("id", claim.get("run_id"))),
                        version=int(claim.get("version", 1)) + 1,
                        payload={"provider_id": str(claim["provider_id"]), "state": "failed", "error_code": safe_code},
                    )

    async def _call_audit_outbox(self, session: Any, *, action: str, run_id: int, version: int, payload: dict) -> None:
        result = self._audit_outbox(
            session,
            action=action,
            aggregate_type="insurance_run",
            aggregate_id=run_id,
            aggregate_version=version,
            payload=payload,
        )
        if hasattr(result, "__await__"):
            await result
