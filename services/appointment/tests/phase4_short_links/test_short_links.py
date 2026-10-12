from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from itertools import count
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, insert, select, text, update

from appointment_service import models as m, operations as op, phase3_core as core
from appointment_service.authorization import Principal
from appointment_service.database import Database
from appointment_service.features.checkin import registration as checkin
from appointment_service.features.short_links import registration as short_links
from appointment_service.features.short_links.repository import ShortLinkRepository
from appointment_service.features.short_links.schema_spec import table_for
from ..test_concurrency import booking, patient, request as base_request, run


class Metrics:
    def __init__(self):
        self.counters = []
        self.observations = []

    def increment(self, name, labels, value=1):
        self.counters.append((name, dict(labels), value))

    def observe(self, name, seconds, labels):
        self.observations.append((name, seconds, dict(labels)))

    def gauge(self, name, value, labels):
        return None


class ShortLinksTestPorts:
    """Production owner sessions and command transaction with a test lock seam."""

    def __init__(self, db):
        self.db = db
        self.ids = count(800_000)
        self.observer = Metrics()
        self.actions = []
        self.read_session_count = 0

    async def authorize(self, request, roles, resource_id, write):
        principal = getattr(request.state, "principal", None)
        if principal is None:
            raise HTTPException(401, detail="unauthorized")
        await core.authorize(request, principal, roles, resource_id, write=write)
        return principal

    async def allocate_id(self):
        return next(self.ids)

    async def command(self, request, principal, route_key, body, if_match, operation):
        identity, fingerprint = op.idempotency(request, principal, body)

        async def work(session):
            code, safe_body, _version = await operation(session, None)
            return code, safe_body

        code, safe_body = await op.command(self.db.session_factory, identity, fingerprint, work)
        return JSONResponse(
            safe_body,
            status_code=code,
            headers={"Cache-Control": "no-store", "ETag": f'"{safe_body["version"]}"'},
        )

    def read_session(self):
        self.read_session_count += 1
        return self.db.session_factory()

    async def read_workflow(self, session, appointment_id):
        return await core.read_workflow(session, appointment_id)

    async def lock_context(self, session, request, principal, appointment_id):
        aid = int(appointment_id)
        booking_row = (await session.execute(
            select(m.appointments).where(m.appointments.c.id == aid).with_for_update()
        )).mappings().first()
        if booking_row is None:
            raise HTTPException(404, detail="not_found")
        hold_rows = (await session.execute(
            select(m.clinical_holds).where(m.clinical_holds.c.appointment_id == aid).with_for_update()
        )).mappings().all()
        workflow_row = (await session.execute(
            select(m.appointment_workflows).where(
                m.appointment_workflows.c.appointment_id == aid
            ).with_for_update()
        )).mappings().first()
        # Frozen order: existing QR rows, then this feature's rows, before later
        # waitlist, queue, journey and audit participants in coordinator wiring.
        await session.execute(select(m.checkin_links.c.id).where(
            m.checkin_links.c.appointment_id == aid
        ).order_by(m.checkin_links.c.id).with_for_update())
        links = table_for()
        await session.execute(select(links.c.id).where(
            links.c.appointment_id == aid
        ).order_by(links.c.id).with_for_update())
        workflows = {aid: dict(workflow_row)} if workflow_row is not None else {}
        return SimpleNamespace(
            bookings={aid: dict(booking_row)},
            workflows=workflows,
            holds={aid: dict(hold_rows[0])} if hold_rows else {},
            plan=SimpleNamespace(appointment_ids=(aid,)),
        )

    def stage_effect(self, session, context, action, resource_id, version, payload):
        self.actions.append((action, resource_id, version, dict(payload)))

    def token_response(self, safe_response, ephemeral_fields):
        value = json.loads(safe_response.body)
        value.update(ephemeral_fields)
        return JSONResponse(
            value,
            status_code=safe_response.status_code,
            headers={
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
                "ETag": safe_response.headers.get("ETag", '"1"'),
            },
        )


