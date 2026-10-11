import asyncio
import json
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import insert, select, text, update

from appointment_service import models as m, operations as op, phase3_core as core
from appointment_service.authorization import Principal
from appointment_service.database import Database
from appointment_service.features.checkin import registration as checkin
from appointment_service.features.checkin.schemas import EmptyBody, StaffCheckinBody, TokenBody
from ..test_concurrency import booking, patient, request, run


class MockOwnerClient:
    def __init__(self):
        self.patient_active = True
        self.doctor_active = True
        self.calls = []

    async def get(self, request, principal, owner, path, scope, schema):
        self.calls.append((owner, path, scope))
        if owner == "patient":
            value = {"patient_id": path.rsplit("/", 2)[-2], "active": self.patient_active, "version": 1}
        else:
            doctor_id = path.rstrip("/").split("/")[-2]
            value = {
                "doctor_id": doctor_id,
                "staff_user_id": str(100 + int(doctor_id)),
                "active": self.doctor_active,
                "version": 1,
            }
        return schema.model_validate(value)


class QueueAdapter:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = 0

    async def allocate_on_checkin(self, session, context):
        self.calls += 1
        if self.fail:
            raise RuntimeError("injected queue failure")
        workflow = next(iter(context.workflows.values()))
        booking_row = context.bookings[workflow["appointment_id"]]
        local_date = context.now.date()
        counter = await session.execute(text(
            "INSERT INTO queue_counters (doctor_id, local_date, next_token) "
            "VALUES (:doctor_id, :local_date, 2) "
            "ON CONFLICT (doctor_id, local_date) DO UPDATE "
            "SET next_token = queue_counters.next_token + 1 "
            "RETURNING next_token - 1"
        ), {"doctor_id": booking_row["doctor_id"], "local_date": local_date})
        token_number = counter.scalar_one()
        entry_id = op.new_id()
        await session.execute(insert(m.queue_entries).values(
            id=entry_id,
            appointment_id=booking_row["id"],
            doctor_id=booking_row["doctor_id"],
            local_date=local_date,
            token_number=token_number,
            state="waiting",
            position=1,
        ))
        return {
            "id": str(entry_id),
            "appointment_id": str(booking_row["id"]),
            "doctor_id": str(booking_row["doctor_id"]),
            "local_date": local_date.isoformat(),
            "token_number": token_number,
            "state": "waiting",
            "position": 1,
            "version": 1,
        }


@pytest.fixture
def current_authority(monkeypatch):
    async def current(_request, principal, roles):
        for role in roles:
            if role in principal.roles:
                return role
        raise HTTPException(403)

    monkeypatch.setattr(core, "current", current)


def make_app(db, queue=None):
    app = FastAPI()
    checkin.register_routes(app, core)
    app.state.database = db
    app.state.domain_client = MockOwnerClient()
    queue_adapter = queue or QueueAdapter()
    app.state.appointment_extensions = {"queue": queue_adapter}
    return app, queue_adapter


def make_request(app, path, method="POST", *, version=1, key=None):
    headers = [(b"idempotency-key", (key or uuid4().hex).encode())]
    if version is not None:
        headers.append((b"if-match", f'"{version}"'.encode()))
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
        },
    }
    from starlette.requests import Request

    return Request(scope)


def endpoint(app, path, method):
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


async def prepare_enrolled(db, patient_id="11", slot_id=1):
    start = op.now() + timedelta(minutes=5)
    async with db.session_factory() as session, session.begin():
        await session.execute(update(m.slots).where(m.slots.c.id == slot_id).values(
            starts_at=start,
            ends_at=start + timedelta(minutes=30),
        ))
    _, appointment = await booking(db, pid=patient_id, sid=slot_id)
    aid = int(appointment["id"])
    journey_id = op.new_id()
    setup_request = request("/synthetic/checkin-enrollment")
    async with db.session_factory() as session, session.begin():
        context = await core.lock_context(
            session,
            setup_request,
            core.worker_actor(),
            core.LockPlan(appointment_ids=(aid,)),
        )
        await session.execute(insert(m.journeys).values(
            id=journey_id,
            appointment_id=aid,
            patient_id=int(patient_id),
            state="active",
        ))
        await core.enroll_workflow(session, context, aid, journey_id)
    return aid


