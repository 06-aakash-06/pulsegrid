"""Frozen Phase 2 public billing endpoints."""

from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import and_, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..authorization import (
    Principal,
    authenticated_user,
    require_current_role,
    verify_current_role,
)
from ..cursor import decode_cursor, encode_cursor, filter_hash
from ..database import get_database_session
from ..idempotency import (
    StoredOutcome,
    lock_and_read,
    payment_durable_key,
    replay_if_present,
    request_fingerprint,
    save_outcome,
    validated_key,
)
from ..ledger import (
    append_audit,
    append_outbox,
    calculate_totals,
    insert_with_random_id,
    invoice_event_payload,
)
from ..models import (
    invoice_items,
    invoices,
    payments,
    tariff_heads,
    tariffs,
)
from ..schemas import (
    ID,
    MAX_ID,
    MAX_MINOR,
    ChargeImport,
    InvoiceCreate,
    InvoiceItemResponse,
    InvoiceResponse,
    Page,
    PaymentCreate,
    PaymentResponse,
    TariffCreate,
    TariffResponse,
)
from ..schemas import ErrorResponse

router = APIRouter()
_ETAG = re.compile(r'^"([1-9][0-9]{0,18})"$')


@dataclass(frozen=True)
class BillingActor:
    principal: Principal
    role: Literal["patient", "billing_staff"]


async def current_billing_actor(
    request: Request,
    principal: Principal = Depends(authenticated_user),
) -> BillingActor:
    if "billing_staff" in principal.roles:
        role: Literal["patient", "billing_staff"] = "billing_staff"
    elif "patient" in principal.roles and principal.patient_id is not None:
        role = "patient"
    else:
        raise HTTPException(403)
    await verify_current_role(request, principal, role)
    return BillingActor(principal, role)


async def current_billing_staff(
    principal: Principal = Depends(require_current_role("billing_staff")),
) -> BillingActor:
    return BillingActor(principal, "billing_staff")


def ensure_query_params(request: Request, allowed: set[str]) -> None:
    for key in request.query_params.keys():
        if key not in allowed or len(request.query_params.getlist(key)) != 1:
            raise HTTPException(422)


def error_outcome(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    *,
    details: dict | None = None,
) -> StoredOutcome:
    body = ErrorResponse(
        error={
            "code": code,
            "message": message,
            "request_id": request.state.request_id,
            "details": details,
        }
    ).model_dump(mode="json", exclude_none=True)
    return StoredOutcome(status_code, body, None)


def send_outcome(outcome: StoredOutcome, *, sensitive: bool = True) -> JSONResponse:
    headers = {"Cache-Control": "no-store"} if sensitive else {}
    if outcome.etag is not None:
        headers["ETag"] = outcome.etag
    return JSONResponse(
        status_code=outcome.status_code,
        content=outcome.body,
        headers=headers,
    )


def current_etag(version: int) -> str:
    return f'"{version}"'


def precondition_error(request: Request, raw_if_match: str | None, current_version: int):
    if raw_if_match is None:
        return error_outcome(
            request, 428, "precondition_required", "If-Match is required."
        )
    match = _ETAG.fullmatch(raw_if_match)
    if match is None or int(match.group(1)) > MAX_MINOR:
        return error_outcome(
            request, 400, "invalid_if_match", "If-Match must be a quoted decimal version."
        )
    if int(match.group(1)) != current_version:
        return error_outcome(
            request, 412, "version_conflict", "The resource version has changed."
        )
    return None


async def lock_resource(session: AsyncSession, namespace: str, key: str) -> None:
    digest = hashlib.sha256((namespace + "\0" + key).encode("utf-8")).digest()
    lock_id = int.from_bytes(digest[:8], byteorder="big", signed=True)
    await session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})


def assert_invoice_scope(row, actor: BillingActor) -> None:
    if actor.role == "patient" and str(row["patient_id"]) != actor.principal.patient_id:
        # Hide both existence and ownership of another patient's financial record.
        raise HTTPException(404)


async def fetch_invoice(session: AsyncSession, invoice_id: str, *, for_update: bool = False):
    statement = select(invoices).where(invoices.c.id == int(invoice_id))
    if for_update:
        statement = statement.with_for_update()
    return (await session.execute(statement)).mappings().first()


