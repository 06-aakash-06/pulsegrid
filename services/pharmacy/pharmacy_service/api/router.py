"""Frozen Phase 2 public and private Pharmacy routes."""

from __future__ import annotations

import hashlib
import base64
import json
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, Path, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import and_, exists, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..authorization import (
    Principal,
    authenticated_user,
    check_current_authority,
    delegated_user,
    require_current_role,
    require_one_current_role,
    require_service,
)
from ..constants import API_PREFIX
from ..database import get_database_session
from ..integrations import get_prescription_context
from ..models import (
    dispensings,
    dispensing_items,
    inventory_batches,
    pharmacy_episode_revisions,
    medicines,
    prescription_item_snapshots,
    prescription_snapshots,
    reservation_items,
    reservations,
    stock_movements,
)
from ..operations import (
    CommandResult,
    allocate_id,
    append_mutation_records,
    append_sensitive_read,
    append_audit,
    batch_json,
    constraint_name,
    dispensing_json,
    encode_cursor,
    etag,
    execute_command,
    expire_reservations,
    fail,
    iso_time,
    lookup_command_replay,
    lock_reservation_aggregate,
    make_page,
    medicine_json,
    normalize_search,
    page_statement,
    parse_if_match,
    reject_unknown_query,
    release_locked_reservation,
    reservation_json,
    response_for,
    sync_prescription_snapshot,
)
from ..schemas import (
    EmptyCommand,
    MedicineCreate,
    MedicinePatch,
    MedicineValidation,
    ReservationCreate,
    StockAdjustment,
)

api_router = APIRouter(prefix=API_PREFIX)
internal_router = APIRouter(prefix="/internal/v1")


def _path_id():
    return Path(pattern=r"^[1-9][0-9]{0,18}$", max_length=19)


def _require_numeric_id(value: str) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        fail(422, "validation_error")
    if not value.isascii() or not value.isdigit() or value.startswith("0") or numeric > 9_223_372_036_854_775_807:
        fail(422, "validation_error")
    return numeric


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


async def _fulfillment(session: AsyncSession, snapshot):
    prescription_id = snapshot["prescription_id"]
    item_rows = list((await session.execute(
        select(prescription_item_snapshots).where(
            prescription_item_snapshots.c.prescription_id == prescription_id
        ).order_by(prescription_item_snapshots.c.item_id)
    )).mappings())
    reservation_rows = list((await session.execute(
        select(reservations).where(reservations.c.prescription_id == prescription_id)
        .order_by(reservations.c.id)
    )).mappings())
    reservation_ids = [row["id"] for row in reservation_rows]
    dispensing_rows = list((await session.execute(
        select(dispensings).where(dispensings.c.reservation_id.in_(reservation_ids))
        .order_by(dispensings.c.id)
    )).mappings()) if reservation_ids else []
    dispensing_ids = [row["id"] for row in dispensing_rows]
    source_rows = list((await session.execute(
        select(dispensing_items.c.dispensing_id, dispensing_items.c.id)
        .where(dispensing_items.c.dispensing_id.in_(dispensing_ids))
        .order_by(dispensing_items.c.id)
    )).mappings()) if dispensing_ids else []
    sources = {row["id"]: [] for row in dispensing_rows}
    for row in source_rows:
        sources[row["dispensing_id"]].append(str(row["id"]))
    items = [dict(
        prescription_item_id=str(row["item_id"]), medicine_id=str(row["medicine_id"]),
        prescribed_quantity=row["prescribed_quantity"],
        reserved_quantity=row["reserved_quantity"],
        dispensed_quantity=row["dispensed_quantity"],
        remaining_quantity=row["prescribed_quantity"] - row["dispensed_quantity"],
    ) for row in item_rows]
    return dict(
        prescription_id=str(prescription_id), appointment_id=str(snapshot["appointment_id"]),
        patient_id=str(snapshot["patient_id"]), prescription_revision=snapshot["revision"],
        prescription_state=snapshot["state"], items=items,
        reservations=[dict(id=str(row["id"]), state=row["state"], version=row["version"])
                      for row in reservation_rows],
        dispensings=[dict(id=str(row["id"]), version=row["version"],
                          source_item_ids=sources[row["id"]]) for row in dispensing_rows],
        review_required=snapshot["state"] == "revoked" and any(
            row["dispensed_quantity"] > 0 for row in item_rows
        ),
        version=snapshot["version"], observed_at=iso_time(datetime.now(timezone.utc)),
    )


async def _medicine_availability(session: AsyncSession, medicine_id: int) -> bool:
    return bool(
        await session.scalar(
            select(
                exists(
                    select(inventory_batches.c.id).where(
                        inventory_batches.c.medicine_id == medicine_id,
                        inventory_batches.c.expires_on > _utc_today(),
                        inventory_batches.c.on_hand > inventory_batches.c.reserved,
                    )
                )
            )
        )
    )


async def _medicine_with_availability(session: AsyncSession, row):
    return medicine_json(row, await _medicine_availability(session, row["id"]))


async def _reservation_lines(session: AsyncSession, reservation_ids: list[int]):
    if not reservation_ids:
        return {}
    rows = list(
        (
            await session.execute(
                select(
                    reservation_items.c.reservation_id,
                    reservation_items.c.item_id,
                    reservation_items.c.quantity,
                    prescription_item_snapshots.c.medicine_id,
                )
                .join(
                    prescription_item_snapshots,
                    prescription_item_snapshots.c.item_id == reservation_items.c.item_id,
                )
                .where(reservation_items.c.reservation_id.in_(reservation_ids))
                .order_by(reservation_items.c.reservation_id, reservation_items.c.id)
            )
        ).mappings()
    )
    grouped = {reservation_id: [] for reservation_id in reservation_ids}
    for row in rows:
        line = {
            "item_id": row["item_id"],
            "quantity": row["quantity"],
        }
        allowance = {"medicine_id": row["medicine_id"]}
        grouped[row["reservation_id"]].append((line, allowance))
    return grouped


async def _reservation_full(session: AsyncSession, reservation_id: int):
    row = (
        await session.execute(
            select(reservations).where(reservations.c.id == reservation_id)
        )
    ).mappings().first()
    if row is None:
        return None
    grouped = await _reservation_lines(session, [reservation_id])
    return row, reservation_json(row, grouped[reservation_id])


