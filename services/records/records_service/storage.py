"""PostgreSQL transactions, replay and safe clinical projections."""

import base64
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from fastapi.responses import JSONResponse, Response
from sqlalchemy import insert, select, text, tuple_

from . import models as m


def now():
    return datetime.now(timezone.utc)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


async def new_id(session):
    return await session.scalar(text("SELECT nextval('records_domain_ids')"))


async def row(session, table, id, lock=False):
    query = select(table).where(table.c.id == int(id))
    if lock:
        query = query.with_for_update()
    result = (await session.execute(query)).mappings().first()
    if result is None:
        raise HTTPException(404)
    return dict(result)


async def audit(
    session, request, principal, action, resource_id, content=None, denied=False
):
    await session.execute(
        text(
            "SELECT records_append_audit(:actor,:action,:resource,:result,:digest,CAST(:request AS uuid),CAST(:correlation AS uuid))"
        ),
        dict(
            actor=int(principal.user_id),
            action=action,
            resource=int(resource_id),
            result="denied" if denied else "allowed",
            digest=digest(content) if content is not None else None,
            request=str(request.state.request_id),
            correlation=str(request.state.correlation_id),
        ),
    )


async def deny(session, request, principal, resource_id):
    await audit(session, request, principal, "denied", resource_id, denied=True)
    await session.commit()
    raise HTTPException(404)


def match(request, version):
    raw = request.headers.get("If-Match")
    if raw is None:
        raise HTTPException(428)
    if (
        not re.fullmatch(r'"[1-9][0-9]{0,15}"', raw)
        or int(raw[1:-1]) > 9007199254740991
    ):
        raise HTTPException(400)
    if int(raw[1:-1]) != version:
        raise HTTPException(412)


def increment(version):
    if version >= 9007199254740991:
        raise HTTPException(409)
    return version + 1


def reply(body=None, status=200, version=None):
    headers = {"Cache-Control": "no-store"}
    if version is not None:
        headers["ETag"] = f'"{version}"'
    if status == 204:
        return Response(status_code=204, headers=headers)
    return JSONResponse(body, status_code=status, headers=headers)


def key_data(request, principal, body):
    key = request.headers.get("Idempotency-Key", "")
    if not re.fullmatch(r"[\x21-\x7e]{16,128}", key):
        raise HTTPException(422)
    scope = "user:" + principal.user_id
    route = request.url.path
    return dict(
        principal_scope=scope, method="POST", route_template=route, key=key
    ), digest({"body": body, "if_match": request.headers.get("If-Match")})


async def replay(session, request, principal, body):
    identity, fingerprint = key_data(request, principal, body)
    # Transaction advisory lock serializes equal keys even before their row exists.
    lock = int.from_bytes(
        hashlib.sha256(canonical(identity).encode()).digest()[:8], "big", signed=True
    )
    await session.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": lock})
    found = (
        (await session.execute(select(m.idempotency_requests).filter_by(**identity)))
        .mappings()
        .first()
    )
    if found:
        if found["request_hash"] != fingerprint:
            raise HTTPException(409)
        result = found["response"]
        return reply(result["body"], found["response_code"], result["version"])
    return None


async def remember(session, request, principal, body, response, status, version):
    identity, fingerprint = key_data(request, principal, body)
    await session.execute(
        insert(m.idempotency_requests).values(
            **identity,
            request_hash=fingerprint,
            response_code=status,
            response={"body": response, "version": version},
            expires_at=now() + timedelta(days=1),
        )
    )


async def event(session, request, aggregate, id, version, action, payload):
    event_id = await new_id(session)
    event_type = f"records.{aggregate}.{action}.v1"
    await session.execute(
        insert(m.outbox_events).values(
            event_id=event_id,
            aggregate_type=aggregate,
            aggregate_id=id,
            aggregate_version=version,
            event_type=event_type,
            envelope={
                "event_id": str(event_id),
                "event_type": event_type,
                "schema_version": 1,
                "producer": "records",
                "occurred_at": now().isoformat(),
                "aggregate_type": aggregate,
                "aggregate_id": str(id),
                "aggregate_version": version,
                "correlation_id": str(request.state.correlation_id),
                "request_id": str(request.state.request_id),
                "causation_id": None,
                "traceparent": getattr(request.state, "traceparent", None),
                "payload": payload,
            },
        )
    )


