"""Database-backed POST replay handling; locks remain local to one command."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .errors import ApiError
from .wire import canonical_json


@dataclass(frozen=True)
class StoredOutcome:
    status_code: int
    body: dict[str, Any]
    entity_tag: str | None


def fingerprint(body: dict[str, Any], if_match: str | None) -> str:
    value = {"body": body, "if_match": if_match}
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _advisory_key(scope: str, route_key: str, key: str) -> int:
    raw = f"{scope}\x1fPOST\x1f{route_key}\x1f{key}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big", signed=True)


async def replay_if_present(
    session: AsyncSession,
    *,
    scope: str,
    route_key: str,
    key: str,
    request_hash: str,
    lock: bool,
) -> StoredOutcome | None:
    """Replay an unexpired outcome, optionally serializing equal concurrent commands."""
    if lock:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": _advisory_key(scope, route_key, key)},
        )
    query = text(
        """SELECT request_hash, response_code, response, expires_at
             FROM idempotency_requests
            WHERE principal_scope=:scope AND method='POST'
              AND route_template=:route_key AND key=:key"""
        + (" FOR UPDATE" if lock else "")
    )
    row = (await session.execute(
        query, {"scope": scope, "route_key": route_key, "key": key}
    )).mappings().first()
    if row is None:
        return None
    now = datetime.now(timezone.utc)
    expires_at = row["expires_at"]
    if expires_at <= now:
        if lock:
            await session.execute(
                text(
                    """DELETE FROM idempotency_requests
                         WHERE principal_scope=:scope AND method='POST'
                           AND route_template=:route_key AND key=:key"""
                ),
                {"scope": scope, "route_key": route_key, "key": key},
            )
        return None
    if row["request_hash"] != request_hash:
        raise ApiError(409, "idempotency_key_reused")
    payload = row["response"]
    if not isinstance(payload, dict) or not isinstance(payload.get("body"), dict):
        raise ApiError(503, "dependency_unavailable")
    return StoredOutcome(
        row["response_code"], payload["body"], payload.get("etag")
    )


async def save_outcome(
    session: AsyncSession,
    *,
    scope: str,
    route_key: str,
    key: str,
    request_hash: str,
    status_code: int,
    body: dict[str, Any],
    entity_tag: str | None,
) -> None:
    await session.execute(
        text(
            """INSERT INTO idempotency_requests
                   (principal_scope,method,route_template,key,request_hash,
                    response_code,response,expires_at)
               VALUES (:scope,'POST',:route_key,:key,:request_hash,
                       :response_code,CAST(:response AS jsonb),:expires_at)"""
        ),
        {
            "scope": scope,
            "route_key": route_key,
            "key": key,
            "request_hash": request_hash,
            "response_code": status_code,
            "response": canonical_json({"body": body, "etag": entity_tag}),
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=24),
        },
    )


def outcome_response(outcome: StoredOutcome | None) -> JSONResponse | None:
    if outcome is None:
        return None
    headers = {"ETag": outcome.entity_tag} if outcome.entity_tag is not None else {}
    return JSONResponse(
        status_code=outcome.status_code,
        content=outcome.body,
        headers=headers,
    )