async def invoice_body(session: AsyncSession, row) -> dict:
    if row is None or row["appointment_id"] is None:
        raise HTTPException(404)
    item_rows = (
        await session.execute(
            select(
                invoice_items.c.id,
                invoice_items.c.source_service,
                invoice_items.c.source_item_id,
                invoice_items.c.quantity,
                invoice_items.c.unit_amount_minor,
                tariffs.c.charge_code,
                tariffs.c.revision.label("tariff_revision"),
            )
            .join(tariffs, tariffs.c.id == invoice_items.c.tariff_id)
            .where(invoice_items.c.invoice_id == row["id"])
            .order_by(invoice_items.c.created_at, invoice_items.c.id)
        )
    ).mappings().all()
    item_values = [
        {
            "id": str(item["id"]),
            "charge_code": item["charge_code"],
            "source_service": item["source_service"],
            "source_item_id": str(item["source_item_id"]),
            "quantity": int(item["quantity"]),
            "unit_amount_minor": int(item["unit_amount_minor"]),
            "tariff_revision": int(item["tariff_revision"]),
        }
        for item in item_rows
    ]
    try:
        subtotal_minor, total_minor = calculate_totals(item_values)
    except ValueError:
        raise HTTPException(503) from None
    total_minor_db = int(row["total_minor"])
    paid_minor = int(row["paid_minor"])
    if subtotal_minor != total_minor_db or total_minor != total_minor_db:
        raise HTTPException(503)
    if paid_minor > total_minor_db or total_minor_db > MAX_MINOR:
        raise HTTPException(503)
    value = InvoiceResponse(
        id=str(row["id"]),
        journey_id=None,
        appointment_id=str(row["appointment_id"]),
        patient_id=str(row["patient_id"]),
        status=row["status"],
        items=[InvoiceItemResponse.model_validate(item) for item in item_values],
        total_minor=total_minor_db,
        paid_minor=paid_minor,
        balance_minor=total_minor_db - paid_minor,
        currency=row["currency"],
        version=int(row["version"]),
    )
    return value.model_dump(mode="json")


def tariff_body(row) -> dict:
    return TariffResponse(
        id=str(row["id"]),
        charge_code=row["charge_code"],
        revision=int(row["revision"]),
        unit_amount_minor=int(row["unit_amount_minor"]),
        currency=row["currency"],
        version=int(row["version"]),
    ).model_dump(mode="json")


def payment_body(row) -> dict:
    return PaymentResponse(
        id=str(row["id"]),
        invoice_id=str(row["invoice_id"]),
        amount_minor=int(row["amount_minor"]),
        currency=row["currency"],
        status=row["status"],
        version=int(row["version"]),
    ).model_dump(mode="json")


async def invoice_updated_event(session, request, row) -> None:
    await append_outbox(
        session,
        request,
        event_type="billing.invoice.updated.v1",
        aggregate_type="invoice",
        aggregate_id=int(row["id"]),
        aggregate_version=int(row["version"]),
        payload=await invoice_event_payload(session, row),
    )


@router.get("/tariffs")
async def list_tariffs(
    request: Request,
    charge_code: str | None = Query(None, min_length=1, max_length=128),
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    _actor: BillingActor = Depends(current_billing_staff),
    session: AsyncSession = Depends(get_database_session),
):
    ensure_query_params(request, {"charge_code", "cursor", "limit"})
    if charge_code is not None and charge_code != "consultation" and not re.fullmatch(
        r"medicine:[1-9][0-9]{0,18}", charge_code
    ):
        raise HTTPException(422)
    if charge_code is not None and charge_code.startswith("medicine:") and int(charge_code[9:]) > MAX_ID:
        raise HTTPException(422)
    filters = {"charge_code": charge_code}
    scope = "billing_staff:" + _actor.principal.user_id
    digest = filter_hash(filters, scope)
    position = decode_cursor(cursor, digest)
    conditions = []
    if charge_code is not None:
        conditions.append(tariffs.c.charge_code == charge_code)
    if position:
        created_at, row_id = position
        conditions.append(
            or_(tariffs.c.created_at > created_at,
                and_(tariffs.c.created_at == created_at, tariffs.c.id > row_id))
        )
    async with session.begin():
        rows = (
            await session.execute(
                select(tariffs)
                .where(*conditions)
                .order_by(tariffs.c.created_at, tariffs.c.id)
                .limit(limit + 1)
            )
        ).mappings().all()
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    next_cursor = (
        encode_cursor(page_rows[-1]["created_at"], page_rows[-1]["id"], digest)
        if has_more and page_rows
        else None
    )
    body = Page[TariffResponse](
        items=[TariffResponse.model_validate(tariff_body(row)) for row in page_rows],
        next_cursor=next_cursor,
    ).model_dump(mode="json")
    return JSONResponse(content=body, headers={"Cache-Control": "no-store"})