async def _dispensing_full(session: AsyncSession, dispensing_id: int):
    row = (
        await session.execute(
            select(dispensings).where(dispensings.c.id == dispensing_id)
        )
    ).mappings().first()
    if row is None:
        return None
    reservation = (
        await session.execute(
            select(reservations).where(reservations.c.id == row["reservation_id"])
        )
    ).mappings().first()
    if reservation is None:
        fail(503, "dependency_unavailable")
    snapshot = (
        await session.execute(
            select(prescription_snapshots).where(
                prescription_snapshots.c.prescription_id
                == reservation["prescription_id"]
            )
        )
    ).mappings().first()
    if snapshot is None:
        fail(503, "dependency_unavailable")
    items = list(
        (
            await session.execute(
                select(
                    dispensing_items.c.id,
                    reservation_items.c.item_id,
                    dispensing_items.c.quantity,
                    prescription_item_snapshots.c.medicine_id,
                )
                .join(
                    reservation_items,
                    reservation_items.c.id == dispensing_items.c.reservation_item_id,
                )
                .join(
                    prescription_item_snapshots,
                    prescription_item_snapshots.c.item_id == reservation_items.c.item_id,
                )
                .where(dispensing_items.c.dispensing_id == dispensing_id)
                .order_by(dispensing_items.c.id.asc())
            )
        ).mappings()
    )
    line_pairs = []
    for item in items:
        line_pairs.append(
            (
                {
                    "id": item["id"],
                    "item_id": item["item_id"],
                    "quantity": item["quantity"],
                },
                {"medicine_id": item["medicine_id"]},
            )
        )
    return row, reservation, snapshot, dispensing_json(row, reservation, snapshot, line_pairs)


async def _authorize_pharmacy_resource(
    request: Request,
    principal: Principal,
    patient_id: int,
    *,
    resource_id: int,
    resource_type: str,
    action: str,
    session: AsyncSession,
) -> bool:
    role = getattr(request.state, "authorized_role", None)
    if role == "pharmacist":
        return True
    if role == "patient" and principal.patient_id is not None and int(principal.patient_id) == patient_id:
        return True
    await append_sensitive_read(
        session,
        request,
        principal=principal,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        result="denied",
    )
    return False


@api_router.get("/medicines")
async def list_medicines(
    request: Request,
    q: str | None = Query(default=None, max_length=100),
    active: bool = True,
    cursor: str | None = Query(default=None, max_length=2048),
    limit: int = Query(default=20, ge=1, le=100),
    principal: Principal = Depends(authenticated_user),
    session: AsyncSession = Depends(get_database_session),
):
    reject_unknown_query(request, {"q", "active", "cursor", "limit"})
    normalized_q = normalize_search(q)
    filters = {"q": normalized_q, "active": active}
    statement = select(medicines).where(medicines.c.active == active)
    if normalized_q is not None:
        escaped = normalized_q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        statement = statement.where(medicines.c.normalized_name.like(escaped + "%", escape="\\"))
    statement = page_statement(
        statement,
        cursor=cursor,
        filters=filters,
        limit=limit,
        created_column=medicines.c.created_at,
        id_column=medicines.c.id,
    )
    rows = list((await session.execute(statement)).mappings())
    page_rows = rows[:limit]
    available_ids = set()
    if page_rows:
        available_ids = set(
            (
                await session.execute(
                    select(inventory_batches.c.medicine_id)
                    .where(
                        inventory_batches.c.medicine_id.in_([row["id"] for row in page_rows]),
                        inventory_batches.c.expires_on > _utc_today(),
                        inventory_batches.c.on_hand > inventory_batches.c.reserved,
                    )
                    .group_by(inventory_batches.c.medicine_id)
                )
            ).scalars()
        )
    page = make_page(
        rows,
        limit=limit,
        filters=filters,
        created_getter=lambda row: row["created_at"],
        id_getter=lambda row: row["id"],
        serializer=lambda row: medicine_json(row, row["id"] in available_ids),
    )
    return JSONResponse(page)


@api_router.get("/medicines/{medicine_id}")
async def get_medicine(
    medicine_id: str = _path_id(),
    principal: Principal = Depends(authenticated_user),
    session: AsyncSession = Depends(get_database_session),
):
    numeric_id = _require_numeric_id(medicine_id)
    row = (
        await session.execute(
            select(medicines).where(medicines.c.id == numeric_id)
        )
    ).mappings().first()
    if row is None:
        fail(404, "not_found")
    body = await _medicine_with_availability(session, row)
    return JSONResponse(body, headers={"ETag": etag(row["version"])})


@api_router.post("/medicines", status_code=201)
async def create_medicine(
    payload: MedicineCreate,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: Principal = Depends(require_one_current_role("pharmacist", "hospital_admin")),
    session: AsyncSession = Depends(get_database_session),
):
    body = payload.model_dump(mode="json")
    replay = await lookup_command_replay(
        session,
        request,
        principal,
        route_template="/api/v1/pharmacy/medicines",
        key=idempotency_key,
        body=body,
    )
    if replay is not None:
        return response_for(replay)

    async def operation():
        duplicate = await session.scalar(
            select(medicines.c.id).where(medicines.c.sku == payload.sku)
        )
        if duplicate is not None:
            fail(409, "duplicate_sku")
        medicine_id = await allocate_id(session, medicines.c.id)
        now = datetime.now(timezone.utc)
        await session.execute(
            medicines.insert().values(
                id=medicine_id,
                sku=payload.sku,
                name=payload.name,
                normalized_name=payload.name.casefold(),
                active=True,
                catalog_version=1,
                version=1,
                created_at=now,
                updated_at=now,
            )
        )
        row = (
            await session.execute(
                select(medicines).where(medicines.c.id == medicine_id)
            )
        ).mappings().one()
        await append_mutation_records(
            session,
            request,
            principal=principal,
            action="medicine.created",
            resource_type="medicine",
            resource_id=medicine_id,
            aggregate_version=1,
        )
        return CommandResult(201, medicine_json(row, False), etag(1))

    try:
        result = await execute_command(
            session,
            request,
            principal,
            route_template="/api/v1/pharmacy/medicines",
            key=idempotency_key,
            body=body,
            operation=operation,
        )
    except IntegrityError as error:
        if constraint_name(error) == "uq_medicines_sku":
            fail(409, "duplicate_sku")
        raise
    return response_for(result)