def _request(app, path, method="POST", *, body=None, version=1, key=None, principal=None, accept=None):
    headers = []
    if body is not None:
        headers.append((b"content-type", b"application/json"))
    if version is not None:
        headers.append((b"if-match", f'"{version}"'.encode()))
    headers.append((b"idempotency-key", (key or uuid4().hex).encode()))
    if accept:
        headers.append((b"accept", accept.encode()))
    body_bytes = json.dumps(body).encode() if body is not None else b""
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    from starlette.requests import Request

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers,
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 12345),
        "root_path": "",
        "app": app,
        "state": {
            "request_id": uuid4(),
            "correlation_id": uuid4(),
            "traceparent": None,
            "principal": principal,
        },
    }
    return Request(scope, receive)


def _endpoint(app, path, method):
    routes = list(app.routes)
    for route in tuple(routes):
        included = getattr(route, "original_router", None)
        if included is not None:
            routes.extend(included.routes)
    return next(
        route.endpoint
        for route in routes
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set())
    )


def _json(response):
    return json.loads(response.body)


async def _install_test_table(db):
    short_links.register_tables(m.metadata)
    table = table_for()
    settings = db.settings
    owner_engine = create_engine(
        f"postgresql+psycopg://appointment_owner:isolated-test-only@127.0.0.1:{settings.db_port}/{settings.db_name}"
    )
    try:
        with owner_engine.begin() as connection:
            table.create(connection, checkfirst=True)
            connection.exec_driver_sql(
                "GRANT SELECT, INSERT, UPDATE ON short_links TO appointment_app"
            )
    finally:
        owner_engine.dispose()


async def _enroll(db, pid="11", slot_id=1):
    _code, appointment = await booking(db, pid=pid, sid=slot_id)
    aid = int(appointment["id"])
    async with db.session_factory() as session, session.begin():
        await session.execute(update(m.doctor_schedule_snapshots).where(
            m.doctor_schedule_snapshots.c.doctor_id == int(appointment["doctor_id"])
        ).values(policy_snapshot={"timezone": "UTC"}))
    journey_id = op.new_id()
    request = base_request("/synthetic/short-link-workflow")
    async with db.session_factory() as session, session.begin():
        context = await core.lock_context(
            session,
            request,
            core.worker_actor(),
            core.LockPlan(appointment_ids=(aid,)),
        )
        await session.execute(insert(m.journeys).values(
            id=journey_id, appointment_id=aid, patient_id=int(pid), state="active"
        ))
        await core.enroll_workflow(session, context, aid, journey_id)
    return aid


def _make_app(db, ports, *, with_checkin=False):
    app = FastAPI()
    app.state.database = db
    short_links.register_routes(app, ports)
    if with_checkin:
        app.state.domain_client = SimpleNamespace(get=_mock_owner_get)
        checkin.register_routes(app, core)
    return app


async def _mock_owner_get(_request, _principal, owner, path, _scope, schema):
    identity = path.rstrip("/").split("/")[-2]
    if owner == "patient":
        return schema.model_validate({"patient_id": identity, "active": True, "version": 1})
    doctor_id = identity
    return schema.model_validate({
        "doctor_id": doctor_id,
        "staff_user_id": str(100 + int(doctor_id)),
        "active": True,
        "version": 1,
    })


async def _create(app, aid, *, purpose="appointment", principal=None, version=1, key=None):
    principal = principal or patient()
    path = f"/api/v1/appointments/{aid}/short-links"
    request = _request(app, path, body={"purpose": purpose}, version=version, key=key, principal=principal)
    return await _endpoint(app, "/api/v1/appointments/{appointment_id}/short-links", "POST")(
        request, appointment_id=str(aid)
    )


async def _resolve(app, alias, *, principal=None, accept="application/json"):
    path = f"/s/{alias}"
    request = _request(app, path, method="GET", version=None, principal=principal, accept=accept)
    return await _endpoint(app, "/s/{alias}", "GET")(request, alias=alias)


async def _revoke(app, aid, link_id, *, principal=None, version=1, key=None):
    principal = principal or patient()
    path = f"/api/v1/appointments/{aid}/short-links/{link_id}/revoke"
    request = _request(app, path, body={}, version=version, key=key, principal=principal)
    return await _endpoint(
        app,
        "/api/v1/appointments/{appointment_id}/short-links/{link_id}/revoke",
        "POST",
    )(request, appointment_id=str(aid), link_id=str(link_id))