@router.post("/tariffs", status_code=201)
async def create_tariff(
    request: Request,
    body: TariffCreate,
    actor: BillingActor = Depends(current_billing_staff),
    session: AsyncSession = Depends(get_database_session),
):
    key = validated_key(request)
    route = "/api/v1/billing/tariffs"
    normalized_body = body.model_dump(mode="json")
    fingerprint = request_fingerprint(normalized_body, resource_ids={})
    replay = await replay_if_present(session, actor.principal, route, key, fingerprint)
    if replay is not None:
        return send_outcome(replay)

    async with session.begin():
        replay = await lock_and_read(session, actor.principal, route, key, fingerprint)
        if replay is not None:
            outcome = replay
        else:
            await lock_resource(session, "tariff", body.charge_code)
            await session.execute(
                pg_insert(tariff_heads)
                .values(charge_code=body.charge_code, last_revision=0)
                .on_conflict_do_nothing(index_elements=[tariff_heads.c.charge_code])
            )
            head = (
                await session.execute(
                    select(tariff_heads)
                    .where(tariff_heads.c.charge_code == body.charge_code)
                    .with_for_update()
                )
            ).mappings().one()
            revision = int(head["last_revision"]) + 1
            if revision > MAX_MINOR:
                outcome = error_outcome(request, 409, "revision_exhausted", "No tariff revision is available.")
            else:
                await session.execute(
                    update(tariff_heads)
                    .where(tariff_heads.c.charge_code == body.charge_code)
                    .values(last_revision=revision)
                )
                tariff_id = await insert_with_random_id(
                    session,
                    tariffs,
                    {
                        "charge_code": body.charge_code,
                        "revision": revision,
                        "unit_amount_minor": body.unit_amount_minor,
                        "currency": body.currency,
                        "version": 1,
                    },
                )
                tariff_row = (
                    await session.execute(select(tariffs).where(tariffs.c.id == tariff_id))
                ).mappings().one()
                await append_audit(
                    session,
                    request,
                    action="tariff.create",
                    actor_user_id=actor.principal.user_id,
                    resource_id=tariff_id,
                    amount_minor=body.unit_amount_minor,
                    currency=body.currency,
                )
                await append_outbox(
                    session,
                    request,
                    event_type="billing.tariff.created.v1",
                    aggregate_type="tariff",
                    aggregate_id=tariff_id,
                    aggregate_version=revision,
                    payload={"resource_id": str(tariff_id), "version": revision, "state": "active"},
                )
                outcome = StoredOutcome(201, tariff_body(tariff_row), current_etag(1))
            await save_outcome(session, actor.principal, route, key, fingerprint, outcome)
    return send_outcome(outcome)


