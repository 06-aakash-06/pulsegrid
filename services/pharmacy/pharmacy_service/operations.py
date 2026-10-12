"""PostgreSQL command, audit, outbox, pagination, and snapshot helpers."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import and_, delete, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .integrations import PrescriptionContext
from .models import (
    audit_entries,
    dispensings,
    dispensing_items,
    idempotency_requests,
    inventory_batches,
    medicines,
    outbox_events,
    prescription_item_snapshots,
    prescription_snapshots,
    reservation_items,
    reservations,
    stock_movements,
)

MAX_ID = 9_223_372_036_854_775_807
MAX_VERSION = 9_007_199_254_740_991
GENESIS_HASH = "0" * 64


def fail(status: int, code: str) -> None:
    raise HTTPException(status, detail={"code": code})


def iso_time(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def normalize_search(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().casefold()
    if not 2 <= len(normalized) <= 100:
        fail(422, "validation_error")
    return normalized


def reject_unknown_query(request: Request, allowed: set[str]) -> None:
    if set(request.query_params.keys()) - allowed:
        fail(422, "validation_error")


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _filter_hash(filters: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(filters)).hexdigest()


def encode_cursor(created_at: datetime, resource_id: int | str, filters: dict[str, Any]) -> str:
    raw = _canonical(
        {
            "created_at": iso_time(created_at),
            "id": str(resource_id),
            "filter_hash": _filter_hash(filters),
        }
    )
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str | None, filters: dict[str, Any]):
    if cursor is None:
        return None
    try:
        if len(cursor) > 2048 or not cursor.isascii():
            raise ValueError
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.b64decode(padded, altchars=b"-_", validate=True)
        payload = json.loads(raw)
        if not isinstance(payload, dict) or set(payload) != {
            "created_at",
            "id",
            "filter_hash",
        }:
            raise ValueError
        if payload["filter_hash"] != _filter_hash(filters):
            raise ValueError
        if (
            not isinstance(payload["id"], str)
            or not payload["id"].isascii()
            or not payload["id"].isdigit()
            or payload["id"].startswith("0")
            or int(payload["id"]) > MAX_ID
        ):
            raise ValueError
        timestamp = payload["created_at"]
        if (
            not isinstance(timestamp, str)
            or "T" not in timestamp
            or not (timestamp.endswith("Z") or timestamp.endswith("+00:00"))
        ):
            raise ValueError
        created_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if created_at.tzinfo is None or created_at.utcoffset() != timedelta(0):
            raise ValueError
        return created_at.astimezone(timezone.utc), int(payload["id"])
    except (ValueError, TypeError, KeyError, AttributeError, binascii.Error):
        fail(400, "bad_request")


def page_statement(statement, *, cursor: str | None, filters: dict[str, Any], limit: int, created_column, id_column):
    position = decode_cursor(cursor, filters)
    if position is not None:
        created_at, resource_id = position
        statement = statement.where(
            or_(created_column > created_at, and_(created_column == created_at, id_column > resource_id))
        )
    return statement.order_by(created_column.asc(), id_column.asc()).limit(limit + 1)


def make_page(rows: list[Any], *, limit: int, filters: dict[str, Any], created_getter, id_getter, serializer):
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    next_cursor = None
    if has_more and page_rows:
        last = page_rows[-1]
        next_cursor = encode_cursor(created_getter(last), id_getter(last), filters)
    return {"items": [serializer(row) for row in page_rows], "next_cursor": next_cursor}


def medicine_json(row, availability: bool) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "sku": row["sku"],
        "name": row["name"],
        "active": row["active"],
        "availability": "available" if availability else "unavailable",
        "catalog_version": row["catalog_version"],
        "version": row["version"],
    }


def batch_json(row, *, fulfillment_view: bool = False) -> dict[str, Any]:
    available = row["on_hand"] - row["reserved"]
    if fulfillment_view and row["expires_on"] <= datetime.now(timezone.utc).date():
        available = 0
    return {
        "id": str(row["id"]),
        "medicine_id": str(row["medicine_id"]),
        "batch_code": row["batch_code"],
        "expires_on": row["expires_on"].isoformat(),
        "on_hand": row["on_hand"],
        "reserved": row["reserved"],
        "available": available,
        "version": row["version"],
    }


def reservation_json(row, item_rows) -> dict[str, Any]:
    quantities: dict[int, tuple[int, int]] = {}
    for line, allowance in item_rows:
        quantity, medicine_id = quantities.get(
            line["item_id"], (0, allowance["medicine_id"])
        )
        quantities[line["item_id"]] = (quantity + line["quantity"], medicine_id)
    return {
        "id": str(row["id"]),
        "patient_id": str(row["patient_id"]),
        "prescription_id": str(row["prescription_id"]),
        "state": row["state"],
        "items": [
            {
                "prescription_item_id": str(item_id),
                "medicine_id": str(medicine_id),
                "quantity": quantity,
            }
            for item_id, (quantity, medicine_id) in sorted(quantities.items())
        ],
        "expires_at": iso_time(row["expires_at"]),
        "version": row["version"],
    }


def dispensing_json(dispensing, reservation, snapshot, item_rows) -> dict[str, Any]:
    return {
        "id": str(dispensing["id"]),
        "reservation_id": str(dispensing["reservation_id"]),
        "prescription_id": str(reservation["prescription_id"]),
        "patient_id": str(reservation["patient_id"]),
        "appointment_id": str(snapshot["appointment_id"]),
        "items": [
            {
                "id": str(line["id"]),
                "prescription_item_id": str(line["item_id"]),
                "medicine_id": str(allowance["medicine_id"]),
                "quantity": line["quantity"],
            }
            for line, allowance in sorted(item_rows, key=lambda pair: pair[0]["id"])
        ],
        "completed_at": iso_time(dispensing["completed_at"]),
        "version": dispensing["version"],
    }


def new_id() -> int:
    return secrets.randbelow(MAX_ID) + 1


async def allocate_id(session: AsyncSession, column) -> int:
    """Choose a positive signed BIGINT and retry existing-key collisions three times."""
    for _attempt in range(3):
        candidate = new_id()
        existing = await session.scalar(select(column).where(column == candidate))
        if existing is None:
            return candidate
    fail(503, "dependency_unavailable")


def _signed_advisory_key(scope: str) -> int:
    value = int.from_bytes(hashlib.blake2b(scope.encode("utf-8"), digest_size=8).digest(), "big")
    return value if value < 2**63 else value - 2**64


def validate_idempotency_key(value: str | None) -> str:
    if (
        value is None
        or not 16 <= len(value) <= 128
        or not value.isascii()
        or any(ord(char) < 33 or ord(char) > 126 for char in value)
    ):
        fail(400, "bad_request")
    return value


@dataclass(frozen=True)
class CommandResult:
    status_code: int
    body: Any
    etag: str | None


def response_for(result: CommandResult, *, no_store: bool = False) -> JSONResponse:
    headers = {}
    if result.etag is not None:
        headers["ETag"] = result.etag
    if no_store:
        headers["Cache-Control"] = "no-store"
    if result.status_code == 204:
        return Response(status_code=204, headers=headers)
    return JSONResponse(status_code=result.status_code, content=result.body, headers=headers)


def _command_identity(request: Request, principal, route_template: str, body: Any, if_match: str | None):
    route_identity = route_template + "|" + request.url.path
    fingerprint = hashlib.sha256(
        _canonical(
            {
                "path": request.url.path,
                "body": body,
                "if_match": if_match,
            }
        )
    ).hexdigest()
    return principal.user_id, route_identity, fingerprint


async def _lock_idempotency(session: AsyncSession, scope: str, method: str, route: str, key: str):
    lock_name = "|".join((scope, method, route, key))
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": _signed_advisory_key(lock_name)},
    )


async def _cached_command(session: AsyncSession, principal_scope: str, method: str, route: str, key: str, fingerprint: str):
    existing = (
        await session.execute(
            select(idempotency_requests).where(
                idempotency_requests.c.principal_scope == principal_scope,
                idempotency_requests.c.method == method,
                idempotency_requests.c.route_template == route,
                idempotency_requests.c.key == key,
            )
        )
    ).mappings().first()
    if existing is None:
        return None
    if existing["expires_at"] <= datetime.now(timezone.utc):
        await session.execute(
            delete(idempotency_requests).where(
                idempotency_requests.c.principal_scope == principal_scope,
                idempotency_requests.c.method == method,
                idempotency_requests.c.route_template == route,
                idempotency_requests.c.key == key,
            )
        )
        return None
    if existing["request_hash"] != fingerprint:
        fail(409, "idempotency_key_reused")
    stored = existing["response"]
    return CommandResult(
        existing["response_code"], stored.get("body"), stored.get("etag")
    )


async def lookup_command_replay(
    session: AsyncSession,
    request: Request,
    principal,
    *,
    route_template: str,
    key: str,
    body: Any,
    if_match: str | None = None,
) -> CommandResult | None:
    key = validate_idempotency_key(key)
    scope, route, fingerprint = _command_identity(
        request, principal, route_template, body, if_match
    )
    async with session.begin():
        await _lock_idempotency(session, f"user:{scope}", "POST", route, key)
        return await _cached_command(session, f"user:{scope}", "POST", route, key, fingerprint)


async def execute_command(
    session: AsyncSession,
    request: Request,
    principal,
    *,
    route_template: str,
    key: str,
    body: Any,
    operation: Callable[[], Awaitable[CommandResult]],
    if_match: str | None = None,
) -> CommandResult:
    key = validate_idempotency_key(key)
    scope, route, fingerprint = _command_identity(
        request, principal, route_template, body, if_match
    )
    async with session.begin():
        await _lock_idempotency(session, f"user:{scope}", "POST", route, key)
        replay = await _cached_command(
            session, f"user:{scope}", "POST", route, key, fingerprint
        )
        if replay is not None:
            return replay
        result = await operation()
        await session.execute(
            idempotency_requests.insert().values(
                principal_scope=f"user:{scope}",
                method="POST",
                route_template=route,
                key=key,
                request_hash=fingerprint,
                response_code=result.status_code,
                response={"body": result.body, "etag": result.etag},
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            )
        )
        return result


def parse_if_match(value: str | None) -> int:
    if value is None:
        fail(428, "precondition_required")
    if len(value) < 3 or value[0] != '"' or value[-1] != '"':
        fail(400, "bad_request")
    raw = value[1:-1]
    if not raw.isascii() or not raw.isdigit() or raw.startswith("0"):
        fail(400, "bad_request")
    version = int(raw)
    if not 1 <= version <= MAX_VERSION:
        fail(400, "bad_request")
    return version


def etag(version: int) -> str:
    return f'"{version}"'


async def _locked_audit_head(session: AsyncSession) -> tuple[int, str]:
    head = (
        await session.execute(text("SELECT * FROM public.pharmacy_lock_audit_head()"))
    ).first()
    if head is None:
        fail(503, "dependency_unavailable")
    return head.last_sequence, head.last_hash


async def append_audit(
    session: AsyncSession,
    request: Request,
    *,
    actor_user_id: str,
    action: str,
    resource_type: str,
    resource_id: int | str,
    result: str = "success",
    content_digest: str | None = None,
    action_kind: str | None = None,
) -> None:
    previous_sequence, previous_hash = await _locked_audit_head(session)
    sequence = previous_sequence + 1
    occurred_at = iso_time(datetime.now(timezone.utc))
    metadata = {
        "chain_id": "pharmacy",
        "sequence": sequence,
        "actor_user_id": actor_user_id,
        "service": "pharmacy",
        "action": action,
        "action_kind": action_kind or "mutation",
        "resource_type": resource_type,
        "resource_id": str(resource_id),
        "result": result,
        "occurred_at": occurred_at,
        "request_id": str(request.state.request_id),
        "correlation_id": str(request.state.correlation_id),
        "content_digest": content_digest,
    }
    entry_hash = hashlib.sha256(previous_hash.encode("ascii") + _canonical(metadata)).hexdigest()
    await session.execute(
        text(
            "SELECT public.pharmacy_append_audit(:entry_id, :sequence, :prev_hash, :entry_hash, CAST(:metadata AS JSONB))"
        ),
        {
            "entry_id": await allocate_id(session, audit_entries.c.entry_id),
            "sequence": sequence,
            "prev_hash": previous_hash,
            "entry_hash": entry_hash,
            "metadata": json.dumps(metadata, separators=(",", ":"), ensure_ascii=False),
        },
    )


async def append_outbox(
    session: AsyncSession,
    request: Request,
    *,
    aggregate_type: str,
    aggregate_id: int,
    aggregate_version: int,
    action: str,
    state: str | None = None,
    event_payload: dict | None = None,
) -> None:
    event_id = await allocate_id(session, outbox_events.c.event_id)
    event_type = f"pharmacy.{action}.v1"
    payload = {"resource_id": str(aggregate_id), "version": aggregate_version}
    if state is not None:
        payload["state"] = state
    if event_payload is not None:
        payload.update(event_payload)
    envelope = {
        "event_id": str(event_id),
        "event_type": event_type,
        "schema_version": 1,
        "producer": "pharmacy",
        "occurred_at": iso_time(datetime.now(timezone.utc)),
        "aggregate_type": aggregate_type,
        "aggregate_id": str(aggregate_id),
        "aggregate_version": aggregate_version,
        "correlation_id": str(request.state.correlation_id),
        "request_id": str(request.state.request_id),
        "causation_id": None,
        "traceparent": getattr(request.state, "traceparent", None),
        "payload": payload,
    }
    await session.execute(
        outbox_events.insert().values(
            event_id=event_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            aggregate_version=aggregate_version,
            event_type=event_type,
            envelope=envelope,
            published_at=None,
            attempt_count=0,
            next_attempt_at=datetime.now(timezone.utc),
            claimed_by=None,
            lease_expires_at=None,
        )
    )


async def append_mutation_records(
    session: AsyncSession,
    request: Request,
    *,
    principal,
    action: str,
    resource_type: str,
    resource_id: int,
    aggregate_version: int,
    state: str | None = None,
    content_digest: str | None = None,
    event_payload: dict | None = None,
) -> None:
    await append_audit(
        session,
        request,
        actor_user_id=principal.user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        content_digest=content_digest,
    )
    await append_outbox(
        session,
        request,
        aggregate_type=resource_type,
        aggregate_id=resource_id,
        aggregate_version=aggregate_version,
        action=action,
        state=state,
        event_payload=event_payload,
    )


async def append_sensitive_read(
    session: AsyncSession,
    request: Request,
    *,
    principal,
    action: str,
    resource_type: str,
    resource_id: int,
    result: str = "success",
) -> None:
    await append_audit(
        session,
        request,
        actor_user_id=principal.user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        result=result,
        action_kind="read",
    )


async def sync_prescription_snapshot(
    session: AsyncSession, context: PrescriptionContext
):
    medicine_ids = sorted({int(item.medicine_id) for item in context.items})
    if medicine_ids:
        known_medicines = set(
            (
                await session.execute(
                    select(medicines.c.id).where(medicines.c.id.in_(medicine_ids))
                )
            ).scalars()
        )
        if known_medicines != set(medicine_ids):
            fail(422, "invalid_reference")

    await session.execute(
        pg_insert(prescription_snapshots)
        .values(
            prescription_id=int(context.prescription_id),
            patient_id=int(context.patient_id),
            journey_id=context.journey_id,
            consultation_id=int(context.consultation_id),
            appointment_id=int(context.appointment_id),
            revision=context.revision,
            state=context.state,
            source_version=context.version,
            version=1,
        )
        .on_conflict_do_nothing(index_elements=[prescription_snapshots.c.prescription_id])
    )
    snapshot = (
        await session.execute(
            select(prescription_snapshots)
            .where(prescription_snapshots.c.prescription_id == int(context.prescription_id))
            .with_for_update()
        )
    ).mappings().first()
    if snapshot is None:
        fail(503, "dependency_unavailable")
    if (
        snapshot["patient_id"] != int(context.patient_id)
        or (snapshot["consultation_id"] is not None and snapshot["consultation_id"] != int(context.consultation_id))
        or (snapshot["appointment_id"] is not None and snapshot["appointment_id"] != int(context.appointment_id))
    ):
        fail(409, "prescription_snapshot_conflict")
    if (
        snapshot["source_version"] > context.version
        or (snapshot["state"] == "revoked" and context.state == "issued")
        or (
            snapshot["source_version"] == context.version
            and (
                snapshot["revision"] != context.revision
                or snapshot["state"] != context.state
            )
        )
    ):
        fail(409, "prescription_snapshot_conflict")

    item_rows = list(
        (
            await session.execute(
                select(prescription_item_snapshots)
                .where(
                    prescription_item_snapshots.c.prescription_id
                    == int(context.prescription_id)
                )
                .order_by(prescription_item_snapshots.c.item_id.asc())
                .with_for_update()
            )
        ).mappings()
    )
    remote_items = {int(item.item_id): item for item in context.items}
    local_items = {row["item_id"]: row for row in item_rows}
    if item_rows and set(local_items) != set(remote_items):
        fail(409, "prescription_snapshot_conflict")
    if item_rows:
        if snapshot["revision"] != context.revision:
            fail(409, "prescription_snapshot_conflict")
        for item_id, remote in remote_items.items():
            local = local_items[item_id]
            if (
                local["medicine_id"] != int(remote.medicine_id)
                or local["prescribed_quantity"] != remote.quantity
            ):
                fail(409, "prescription_snapshot_conflict")
    else:
        for item_id, remote in sorted(remote_items.items()):
            await session.execute(
                prescription_item_snapshots.insert().values(
                    item_id=item_id,
                    prescription_id=int(context.prescription_id),
                    medicine_id=int(remote.medicine_id),
                    prescribed_quantity=remote.quantity,
                    reserved_quantity=0,
                    dispensed_quantity=0,
                    version=1,
                )
            )
        item_rows = list(
            (
                await session.execute(
                    select(prescription_item_snapshots)
                    .where(
                        prescription_item_snapshots.c.prescription_id
                        == int(context.prescription_id)
                    )
                    .order_by(prescription_item_snapshots.c.item_id.asc())
                    .with_for_update()
                )
            ).mappings()
        )

    changed = any(
        (
            snapshot[field] != new_value
            for field, new_value in (
                ("journey_id", context.journey_id),
                ("consultation_id", int(context.consultation_id)),
                ("appointment_id", int(context.appointment_id)),
                ("revision", context.revision),
                ("state", context.state),
                ("source_version", context.version),
            )
        )
    )
    if changed:
        await session.execute(
            update(prescription_snapshots)
            .where(prescription_snapshots.c.prescription_id == int(context.prescription_id))
            .values(
                journey_id=context.journey_id,
                consultation_id=int(context.consultation_id),
                appointment_id=int(context.appointment_id),
                revision=context.revision,
                state=context.state,
                source_version=context.version,
                version=prescription_snapshots.c.version + 1,
                updated_at=datetime.now(timezone.utc),
            )
        )
        snapshot = dict(snapshot)
        snapshot.update(
            {
                "journey_id": context.journey_id,
                "consultation_id": int(context.consultation_id),
                "appointment_id": int(context.appointment_id),
                "revision": context.revision,
                "state": context.state,
                "source_version": context.version,
                "version": snapshot["version"] + 1,
            }
        )
    return snapshot, {row["item_id"]: row for row in item_rows}


async def lock_reservation_aggregate(session: AsyncSession, reservation_id: int):
    preliminary = (
        await session.execute(
            select(reservations.c.prescription_id).where(reservations.c.id == reservation_id)
        )
    ).scalar_one_or_none()
    if preliminary is None:
        return None
    snapshot = (
        await session.execute(
            select(prescription_snapshots)
            .where(prescription_snapshots.c.prescription_id == preliminary)
            .with_for_update()
        )
    ).mappings().first()
    if snapshot is None:
        fail(503, "dependency_unavailable")
    allowances = list(
        (
            await session.execute(
                select(prescription_item_snapshots)
                .where(prescription_item_snapshots.c.prescription_id == preliminary)
                .order_by(prescription_item_snapshots.c.item_id.asc())
                .with_for_update()
            )
        ).mappings()
    )
    locked_reservations = list(
        (
            await session.execute(
                select(reservations)
                .where(reservations.c.prescription_id == preliminary)
                .order_by(reservations.c.id.asc())
                .with_for_update()
            )
        ).mappings()
    )
    reservation = next(
        (row for row in locked_reservations if row["id"] == reservation_id), None
    )
    if reservation is None:
        return None
    lines = list(
        (
            await session.execute(
                select(reservation_items)
                .where(reservation_items.c.reservation_id == reservation_id)
                .order_by(reservation_items.c.id.asc())
            )
        ).mappings()
    )
    batch_ids = sorted({line["batch_id"] for line in lines})
    batches = {}
    if batch_ids:
        rows = list(
            (
                await session.execute(
                    select(inventory_batches)
                    .where(inventory_batches.c.id.in_(batch_ids))
                    .order_by(inventory_batches.c.id.asc())
                    .with_for_update()
                )
            ).mappings()
        )
        batches = {row["id"]: row for row in rows}
    allowance_map = {row["item_id"]: row for row in allowances}
    return snapshot, allowance_map, reservation, lines, batches


async def release_locked_reservation(
    session: AsyncSession,
    request: Request,
    principal,
    locked,
    *,
    next_state: str,
) -> CommandResult | None:
    if locked is None:
        return None
    snapshot, allowance_map, reservation, lines, batches = locked
    if reservation["state"] != "reserved":
        return None
    by_item: dict[int, int] = {}
    for line in lines:
        by_item[line["item_id"]] = by_item.get(line["item_id"], 0) + line["quantity"]
    for batch_id in sorted({line["batch_id"] for line in lines}):
        batch = batches.get(batch_id)
        quantity = sum(
            line["quantity"] for line in lines if line["batch_id"] == batch_id
        )
        if batch is None or batch["reserved"] < quantity:
            fail(503, "dependency_unavailable")
        await session.execute(
            update(inventory_batches)
            .where(inventory_batches.c.id == batch_id)
            .values(
                reserved=inventory_batches.c.reserved - quantity,
                version=inventory_batches.c.version + 1,
                updated_at=datetime.now(timezone.utc),
            )
        )
    for item_id, quantity in sorted(by_item.items()):
        allowance = allowance_map.get(item_id)
        if allowance is None or allowance["reserved_quantity"] < quantity:
            fail(503, "dependency_unavailable")
        await session.execute(
            update(prescription_item_snapshots)
            .where(prescription_item_snapshots.c.item_id == item_id)
            .values(
                reserved_quantity=prescription_item_snapshots.c.reserved_quantity - quantity,
                version=prescription_item_snapshots.c.version + 1,
                updated_at=datetime.now(timezone.utc),
            )
        )
    new_version = reservation["version"] + 1
    await session.execute(
        update(reservations)
        .where(reservations.c.id == reservation["id"])
        .values(
            state=next_state,
            version=new_version,
            updated_at=datetime.now(timezone.utc),
        )
    )
    action = "reservation.expired" if next_state == "expired" else "reservation.released"
    await append_mutation_records(
        session,
        request,
        principal=principal,
        action=action,
        resource_type="reservation",
        resource_id=reservation["id"],
        aggregate_version=new_version,
        state=next_state,
    )
    updated = dict(reservation)
    updated.update({"state": next_state, "version": new_version})
    allowance_rows = {
        row["item_id"]: row for row in allowance_map.values()
    }
    item_rows = [
        (line, allowance_rows[line["item_id"]])
        for line in lines
        if line["item_id"] in allowance_rows
    ]
    return CommandResult(
        200,
        reservation_json(updated, item_rows),
        f'"{new_version}"',
    )


async def expire_reservations(
    session: AsyncSession,
    request: Request,
    principal,
    *,
    medicine_id: int | None = None,
    prescription_id: int | None = None,
    reservation_id: int | None = None,
) -> None:
    """Release relevant expired holds in their own local transactions."""
    conditions = [
        reservations.c.state == "reserved",
        reservations.c.expires_at <= datetime.now(timezone.utc),
    ]
    statement = select(reservations.c.id)
    if medicine_id is not None:
        statement = statement.select_from(
            reservations.join(
                reservation_items,
                reservation_items.c.reservation_id == reservations.c.id,
            ).join(
                inventory_batches,
                inventory_batches.c.id == reservation_items.c.batch_id,
            )
        ).where(inventory_batches.c.medicine_id == medicine_id)
    if prescription_id is not None:
        conditions.append(reservations.c.prescription_id == prescription_id)
    if reservation_id is not None:
        conditions.append(reservations.c.id == reservation_id)
    statement = statement.where(*conditions).distinct().order_by(reservations.c.id.asc())
    async with session.begin():
        candidates = list((await session.execute(statement)).scalars())
    for candidate_id in candidates:
        async with session.begin():
            locked = await lock_reservation_aggregate(session, candidate_id)
            if locked is None:
                continue
            reservation = locked[2]
            if (
                reservation["state"] == "reserved"
                and reservation["expires_at"] <= datetime.now(timezone.utc)
            ):
                await release_locked_reservation(
                    session,
                    request,
                    principal,
                    locked,
                    next_state="expired",
                )


def constraint_name(error: IntegrityError) -> str | None:
    original = getattr(error, "orig", None)
    diagnostic = getattr(original, "diag", None)
    return getattr(diagnostic, "constraint_name", None)