def consultation(r):
    return {
        **{k: str(r[k]) for k in ("id", "appointment_id", "patient_id", "doctor_id")},
        **{k: r[k] for k in ("status", "clinical_content", "revision", "version")},
    }


def record(r, summary=False):
    out = {
        **{k: str(r[k]) for k in ("id", "consultation_id", "patient_id")},
        "revision": r["revision"],
        "version": r["version"],
    }
    if summary:
        out["created_at"] = r["created_at"].astimezone(timezone.utc).isoformat()
    else:
        out.update(
            content=r["content"],
            supersedes_id=str(r["supersedes_id"]) if r["supersedes_id"] else None,
        )
    return out


async def prescription(session, r, minimal=False):
    items = (
        (
            await session.execute(
                select(m.prescription_items)
                .where(m.prescription_items.c.prescription_id == r["id"])
                .order_by(m.prescription_items.c.id)
            )
        )
        .mappings()
        .all()
    )
    fields = (
        ("id", "medicine_id", "quantity")
        if minimal
        else ("id", "medicine_id", "quantity", "dosage", "instructions")
    )
    return {
        **{k: str(r[k]) for k in ("id", "consultation_id", "patient_id")},
        "journey_id": None,
        "revision": r["revision"],
        "state": r["state"],
        "version": r["version"],
        "items": [
            {k: str(i[k]) if k in ("id", "medicine_id") else i[k] for k in fields}
            for i in items
        ],
    }


def grant(r):
    return {
        **{k: str(r[k]) for k in ("id", "patient_id", "grantee_user_id")},
        "scope": r["scope"],
        "expires_at": r["expires_at"].isoformat(),
        "version": r["version"],
    }


def query_args(request, allowed):
    if set(request.query_params) - set(allowed) - {"cursor", "limit"}:
        raise HTTPException(422)
    if any(len(request.query_params.getlist(k)) != 1 for k in request.query_params):
        raise HTTPException(422)
    try:
        raw = request.query_params.get("limit", "20")
        if not raw.isascii() or not raw.isdecimal():
            raise ValueError()
        limit = int(raw)
        if not 1 <= limit <= 100:
            raise ValueError()
    except ValueError:
        raise HTTPException(422) from None
    return limit


async def page(session, request, table, conditions, filters, serialize):
    limit = int(request.query_params.get("limit", "20"))
    scope_hash = digest(filters)
    query = select(table).where(*conditions)
    cursor = request.query_params.get("cursor")
    if cursor:
        try:
            if len(cursor) > 2048:
                raise ValueError()
            data = json.loads(
                base64.b64decode(
                    cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True
                )
            )
            from .clinical_schemas import identifier, utc

            if (
                set(data) != {"created_at", "id", "filter_hash"}
                or data["filter_hash"] != scope_hash
            ):
                raise ValueError()
            timestamp = utc(datetime.fromisoformat(data["created_at"]))
            identifier(data["id"])
            query = query.where(
                tuple_(table.c.created_at, table.c.id)
                > tuple_(timestamp, int(data["id"]))
            )
        except (ValueError, TypeError, KeyError):
            raise HTTPException(400) from None
    rows = (
        (
            await session.execute(
                query.order_by(table.c.created_at, table.c.id).limit(limit + 1)
            )
        )
        .mappings()
        .all()
    )
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        data = {
            "created_at": last["created_at"].isoformat(),
            "id": str(last["id"]),
            "filter_hash": scope_hash,
        }
        next_cursor = (
            base64.urlsafe_b64encode(canonical(data).encode()).decode().rstrip("=")
        )
    items = []
    for r in rows[:limit]:
        result = serialize(dict(r))
        if hasattr(result, "__await__"):
            result = await result
        items.append(result)
    return {"items": items, "next_cursor": next_cursor}
