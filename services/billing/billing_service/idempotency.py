"""PostgreSQL-local, response-preserving idempotency for Billing POSTs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from .models import idempotency_requests


@dataclass(frozen=True)
class StoredOutcome:
    status_code: int
    body: dict
    etag: str | None


def validated_key(request: Request) -> str:
    value = request.headers.get("Idempotency-Key", "")
    if not 16 <= len(value) <= 128 or any(not 0x21 <= ord(char) <= 0x7E for char in value):
        raise HTTPException(
            400,
            detail={"code": "invalid_idempotency_key", "message": "Idempotency-Key must contain 16 to 128 printable ASCII non-space characters."},
        )
    return value


def request_fingerprint(body: dict, *, resource_ids: dict, if_match: str | None = None) -> str:
    payload = {"body": body, "resource_ids": resource_ids, "if_match": if_match}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()


def _identity(principal, route: str, key: str):
    return {
        "principal_scope": "user:" + principal.user_id,
        "method": "POST",
        "route_template": route,
        "key": key,
    }


def _expiry(route: str) -> datetime:
    duration = timedelta(days=7) if route.endswith("/payments") else timedelta(hours=24)
    return datetime.now(timezone.utc) + duration


async def replay_if_present(
    session: AsyncSession,
    principal,
    route: str,
    key: str,
    fingerprint: str,
) -> StoredOutcome | None:
    identity = _identity(principal, route, key)
    async with session.begin():
        row = (
            await session.execute(
                select(idempotency_requests).where(
                    *(idempotency_requests.c[name] == value for name, value in identity.items())
                )
            )
        ).mappings().first()
        if row is None or row["expires_at"] <= datetime.now(timezone.utc):
            return None
        if row["request_hash"] != fingerprint:
            raise HTTPException(
                409,
                detail={"code": "idempotency_key_reused", "message": "The key was already used for different request content."},
            )
        return unpack(row["response_code"], row["response"])


async def lock_and_read(
    session: AsyncSession,
    principal,
    route: str,
    key: str,
    fingerprint: str,
) -> StoredOutcome | None:
    """Call inside a transaction after remote reads; serialize equal keys locally."""
    identity = _identity(principal, route, key)
    lock_digest = hashlib.sha256(
        "\0".join(identity.values()).encode("utf-8")
    ).digest()
    lock_id = int.from_bytes(lock_digest[:8], byteorder="big", signed=True)
    await session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})
    row = (
        await session.execute(
            select(idempotency_requests)
            .where(*(idempotency_requests.c[name] == value for name, value in identity.items()))
            .with_for_update()
        )
    ).mappings().first()
    if row is not None and row["expires_at"] > datetime.now(timezone.utc):
        if row["request_hash"] != fingerprint:
            raise HTTPException(
                409,
                detail={"code": "idempotency_key_reused", "message": "The key was already used for different request content."},
            )
        return unpack(row["response_code"], row["response"])
    if row is not None:
        await session.execute(delete(idempotency_requests).where(
            *(idempotency_requests.c[name] == value for name, value in identity.items())
        ))
    return None


async def save_outcome(
    session: AsyncSession,
    principal,
    route: str,
    key: str,
    fingerprint: str,
    outcome: StoredOutcome,
) -> None:
    identity = _identity(principal, route, key)
    await session.execute(
        insert(idempotency_requests).values(
            **identity,
            request_hash=fingerprint,
            response_code=outcome.status_code,
            response={"body": outcome.body, "etag": outcome.etag},
            expires_at=_expiry(route),
        )
    )


def unpack(status_code: int, response: dict) -> StoredOutcome:
    if not isinstance(response, dict) or set(response) != {"body", "etag"} or not isinstance(response["body"], dict):
        raise HTTPException(503)
    etag = response["etag"]
    if etag is not None and not isinstance(etag, str):
        raise HTTPException(503)
    return StoredOutcome(status_code, response["body"], etag)


def payment_durable_key(principal, invoice_id: str, key: str) -> str:
    """Stable ledger uniqueness that survives idempotency response retention."""
    material = f"user:{principal.user_id}\0POST\0/api/v1/billing/invoices/{{invoice_id}}/payments\0{invoice_id}\0{key}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