@router.post("/invoices", status_code=201)
async def create_invoice(
    request: Request,
    body: InvoiceCreate,
    actor: BillingActor = Depends(current_billing_staff),
    session: AsyncSession = Depends(get_database_session),
):
    key = validated_key(request)
    route = "/api/v1/billing/invoices"
    normalized_body = body.model_dump(mode="json")
    fingerprint = request_fingerprint(normalized_body, resource_ids={"appointment_id": body.appointment_id})
    replay = await replay_if_present(session, actor.principal, route, key, fingerprint)
    if replay is not None:
        return send_outcome(replay)

    context = await request.app.state.billing_domain_client.appointment_billing_context(
        request, actor.principal, body.appointment_id
    )
    if context is None:
        raise HTTPException(422, detail={"code": "invalid_reference", "message": "The appointment reference is invalid."})
    if context.appointment_id != body.appointment_id:
        raise HTTPException(422, detail={"code": "invalid_reference", "message": "The appointment reference is invalid."})

    async with session.begin():
        replay = await lock_and_read(session, actor.principal, route, key, fingerprint)
        if replay is not None:
            outcome = replay
        else:
            await lock_resource(session, "invoice-appointment", body.appointment_id)
            existing = (
                await session.execute(
                    select(invoices).where(invoices.c.appointment_id == int(body.appointment_id))
                )
            ).mappings().first()
            if existing is not None:
                outcome = error_outcome(request, 409, "invoice_exists", "An invoice already exists for this appointment.")
            else:
                invoice_id = await insert_with_random_id(
                    session,
                    invoices,
                    {
                        "journey_id": None,
                        "appointment_id": int(body.appointment_id),
                        "patient_id": int(context.patient_id),
                        "currency": body.currency,
                        "status": "open",
                        "total_minor": 0,
                        "paid_minor": 0,
                        "version": 1,
                    },
                )
                invoice = await fetch_invoice(session, str(invoice_id))
                await append_audit(
                    session,
                    request,
                    action="invoice.create",
                    actor_user_id=actor.principal.user_id,
                    resource_id=invoice_id,
                    currency=body.currency,
                )
                await invoice_updated_event(session, request, invoice)
                outcome = StoredOutcome(201, await invoice_body(session, invoice), current_etag(1))
            await save_outcome(session, actor.principal, route, key, fingerprint, outcome)
    return send_outcome(outcome)


@router.get("/invoices")
async def list_invoices(
    request: Request,
    patient_id: ID | None = None,
    status: Literal["open", "paid"] | None = None,
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    actor: BillingActor = Depends(current_billing_actor),
    session: AsyncSession = Depends(get_database_session),
):
    ensure_query_params(request, {"patient_id", "status", "cursor", "limit"})
    if actor.role == "patient":
        if patient_id is not None and patient_id != actor.principal.patient_id:
            raise HTTPException(404)
        scoped_patient_id = actor.principal.patient_id
    else:
        scoped_patient_id = patient_id
    filters = {"patient_id": scoped_patient_id, "status": status}
    scope = f"{actor.role}:{actor.principal.user_id}:{scoped_patient_id or '*'}"
    digest = filter_hash(filters, scope)
    position = decode_cursor(cursor, digest)
    conditions = [invoices.c.appointment_id.is_not(None)]
    if scoped_patient_id is not None:
        conditions.append(invoices.c.patient_id == int(scoped_patient_id))
    if status is not None:
        conditions.append(invoices.c.status == status)
    if position:
        created_at, row_id = position
        conditions.append(
            or_(invoices.c.created_at > created_at,
                and_(invoices.c.created_at == created_at, invoices.c.id > row_id))
        )
    async with session.begin():
        rows = (
            await session.execute(
                select(invoices)
                .where(*conditions)
                .order_by(invoices.c.created_at, invoices.c.id)
                .limit(limit + 1)
            )
        ).mappings().all()
        has_more = len(rows) > limit
        page_rows = rows[:limit]
        items = [await invoice_body(session, row) for row in page_rows]
    next_cursor = (
        encode_cursor(page_rows[-1]["created_at"], page_rows[-1]["id"], digest)
        if has_more and page_rows
        else None
    )
    body = Page[InvoiceResponse](
        items=[InvoiceResponse.model_validate(item) for item in items],
        next_cursor=next_cursor,
    ).model_dump(mode="json")
    return JSONResponse(content=body, headers={"Cache-Control": "no-store"})


@router.get("/invoices/{invoice_id}")
async def get_invoice(
    invoice_id: ID,
    request: Request,
    actor: BillingActor = Depends(current_billing_actor),
    session: AsyncSession = Depends(get_database_session),
):
    ensure_query_params(request, set())
    async with session.begin():
        row = await fetch_invoice(session, invoice_id)
        if row is None or row["appointment_id"] is None:
            raise HTTPException(404)
        assert_invoice_scope(row, actor)
        body = await invoice_body(session, row)
    return JSONResponse(
        content=body,
        headers={"ETag": current_etag(int(row["version"])), "Cache-Control": "no-store"},
    )


