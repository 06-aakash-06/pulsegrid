"""Build immutable unpublished envelopes inside the Doctor owner transaction."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .constants import SERVICE_NAME
from .ids import new_id


async def append_outbox(
    session: AsyncSession,
    request: Request,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    aggregate_version: int,
    payload: dict[str, Any],
) -> None:
    now = datetime.now(timezone.utc)
    occurred_at = now.isoformat().replace("+00:00", "Z")
    envelope = {
        "event_id": str(new_id()),
        "event_type": event_type,
        "schema_version": 1,
        "producer": SERVICE_NAME,
        "occurred_at": occurred_at,
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "aggregate_version": aggregate_version,
        "correlation_id": str(request.state.correlation_id),
        "request_id": str(request.state.request_id),
        "causation_id": None,
        "traceparent": getattr(request.state, "traceparent", None),
        "payload": payload,
    }
    await session.execute(
        text(
            """INSERT INTO outbox_events
                   (event_id,aggregate_type,aggregate_id,aggregate_version,
                    event_type,envelope,next_attempt_at)
               VALUES (:event_id,:aggregate_type,:aggregate_id,:aggregate_version,
                       :event_type,CAST(:envelope AS jsonb),:next_attempt_at)"""
        ),
        {
            "event_id": int(envelope["event_id"]),
            "aggregate_type": aggregate_type,
            "aggregate_id": int(aggregate_id),
            "aggregate_version": aggregate_version,
            "event_type": event_type,
            "envelope": json.dumps(envelope, separators=(",", ":"), sort_keys=True),
            "next_attempt_at": now,
        },
    )