def test_create_resolve_digest_only_and_idempotent_replay(database, current_authority):
    async def work(db):
        await _install_test_table(db)
        aid = await _enroll(db)
        ports = ShortLinksTestPorts(db)
        app = _make_app(db, ports)
        key = uuid4().hex
        created = await _create(app, aid, purpose="check_in", key=key)
        value = _json(created)
        assert created.status_code == 201
        assert value["appointment_id"] == str(aid)
        assert value["purpose"] == "check_in"
        assert value["short_path"].startswith("/s/")
        assert created.headers["Cache-Control"] == "no-store"
        assert created.headers["Referrer-Policy"] == "no-referrer"

        alias = value["short_path"].split("/", 2)[-1]
        resolved = await _resolve(app, alias, principal=patient())
        result = _json(resolved)
        assert resolved.status_code == 200
        assert result == {
            "appointment_id": str(aid),
            "purpose": "check_in",
            "landing_path": f"/patient/check-in#appointment_id={aid}",
            "expires_at": value["expires_at"],
        }
        assert resolved.headers["Cache-Control"] == "no-store"
        assert resolved.headers["Referrer-Policy"] == "no-referrer"

        replay = await _create(app, aid, purpose="check_in", key=key)
        replay_value = _json(replay)
        assert replay.status_code == 409
        assert replay_value["error"]["code"] == "token_response_unavailable"
        assert replay_value["error"]["details"] == {"resource_id": value["id"]}

        async with db.session_factory() as session:
            rows = (await session.execute(select(table_for()))).mappings().all()
            saved = (await session.execute(select(m.idempotency_requests))).mappings().all()
            workflow = await core.read_workflow(session, str(aid))
        assert len(rows) == 1
        assert rows[0]["token_hash"] == short_links.alias_digest(alias)
        assert alias not in str(dict(rows[0]))
        assert alias not in json.dumps([dict(row) for row in saved], default=str)
        assert workflow["version"] == 1
        assert ports.observer.counters
        assert all("alias" not in labels and "appointment_id" not in labels
                   for _name, labels, _value in ports.observer.counters)

    run(database, work)


def test_alias_expiry_revocation_and_hidden_workflow_change(database, current_authority, monkeypatch):
    async def work(db):
        await _install_test_table(db)
        aid = await _enroll(db)
        ports = ShortLinksTestPorts(db)
        app = _make_app(db, ports)
        created = _json(await _create(app, aid))
        link_id = int(created["id"])
        alias = created["short_path"].rsplit("/", 1)[1]

        revoked = await _revoke(app, aid, link_id, version=1)
        assert revoked.status_code == 200
        revoked_value = _json(revoked)
        assert revoked_value["revoked"] is True and revoked_value["version"] == 2
        repeat = await _revoke(app, aid, link_id, version=2)
        assert _json(repeat)["version"] == 2
        hidden = await _resolve(app, alias, principal=patient())
        assert hidden.status_code == 404

        replacement = _json(await _create(app, aid))
        replacement_alias = replacement["short_path"].rsplit("/", 1)[1]
        async with db.session_factory() as session, session.begin():
            await session.execute(update(table_for()).where(
                table_for().c.id == int(replacement["id"])
            ).values(expires_at=func_clock_now_minus_second()))
        expired = await _resolve(app, replacement_alias, principal=patient())
        assert expired.status_code == 404
        hidden_error = _json(hidden)["error"]
        expired_error = _json(expired)["error"]
        assert (expired_error["code"], expired_error["message"]) == (
            hidden_error["code"], hidden_error["message"]
        )
        staged = []
        monkeypatch.setattr(core, "stage_effect", lambda *args: staged.append(args))
        context = SimpleNamespace(
            plan=SimpleNamespace(appointment_ids=(aid,)),
            workflows={aid: {"state": "completed"}},
        )
        async with db.session_factory() as session, session.begin():
            await session.execute(select(m.appointments.c.id).where(
                m.appointments.c.id == aid
            ).with_for_update())
            await session.execute(select(m.checkin_links.c.id).where(
                m.checkin_links.c.appointment_id == aid
            ).with_for_update())
            await session.execute(select(table_for().c.id).where(
                table_for().c.appointment_id == aid
            ).with_for_update())
            session.info["phase3_lock_context"] = context
            await short_links.revoke_for_booking_change(session, context, aid)
        async with db.session_factory() as session:
            row = (await session.execute(select(table_for()).where(
                table_for().c.id == int(replacement["id"])
            ))).mappings().one()
        assert row["revoked_at"] is not None
        assert staged and staged[0][2] == "short_link_revoked"

    run(database, work)