@router.get("/invoices/{invoice_id}/payments")
async def list_invoice_payments(
    invoice_id: ID,
    request: Request,
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    actor: BillingActor = Depends(current_billing_actor),
    session: AsyncSession = Depends(get_database_session),
):
    ensure_query_params(request, {"cursor", "limit"})
    async with session.begin():
        invoice = await fetch_invoice(session, invoice_id)
        if invoice is None or invoice["appointment_id"] is None:
            raise HTTPException(404)
        assert_invoice_scope(invoice, actor)
        scope = f"{actor.role}:{actor.principal.user_id}:{invoice['patient_id']}"
        digest = filter_hash({"invoice_id": invoice_id}, scope)
        position = decode_cursor(cursor, digest)
        conditions = [payments.c.invoice_id == int(invoice_id)]
        if position:
            created_at, row_id = position
            conditions.append(
                or_(payments.c.created_at > created_at,
                    and_(payments.c.created_at == created_at, payments.c.id > row_id))
            )
        rows = (
            await session.execute(
                select(payments)
                .where(*conditions)
                .order_by(payments.c.created_at, payments.c.id)
                .limit(limit + 1)
            )
        ).mappings().all()
        has_more = len(rows) > limit
        page_rows = rows[:limit]
        items = [payment_body(row) for row in page_rows]
    next_cursor = (
        encode_cursor(page_rows[-1]["created_at"], page_rows[-1]["id"], digest)
        if has_more and page_rows
        else None
    )
    body = Page[PaymentResponse](items=items, next_cursor=next_cursor).model_dump(mode="json")
    return JSONResponse(content=body, headers={"Cache-Control": "no-store"})


@router.post("/invoices/{invoice_id}/charges")
async def import_charges(
    invoice_id: ID,
    request: Request,
    body: ChargeImport,
    actor: BillingActor = Depends(current_billing_staff),
    session: AsyncSession = Depends(get_database_session),
):
    key = validated_key(request)
    raw_if_match = request.headers.get("If-Match")
    route = "/api/v1/billing/invoices/{invoice_id}/charges"
    normalized_body = body.model_dump(mode="json")
    fingerprint = request_fingerprint(
        normalized_body, resource_ids={"invoice_id": invoice_id}, if_match=raw_if_match
    )
    replay = await replay_if_present(session, actor.principal, route, key, fingerprint)
    if replay is not None:
        return send_outcome(replay)

    async with session.begin():
        initial_invoice = await fetch_invoice(session, invoice_id)
        if initial_invoice is None or initial_invoice["appointment_id"] is None:
            raise HTTPException(404)
    early_precondition = precondition_error(
        request, raw_if_match, int(initial_invoice["version"])
    )
    if early_precondition is not None:
        async with session.begin():
            replay = await lock_and_read(
                session, actor.principal, route, key, fingerprint
            )
            if replay is None:
                outcome = early_precondition
                await save_outcome(
                    session, actor.principal, route, key, fingerprint, outcome
                )
            else:
                outcome = replay
        return send_outcome(outcome)
    sources = await _charge_sources(request, actor, body, initial_invoice)

    outcome: StoredOutcome
    try:
        async with session.begin():
            replay = await lock_and_read(session, actor.principal, route, key, fingerprint)
            if replay is not None:
                outcome = replay
            else:
                invoice = await fetch_invoice(session, invoice_id, for_update=True)
                if invoice is None or invoice["appointment_id"] is None:
                    outcome = error_outcome(request, 404, "not_found", "The requested resource was not found.")
                else:
                    precondition = precondition_error(request, raw_if_match, int(invoice["version"]))
                    if precondition is not None:
                        outcome = precondition
                    else:
                        await _lock_charge_sources(session, sources)
                        outcome = await _apply_charge_sources(
                            session, request, actor, route, key, fingerprint, invoice, sources
                        )
                    await save_outcome(session, actor.principal, route, key, fingerprint, outcome)
    except IntegrityError:
        # A cross-invoice source race is backed by a durable unique constraint.
        outcome = error_outcome(request, 409, "source_mismatch", "A charge source was already attached elsewhere.")
    return send_outcome(outcome)


