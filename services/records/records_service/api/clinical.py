"""Assignment-scoped synthetic consultation and immutable record commands."""

import time
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import exists, insert, select, update

from .. import models as m
from .. import storage as s
from ..authorization import authenticated_user, bearer, require_current_role
from ..clinical_schemas import (
    ID,
    AccessGrant,
    Amendment,
    ChargeContext,
    Consultation,
    CreateConsultation,
    DispensingContext,
    EditConsultation,
    Finalize,
    FinalizeResult,
    Grant,
    MedicalRecord,
    Page,
    Prescription,
    RecordSummary,
    Revoke,
    identifier,
)
from ..database import get_database_session


async def command_queries(request: Request):
    if request.method != "GET" and request.query_params:
        raise HTTPException(422)


router = APIRouter(prefix="/api/v1/records", dependencies=[Depends(command_queries)])
private_router = APIRouter(prefix="/internal/v1")


async def rejected_role(request, principal, status=403):
    factory = request.app.state.database.session_factory
    if factory is None:
        raise HTTPException(503)
    async with factory() as session:
        await s.audit(
            session, request, principal, "denied", int(principal.user_id), denied=True
        )
        await session.commit()
    raise HTTPException(status)


async def select_role(request, principal, candidates):
    role = candidates[0]
    if len(candidates) == 1:
        return role
    patient_id = request.path_params.get("patient_id") or request.query_params.get(
        "patient_id"
    )
    resource = next(
        (
            (name, table)
            for name, table in (
                ("record_id", m.medical_records),
                ("consultation_id", m.consultations),
                ("prescription_id", m.prescriptions),
            )
            if name in request.path_params
        ),
        None,
    )
    if resource and request.app.state.database.session_factory:
        name, table = resource
        try:
            id = identifier(request.path_params[name])
        except ValueError:
            return role
        async with request.app.state.database.session_factory() as session:
            patient_id = await session.scalar(
                select(table.c.patient_id).where(table.c.id == int(id))
            )
            patient_id = str(patient_id) if patient_id is not None else None
    if (
        "patient" in candidates
        and principal.patient_id
        and (
            patient_id == principal.patient_id
            or (patient_id is None and resource is None)
        )
    ):
        return "patient"
    if "pharmacist" in candidates and "prescription_id" in request.path_params:
        return "pharmacist"
    return role


def current(*roles):
    async def dependency(request: Request, principal=Depends(authenticated_user)):
        # A role never substitutes for a resource policy. Use exactly one current role.
        candidates = [r for r in roles if r in principal.roles]
        if not candidates:
            await rejected_role(request, principal)
        role = await select_role(request, principal, candidates)
        request.state.domain_deadline = time.monotonic() + 5
        try:
            await require_current_role(role)(request, principal)
        except HTTPException as exc:
            if exc.status_code == 403:
                await rejected_role(request, principal)
            raise
        request.state.effective_role = role
        return principal

    return dependency


reader = current("doctor", "patient")
prescription_reader = current("doctor", "patient", "pharmacist")
doctor = current("doctor")
patient = current("patient")


def self_patient(request, principal, patient_id):
    return request.state.effective_role == "patient" and principal.patient_id == str(
        patient_id
    )


def author(request, principal, c):
    return request.state.effective_role == "doctor" and c["author_user_id"] == int(
        principal.user_id
    )


async def grant_exists(session, principal, patient_id, scope, *, lock=False):
    query = select(m.record_access_grants).where(
        m.record_access_grants.c.patient_id == int(patient_id),
        m.record_access_grants.c.grantee_user_id == int(principal.user_id),
        m.record_access_grants.c.scope == scope,
        m.record_access_grants.c.revoked_at.is_(None),
        m.record_access_grants.c.expires_at > s.now(),
    )
    if lock:
        query = query.with_for_update()
    return (await session.execute(query)).first() is not None