def func_clock_now_minus_second():
    return text("clock_timestamp() - interval '1 second'")


def test_auth_scope_invalid_destination_and_static_redirect(database, current_authority):
    async def work(db):
        await _install_test_table(db)
        aid = await _enroll(db)
        ports = ShortLinksTestPorts(db)
        app = _make_app(db, ports)

        invalid_request = _request(
            app,
            f"/api/v1/appointments/{aid}/short-links",
            body={"purpose": "appointment", "destination_url": "https://evil.invalid"},
            principal=patient(),
        )
        invalid = await _endpoint(app, "/api/v1/appointments/{appointment_id}/short-links", "POST")(
            invalid_request, appointment_id=str(aid)
        )
        assert invalid.status_code == 422
        assert _json(invalid)["error"]["code"] == "validation_error"

        created = _json(await _create(app, aid))
        alias = created["short_path"].rsplit("/", 1)[1]
        wrong_owner = Principal("22", "22", frozenset({"patient"}), 1, "test")
        hidden = await _resolve(app, alias, principal=wrong_owner)
        assert hidden.status_code == 404
        assert _json(hidden)["error"]["code"] == "not_found"
        with pytest.raises(HTTPException) as unauthenticated:
            await _resolve(app, alias, principal=None)
        assert unauthenticated.value.status_code == 401

        malformed = await _resolve(
            app, "../https://evil.invalid", principal=patient(), accept="application/json"
        )
        assert malformed.status_code == 404
        before = ports.read_session_count
        redirect = await _resolve(app, alias, accept="text/html")
        assert redirect.status_code == 303
        assert redirect.headers["location"] == f"/short-link#alias={alias}"
        assert redirect.headers["Cache-Control"] == "no-store"
        assert redirect.headers["Referrer-Policy"] == "no-referrer"
        assert ports.read_session_count == before

    run(database, work)


def test_concurrent_reissue_leaves_one_live_alias_and_retries_forced_collision(database, current_authority, monkeypatch):
    async def work(db):
        await _install_test_table(db)
        aid = await _enroll(db)
        ports = ShortLinksTestPorts(db)
        app = _make_app(db, ports)
        first = _json(await _create(app, aid))
        old_alias = first["short_path"].rsplit("/", 1)[1]
        # Decode using the actual base-62 alphabet.
        old_number = 0
        for char in old_alias:
            old_number = old_number * 62 + short_links.ALIAS_ALPHABET.index(char)
        old_entropy = old_number.to_bytes(16, "big")
        generated = iter([old_entropy, b"\x03" * 16, b"\x04" * 16])
        monkeypatch.setattr(short_links.secrets, "token_bytes", lambda length: next(generated))

        concurrent = await asyncio.gather(
            _create(app, aid, key=uuid4().hex),
            _create(app, aid, key=uuid4().hex),
        )
        assert all(response.status_code == 201 for response in concurrent)
        async with db.session_factory() as session:
            rows = (await session.execute(select(table_for()).where(
                table_for().c.appointment_id == aid
            ).order_by(table_for().c.id))).mappings().all()
        assert len([row for row in rows if row["revoked_at"] is None]) == 1
        assert sum(1 for name, _labels, _value in ports.observer.counters
                   if name == "pulsegrid_short_link_collisions_total") >= 1

    run(database, work)