@router.post("/invoices/{invoice_id}/payments", status_code=201)
async def simulate_payment(
    invoice_id: ID,
    request: Request,
    body: PaymentCreate,
    actor: BillingActor = Depends(current_billing_actor),
    session: AsyncSession = Depends(get_database_session),
):
    key = validated_key(request)
    raw_if_match = request.headers.get("If-Match")
    route = "/api/v1/billing/invoices/{invoice_id}/payments"
    normalized_body = body.model_dump(mode="json")
    fingerprint = request_fingerprint(
        normalized_body, resource_ids={"invoice_id": invoice_id}, if_match=raw_if_match
    )
    async with session.begin():
        invoice = await fetch_invoice(session, invoice_id)
        if invoice is None or invoice["appointment_id"] is None:
            raise HTTPException(404)
        assert_invoice_scope(invoice, actor)
    replay = await replay_if_present(session, actor.principal, route, key, fingerprint)
    if replay is not None:
        return send_outcome(replay)

    durable_key = payment_durable_key(actor.principal, invoice_id, key)
    async with session.begin():
        existing_payment = (
            await session.execute(
                select(payments).where(
                    payments.c.invoice_id == int(invoice_id),
                    payments.c.idempotency_key == durable_key,
                )
            )
        ).mappings().first()
    if existing_payment is not None:
        if existing_payment["request_hash"] != fingerprint:
            return send_outcome(error_outcome(
                request, 409, "idempotency_key_reused", "The key was already used for different request content."
            ))
        return send_outcome(
            StoredOutcome(201, payment_body(existing_payment), current_etag(int(existing_payment["version"])))
        )

    async with session.begin():
        replay = await lock_and_read(session, actor.principal, route, key, fingerprint)
        if replay is not None:
            outcome = replay
        else:
            invoice = await fetch_invoice(session, invoice_id, for_update=True)
            if invoice is None or invoice["appointment_id"] is None:
                outcome = error_outcome(request, 404, "not_found", "The requested resource was not found.")
            else:
                assert_invoice_scope(invoice, actor)
                precondition = precondition_error(request, raw_if_match, int(invoice["version"]))
                if precondition is not None:
                    outcome = precondition
                elif body.currency != invoice["currency"]:
                    outcome = error_outcome(request, 409, "currency_mismatch", "The payment currency does not match the invoice.")
                else:
                    balance = int(invoice["total_minor"]) - int(invoice["paid_minor"])
                    if body.amount_minor > balance or balance <= 0:
                        outcome = error_outcome(request, 409, "overpayment", "The payment exceeds the permitted invoice balance.")
                    elif int(invoice["version"]) >= MAX_MINOR:
                        outcome = error_outcome(request, 409, "version_exhausted", "The invoice version cannot be advanced.")
                    else:
                        new_version = int(invoice["version"]) + 1
                        payment_status = "success" if body.simulated_outcome == "success" else "declined"
                        paid_minor = int(invoice["paid_minor"])
                        if payment_status == "success":
                            paid_minor += body.amount_minor
                        new_status = (
                            "paid"
                            if int(invoice["total_minor"]) > 0 and paid_minor == int(invoice["total_minor"])
                            else "open"
                        )
                        payment_id = await insert_with_random_id(
                            session,
                            payments,
                            {
                                "invoice_id": int(invoice_id),
                                "idempotency_key": durable_key,
                                "request_hash": fingerprint,
                                "amount_minor": body.amount_minor,
                                "currency": body.currency,
                                "status": payment_status,
                                "version": new_version,
                            },
                        )
                        await session.execute(
                            update(invoices)
                            .where(invoices.c.id == int(invoice_id))
                            .values(
                                paid_minor=paid_minor,
                                status=new_status,
                                version=new_version,
                                updated_at=datetime.now(timezone.utc),
                            )
                        )
                        updated_invoice = await fetch_invoice(session, invoice_id)
                        await append_audit(
                            session,
                            request,
                            action="payment.attempt",
                            actor_user_id=actor.principal.user_id,
                            resource_id=int(invoice_id),
                            result=payment_status,
                            amount_minor=body.amount_minor,
                            currency=body.currency,
                        )
                        await invoice_updated_event(session, request, updated_invoice)
                        if payment_status == "success":
                            payload = await invoice_event_payload(session, updated_invoice)
                            payload.update({"payment_id": str(payment_id), "amount_minor": body.amount_minor})
                            event_type = "billing.payment.succeeded.v1"
                        else:
                            payload = {
                                "resource_id": str(payment_id),
                                "version": new_version,
                                "state": "declined",
                            }
                            event_type = "billing.payment.declined.v1"
                        await append_outbox(
                            session,
                            request,
                            event_type=event_type,
                            aggregate_type="invoice",
                            aggregate_id=int(invoice_id),
                            aggregate_version=new_version,
                            payload=payload,
                        )
                        payment_row = (
                            await session.execute(select(payments).where(payments.c.id == payment_id))
                        ).mappings().one()
                        outcome = StoredOutcome(
                            201,
                            payment_body(payment_row),
                            current_etag(new_version),
                        )
                await save_outcome(session, actor.principal, route, key, fingerprint, outcome)
    return send_outcome(outcome)