@api_router.patch("/medicines/{medicine_id}")
async def patch_medicine(
    payload: MedicinePatch,
    request: Request,
    medicine_id: str = _path_id(),
    if_match: str | None = Header(default=None, alias="If-Match"),
    principal: Principal = Depends(require_one_current_role("pharmacist", "hospital_admin")),
    session: AsyncSession = Depends(get_database_session),
):
    expected_version = parse_if_match(if_match)
    numeric_id = _require_numeric_id(medicine_id)
    changes = payload.model_dump(mode="json", exclude_unset=True)
    async with session.begin():
        row = (
            await session.execute(
                select(medicines)
                .where(medicines.c.id == numeric_id)
                .with_for_update()
            )
        ).mappings().first()
        if row is None:
            fail(404, "not_found")
        if row["version"] != expected_version:
            fail(412, "version_conflict")
        values = {
            "version": row["version"] + 1,
            "catalog_version": row["catalog_version"] + 1,
            "updated_at": datetime.now(timezone.utc),
        }
        if "name" in changes:
            values["name"] = changes["name"]
            values["normalized_name"] = changes["name"].casefold()
        if "active" in changes:
            values["active"] = changes["active"]
        await session.execute(
            update(medicines).where(medicines.c.id == numeric_id).values(**values)
        )
        updated = (
            await session.execute(
                select(medicines).where(medicines.c.id == numeric_id)
            )
        ).mappings().one()
        await append_mutation_records(
            session,
            request,
            principal=principal,
            action="medicine.updated",
            resource_type="medicine",
            resource_id=numeric_id,
            aggregate_version=updated["version"],
        )
        body = medicine_json(updated, await _medicine_availability(session, numeric_id))
    return JSONResponse(body, headers={"ETag": etag(updated["version"])})


@api_router.get("/inventory")
async def list_inventory(
    request: Request,
    medicine_id: str | None = Query(default=None, pattern=r"^[1-9][0-9]{0,18}$"),
    cursor: str | None = Query(default=None, max_length=2048),
    limit: int = Query(default=20, ge=1, le=100),
    principal: Principal = Depends(require_current_role("pharmacist")),
    session: AsyncSession = Depends(get_database_session),
):
    reject_unknown_query(request, {"medicine_id", "cursor", "limit"})
    numeric_medicine_id = _require_numeric_id(medicine_id) if medicine_id else None
    filters = {"medicine_id": medicine_id}
    statement = select(inventory_batches)
    if numeric_medicine_id is not None:
        statement = statement.where(inventory_batches.c.medicine_id == numeric_medicine_id)
    statement = page_statement(
        statement,
        cursor=cursor,
        filters=filters,
        limit=limit,
        created_column=inventory_batches.c.created_at,
        id_column=inventory_batches.c.id,
    )
    async with session.begin():
        rows = list((await session.execute(statement)).mappings())
        page = make_page(
            rows,
            limit=limit,
            filters=filters,
            created_getter=lambda row: row["created_at"],
            id_getter=lambda row: row["id"],
            serializer=lambda row: batch_json(row, fulfillment_view=True),
        )
        await append_sensitive_read(
            session,
            request,
            principal=principal,
            action="inventory.list",
            resource_type="inventory_collection",
            resource_id=int(principal.user_id),
        )
    return JSONResponse(page, headers={"Cache-Control": "no-store"})