async def historical_access(
    session, request, principal, patient_id, scope="records:read"
):
    if self_patient(request, principal, patient_id):
        return ("self", None)
    if request.state.effective_role != "doctor":
        await s.deny(session, request, principal, patient_id)
    if await grant_exists(session, principal, patient_id, scope):
        return ("grant", None)
    if scope == "records:read":
        appointments = (
            (
                await session.execute(
                    select(m.consultations.c.appointment_id).where(
                        m.consultations.c.patient_id == int(patient_id),
                        m.consultations.c.author_user_id == int(principal.user_id),
                        m.consultations.c.hold_finalized_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        await session.rollback()  # No transaction/locks across dependency calls.
        for appointment_id in appointments:
            context = await request.app.state.domain_client.context(
                request, principal, appointment_id
            )
            if (
                context["patient_id"] == str(patient_id)
                and context["doctor_user_id"] == principal.user_id
                and context["state"] == "confirmed"
                and context["clinical_hold"] == "active"
            ):
                return ("hold", appointment_id)
    await s.deny(session, request, principal, patient_id)


async def recheck_grant(
    session, request, principal, patient_id, access, scope="records:read"
):
    if access[0] == "grant" and not await grant_exists(
        session, principal, patient_id, scope, lock=True
    ):
        await s.deny(session, request, principal, patient_id)


async def scoped_consultation(session, request, principal, id, lock=False):
    c = await s.row(session, m.consultations, id, lock)
    if not (
        author(request, principal, c)
        or self_patient(request, principal, c["patient_id"])
    ):
        await s.deny(session, request, principal, id)
    return c


def filters(request, allowed):
    s.query_args(request, allowed)
    result = {}
    for key in allowed:
        value = request.query_params.get(key)
        if value is not None:
            try:
                identifier(value)
            except ValueError:
                raise HTTPException(422) from None
        result[key] = value
    return result


@router.get("/patients/{patient_id}", response_model=Page[RecordSummary])
async def history(
    patient_id: ID,
    request: Request,
    principal=Depends(reader),
    session=Depends(get_database_session),
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None, max_length=2048),
):
    filters(request, [])
    access = await historical_access(session, request, principal, patient_id)
    await recheck_grant(session, request, principal, patient_id, access)
    result = await s.page(
        session,
        request,
        m.medical_records,
        [m.medical_records.c.patient_id == int(patient_id)],
        {
            "patient_id": patient_id,
            "_scope": principal.user_id + ":" + request.state.effective_role,
        },
        lambda r: s.record(r, True),
    )
    await s.audit(session, request, principal, "read", patient_id)
    await session.commit()
    return s.reply(result)


@router.get("/consultations", response_model=Page[Consultation])
async def consultations(
    request: Request,
    principal=Depends(reader),
    session=Depends(get_database_session),
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None, max_length=2048),
    appointment_id: ID | None = Query(None),
    patient_id: ID | None = Query(None),
):
    f = filters(request, ["appointment_id", "patient_id"])
    conditions = []
    if request.state.effective_role == "doctor":
        conditions.append(m.consultations.c.author_user_id == int(principal.user_id))
    elif principal.patient_id:
        if f["patient_id"] and f["patient_id"] != principal.patient_id:
            await s.deny(session, request, principal, f["patient_id"])
        conditions.append(m.consultations.c.patient_id == int(principal.patient_id))
    else:
        raise HTTPException(404)
    for key, value in f.items():
        if value:
            conditions.append(m.consultations.c[key] == int(value))
    result = await s.page(
        session,
        request,
        m.consultations,
        conditions,
        {**f, "_scope": principal.user_id + ":" + request.state.effective_role},
        s.consultation,
    )
    await s.audit(session, request, principal, "read", int(principal.user_id))
    await session.commit()
    return s.reply(result)


@router.get("/consultations/{consultation_id}", response_model=Consultation)
async def get_consultation(
    consultation_id: ID,
    request: Request,
    principal=Depends(reader),
    session=Depends(get_database_session),
):
    if request.query_params:
        raise HTTPException(422)
    c = await scoped_consultation(session, request, principal, consultation_id)
    await s.audit(session, request, principal, "read", c["id"])
    await session.commit()
    return s.reply(s.consultation(c), version=c["version"])


@router.post("/consultations", response_model=Consultation, status_code=201)
async def create_consultation(
    body: CreateConsultation,
    request: Request,
    principal=Depends(doctor),
    session=Depends(get_database_session),
):
    payload = body.model_dump(mode="json")
    identity, fingerprint = s.key_data(request, principal, payload)
    previous = await s.replay(session, request, principal, payload)
    if previous:
        return previous
    prepared = (
        (
            await session.execute(
                select(m.command_preparations).where(
                    m.command_preparations.c.principal_scope
                    == identity["principal_scope"],
                    m.command_preparations.c.key == identity["key"],
                )
            )
        )
        .mappings()
        .first()
    )
    await session.commit()
    context = await request.app.state.domain_client.context(
        request, principal, body.appointment_id
    )
    if context["doctor_user_id"] != principal.user_id:
        await s.deny(session, request, principal, body.appointment_id)
    if context["state"] != "confirmed" or context["clinical_hold"] == "finalized":
        raise HTTPException(409, detail="appointment_unavailable")
    await request.app.state.domain_client.patient(
        request, principal, context["patient_id"]
    )
    if prepared:
        if prepared["request_hash"] != fingerprint:
            raise HTTPException(409)
        preparation = dict(prepared)
        stored = preparation["context"]
        if any(
            stored[k] != context[k]
            for k in ("appointment_id", "patient_id", "doctor_id", "doctor_user_id")
        ):
            raise HTTPException(409, detail="appointment_unavailable")
    else:
        # Recheck replay/preparation after reacquiring the key lock; another replica may have prepared.
        previous = await s.replay(session, request, principal, payload)
        if previous:
            return previous
        prepared = (
            (
                await session.execute(
                    select(m.command_preparations).where(
                        m.command_preparations.c.principal_scope
                        == identity["principal_scope"],
                        m.command_preparations.c.key == identity["key"],
                    )
                )
            )
            .mappings()
            .first()
        )
        if prepared:
            if prepared["request_hash"] != fingerprint:
                raise HTTPException(409)
            preparation = dict(prepared)
        else:
            if await session.scalar(
                select(
                    exists().where(
                        m.consultations.c.appointment_id == int(body.appointment_id)
                    )
                )
            ):
                raise HTTPException(409, detail="consultation_exists")
            preparation = dict(
                principal_scope=identity["principal_scope"],
                key=identity["key"],
                request_hash=fingerprint,
                consultation_id=await s.new_id(session),
                appointment_id=int(body.appointment_id),
                context=context,
                hold_version=context["version"],
            )
            await session.execute(insert(m.command_preparations).values(**preparation))
        await session.commit()
    held = await request.app.state.domain_client.hold(request, principal, preparation)
    if any(
        held[k] != preparation["context"][k]
        for k in ("appointment_id", "patient_id", "doctor_id", "doctor_user_id")
    ):
        raise HTTPException(503)
    previous = await s.replay(session, request, principal, payload)
    if previous:
        return previous
    await session.execute(
        s.text("SELECT pg_advisory_xact_lock(:id)"), {"id": -int(body.appointment_id)}
    )
    if await session.scalar(
        select(
            exists().where(m.consultations.c.appointment_id == int(body.appointment_id))
        )
    ):
        raise HTTPException(409, detail="consultation_exists")
    c = dict(
        id=preparation["consultation_id"],
        appointment_id=int(body.appointment_id),
        journey_id=None,
        patient_id=int(held["patient_id"]),
        doctor_id=int(held["doctor_id"]),
        author_user_id=int(principal.user_id),
        hold_version=held["version"],
        status="draft",
        revision=1,
        version=1,
        clinical_content=payload["clinical_content"],
    )
    await session.execute(insert(m.consultations).values(**c))
    result = s.consultation(c)
    await s.event(
        session,
        request,
        "consultation",
        c["id"],
        1,
        "created",
        {"resource_id": str(c["id"]), "version": 1, "state": "draft"},
    )
    await s.audit(
        session, request, principal, "created", c["id"], payload["clinical_content"]
    )
    await s.remember(session, request, principal, payload, result, 201, 1)
    await session.commit()
    return s.reply(result, 201, 1)


async def assigned_context(session, request, principal, consultation_id):
    c = await scoped_consultation(session, request, principal, consultation_id)
    if not author(request, principal, c):
        await s.deny(session, request, principal, consultation_id)
    await session.rollback()
    context = await request.app.state.domain_client.context(
        request, principal, c["appointment_id"]
    )
    if (
        context["doctor_user_id"] != principal.user_id
        or context["patient_id"] != str(c["patient_id"])
        or context["doctor_id"] != str(c["doctor_id"])
    ):
        await s.deny(session, request, principal, consultation_id)
    if context["state"] != "confirmed" or context["clinical_hold"] not in (
        "active",
        "finalized",
    ):
        raise HTTPException(409, detail="appointment_unavailable")
    return c


@router.patch("/consultations/{consultation_id}", response_model=Consultation)
async def edit_consultation(
    consultation_id: ID,
    body: EditConsultation,
    request: Request,
    principal=Depends(doctor),
    session=Depends(get_database_session),
):
    await assigned_context(session, request, principal, consultation_id)
    c = await scoped_consultation(session, request, principal, consultation_id, True)
    s.match(request, c["version"])
    if c["status"] != "draft":
        raise HTTPException(409, detail="finalized")
    c.update(
        clinical_content=body.clinical_content.model_dump(),
        version=s.increment(c["version"]),
    )
    await session.execute(
        update(m.consultations)
        .where(m.consultations.c.id == c["id"])
        .values(
            clinical_content=c["clinical_content"],
            version=c["version"],
            updated_at=s.now(),
        )
    )
    await s.event(
        session,
        request,
        "consultation",
        c["id"],
        c["version"],
        "updated",
        {"resource_id": str(c["id"]), "version": c["version"]},
    )
    await s.audit(
        session, request, principal, "updated", c["id"], c["clinical_content"]
    )
    await session.commit()
    return s.reply(s.consultation(c), version=c["version"])


async def finalize_hold(session, request, principal, c):
    if c.get("hold_finalized_at"):
        return
    try:
        await request.app.state.domain_client.hold(
            request,
            principal,
            dict(
                consultation_id=c["id"],
                appointment_id=c["appointment_id"],
                hold_version=c["hold_version"],
            ),
            finalize=True,
        )
    except HTTPException:
        request.app.state.logger.warning(
            "clinical_hold_finalize_pending",
            extra={"service": "records", "request_id": str(request.state.request_id)},
        )
        return
    await session.execute(
        update(m.consultations)
        .where(
            m.consultations.c.id == c["id"],
            m.consultations.c.hold_finalized_at.is_(None),
        )
        .values(hold_finalized_at=s.now())
    )
    await session.commit()


@router.post("/consultations/{consultation_id}/finalize", response_model=FinalizeResult)
async def finalize(
    consultation_id: ID,
    body: Finalize,
    request: Request,
    principal=Depends(doctor),
    session=Depends(get_database_session),
):
    payload = body.model_dump(mode="json")
    c = await scoped_consultation(session, request, principal, consultation_id)
    previous = await s.replay(session, request, principal, payload)
    if previous:
        await session.commit()
        await finalize_hold(session, request, principal, c)
        return previous
    await session.rollback()
    await assigned_context(session, request, principal, consultation_id)
    snapshots = await request.app.state.domain_client.medicines(
        request, principal, [i.medicine_id for i in body.prescription_items]
    )
    previous = await s.replay(session, request, principal, payload)
    if previous:
        await session.commit()
        await finalize_hold(session, request, principal, c)
        return previous
    c = await scoped_consultation(session, request, principal, consultation_id, True)
    s.match(request, c["version"])
    if c["status"] != "draft":
        raise HTTPException(409, detail="finalized")
    c.update(status="finalized", version=s.increment(c["version"]))
    await session.execute(
        update(m.consultations)
        .where(m.consultations.c.id == c["id"])
        .values(status=c["status"], version=c["version"], updated_at=s.now())
    )
    r = dict(
        id=await s.new_id(session),
        consultation_id=c["id"],
        patient_id=c["patient_id"],
        author_user_id=c["author_user_id"],
        revision=1,
        version=1,
        content=c["clinical_content"],
        supersedes_id=None,
    )
    await session.execute(insert(m.medical_records).values(**r))
    prescription = None
    prescription_id = None
    if body.prescription_items:
        p = dict(
            id=await s.new_id(session),
            consultation_id=c["id"],
            patient_id=c["patient_id"],
            journey_id=None,
            revision=1,
            state="issued",
            version=1,
        )
        prescription_id = p["id"]
        await session.execute(insert(m.prescriptions).values(**p))
        for item in body.prescription_items:
            await session.execute(
                insert(m.prescription_items).values(
                    id=await s.new_id(session),
                    prescription_id=p["id"],
                    medicine_id=int(item.medicine_id),
                    quantity=item.quantity,
                    dosage=item.dosage,
                    instructions=item.instructions,
                    medicine_snapshot=snapshots[item.medicine_id],
                )
            )
        prescription = await s.prescription(session, p)
        await s.event(
            session,
            request,
            "prescription",
            p["id"],
            1,
            "issued",
            {
                "prescription_id": str(p["id"]),
                "consultation_id": str(c["id"]),
                "journey_id": None,
                "patient_id": str(c["patient_id"]),
                "revision": 1,
                "state": "issued",
                "items": [
                    {
                        "item_id": i["id"],
                        "medicine_id": i["medicine_id"],
                        "quantity": i["quantity"],
                    }
                    for i in prescription["items"]
                ],
            },
        )
        await s.audit(session, request, principal, "issued", p["id"], payload)
    result = dict(
        consultation=s.consultation(c), record=s.record(r), prescription=prescription
    )
    await s.event(
        session,
        request,
        "consultation",
        c["id"],
        c["version"],
        "completed",
        {
            "consultation_id": str(c["id"]),
            "appointment_id": str(c["appointment_id"]),
            "journey_id": None,
            "patient_id": str(c["patient_id"]),
            "doctor_id": str(c["doctor_id"]),
            "prescription_id": str(prescription_id) if prescription_id else None,
            "charge_code": "consultation",
        },
    )
    await s.audit(
        session, request, principal, "finalized", c["id"], c["clinical_content"]
    )
    await s.remember(session, request, principal, payload, result, 200, c["version"])
    await session.commit()
    await finalize_hold(session, request, principal, c)
    return s.reply(result, version=c["version"])


@router.get("/prescriptions", response_model=Page[Prescription])
async def prescriptions(
    request: Request,
    principal=Depends(reader),
    session=Depends(get_database_session),
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None, max_length=2048),
    patient_id: ID | None = Query(None),
    consultation_id: ID | None = Query(None),
):
    f = filters(request, ["patient_id", "consultation_id"])
    conditions = []
    if request.state.effective_role == "doctor":
        conditions.append(
            m.prescriptions.c.consultation_id.in_(
                select(m.consultations.c.id).where(
                    m.consultations.c.author_user_id == int(principal.user_id)
                )
            )
        )
    elif principal.patient_id:
        if f["patient_id"] and f["patient_id"] != principal.patient_id:
            await s.deny(session, request, principal, f["patient_id"])
        conditions.append(m.prescriptions.c.patient_id == int(principal.patient_id))
    else:
        raise HTTPException(404)
    for key, value in f.items():
        if value:
            conditions.append(m.prescriptions.c[key] == int(value))
    result = await s.page(
        session,
        request,
        m.prescriptions,
        conditions,
        {**f, "_scope": principal.user_id + ":" + request.state.effective_role},
        lambda r: s.prescription(session, r),
    )
    await s.audit(session, request, principal, "read", int(principal.user_id))
    await session.commit()
    return s.reply(result)


async def prescription_access(session, request, principal, p):
    if request.state.effective_role == "pharmacist" or self_patient(
        request, principal, p["patient_id"]
    ):
        return
    c = await s.row(session, m.consultations, p["consultation_id"])
    if author(request, principal, c):
        return
    access = await historical_access(
        session, request, principal, p["patient_id"], "prescriptions:read"
    )
    await recheck_grant(
        session, request, principal, p["patient_id"], access, "prescriptions:read"
    )


@router.get("/prescriptions/{prescription_id}", response_model=Prescription)
async def get_prescription(
    prescription_id: ID,
    request: Request,
    principal=Depends(prescription_reader),
    session=Depends(get_database_session),
):
    if request.query_params:
        raise HTTPException(422)
    p = await s.row(session, m.prescriptions, prescription_id)
    await prescription_access(session, request, principal, p)
    result = await s.prescription(session, p)
    await s.audit(session, request, principal, "read", p["id"])
    await session.commit()
    return s.reply(result, version=p["version"])


@router.post("/prescriptions/{prescription_id}/revoke", response_model=Prescription)
async def revoke(
    prescription_id: ID,
    body: Revoke,
    request: Request,
    principal=Depends(doctor),
    session=Depends(get_database_session),
):
    p = await s.row(session, m.prescriptions, prescription_id)
    c = await s.row(session, m.consultations, p["consultation_id"])
    if not author(request, principal, c):
        await s.deny(session, request, principal, p["id"])
    payload = body.model_dump(mode="json")
    previous = await s.replay(session, request, principal, payload)
    if previous:
        return previous
    p = await s.row(session, m.prescriptions, prescription_id, True)
    s.match(request, p["version"])
    if p["state"] == "issued":
        p.update(state="revoked", version=s.increment(p["version"]))
        await session.execute(
            update(m.prescriptions)
            .where(m.prescriptions.c.id == p["id"])
            .values(state="revoked", version=p["version"], updated_at=s.now())
        )
        await s.event(
            session,
            request,
            "prescription",
            p["id"],
            p["version"],
            "revoked",
            {
                "prescription_id": str(p["id"]),
                "consultation_id": str(c["id"]),
                "journey_id": None,
                "patient_id": str(p["patient_id"]),
                "revision": p["revision"],
                "reason_code": "author_revoked",
            },
        )
    result = await s.prescription(session, p)
    await s.audit(session, request, principal, "revoked", p["id"], payload)
    await s.remember(session, request, principal, payload, result, 200, p["version"])
    await session.commit()
    return s.reply(result, version=p["version"])


@router.post("/access-grants", response_model=AccessGrant, status_code=201)
async def create_grant(
    body: Grant,
    request: Request,
    principal=Depends(patient),
    session=Depends(get_database_session),
):
    if not self_patient(request, principal, body.patient_id):
        await s.deny(session, request, principal, body.patient_id)
    payload = body.model_dump(mode="json")
    previous = await s.replay(session, request, principal, payload)
    if previous:
        return previous
    await session.rollback()
    if not s.now() < body.expires_at <= s.now() + timedelta(days=30):
        raise HTTPException(422)
    await request.app.state.domain_client.staff(
        request, principal, body.grantee_user_id
    )
    previous = await s.replay(session, request, principal, payload)
    if previous:
        return previous
    if not s.now() < body.expires_at <= s.now() + timedelta(days=30):
        raise HTTPException(422)
    g = dict(
        id=await s.new_id(session),
        patient_id=int(body.patient_id),
        grantee_user_id=int(body.grantee_user_id),
        scope=body.scope,
        expires_at=body.expires_at,
        version=1,
    )
    await session.execute(insert(m.record_access_grants).values(**g))
    result = s.grant(g)
    await s.event(
        session,
        request,
        "grant",
        g["id"],
        1,
        "created",
        {"resource_id": str(g["id"]), "version": 1},
    )
    await s.audit(session, request, principal, "grant_created", g["id"])
    await s.remember(session, request, principal, payload, result, 201, 1)
    await session.commit()
    return s.reply(result, 201, 1)


@router.delete("/access-grants/{grant_id}", status_code=204)
async def delete_grant(
    grant_id: ID,
    request: Request,
    principal=Depends(patient),
    session=Depends(get_database_session),
):
    g = await s.row(session, m.record_access_grants, grant_id, True)
    if not self_patient(request, principal, g["patient_id"]):
        await s.deny(session, request, principal, grant_id)
    s.match(request, g["version"])
    if not g["revoked_at"]:
        g["version"] = s.increment(g["version"])
        await session.execute(
            update(m.record_access_grants)
            .where(m.record_access_grants.c.id == g["id"])
            .values(revoked_at=s.now(), version=g["version"], updated_at=s.now())
        )
        await s.event(
            session,
            request,
            "grant",
            g["id"],
            g["version"],
            "revoked",
            {"resource_id": str(g["id"]), "version": g["version"]},
        )
    await s.audit(session, request, principal, "grant_revoked", g["id"])
    await session.commit()
    return s.reply(status=204, version=g["version"])


@router.post("/{record_id}/amendments", response_model=MedicalRecord, status_code=201)
async def amend(
    record_id: ID,
    body: Amendment,
    request: Request,
    principal=Depends(doctor),
    session=Depends(get_database_session),
):
    r = await s.row(session, m.medical_records, record_id)
    c = await s.row(session, m.consultations, r["consultation_id"])
    if not author(request, principal, c):
        await s.deny(session, request, principal, record_id)
    payload = body.model_dump(mode="json")
    # Replay still needs historical scope, even when the record has become superseded.
    access = await historical_access(session, request, principal, r["patient_id"])
    await session.rollback()
    previous = await s.replay(session, request, principal, payload)
    await s.row(session, m.consultations, c["id"], True)
    await recheck_grant(session, request, principal, r["patient_id"], access)
    if previous:
        return previous
    s.match(request, r["version"])
    if await session.scalar(
        select(exists().where(m.medical_records.c.supersedes_id == r["id"]))
    ):
        raise HTTPException(409, detail="superseded")
    amended = dict(
        id=await s.new_id(session),
        consultation_id=c["id"],
        patient_id=c["patient_id"],
        author_user_id=int(principal.user_id),
        content=body.content.model_dump(),
        revision=s.increment(r["revision"]),
        version=1,
        supersedes_id=r["id"],
    )
    await session.execute(insert(m.medical_records).values(**amended))
    result = s.record(amended)
    await s.event(
        session,
        request,
        "record",
        amended["id"],
        1,
        "amended",
        {
            "record_id": str(amended["id"]),
            "consultation_id": str(c["id"]),
            "appointment_id": str(c["appointment_id"]),
            "journey_id": None,
            "revision": amended["revision"],
            "workflow_review_required": True,
        },
    )
    await s.audit(session, request, principal, "amended", amended["id"], payload)
    await s.remember(session, request, principal, payload, result, 201, 1)
    await session.commit()
    return s.reply(result, 201, 1)


@router.get("/{record_id}", response_model=MedicalRecord)
async def get_record(
    record_id: ID,
    request: Request,
    principal=Depends(reader),
    session=Depends(get_database_session),
):
    if request.query_params:
        raise HTTPException(422)
    r = await s.row(session, m.medical_records, record_id)
    c = await s.row(session, m.consultations, r["consultation_id"])
    if not author(request, principal, c):
        access = await historical_access(session, request, principal, r["patient_id"])
        await recheck_grant(session, request, principal, r["patient_id"], access)
    await s.audit(session, request, principal, "read", r["id"])
    await session.commit()
    return s.reply(s.record(r), version=r["version"])


def delegated(caller, scope, roles):
    async def dependency(request: Request):
        actual = request.app.state.auth_verifier.service(bearer(request), scope)
        if actual != caller:
            raise HTTPException(403)
        p = request.app.state.auth_verifier.user(
            bearer(request, "X-Delegated-Authorization")
        )
        role = next((r for r in roles if r in p.roles), None)
        if not role:
            raise HTTPException(403)
        request.state.effective_role = role
        return p

    return dependency


@private_router.get(
    "/prescriptions/{prescription_id}/dispensing-context",
    response_model=DispensingContext,
)
async def dispensing_context(
    prescription_id: ID,
    request: Request,
    principal=Depends(
        delegated(
            "pharmacy", "prescriptions:dispensing-context", ("pharmacist", "patient")
        )
    ),
    session=Depends(get_database_session),
):
    if request.query_params:
        raise HTTPException(422)
    p = await s.row(session, m.prescriptions, prescription_id)
    if request.state.effective_role != "pharmacist" and not self_patient(
        request, principal, p["patient_id"]
    ):
        await s.deny(session, request, principal, p["id"])
    c = await s.row(session, m.consultations, p["consultation_id"])
    result = await s.prescription(session, p, True)
    result["prescription_id"] = result.pop("id")
    result["appointment_id"] = str(c["appointment_id"])
    await s.audit(session, request, principal, "read", p["id"])
    await session.commit()
    return s.reply(result, version=p["version"])


@private_router.get(
    "/consultations/{consultation_id}/charge-context", response_model=ChargeContext
)
async def charge_context(
    consultation_id: ID,
    request: Request,
    principal=Depends(
        delegated("billing", "consultations:charge-context", ("billing_staff",))
    ),
    session=Depends(get_database_session),
):
    if request.query_params:
        raise HTTPException(422)
    c = await s.row(session, m.consultations, consultation_id)
    result = dict(
        consultation_id=str(c["id"]),
        appointment_id=str(c["appointment_id"]),
        patient_id=str(c["patient_id"]),
        status=c["status"],
        charge_code="consultation",
        quantity=1,
        version=c["version"],
    )
    await s.audit(session, request, principal, "read", c["id"])
    await session.commit()
    return s.reply(result, version=c["version"])
