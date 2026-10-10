"""Stable, filter-bound cursors for billing history lists."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import datetime, timezone

from fastapi import HTTPException


def filter_hash(filters: dict, scope: str) -> str:
    canonical = json.dumps(
        {"filters": filters, "scope": scope}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def encode_cursor(created_at: datetime, row_id: int, expected_hash: str) -> str:
    timestamp = created_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    payload = json.dumps(
        {"created_at": timestamp, "id": str(row_id), "filter_hash": expected_hash},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def decode_cursor(cursor: str | None, expected_hash: str) -> tuple[datetime, int] | None:
    if cursor is None:
        return None
    try:
        if not cursor or len(cursor) > 2048:
            raise ValueError
        raw = base64.b64decode(
            cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True
        )
        value = json.loads(raw)
        if (
            not isinstance(value, dict)
            or set(value) != {"created_at", "id", "filter_hash"}
            or value["filter_hash"] != expected_hash
            or not isinstance(value["id"], str)
            or not re.fullmatch(r"[1-9][0-9]{0,18}", value["id"])
            or str(int(value["id"])) != value["id"]
            or int(value["id"]) <= 0
            or int(value["id"]) > 9_223_372_036_854_775_807
        ):
            raise ValueError
        timestamp = value["created_at"]
        if not isinstance(timestamp, str):
            raise ValueError
        position = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if position.utcoffset() != timezone.utc.utcoffset(position):
            raise ValueError
        return position.astimezone(timezone.utc), int(value["id"])
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_cursor", "message": "The cursor is invalid or does not match these filters."},
        ) from None