async def call_issue(app, aid, principal=None, *, version=1, key=None):
    principal = principal or patient()
    path = f"/api/v1/appointments/{aid}/check-in-links"
    req = make_request(app, path, version=version, key=key)
    result = await endpoint(app, "/api/v1/appointments/{appointment_id}/check-in-links", "POST")(
        req, appointment_id=str(aid), body=EmptyBody(), p=principal
    )
    return result


async def call_checkin(app, aid, token, principal=None, *, version=1, key=None):
    principal = principal or patient()
    path = f"/api/v1/appointments/{aid}/check-in"
    req = make_request(app, path, version=version, key=key)
    return await endpoint(app, "/api/v1/appointments/{appointment_id}/check-in", "POST")(
        req, appointment_id=str(aid), body=TokenBody(token=token), p=principal
    )


async def call_workflow(app, aid, principal=None):
    principal = principal or patient()
    path = f"/api/v1/appointments/{aid}/workflow"
    req = make_request(app, path, method="GET", version=None)
    return await endpoint(app, "/api/v1/appointments/{appointment_id}/workflow", "GET")(
        req, appointment_id=str(aid), p=principal
    )


def response_json(response):
    return json.loads(response.body)


def test_issue_digest_only_reissue_binding_and_nonsecret_same_key_replay(checkin_database, current_authority):
    async def work(db):
        aid = await prepare_enrolled(db)
        app, _ = make_app(db)
        key = uuid4().hex
        first = response_json(await call_issue(app, aid, key=key))
        token = first["token"]
        assert checkin.canonical_token(token)
        assert first["landing_path"] == checkin.landing_path(str(aid), token)
        assert first["expires_at"]

        replay = await call_issue(app, aid, key=key)
        replay_value = response_json(replay)
        assert replay.status_code == 409
        assert replay_value["error"]["code"] == "token_response_unavailable"
        assert replay_value["error"]["details"] == {"resource_id": first["link_id"]}

        async with db.session_factory() as session:
            links = (await session.execute(text(
                "SELECT token_hash, purpose, consumed_at, revoked_at, workflow_version, schedule_fingerprint "
                "FROM checkin_links WHERE appointment_id = :aid ORDER BY id"
            ), {"aid": aid})).mappings().all()
            stored = (await session.execute(select(m.idempotency_requests))).mappings().all()
            workflow = await core.read_workflow(session, aid)
        assert len(links) == 1
        assert links[0]["token_hash"] == checkin.token_digest(token)
        assert links[0]["token_hash"] != token
        assert links[0]["purpose"] == "check_in"
        assert links[0]["workflow_version"] == 1
        assert len(links[0]["schedule_fingerprint"]) == 64
        assert workflow["version"] == 1
        assert token not in json.dumps([dict(row) for row in stored], default=str)

        second = response_json(await call_issue(app, aid, version=1))
        assert second["token"] != token
        async with db.session_factory() as session:
            link_rows = (await session.execute(text(
                "SELECT token_hash, revoked_at, workflow_version FROM checkin_links "
                "WHERE appointment_id = :aid ORDER BY created_at, id"
            ), {"aid": aid})).mappings().all()
            workflow = await core.read_workflow(session, aid)
        assert link_rows[0]["revoked_at"] is not None
        assert link_rows[1]["revoked_at"] is None
        assert link_rows[1]["workflow_version"] == 2
        assert workflow["version"] == 2

    run(checkin_database, work)


def test_workflow_get_returns_scoped_checkin_status_without_mutation(checkin_database, current_authority):
    async def work(db):
        aid = await prepare_enrolled(db)
        app, _ = make_app(db)
        response = await call_workflow(app, aid)
        value = response_json(response)
        assert response.status_code == 200
        assert response.headers["ETag"] == '"1"'
        assert response.headers["Cache-Control"] == "no-store"
        assert value["state"] == "booked"
        assert value["appointment_id"] == str(aid)
        async with db.session_factory() as session:
            workflow = await core.read_workflow(session, aid)
            links = (await session.execute(select(m.checkin_links))).all()
            queues = (await session.execute(select(m.queue_entries))).all()
        assert workflow["version"] == 1
        assert links == [] and queues == []

    run(checkin_database, work)


