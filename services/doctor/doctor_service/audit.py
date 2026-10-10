"""Append domain audit through the constrained service-owned DB function."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .ids import new_id


async def append_audit(
    session: AsyncSession,
    request: Request,
    *,
    actor_user_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    resource_version: int,
    details: dict[str, Any] | None = None,
) -> None:
    occurred_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    metadata = {
        "action": action,
        "result": "success",
        "actor_user_id": actor_user_id,
        "request_id": str(request.state.request_id),
        "correlation_id": str(request.state.correlation_id),
        "occurred_at": occurred_at,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "resource_version": resource_version,
        "details": details or {},
    }
    await session.execute(
        text("SELECT public.doctor_append_audit(:entry_id, CAST(:metadata AS jsonb))"),
        {
            "entry_id": new_id(),
            "metadata": json.dumps(metadata, separators=(",", ":"), sort_keys=True),
        },
    )