@api_router.post("/inventory-adjustments", status_code=201)
async def adjust_inventory(
    payload: StockAdjustment,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: Principal = Depends(require_current_role("pharmacist")),
    session: AsyncSession = Depends(get_database_session),
):
    body = payload.model_dump(mode="json")
    replay = await lookup_command_replay(
        session,
        request,
        principal,
        route_template="/api/v1/pharmacy/inventory-adjustments",
        key=idempotency_key,
        body=body,
    )
    if replay is not None:
        return response_for(replay)
    medicine_id = int(payload.medicine_id)
    await expire_reservations(
        session, request, principal, medicine_id=medicine_id
    )

    async def operation():
        medicine_exists = await session.scalar(
            select(medicines.c.id).where(medicines.c.id == medicine_id)
        )
        if medicine_exists is None:
            fail(404, "not_found")
        expires_on = date.fromisoformat(payload.expires_on)
        if payload.expected_batch_version == 0 and expires_on < _utc_today():
            fail(422, "validation_error")
        existing = (
            await session.execute(
                select(inventory_batches)
                .where(
                    inventory_batches.c.medicine_id == medicine_id,
                    inventory_batches.c.batch_code == payload.batch_code,
                )
                .with_for_update()
            )
        ).mappings().first()
        now = datetime.now(timezone.utc)
        if payload.expected_batch_version == 0:
            if existing is not None:
                fail(412, "version_conflict")
            if payload.delta <= 0:
                fail(409, "insufficient_inventory")
            batch_id = await allocate_id(session, inventory_batches.c.id)
            await session.execute(
                inventory_batches.insert().values(
                    id=batch_id,
                    medicine_id=medicine_id,
                    batch_code=payload.batch_code,
                    expires_on=expires_on,
                    on_hand=payload.delta,
                    reserved=0,
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
            )
            version = 1
        else:
            if existing is None or existing["version"] != payload.expected_batch_version:
                fail(412, "version_conflict")
            if existing["expires_on"] != expires_on:
                fail(409, "batch_expiry_immutable")
            new_on_hand = existing["on_hand"] + payload.delta
            if new_on_hand < existing["reserved"]:
                fail(409, "stock_reserved")
            if new_on_hand < 0:
                fail(409, "insufficient_inventory")
            if new_on_hand > 1_000_000:
                fail(422, "validation_error")
            batch_id = existing["id"]
            version = existing["version"] + 1
            await session.execute(
                update(inventory_batches)
                .where(
                    inventory_batches.c.id == batch_id,
                    inventory_batches.c.version == payload.expected_batch_version,
                )
                .values(
                    on_hand=new_on_hand,
                    version=version,
                    updated_at=now,
                )
            )
        movement_id = await allocate_id(session, stock_movements.c.id)
        await session.execute(
            stock_movements.insert().values(
                id=movement_id,
                batch_id=batch_id,
                delta=payload.delta,
                reason="adjustment",
                source_id=movement_id,
                created_at=now,
                updated_at=now,
            )
        )
        batch = (
            await session.execute(
                select(inventory_batches).where(inventory_batches.c.id == batch_id)
            )
        ).mappings().one()
        await append_mutation_records(
            session,
            request,
            principal=principal,
            action="inventory.adjusted",
            resource_type="inventory_batch",
            resource_id=batch_id,
            aggregate_version=version,
            content_digest=hashlib.sha256(payload.reason.encode("utf-8")).hexdigest(),
        )
        return CommandResult(
            201,
            {"movement_id": str(movement_id), "batch": batch_json(batch)},
            etag(version),
        )

    try:
        result = await execute_command(
            session,
            request,
            principal,
            route_template="/api/v1/pharmacy/inventory-adjustments",
            key=idempotency_key,
            body=body,
            operation=operation,
        )
    except IntegrityError as error:
        if constraint_name(error) == "uq_inventory_batches_medicine_id":
            fail(412, "version_conflict")
        raise
    return response_for(result)


@api_router.post("/reservations", status_code=201)
async def create_reservation(
    payload: ReservationCreate,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: Principal = Depends(require_one_current_role("pharmacist", "patient")),
    session: AsyncSession = Depends(get_database_session),
):
    body = payload.model_dump(mode="json")
    replay = await lookup_command_replay(
        session,
        request,
        principal,
        route_template="/api/v1/pharmacy/reservations",
        key=idempotency_key,
        body=body,
    )
    if replay is not None:
        return response_for(replay, no_store=True)
    context = await get_prescription_context(
        request, principal, payload.prescription_id
    )
    if (
        request.state.authorized_role == "patient"
        and principal.patient_id != context.patient_id
    ):
        fail(404, "not_found")
    requested = {
        int(item.prescription_item_id): item.quantity for item in payload.items
    }
    context_item_ids = {int(item.item_id) for item in context.items}
    if not set(requested).issubset(context_item_ids):
        fail(409, "allowance_exceeded")
    await expire_reservations(
        session,
        request,
        principal,
        prescription_id=int(payload.prescription_id),
    )
    if context.state == "revoked":
        async with session.begin():
            await sync_prescription_snapshot(session, context)
        fail(409, "prescription_revoked")

    async def operation():
        snapshot, allowances = await sync_prescription_snapshot(session, context)
        if snapshot["state"] != "issued":
            fail(409, "prescription_revoked")
        await session.execute(
            select(reservations)
            .where(reservations.c.prescription_id == int(payload.prescription_id))
            .order_by(reservations.c.id.asc())
            .with_for_update()
        )
        for item_id, quantity in sorted(requested.items()):
            allowance = allowances.get(item_id)
            if allowance is None:
                fail(409, "allowance_exceeded")
            remaining = (
                allowance["prescribed_quantity"]
                - allowance["reserved_quantity"]
                - allowance["dispensed_quantity"]
            )
            if quantity > remaining:
                fail(409, "allowance_exceeded")

        medicine_ids = sorted(
            {allowances[item_id]["medicine_id"] for item_id in requested}
        )
        locked_batches = list(
            (
                await session.execute(
                    select(inventory_batches)
                    .where(
                        inventory_batches.c.medicine_id.in_(medicine_ids),
                        inventory_batches.c.expires_on > _utc_today(),
                    )
                    .order_by(inventory_batches.c.id.asc())
                    .with_for_update()
                )
            ).mappings()
        ) if medicine_ids else []
        batch_availability = {
            row["id"]: row["on_hand"] - row["reserved"] for row in locked_batches
        }
        allocations = []
        batches_by_medicine: dict[int, list] = {}
        for row in locked_batches:
            batches_by_medicine.setdefault(row["medicine_id"], []).append(row)
        for item_id, quantity in sorted(requested.items()):
            allowance = allowances[item_id]
            available = quantity
            fefo = sorted(
                batches_by_medicine.get(allowance["medicine_id"], []),
                key=lambda row: (row["expires_on"], row["id"]),
            )
            for batch in fefo:
                take = min(available, batch_availability[batch["id"]])
                if take <= 0:
                    continue
                allocations.append((item_id, batch, take))
                batch_availability[batch["id"]] -= take
                available -= take
                if available == 0:
                    break
            if available:
                fail(409, "insufficient_stock")

        reservation_id = await allocate_id(session, reservations.c.id)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=30)
        await session.execute(
            reservations.insert().values(
                id=reservation_id,
                prescription_id=int(payload.prescription_id),
                patient_id=int(context.patient_id),
                state="reserved",
                expires_at=expires_at,
                version=1,
                created_at=now,
                updated_at=now,
            )
        )
        for item_id, batch, quantity in allocations:
            await session.execute(
                reservation_items.insert().values(
                    id=await allocate_id(session, reservation_items.c.id),
                    reservation_id=reservation_id,
                    item_id=item_id,
                    batch_id=batch["id"],
                    quantity=quantity,
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.execute(
                update(inventory_batches)
                .where(inventory_batches.c.id == batch["id"])
                .values(
                    reserved=inventory_batches.c.reserved + quantity,
                    version=inventory_batches.c.version + 1,
                    updated_at=now,
                )
            )
        for item_id, quantity in sorted(requested.items()):
            await session.execute(
                update(prescription_item_snapshots)
                .where(prescription_item_snapshots.c.item_id == item_id)
                .values(
                    reserved_quantity=prescription_item_snapshots.c.reserved_quantity + quantity,
                    version=prescription_item_snapshots.c.version + 1,
                    updated_at=now,
                )
            )
        row = (
            await session.execute(
                select(reservations).where(reservations.c.id == reservation_id)
            )
        ).mappings().one()
        item_rows = []
        for item_id, batch, quantity in allocations:
            item_rows.append(
                (
                    {"item_id": item_id, "quantity": quantity},
                    {"medicine_id": allowances[item_id]["medicine_id"]},
                )
            )
        await append_mutation_records(
            session,
            request,
            principal=principal,
            action="reservation.created",
            resource_type="reservation",
            resource_id=reservation_id,
            aggregate_version=1,
            state="reserved",
        )
        return CommandResult(201, reservation_json(row, item_rows), etag(1))

    result = await execute_command(
        session,
        request,
        principal,
        route_template="/api/v1/pharmacy/reservations",
        key=idempotency_key,
        body=body,
        operation=operation,
    )
    return response_for(result, no_store=True)


@api_router.get("/reservations")
async def list_reservations(
    request: Request,
    patient_id: str | None = Query(default=None, pattern=r"^[1-9][0-9]{0,18}$"),
    prescription_id: str | None = Query(default=None, pattern=r"^[1-9][0-9]{0,18}$"),
    state: str | None = None,
    cursor: str | None = Query(default=None, max_length=2048),
    limit: int = Query(default=20, ge=1, le=100),
    principal: Principal = Depends(require_one_current_role("pharmacist", "patient")),
    session: AsyncSession = Depends(get_database_session),
):
    reject_unknown_query(
        request,
        {"patient_id", "prescription_id", "state", "cursor", "limit"},
    )
    if state is not None and state not in {"reserved", "expired", "released", "dispensed"}:
        fail(422, "validation_error")
    scope_role = request.state.authorized_role
    effective_patient_id = patient_id
    if scope_role == "patient":
        if principal.patient_id is None:
            fail(403, "forbidden")
        if patient_id is not None and patient_id != principal.patient_id:
            fail(404, "not_found")
        effective_patient_id = principal.patient_id
    numeric_patient = _require_numeric_id(effective_patient_id) if effective_patient_id else None
    numeric_prescription = _require_numeric_id(prescription_id) if prescription_id else None
    filters = {
        "patient_id": effective_patient_id,
        "prescription_id": prescription_id,
        "state": state,
        "scope_role": scope_role,
        "scope_user_id": principal.user_id,
    }
    statement = select(reservations)
    if numeric_patient is not None:
        statement = statement.where(reservations.c.patient_id == numeric_patient)
    if numeric_prescription is not None:
        statement = statement.where(reservations.c.prescription_id == numeric_prescription)
    if state is not None:
        statement = statement.where(reservations.c.state == state)
    statement = page_statement(
        statement,
        cursor=cursor,
        filters=filters,
        limit=limit,
        created_column=reservations.c.created_at,
        id_column=reservations.c.id,
    )
    async with session.begin():
        rows = list((await session.execute(statement)).mappings())
        grouped = await _reservation_lines(
            session, [row["id"] for row in rows[:limit]]
        )
        page = make_page(
            rows,
            limit=limit,
            filters=filters,
            created_getter=lambda row: row["created_at"],
            id_getter=lambda row: row["id"],
            serializer=lambda row: reservation_json(row, grouped[row["id"]]),
        )
        await append_sensitive_read(
            session,
            request,
            principal=principal,
            action="reservation.list",
            resource_type="reservation_collection",
            resource_id=numeric_patient or int(principal.user_id),
        )
    return JSONResponse(page, headers={"Cache-Control": "no-store"})


@api_router.get("/reservations/{reservation_id}")
async def get_reservation(
    request: Request,
    reservation_id: str = _path_id(),
    principal: Principal = Depends(require_one_current_role("pharmacist", "patient")),
    session: AsyncSession = Depends(get_database_session),
):
    numeric_id = _require_numeric_id(reservation_id)
    denied = False
    result = None
    async with session.begin():
        full = await _reservation_full(session, numeric_id)
        if full is None:
            await append_sensitive_read(
                session,
                request,
                principal=principal,
                action="reservation.read",
                resource_type="reservation",
                resource_id=numeric_id,
                result="denied",
            )
            denied = True
        else:
            row, body = full
            allowed = await _authorize_pharmacy_resource(
                request,
                principal,
                row["patient_id"],
                resource_id=numeric_id,
                resource_type="reservation",
                action="reservation.read",
                session=session,
            )
            if not allowed:
                denied = True
            else:
                await append_sensitive_read(
                    session,
                    request,
                    principal=principal,
                    action="reservation.read",
                    resource_type="reservation",
                    resource_id=numeric_id,
                )
                result = JSONResponse(
                    body,
                    headers={"ETag": etag(row["version"]), "Cache-Control": "no-store"},
                )
    if denied:
        fail(404, "not_found")
    return result


@api_router.delete("/reservations/{reservation_id}", status_code=204)
async def release_reservation(
    request: Request,
    reservation_id: str = _path_id(),
    if_match: str | None = Header(default=None, alias="If-Match"),
    principal: Principal = Depends(require_one_current_role("pharmacist", "patient")),
    session: AsyncSession = Depends(get_database_session),
):
    numeric_id = _require_numeric_id(reservation_id)
    denied = False
    response_headers = {}
    async with session.begin():
        locked = await lock_reservation_aggregate(session, numeric_id)
        if locked is None:
            await append_sensitive_read(
                session,
                request,
                principal=principal,
                action="reservation.release",
                resource_type="reservation",
                resource_id=numeric_id,
                result="denied",
            )
            denied = True
        else:
            snapshot, allowances, row, lines, batches = locked
            allowed = await _authorize_pharmacy_resource(
                request,
                principal,
                row["patient_id"],
                resource_id=numeric_id,
                resource_type="reservation",
                action="reservation.release",
                session=session,
            )
            if not allowed:
                denied = True
            else:
                expected_version = parse_if_match(if_match)
                if row["version"] != expected_version:
                    fail(412, "version_conflict")
                if row["state"] == "dispensed":
                    fail(409, "dispensed")
                if row["state"] == "reserved":
                    next_state = (
                        "expired"
                        if row["expires_at"] <= datetime.now(timezone.utc)
                        else "released"
                    )
                    await release_locked_reservation(
                        session,
                        request,
                        principal,
                        locked,
                        next_state=next_state,
                    )
                    response_headers["ETag"] = etag(row["version"] + 1)
                else:
                    response_headers["ETag"] = etag(row["version"])
    if denied:
        fail(404, "not_found")
    from fastapi.responses import Response

    return Response(status_code=204, headers={**response_headers, "Cache-Control": "no-store"})


@api_router.post("/reservations/{reservation_id}/dispense", status_code=201)
async def dispense_reservation(
    payload: EmptyCommand,
    request: Request,
    reservation_id: str = _path_id(),
    if_match: str | None = Header(default=None, alias="If-Match"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: Principal = Depends(require_current_role("pharmacist")),
    session: AsyncSession = Depends(get_database_session),
):
    numeric_id = _require_numeric_id(reservation_id)
    body = payload.model_dump(mode="json")
    expected_version = parse_if_match(if_match)
    replay = await lookup_command_replay(
        session,
        request,
        principal,
        route_template="/api/v1/pharmacy/reservations/{reservation_id}/dispense",
        key=idempotency_key,
        body=body,
        if_match=if_match,
    )
    if replay is not None:
        return response_for(replay, no_store=True)

    async with session.begin():
        prior = (
            await session.execute(
                select(dispensings.c.id).where(dispensings.c.reservation_id == numeric_id)
            )
        ).scalar_one_or_none()
        reservation_row = (
            await session.execute(
                select(reservations.c.prescription_id).where(reservations.c.id == numeric_id)
            )
        ).scalar_one_or_none()
    if prior is not None:
        async def existing_operation():
            current = (
                await session.execute(
                    select(dispensings.c.id).where(
                        dispensings.c.reservation_id == numeric_id
                    )
                )
            ).scalar_one_or_none()
            if current is None:
                fail(409, "dispensing_in_progress")
            full = await _dispensing_full(session, current)
            row = full[0]
            return CommandResult(201, full[3], etag(row["version"]))

        result = await execute_command(
            session,
            request,
            principal,
            route_template="/api/v1/pharmacy/reservations/{reservation_id}/dispense",
            key=idempotency_key,
            body=body,
            if_match=if_match,
            operation=existing_operation,
        )
        return response_for(result, no_store=True)
    if reservation_row is None:
        fail(404, "not_found")

    context = await get_prescription_context(
        request, principal, str(reservation_row)
    )
    if context.state == "revoked":
        async with session.begin():
            await sync_prescription_snapshot(session, context)
        fail(409, "prescription_revoked")
    await expire_reservations(
        session,
        request,
        principal,
        reservation_id=numeric_id,
    )

    async def operation():
        await sync_prescription_snapshot(session, context)
        locked = await lock_reservation_aggregate(session, numeric_id)
        if locked is None:
            fail(404, "not_found")
        snapshot, allowances, reservation, lines, batches = locked
        prior_id = await session.scalar(
            select(dispensings.c.id).where(
                dispensings.c.reservation_id == numeric_id
            )
        )
        if prior_id is not None:
            prior_full = await _dispensing_full(session, prior_id)
            return CommandResult(
                201, prior_full[3], etag(prior_full[0]["version"])
            )
        if reservation["state"] == "expired":
            fail(409, "expired")
        if reservation["state"] == "released":
            fail(409, "released")
        if reservation["state"] == "dispensed":
            fail(503, "dependency_unavailable")
        if snapshot["state"] != "issued":
            fail(409, "prescription_revoked")
        if reservation["version"] != expected_version:
            fail(412, "version_conflict")
        if reservation["expires_at"] <= datetime.now(timezone.utc):
            fail(409, "expired")
        if not lines:
            fail(409, "allowance_exceeded")

        now = datetime.now(timezone.utc)
        dispensing_id = await allocate_id(session, dispensings.c.id)
        new_reservation_version = reservation["version"] + 1
        await session.execute(
            dispensings.insert().values(
                id=dispensing_id,
                reservation_id=numeric_id,
                staff_user_id=int(principal.user_id),
                completed_at=now,
                version=1,
                created_at=now,
                updated_at=now,
            )
        )
        quantity_by_batch: dict[int, int] = {}
        quantity_by_item: dict[int, int] = {}
        for line in lines:
            quantity_by_batch[line["batch_id"]] = (
                quantity_by_batch.get(line["batch_id"], 0) + line["quantity"]
            )
            quantity_by_item[line["item_id"]] = (
                quantity_by_item.get(line["item_id"], 0) + line["quantity"]
            )
            await session.execute(
                dispensing_items.insert().values(
                    id=await allocate_id(session, dispensing_items.c.id),
                    dispensing_id=dispensing_id,
                    reservation_item_id=line["id"],
                    quantity=line["quantity"],
                    created_at=now,
                    updated_at=now,
                )
            )
        for batch_id, quantity in sorted(quantity_by_batch.items()):
            batch = batches.get(batch_id)
            if batch is None or batch["on_hand"] < quantity or batch["reserved"] < quantity:
                fail(409, "insufficient_stock")
            await session.execute(
                update(inventory_batches)
                .where(inventory_batches.c.id == batch_id)
                .values(
                    on_hand=inventory_batches.c.on_hand - quantity,
                    reserved=inventory_batches.c.reserved - quantity,
                    version=inventory_batches.c.version + 1,
                    updated_at=now,
                )
            )
            movement_id = await allocate_id(session, stock_movements.c.id)
            await session.execute(
                stock_movements.insert().values(
                    id=movement_id,
                    batch_id=batch_id,
                    delta=-quantity,
                    reason="dispense",
                    source_id=dispensing_id,
                    created_at=now,
                    updated_at=now,
                )
            )
        for item_id, quantity in sorted(quantity_by_item.items()):
            allowance = allowances.get(item_id)
            if (
                allowance is None
                or allowance["reserved_quantity"] < quantity
                or allowance["dispensed_quantity"] + quantity
                > allowance["prescribed_quantity"]
            ):
                fail(409, "allowance_exceeded")
            await session.execute(
                update(prescription_item_snapshots)
                .where(prescription_item_snapshots.c.item_id == item_id)
                .values(
                    reserved_quantity=prescription_item_snapshots.c.reserved_quantity - quantity,
                    dispensed_quantity=prescription_item_snapshots.c.dispensed_quantity + quantity,
                    version=prescription_item_snapshots.c.version + 1,
                    updated_at=now,
                )
            )
        await session.execute(
            update(reservations)
            .where(reservations.c.id == numeric_id)
            .values(
                state="dispensed",
                version=new_reservation_version,
                updated_at=now,
            )
        )
        await append_mutation_records(
            session,
            request,
            principal=principal,
            action="reservation.dispensed",
            resource_type="reservation",
            resource_id=numeric_id,
            aggregate_version=new_reservation_version,
            state="dispensed",
            event_payload=(
                {"appointment_id": str(snapshot["appointment_id"])}
                if snapshot["appointment_id"] is not None
                else None
            ),
        )
        full = await _dispensing_full(session, dispensing_id)
        return CommandResult(201, full[3], etag(1))

    result = await execute_command(
        session,
        request,
        principal,
        route_template="/api/v1/pharmacy/reservations/{reservation_id}/dispense",
        key=idempotency_key,
        body=body,
        if_match=if_match,
        operation=operation,
    )
    return response_for(result, no_store=True)


@api_router.post("/reservations/{reservation_id}/revalidate")
async def revalidate_reservation(
    payload: EmptyCommand,
    request: Request,
    reservation_id: str = _path_id(),
    if_match: str | None = Header(default=None, alias="If-Match"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: Principal = Depends(require_current_role("pharmacist")),
    session: AsyncSession = Depends(get_database_session),
):
    numeric_id = _require_numeric_id(reservation_id)
    expected_version = parse_if_match(if_match)
    body = payload.model_dump(mode="json")
    replay = await lookup_command_replay(
        session,
        request,
        principal,
        route_template="/api/v1/pharmacy/reservations/{reservation_id}/revalidate",
        key=idempotency_key,
        body=body,
        if_match=if_match,
    )
    if replay is not None:
        return response_for(replay, no_store=True)
    async with session.begin():
        prescription_id = (
            await session.execute(
                select(reservations.c.prescription_id).where(
                    reservations.c.id == numeric_id
                )
            )
        ).scalar_one_or_none()
    if prescription_id is None:
        fail(404, "not_found")
    context = await get_prescription_context(request, principal, str(prescription_id))

    async def operation():
        await sync_prescription_snapshot(session, context)
        locked = await lock_reservation_aggregate(session, numeric_id)
        if locked is None:
            fail(404, "not_found")
        snapshot, allowances, reservation, lines, batches = locked
        if reservation["version"] != expected_version:
            fail(412, "version_conflict")
        next_state = None
        if reservation["state"] == "reserved":
            if context.state == "revoked":
                next_state = "released"
            elif reservation["expires_at"] <= datetime.now(timezone.utc):
                next_state = "expired"
        if next_state is not None:
            await release_locked_reservation(
                session,
                request,
                principal,
                locked,
                next_state=next_state,
            )
            row = dict(reservation)
            row["state"] = next_state
            row["version"] += 1
        else:
            row = reservation
            await append_sensitive_read(
                session,
                request,
                principal=principal,
                action="reservation.revalidated",
                resource_type="reservation",
                resource_id=numeric_id,
            )
        item_rows = [
            (line, allowances[line["item_id"]])
            for line in lines
            if line["item_id"] in allowances
        ]
        return CommandResult(
            200,
            reservation_json(row, item_rows),
            etag(row["version"]),
        )

    result = await execute_command(
        session,
        request,
        principal,
        route_template="/api/v1/pharmacy/reservations/{reservation_id}/revalidate",
        key=idempotency_key,
        body=body,
        if_match=if_match,
        operation=operation,
    )
    return response_for(result, no_store=True)


@api_router.get("/dispensings")
async def list_dispensings(
    request: Request,
    patient_id: str | None = Query(default=None, pattern=r"^[1-9][0-9]{0,18}$"),
    prescription_id: str | None = Query(default=None, pattern=r"^[1-9][0-9]{0,18}$"),
    appointment_id: str | None = Query(default=None, pattern=r"^[1-9][0-9]{0,18}$"),
    cursor: str | None = Query(default=None, max_length=2048),
    limit: int = Query(default=20, ge=1, le=100),
    principal: Principal = Depends(require_one_current_role("pharmacist", "patient")),
    session: AsyncSession = Depends(get_database_session),
):
    reject_unknown_query(
        request,
        {"patient_id", "prescription_id", "appointment_id", "cursor", "limit"},
    )
    role = request.state.authorized_role
    effective_patient = patient_id
    if role == "patient":
        if principal.patient_id is None:
            fail(403, "forbidden")
        if patient_id is not None and patient_id != principal.patient_id:
            fail(404, "not_found")
        effective_patient = principal.patient_id
    numeric_patient = _require_numeric_id(effective_patient) if effective_patient else None
    numeric_prescription = _require_numeric_id(prescription_id) if prescription_id else None
    numeric_appointment = _require_numeric_id(appointment_id) if appointment_id else None
    filters = {
        "patient_id": effective_patient,
        "prescription_id": prescription_id,
        "appointment_id": appointment_id,
        "scope_role": role,
        "scope_user_id": principal.user_id,
    }
    statement = select(dispensings)
    statement = statement.join(
        reservations, reservations.c.id == dispensings.c.reservation_id
    ).join(
        prescription_snapshots,
        prescription_snapshots.c.prescription_id == reservations.c.prescription_id,
    )
    if numeric_patient is not None:
        statement = statement.where(reservations.c.patient_id == numeric_patient)
    if numeric_prescription is not None:
        statement = statement.where(reservations.c.prescription_id == numeric_prescription)
    if numeric_appointment is not None:
        statement = statement.where(
            prescription_snapshots.c.appointment_id == numeric_appointment
        )
    statement = page_statement(
        statement,
        cursor=cursor,
        filters=filters,
        limit=limit,
        created_column=dispensings.c.created_at,
        id_column=dispensings.c.id,
    )
    async with session.begin():
        rows = list((await session.execute(statement)).mappings())
        serialized = []
        for row in rows[:limit]:
            full = await _dispensing_full(session, row["id"])
            if full is None:
                fail(503, "dependency_unavailable")
            serialized.append((row, full[3]))
        page = make_page(
            rows,
            limit=limit,
            filters=filters,
            created_getter=lambda row: row["created_at"],
            id_getter=lambda row: row["id"],
            serializer=lambda row: next(body for item, body in serialized if item["id"] == row["id"]),
        )
        await append_sensitive_read(
            session,
            request,
            principal=principal,
            action="dispensing.list",
            resource_type="dispensing_collection",
            resource_id=numeric_patient or int(principal.user_id),
        )
    return JSONResponse(page, headers={"Cache-Control": "no-store"})


@api_router.get("/dispensings/{dispensing_id}")
async def get_dispensing(
    request: Request,
    dispensing_id: str = _path_id(),
    principal: Principal = Depends(require_one_current_role("pharmacist", "patient")),
    session: AsyncSession = Depends(get_database_session),
):
    numeric_id = _require_numeric_id(dispensing_id)
    denied = False
    result = None
    async with session.begin():
        full = await _dispensing_full(session, numeric_id)
        if full is None:
            await append_sensitive_read(
                session,
                request,
                principal=principal,
                action="dispensing.read",
                resource_type="dispensing",
                resource_id=numeric_id,
                result="denied",
            )
            denied = True
        else:
            row, reservation, snapshot, body = full
            if snapshot["patient_id"] != reservation["patient_id"]:
                fail(503, "dependency_unavailable")
            allowed = await _authorize_pharmacy_resource(
                request,
                principal,
                reservation["patient_id"],
                resource_id=numeric_id,
                resource_type="dispensing",
                action="dispensing.read",
                session=session,
            )
            if not allowed:
                denied = True
            else:
                await append_sensitive_read(
                    session,
                    request,
                    principal=principal,
                    action="dispensing.read",
                    resource_type="dispensing",
                    resource_id=numeric_id,
                )
                result = JSONResponse(
                    body,
                    headers={"ETag": etag(row["version"]), "Cache-Control": "no-store"},
                )
    if denied:
        fail(404, "not_found")
    return result


@internal_router.post(
    "/medicines/validate",
    dependencies=[Depends(require_service("medicines:validate", "records"))],
)
async def validate_medicines(
    payload: MedicineValidation,
    request: Request,
    principal: Principal = Depends(delegated_user),
    session: AsyncSession = Depends(get_database_session),
):
    await check_current_authority(request, principal, "doctor")
    ids = [int(value) for value in payload.medicine_ids]
    rows = list(
        (
            await session.execute(select(medicines).where(medicines.c.id.in_(ids)))
        ).mappings()
    )
    by_id = {row["id"]: row for row in rows}
    if set(by_id) != set(ids):
        fail(422, "invalid_reference")
    return JSONResponse(
        {
            "items": [
                {
                    "id": str(medicine_id),
                    "active": by_id[medicine_id]["active"],
                    "catalog_version": by_id[medicine_id]["catalog_version"],
                    "name": by_id[medicine_id]["name"],
                }
                for medicine_id in ids
            ]
        },
        headers={"Cache-Control": "no-store"},
    )


@internal_router.get(
    "/dispensings/{dispensing_id}/charge-context",
    dependencies=[Depends(require_service("dispensings:charge-context", "billing"))],
)
async def dispensing_charge_context(
    request: Request,
    dispensing_id: str = _path_id(),
    principal: Principal = Depends(delegated_user),
    session: AsyncSession = Depends(get_database_session),
):
    await check_current_authority(request, principal, "billing_staff")
    numeric_id = _require_numeric_id(dispensing_id)
    async with session.begin():
        full = await _dispensing_full(session, numeric_id)
        if full is None:
            fail(404, "not_found")
        row, reservation, snapshot, _ = full
        if snapshot["appointment_id"] is None:
            fail(503, "dependency_unavailable")
        items = list(
            (
                await session.execute(
                    select(
                        dispensing_items.c.id,
                        dispensing_items.c.quantity,
                        prescription_item_snapshots.c.medicine_id,
                    )
                    .join(
                        reservation_items,
                        reservation_items.c.id == dispensing_items.c.reservation_item_id,
                    )
                    .join(
                        prescription_item_snapshots,
                        prescription_item_snapshots.c.item_id == reservation_items.c.item_id,
                    )
                    .where(dispensing_items.c.dispensing_id == numeric_id)
                    .order_by(dispensing_items.c.id.asc())
                )
            ).mappings()
        )
        body = {
            "dispensing_id": str(numeric_id),
            "appointment_id": str(snapshot["appointment_id"]),
            "patient_id": str(reservation["patient_id"]),
            "items": [
                {
                    "source_item_id": str(item["id"]),
                    "medicine_id": str(item["medicine_id"]),
                    "charge_code": f"medicine:{item['medicine_id']}",
                    "quantity": item["quantity"],
                }
                for item in items
            ],
            "version": row["version"],
        }
        await append_sensitive_read(
            session,
            request,
            principal=principal,
            action="dispensing.charge_context_read",
            resource_type="dispensing",
            resource_id=numeric_id,
        )
    return JSONResponse(
        body,
        headers={"ETag": etag(row["version"]), "Cache-Control": "no-store"},
    )


@api_router.get("/prescriptions/{prescription_id}/fulfillment")
async def get_fulfillment(
    request: Request,
    prescription_id: str = _path_id(),
    principal: Principal = Depends(require_one_current_role("patient", "pharmacist")),
    session: AsyncSession = Depends(get_database_session),
):
    reject_unknown_query(request, set())
    numeric_id = _require_numeric_id(prescription_id)
    context = await get_prescription_context(request, principal, prescription_id)
    if request.state.authorized_role == "patient" and principal.patient_id != context.patient_id:
        fail(404, "not_found")
    async with session.begin():
        snapshot, _ = await sync_prescription_snapshot(session, context)
        fulfillment = await _fulfillment(session, snapshot)
        episode_revision = await session.scalar(select(pharmacy_episode_revisions.c.revision).where(
            pharmacy_episode_revisions.c.appointment_id == int(context.appointment_id)
        ))
        fulfillment["version"] = episode_revision or snapshot["version"]
        await append_sensitive_read(
            session, request, principal=principal, action="prescription.fulfillment_read",
            resource_type="prescription", resource_id=numeric_id,
        )
    return JSONResponse(fulfillment, headers={"ETag": etag(fulfillment["version"]),
                                              "Cache-Control": "no-store"})


@internal_router.get("/appointments/{appointment_id}/workflow-snapshot")
async def pharmacy_workflow_snapshot(
    request: Request,
    appointment_id: str = _path_id(),
    patient_id: str = Query(...),
    prescription_id: str = Query(...),
    cursor: str | None = Query(None, max_length=2048),
    limit: int = Query(100, ge=1, le=100),
    caller: str = Depends(require_service("workflow:pharmacy-read", "appointment")),
    session: AsyncSession = Depends(get_database_session),
):
    reject_unknown_query(request, {"patient_id", "prescription_id", "cursor", "limit"})
    if any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
        fail(422, "validation_error")
    appointment_number = _require_numeric_id(appointment_id)
    patient_number = _require_numeric_id(patient_id)
    prescription_number = _require_numeric_id(prescription_id)
    async with session.begin():
        snapshot = (await session.execute(
            select(prescription_snapshots).where(
                prescription_snapshots.c.prescription_id == prescription_number
            )
        )).mappings().first()
        if snapshot and (snapshot["appointment_id"] != appointment_number or
                         snapshot["patient_id"] != patient_number):
            fail(404, "not_found")
        episode = (await session.execute(
            select(pharmacy_episode_revisions).where(
                pharmacy_episode_revisions.c.appointment_id == appointment_number
            )
        )).mappings().first()
        if episode and (episode["patient_id"] != patient_number or
                        episode["prescription_id"] != prescription_number):
            fail(404, "not_found")
        revision = episode["revision"] if episode else 1
        offset = 0
        if cursor:
            try:
                decoded = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
                if decoded["a"] != appointment_id or decoded["p"] != patient_id or decoded["x"] != prescription_id:
                    raise ValueError
                if decoded["r"] != revision:
                    fail(409, "source_changed")
                offset = decoded["o"]
                if type(offset) is not int or offset < 0:
                    raise ValueError
            except (ValueError, KeyError, TypeError):
                fail(422, "validation_error")
        fulfillment = await _fulfillment(session, snapshot) if snapshot else None
        next_cursor = None
        if fulfillment is not None:
            fulfillment["version"] = revision
            collections = (fulfillment["items"], fulfillment["reservations"],
                           fulfillment["dispensings"])
            if offset > max(map(len, collections)):
                fail(422, "validation_error")
            for key in ("items", "reservations", "dispensings"):
                fulfillment[key] = fulfillment[key][offset:offset + limit]
            if any(offset + limit < len(collection) for collection in collections):
                next_cursor = base64.urlsafe_b64encode(json.dumps(dict(
                    a=appointment_id, p=patient_id, x=prescription_id,
                    r=revision, o=offset + limit,
                ), separators=(",", ":")).encode()).decode().rstrip("=")
        result = dict(snapshot=dict(
            appointment_id=appointment_id, patient_id=patient_id,
            prescription_id=prescription_id, revision=revision,
            fulfillment=fulfillment, observed_at=iso_time(datetime.now(timezone.utc)),
        ), next_cursor=next_cursor)
        latest = await session.scalar(select(pharmacy_episode_revisions.c.revision).where(
            pharmacy_episode_revisions.c.appointment_id == appointment_number
        )) or 1
        if latest != revision:
            fail(409, "source_changed")
        await append_audit(
            session, request, actor_user_id="0", action="prescription.workflow_snapshot_read",
            action_kind="read", resource_type="prescription", resource_id=prescription_number,
        )
    return JSONResponse(result, headers={"ETag": etag(revision), "Cache-Control": "no-store"})
