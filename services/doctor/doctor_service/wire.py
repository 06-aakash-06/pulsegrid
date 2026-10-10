"""Shared strict parsing for IDs, ETags, idempotency keys, cursors, and queries."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable

from fastapi import Request

from .errors import ApiError

_ID = re.compile(r"^[1-9][0-9]{0,18}$")
_ETAG = re.compile(r'^"([1-9][0-9]{0,15})"$')
_CURSOR_TIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$"
)


def parse_id(value: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ApiError(422, "validation_error")
    if int(value) > 9223372036854775807:
        raise ApiError(422, "validation_error")
    return value


def parse_if_match(value: str | None) -> int:
    if value is None:
        raise ApiError(428, "precondition_required")
    match = _ETAG.fullmatch(value)
    if match is None:
        raise ApiError(400, "bad_request")
    version = int(match.group(1))
    if version > 9007199254740991:
        raise ApiError(400, "bad_request")
    return version


def etag(version: int) -> str:
    return f'"{version}"'


def idempotency_key(value: str | None) -> str:
    if (
        value is None
        or not 16 <= len(value) <= 128
        or any(ord(char) < 33 or ord(char) > 126 for char in value)
    ):
        raise ApiError(400, "bad_request")
    return value


def validate_query_keys(request: Request, allowed: Iterable[str]) -> None:
    allowed_keys = set(allowed)
    if any(key not in allowed_keys for key in request.query_params.keys()):
        raise ApiError(422, "validation_error")
    if any(len(request.query_params.getlist(key)) != 1 for key in request.query_params.keys()):
        raise ApiError(422, "validation_error")


def normalized_search(value: str | None) -> str | None:
    if value is None:
        return None
    result = value.strip().lower()
    if not 2 <= len(result) <= 100:
        raise ApiError(422, "validation_error")
    return result


def limit_value(value: int) -> int:
    if not 1 <= value <= 100:
        raise ApiError(422, "validation_error")
    return value


def filter_digest(filters: dict[str, Any]) -> str:
    canonical = json.dumps(filters, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def encode_cursor(created_at: datetime, resource_id: str, filter_hash: str) -> str:
    if created_at.tzinfo is None:
        raise ValueError("cursor timestamp must be timezone-aware")
    timestamp = created_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    payload = json.dumps(
        {"created_at": timestamp, "id": resource_id, "filter_hash": filter_hash},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_cursor(value: str | None, expected_filter_hash: str) -> tuple[datetime, str] | None:
    if value is None:
        return None
    if not value or len(value) > 1024 or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ApiError(400, "bad_request")
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        payload = json.loads(raw)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        raise ApiError(400, "bad_request") from None
    if (
        not isinstance(payload, dict)
        or set(payload) != {"created_at", "id", "filter_hash"}
        or not isinstance(payload["created_at"], str)
        or not _CURSOR_TIME.fullmatch(payload["created_at"])
        or payload["filter_hash"] != expected_filter_hash
    ):
        raise ApiError(400, "bad_request")
    try:
        resource_id = parse_id(payload["id"])
    except ApiError:
        raise ApiError(400, "bad_request") from None
    try:
        raw_time = payload["created_at"]
        created_at = datetime.fromisoformat(
            raw_time[:-1] + "+00:00" if raw_time.endswith("Z") else raw_time
        )
    except ValueError:
        raise ApiError(400, "bad_request") from None
    if created_at.utcoffset() != timezone.utc.utcoffset(created_at):
        raise ApiError(400, "bad_request")
    return created_at.astimezone(timezone.utc), resource_id


def canonical_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def escape_like_prefix(value: str) -> str:
    return value.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