def test_successful_redemption_is_atomic_and_replay_returns_saved_result(checkin_database, current_authority):
    async def work(db):
        aid = await prepare_enrolled(db)
        app, queue = make_app(db)
        issued = response_json(await call_issue(app, aid))
        key = uuid4().hex
        first_response = await call_checkin(app, aid, issued["token"], key=key)
        first = response_json(first_response)
        assert first_response.status_code == 200
        assert first_response.headers["ETag"] == f'"{first["workflow"]["version"]}"'
        assert first["workflow"]["state"] == "checked_in"
        assert first["workflow"]["queue_entry_id"] == first["queue_entry"]["id"]
        assert first["queue_entry"]["state"] == "waiting"
        assert first["queue_entry"]["appointment_id"] == str(aid)
        assert queue.calls == 1

        replay_response = await call_checkin(app, aid, issued["token"], key=key)
        assert response_json(replay_response) == first
        assert replay_response.headers["ETag"] == first_response.headers["ETag"]
        assert len(app.state.domain_client.calls) == 2
        async with db.session_factory() as session:
            link = (await session.execute(text(
                "SELECT consumed_at, revoked_at FROM checkin_links WHERE appointment_id = :aid"
            ), {"aid": aid})).mappings().one()
            queue_rows = (await session.execute(select(m.queue_entries))).all()
            events = (await session.execute(select(m.outbox_events.c.event_type))).scalars().all()
            saved = (await session.execute(select(m.idempotency_requests))).mappings().all()
        assert link["consumed_at"] is not None and link["revoked_at"] is None
        assert len(queue_rows) == 1
        assert events.count("appointment.workflow.checked_in.v1") == 1
        assert issued["token"] not in json.dumps([dict(row) for row in saved], default=str)

        with pytest.raises(checkin.CheckinFailure) as distinct_key:
            await call_checkin(app, aid, issued["token"])
        assert distinct_key.value.code == "token_invalid"
        assert queue.calls == 1

    run(checkin_database, work)


def test_queue_failure_rolls_back_token_consumption_and_workflow(checkin_database, current_authority):
    async def work(db):
        aid = await prepare_enrolled(db)
        app, _ = make_app(db, QueueAdapter(fail=True))
        issued = response_json(await call_issue(app, aid))
        with pytest.raises(RuntimeError, match="injected queue failure"):
            await call_checkin(app, aid, issued["token"])
        async with db.session_factory() as session:
            link = (await session.execute(text(
                "SELECT consumed_at FROM checkin_links WHERE appointment_id = :aid"
            ), {"aid": aid})).mappings().one()
            workflow = await core.read_workflow(session, aid)
            rows = (await session.execute(select(m.queue_entries))).all()
        assert link["consumed_at"] is None
        assert workflow["state"] == "booked" and workflow["version"] == 1
        assert rows == []

    run(checkin_database, work)


def test_expired_revoked_and_consumed_links_have_same_token_error(checkin_database, current_authority):
    async def work(db):
        aid = await prepare_enrolled(db)
        app, _ = make_app(db)
        issued = response_json(await call_issue(app, aid))
        async with db.session_factory() as session, session.begin():
            await session.execute(text(
                "UPDATE checkin_links SET expires_at = :expiry WHERE appointment_id = :aid"
            ), {"expiry": op.now() - timedelta(seconds=1), "aid": aid})
        with pytest.raises(checkin.CheckinFailure) as expired:
            await call_checkin(app, aid, issued["token"])
        assert expired.value.code == "token_invalid"

        async with db.session_factory() as session, session.begin():
            await session.execute(text(
                "UPDATE checkin_links SET expires_at = :expiry, revoked_at = :now "
                "WHERE appointment_id = :aid"
            ), {"expiry": op.now() + timedelta(minutes=1), "now": op.now(), "aid": aid})
        with pytest.raises(checkin.CheckinFailure) as revoked:
            await call_checkin(app, aid, issued["token"])
        assert revoked.value.code == "token_invalid"

    run(checkin_database, work)