async def _charge_sources(request, actor, body: ChargeImport, invoice) -> list[dict]:
    domain_client = request.app.state.billing_domain_client
    calls = []
    if body.consultation_id is not None:
        calls.append(("records", body.consultation_id, domain_client.consultation_charge_context(
            request, actor.principal, body.consultation_id
        )))
    for dispensing_id in body.dispensing_ids:
        calls.append(("pharmacy", dispensing_id, domain_client.dispensing_charge_context(
            request, actor.principal, dispensing_id
        )))
    try:
        async with asyncio.timeout(5.0):
            contexts = await asyncio.gather(*(call for _, _, call in calls))
    except TimeoutError:
        raise HTTPException(504, detail={"code": "dependency_timeout", "message": "A required service did not respond in time."}) from None

    expected_appointment = str(invoice["appointment_id"])
    expected_patient = str(invoice["patient_id"])
    sources: list[dict] = []
    seen_keys: set[tuple[str, str]] = set()
    for (service, requested_id, _), context in zip(calls, contexts, strict=True):
        if context is None:
            raise HTTPException(
                409,
                detail={"code": "source_not_finalized", "message": "A requested charge source is not available for billing."},
            )
        if service == "records":
            if context.consultation_id != requested_id or context.status != "finalized":
                raise HTTPException(409, detail={"code": "source_not_finalized", "message": "The consultation is not finalized."})
            if context.appointment_id != expected_appointment or context.patient_id != expected_patient:
                raise HTTPException(409, detail={"code": "source_mismatch", "message": "A charge source does not match this invoice."})
            sources.append({
                "source_service": "records",
                "source_item_id": context.consultation_id,
                "charge_code": context.charge_code,
                "quantity": context.quantity,
            })
            continue
        if context.dispensing_id != requested_id:
            raise HTTPException(409, detail={"code": "source_mismatch", "message": "A charge source does not match this invoice."})
        if context.appointment_id != expected_appointment or context.patient_id != expected_patient:
            raise HTTPException(409, detail={"code": "source_mismatch", "message": "A charge source does not match this invoice."})
        if not context.items:
            raise HTTPException(409, detail={"code": "source_not_finalized", "message": "The dispensing contains no billable items."})
        local_ids: set[str] = set()
        for item in context.items:
            if item.source_item_id in local_ids or item.charge_code != f"medicine:{item.medicine_id}":
                raise HTTPException(409, detail={"code": "source_mismatch", "message": "A charge source is inconsistent."})
            local_ids.add(item.source_item_id)
            sources.append({
                "source_service": "pharmacy",
                "source_item_id": item.source_item_id,
                "charge_code": item.charge_code,
                "quantity": item.quantity,
            })
    for source in sources:
        source_key = (source["source_service"], source["source_item_id"])
        if source_key in seen_keys:
            raise HTTPException(409, detail={"code": "source_mismatch", "message": "A charge source was included more than once."})
        seen_keys.add(source_key)
    return sources


async def _lock_charge_sources(session, sources: list[dict]) -> None:
    for service, source_id in sorted(
        {(source["source_service"], source["source_item_id"]) for source in sources}
    ):
        await lock_resource(session, "charge-source:" + service, source_id)


