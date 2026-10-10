"""Exact-money calculations and transactional Billing audit/outbox helpers."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from .models import invoice_items, outbox_events
from .schemas import MAX_MINOR

MAX_BIGINT = 9_223_372_036_854_775_807


def new_id() -> int:
    return secrets.randbelow(MAX_BIGINT) + 1


def calculate_totals(items: list[dict]) -> tuple[int, int]:
    """Return exact integer-minor subtotal and total; Phase 2 has no adjustments."""
    subtotal = 0
    for item in items:
        line_total = item["quantity"] * item["unit_amount_minor"]
        if line_total > MAX_MINOR:
            raise ValueError("line total exceeds the safe integer range")
        subtotal += line_total
        if subtotal > MAX_MINOR:
            raise ValueError("invoice total exceeds the safe integer range")
    total = subtotal
    return subtotal, total


async def insert_with_random_id(session: AsyncSession, table, values: dict) -> int:
    """Retry only a primary-key collision; other uniqueness rules remain errors."""
    for _ in range(8):
        candidate = new_id()
        result = await session.execute(
            insert(table)
            .values(id=candidate, **values)
            .on_conflict_do_nothing(index_elements=[table.c.id])
            .returning(table.c.id)
        )
        inserted = result.scalar_one_or_none()
        if inserted is not None:
            return int(inserted)
    raise RuntimeError("Could not allocate a unique billing ID")


async def append_audit(
    session: AsyncSession,
    request,
    *,
    action: str,
    actor_user_id: str,
    resource_id: int,
    result: str = "success",
    amount_minor: int | None = None,
    currency: str | None = None,
    item_count: int | None = None,
) -> None:
    metadata = {
        "action": action,
        "result": result,
        "actor_user_id": actor_user_id,
        "resource_id": str(resource_id),
        "request_id": str(request.state.request_id),
        "correlation_id": str(request.state.correlation_id),
        "occurred_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if amount_minor is not None:
        metadata["amount_minor"] = amount_minor
    if currency is not None:
        metadata["currency"] = currency
    if item_count is not None:
        metadata["item_count"] = item_count
    await session.execute(
        text("SELECT public.billing_append_audit(:entry_id, CAST(:metadata AS jsonb))"),
        {"entry_id": new_id(), "metadata": json.dumps(metadata)},
    )


async def append_outbox(
    session: AsyncSession,
    request,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: int,
    aggregate_version: int,
    payload: dict,
) -> int:
    occurred_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for _ in range(8):
        event_id = new_id()
        envelope = {
            "event_id": str(event_id),
            "event_type": event_type,
            "schema_version": 1,
            "producer": "billing",
            "occurred_at": occurred_at,
            "aggregate_type": aggregate_type,
            "aggregate_id": str(aggregate_id),
            "aggregate_version": aggregate_version,
            "correlation_id": str(request.state.correlation_id),
            "request_id": str(request.state.request_id),
            "causation_id": None,
            "traceparent": request.state.traceparent,
            "payload": payload,
        }
        result = await session.execute(
            insert(outbox_events)
            .values(
                event_id=event_id,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                aggregate_version=aggregate_version,
                event_type=event_type,
                envelope=envelope,
            )
            .on_conflict_do_nothing(index_elements=[outbox_events.c.event_id])
            .returning(outbox_events.c.event_id)
        )
        inserted = result.scalar_one_or_none()
        if inserted is not None:
            return int(inserted)
    raise RuntimeError("Could not allocate a unique billing event ID")


async def invoice_event_payload(session: AsyncSession, invoice) -> dict:
    source_rows = (
        await session.execute(
            select(invoice_items.c.source_service, invoice_items.c.source_item_id)
            .where(invoice_items.c.invoice_id == invoice["id"])
            .order_by(invoice_items.c.source_service, invoice_items.c.source_item_id)
        )
    ).all()
    total = int(invoice["total_minor"])
    paid = int(invoice["paid_minor"])
    return {
        "invoice_id": str(invoice["id"]),
        "journey_id": None,
        "patient_id": str(invoice["patient_id"]),
        "currency": invoice["currency"],
        "total_minor": total,
        "paid_minor": paid,
        "balance_minor": total - paid,
        "state": invoice["status"],
        "charge_source_keys": [
            {"source_service": row.source_service, "source_item_id": str(row.source_item_id)}
            for row in source_rows
        ],
    }