@pytest.mark.parametrize(
    "case,expected",
    [
        ("before_start", "checkin_window_closed"),
        ("exact_start", None),
        ("before_end", None),
        ("exact_end", "checkin_window_closed"),
    ],
)
def test_window_boundary_inclusivity(
    checkin_database, current_authority, monkeypatch,
    case, expected,
):
    async def work(db):
        aid = await prepare_enrolled(db)
        async with db.session_factory() as session:
            workflow = await core.read_workflow(session, aid)
        window_start = workflow["window_starts_at"]
        window_end = workflow["window_ends_at"]
        issue_time = window_start - timedelta(seconds=2)
        check_time = (
            window_start - timedelta(microseconds=1)
            if case == "before_start"
            else window_start
            if case == "exact_start"
            else window_end - timedelta(microseconds=1)
            if case == "before_end"
            else window_end
        )
        app, _ = make_app(db)
        monkeypatch.setattr(core.op, "now", lambda: issue_time)
        issued = response_json(await call_issue(app, aid))
        monkeypatch.setattr(core.op, "now", lambda: check_time)
        if expected:
            with pytest.raises(checkin.CheckinFailure) as result:
                await call_checkin(app, aid, issued["token"])
            assert result.value.code == expected
        else:
            result = response_json(await call_checkin(app, aid, issued["token"]))
            assert result["workflow"]["state"] == "checked_in"

    run(checkin_database, work)


def test_inactive_patient_or_doctor_blocks_redemption_before_mutation(checkin_database, current_authority):
    async def work(db):
        aid = await prepare_enrolled(db)
        app, queue = make_app(db)
        issued = response_json(await call_issue(app, aid))
        app.state.domain_client.patient_active = False
        with pytest.raises(checkin.CheckinFailure) as patient_inactive:
            await call_checkin(app, aid, issued["token"])
        assert patient_inactive.value.code == "invalid_transition"
        app.state.domain_client.patient_active = True
        app.state.domain_client.doctor_active = False
        with pytest.raises(checkin.CheckinFailure) as doctor_inactive:
            await call_checkin(app, aid, issued["token"])
        assert doctor_inactive.value.code == "invalid_transition"
        async with db.session_factory() as session:
            workflow = await core.read_workflow(session, aid)
            link = (await session.execute(text(
                "SELECT consumed_at FROM checkin_links WHERE appointment_id = :aid"
            ), {"aid": aid})).mappings().one()
        assert workflow["state"] == "booked" and link["consumed_at"] is None
        assert queue.calls == 0

    run(checkin_database, work)


def test_invalid_booking_and_authorization_are_rejected_without_token_probe(checkin_database, current_authority):
    async def work(db):
        aid = await prepare_enrolled(db)
        app, queue = make_app(db)
        issued = response_json(await call_issue(app, aid))
        stranger = Principal("12", "12", frozenset({"patient"}), 1, "synthetic-test-token")
        with pytest.raises(HTTPException) as concealed:
            await call_checkin(app, aid, "not-the-token", principal=stranger)
        assert concealed.value.status_code == 404
        assert app.state.domain_client.calls == []

        async with db.session_factory() as session, session.begin():
            await session.execute(update(m.appointments).where(m.appointments.c.id == aid).values(state="cancelled"))
        with pytest.raises(checkin.CheckinFailure) as invalid:
            await call_checkin(app, aid, issued["token"])
        assert invalid.value.code == "invalid_transition"
        assert queue.calls == 0

    run(checkin_database, work)