async def _apply_charge_sources(
    session,
    request,
    actor,
    route,
    key,
    fingerprint,
    invoice,
    sources: list[dict],
) -> StoredOutcome:
    requested_keys = [(source["source_service"], int(source["source_item_id"])) for source in sources]
    existing_conditions = [
        and_(invoice_items.c.source_service == service, invoice_items.c.source_item_id == source_id)
        for service, source_id in requested_keys
    ]
    existing_rows = (
        await session.execute(
            select(
                invoice_items,
                tariffs.c.charge_code.label("charge_code"),
            )
            .join(tariffs, tariffs.c.id == invoice_items.c.tariff_id)
            .where(or_(*existing_conditions))
        )
    ).mappings().all()
    existing_by_key = {
        (row["source_service"], int(row["source_item_id"])): row for row in existing_rows
    }
    new_sources = []
    for source in sources:
        source_key = (source["source_service"], int(source["source_item_id"]))
        existing = existing_by_key.get(source_key)
        if existing is None:
            new_sources.append(source)
        elif (
            int(existing["invoice_id"]) != int(invoice["id"])
            or int(existing["quantity"]) != source["quantity"]
            or existing["charge_code"] != source["charge_code"]
        ):
            return error_outcome(request, 409, "source_mismatch", "A charge source conflicts with a posted charge.")

    latest_tariffs = {}
    if new_sources:
        codes = sorted({source["charge_code"] for source in new_sources})
        rows = (
            await session.execute(
                select(tariffs)
                .where(tariffs.c.charge_code.in_(codes), tariffs.c.currency == invoice["currency"])
                .order_by(tariffs.c.charge_code, tariffs.c.revision.desc())
            )
        ).mappings().all()
        for row in rows:
            latest_tariffs.setdefault(row["charge_code"], row)
        if any(source["charge_code"] not in latest_tariffs for source in new_sources):
            return error_outcome(request, 409, "unpriced_source", "A requested charge source has no configured tariff.")

    existing_invoice_items = (
        await session.execute(
            select(invoice_items.c.quantity, invoice_items.c.unit_amount_minor)
            .where(invoice_items.c.invoice_id == int(invoice["id"]))
        )
    ).all()
    projected_items = [
        {"quantity": int(row.quantity), "unit_amount_minor": int(row.unit_amount_minor)}
        for row in existing_invoice_items
    ]
    for source in new_sources:
        projected_items.append({
            "quantity": source["quantity"],
            "unit_amount_minor": int(latest_tariffs[source["charge_code"]]["unit_amount_minor"]),
        })
    try:
        _subtotal_minor, total_minor = calculate_totals(projected_items)
    except ValueError:
        return error_outcome(request, 409, "amount_overflow", "The invoice total exceeds the supported amount range.")
    if new_sources and int(invoice["version"]) >= MAX_MINOR:
        return error_outcome(request, 409, "version_exhausted", "The invoice version cannot be advanced.")

    for source in new_sources:
        tariff = latest_tariffs[source["charge_code"]]
        await insert_with_random_id(
            session,
            invoice_items,
            {
                "invoice_id": int(invoice["id"]),
                "source_service": source["source_service"],
                "source_event_id": None,
                "source_item_id": int(source["source_item_id"]),
                "tariff_id": int(tariff["id"]),
                "quantity": source["quantity"],
                "unit_amount_minor": int(tariff["unit_amount_minor"]),
            },
        )

    if new_sources:
        paid_minor = int(invoice["paid_minor"])
        new_status = (
            "paid"
            if total_minor > 0 and total_minor == paid_minor
            else "open"
        )
        new_version = int(invoice["version"]) + 1
        await session.execute(
            update(invoices)
            .where(invoices.c.id == int(invoice["id"]))
            .values(
                total_minor=total_minor,
                status=new_status,
                version=new_version,
                updated_at=datetime.now(timezone.utc),
            )
        )
        invoice = await fetch_invoice(session, str(invoice["id"]))
        await append_audit(
            session,
            request,
            action="invoice.charges.import",
            actor_user_id=actor.principal.user_id,
            resource_id=int(invoice["id"]),
            amount_minor=total_minor,
            currency=invoice["currency"],
            item_count=len(new_sources),
        )
        await invoice_updated_event(session, request, invoice)
    response_body = await invoice_body(session, invoice)
    outcome = StoredOutcome(200, response_body, current_etag(int(invoice["version"])))
    return outcome