def test_hash_unique_race_retries_across_appointments(database, current_authority, monkeypatch):
    async def work(db):
        await _install_test_table(db)
        first_aid = await _enroll(db, pid="11", slot_id=1)
        second_aid = await _enroll(db, pid="12", slot_id=3)
        ports = ShortLinksTestPorts(db)
        app = _make_app(db, ports)
        same_entropy = b"\x07" * 16
        tokens = iter([same_entropy, same_entropy, b"\x08" * 16, b"\x09" * 16])
        monkeypatch.setattr(short_links.secrets, "token_bytes", lambda length: next(tokens))
        shared_digest = short_links.alias_digest(short_links.encode_alias(same_entropy))
        original = ShortLinkRepository.by_digest
        barrier = asyncio.Barrier(2)
        calls = 0

        async def synchronized_lookup(repository, token_hash):
            nonlocal calls
            result = await original(repository, token_hash)
            if token_hash == shared_digest and calls < 2:
                calls += 1
                await barrier.wait()
            return result

        monkeypatch.setattr(ShortLinkRepository, "by_digest", synchronized_lookup)
        responses = await asyncio.gather(
            _create(app, first_aid, principal=patient("11"), key=uuid4().hex),
            _create(app, second_aid, principal=patient("12"), key=uuid4().hex),
        )
        assert all(response.status_code == 201 for response in responses)
        async with db.session_factory() as session:
            rows = (await session.execute(select(table_for()).order_by(table_for().c.id))).mappings().all()
        assert len(rows) == 2
        assert len({row["token_hash"] for row in rows}) == 2
        assert any(name == "pulsegrid_short_link_collisions_total"
                   for name, _labels, _value in ports.observer.counters)

    run(database, work)


def test_existing_qr_issue_and_workflow_binding_remain_compatible(database, current_authority):
    async def work(db):
        await _install_test_table(db)
        aid = await _enroll(db)
        ports = ShortLinksTestPorts(db)
        app = _make_app(db, ports, with_checkin=True)
        short = _json(await _create(app, aid))

        qr_request = _request(
            app,
            f"/api/v1/appointments/{aid}/check-in-links",
            body={},
            principal=patient(),
        )
        qr_endpoint = _endpoint(app, "/api/v1/appointments/{appointment_id}/check-in-links", "POST")
        qr_first = _json(await qr_endpoint(
            qr_request, appointment_id=str(aid), body=checkin.EmptyBody(), p=patient()
        ))
        assert checkin.canonical_token(qr_first["token"])
        async with db.session_factory() as session:
            qr_rows = (await session.execute(select(m.checkin_links).where(
                m.checkin_links.c.appointment_id == aid
            ))).mappings().all()
            short_rows = (await session.execute(select(table_for()).where(
                table_for().c.appointment_id == aid
            ))).mappings().all()
            workflow = await core.read_workflow(session, str(aid))
        assert len(qr_rows) == len(short_rows) == 1
        assert qr_rows[0]["token_hash"] == checkin.token_digest(qr_first["token"])
        assert qr_rows[0]["token_hash"] != qr_first["token"]
        assert workflow["version"] == 1
        assert short["version"] == 1

        # Existing QR reissue remains an explicit POST, revokes the previous QR,
        # and advances the workflow version that invalidates the old alias.
        qr_request2 = _request(
            app,
            f"/api/v1/appointments/{aid}/check-in-links",
            body={},
            principal=patient(),
        )
        qr_second = _json(await qr_endpoint(
            qr_request2, appointment_id=str(aid), body=checkin.EmptyBody(), p=patient()
        ))
        assert qr_second["token"] != qr_first["token"]
        old_alias = short["short_path"].rsplit("/", 1)[1]
        assert (await _resolve(app, old_alias, principal=patient())).status_code == 404
        async with db.session_factory() as session:
            qr_rows = (await session.execute(select(m.checkin_links).where(
                m.checkin_links.c.appointment_id == aid
            ).order_by(m.checkin_links.c.created_at, m.checkin_links.c.id))).mappings().all()
            assert qr_rows[0]["revoked_at"] is not None
            assert qr_rows[1]["revoked_at"] is None
            assert qr_rows[1]["token_hash"] == checkin.token_digest(qr_second["token"])

    run(database, work)