def test_patient_cannot_use_receptionist_fallback_and_staff_fallback_revokes_links(checkin_database, current_authority):
    async def work(db):
        aid = await prepare_enrolled(db)
        app, queue = make_app(db)
        issued = response_json(await call_issue(app, aid))
        patient_req = make_request(app, f"/api/v1/appointments/{aid}/staff-check-in")
        patient_endpoint = endpoint(app, "/api/v1/appointments/{appointment_id}/staff-check-in", "POST")
        with pytest.raises(HTTPException) as denied:
            await patient_endpoint(
                patient_req,
                appointment_id=str(aid),
                body=StaffCheckinBody(reason="Patient supplied reason"),
                p=patient(),
            )
        assert denied.value.status_code == 403

        receptionist = Principal("200", None, frozenset({"receptionist"}), 1, "synthetic-test-token")
        staff_req = make_request(app, f"/api/v1/appointments/{aid}/staff-check-in")
        staff_result = await patient_endpoint(
            staff_req,
            appointment_id=str(aid),
            body=StaffCheckinBody(reason="Verified identity at reception"),
            p=receptionist,
        )
        value = response_json(staff_result)
        assert value["workflow"]["state"] == "checked_in"
        assert queue.calls == 1
        async with db.session_factory() as session:
            link = (await session.execute(text(
                "SELECT revoked_at, consumed_at FROM checkin_links WHERE appointment_id = :aid"
            ), {"aid": aid})).mappings().one()
            events = (await session.execute(select(m.outbox_events.c.event_type))).scalars().all()
            audit = (await session.execute(select(m.audit_entries.c.canonical_metadata))).mappings().all()
        assert link["revoked_at"] is not None and link["consumed_at"] is None
        assert events.count("appointment.workflow.checked_in.v1") == 1
        assert all("Verified identity at reception" not in json.dumps(dict(row)) for row in audit)
        with pytest.raises(checkin.CheckinFailure) as stale_qr:
            await call_checkin(app, aid, issued["token"], version=1)
        assert stale_qr.value.code == "token_invalid"

    run(checkin_database, work)


@pytest.mark.parametrize("change_kind", ["cancel", "reschedule"])
def test_revoke_hook_invalidates_links_for_cancel_and_reschedule(
    checkin_database, current_authority, change_kind, monkeypatch
):
    async def work(db):
        aid = await prepare_enrolled(db)
        app, _ = make_app(db)
        issued = response_json(await call_issue(app, aid))
        change_request = request(f"/synthetic/checkin-booking-change/{change_kind}")
        async with db.session_factory() as session, session.begin():
            context = await core.lock_context(
                session,
                change_request,
                core.worker_actor(),
                core.LockPlan(appointment_ids=(aid,)),
            )
            await checkin.revoke_for_booking_change(session, context)
        async with db.session_factory() as session:
            link = (await session.execute(text(
                "SELECT revoked_at FROM checkin_links WHERE appointment_id = :aid"
            ), {"aid": aid})).mappings().one()
        assert link["revoked_at"] is not None
        with pytest.raises(checkin.CheckinFailure) as invalid:
            await call_checkin(app, aid, issued["token"], version=1)
        assert invalid.value.code == "token_invalid"

    run(checkin_database, work)


def test_concurrent_scans_same_key_replay_and_distinct_key_single_use(checkin_database, current_authority):
    async def work(db):
        aid = await prepare_enrolled(db)
        app, queue = make_app(db)
        issued = response_json(await call_issue(app, aid))
        second_database = Database(db.settings)
        await second_database.start()
        app2, queue2 = make_app(second_database)
        try:
            key = uuid4().hex
            same_key_calls = [
                call_checkin(app if index % 2 == 0 else app2, aid, issued["token"], key=key)
                for index in range(12)
            ]
            same_key = await asyncio.gather(*same_key_calls)
            values = [response_json(result) for result in same_key]
            assert all(value == values[0] for value in values)
            assert queue.calls + queue2.calls == 1

            aid2 = await prepare_enrolled(db, patient_id="12", slot_id=3)
            second_issue = response_json(await call_issue(app2, aid2, principal=patient("12")))
            distinct_calls = [
                call_checkin(app if index % 2 == 0 else app2, aid2, second_issue["token"],
                             principal=patient("12"))
                for index in range(12)
            ]
            results = await asyncio.gather(*distinct_calls, return_exceptions=True)
            assert sum(not isinstance(result, BaseException) for result in results) == 1
            errors = [result for result in results if isinstance(result, checkin.CheckinFailure)]
            assert len(errors) == 11 and all(error.code == "token_invalid" for error in errors)
            assert queue.calls + queue2.calls == 2
            async with db.session_factory() as session:
                entries = (await session.execute(select(m.queue_entries))).all()
            assert len(entries) == 2
        finally:
            await second_database.close()

    run(checkin_database, work)
