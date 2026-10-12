"""Phase 2 PostgreSQL workflow checks using an explicitly isolated test database."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError

from pharmacy_service import authorization, integrations, event_delivery
from pharmacy_service import operations as pharmacy_operations
from pharmacy_service.authorization import Principal, authenticated_user
from pharmacy_service.database import Database
from pharmacy_service.main import create_app
from pharmacy_service.settings import Settings


TEST_PRINCIPALS = {
    "pharmacist": Principal("601", None, frozenset({"pharmacist"}), 1, "staff-access"),
    "patient": Principal("701", "201", frozenset({"patient"}), 1, "patient-access"),
    "other_patient": Principal("702", "202", frozenset({"patient"}), 1, "other-access"),
    "inactive_pharmacist": Principal("603", None, frozenset({"pharmacist"}), 1, "inactive-access"),
    "doctor": Principal("801", None, frozenset({"doctor"}), 1, "doctor-access"),
    "billing": Principal("901", None, frozenset({"billing_staff"}), 1, "billing-access"),
}


class FakeVerifier:
    def user(self, token):
        for principal in TEST_PRINCIPALS.values():
            if principal.access_token == token:
                return principal
        raise HTTPException(401)

    def service(self, token, scope):
        allowed = {
            ("records-service", "medicines:validate"): "records",
            ("billing-service", "dispensings:charge-context"): "billing",
            ("appointment-service", "workflow:pharmacy-read"): "appointment",
        }
        caller = allowed.get((token, scope))
        if caller is None:
            raise HTTPException(403)
        return caller


def _database_configuration(monkeypatch):
    raw_url = os.environ.get("PULSEGRID_PHARMACY_TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("PULSEGRID_PHARMACY_TEST_DATABASE_URL is not configured")
    database_url = make_url(raw_url)
    if not database_url.database or not database_url.database.endswith("_test"):
        pytest.fail("Pharmacy workflow tests require a database name ending in _test")
    if database_url.drivername not in {"postgresql", "postgresql+psycopg"}:
        pytest.fail("Pharmacy workflow tests require PostgreSQL with Psycopg")
    database_url = database_url.set(drivername="postgresql+psycopg")
    database_name = database_url.database
    db_values = {
        "DB_HOST": database_url.host or "localhost",
        "DB_PORT": str(database_url.port or 5432),
        "DB_NAME": database_name,
        "DB_USER": database_url.username or "",
        "DB_PASSWORD": database_url.password or "test-only",
    }
    for name, value in db_values.items():
        monkeypatch.setenv(f"PULSEGRID_PHARMACY_{name}", value)
    settings = Settings(
        db_host=db_values["DB_HOST"],
        db_port=int(db_values["DB_PORT"]),
        db_name=db_values["DB_NAME"],
        db_user=db_values["DB_USER"],
        db_password=db_values["DB_PASSWORD"],
    )
    return database_url, settings


@pytest.fixture
def pharmacy_client(monkeypatch):
    database_url, settings = _database_configuration(monkeypatch)
    package_root = Path(__file__).parents[1]
    alembic_config = Config(str(package_root / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(package_root / "migrations"))
    command.upgrade(alembic_config, "head")

    engine = create_engine(database_url, hide_parameters=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE TABLE dispensing_items, dispensings, stock_movements, "
                "reservation_items, reservations, prescription_item_snapshots, "
                "prescription_snapshots, inventory_batches, medicines, "
                "idempotency_requests, inbox_events, outbox_events, audit_entries, "
                "audit_heads CASCADE"
            )
        )

    app = create_app(settings)
    app.state.auth_verifier = FakeVerifier()
    role_by_user = {principal.user_id: principal.roles for principal in TEST_PRINCIPALS.values()}

    def authority_handler(request):
        payload = json.loads(request.content)
        roles = role_by_user.get(payload["subject_user_id"], frozenset())
        allowed = payload["required_role"] in roles
        if payload["subject_user_id"] == TEST_PRINCIPALS["inactive_pharmacist"].user_id:
            allowed = False
        return __import__("httpx").Response(
            200,
            json={
                "active": allowed,
                "allowed": allowed,
                "current_auth_version": payload["auth_version"],
            },
        )

    def records_handler(request):
        if request.url.path.startswith("/internal/v1/prescriptions/"):
            return __import__("httpx").Response(
                200, json=app.state.records_context_payload
            )
        return __import__("httpx").Response(404, json={"error": "not_found"})

    app.state.internal_transport = __import__("httpx").MockTransport(authority_handler)
    app.state.records_transport = __import__("httpx").MockTransport(records_handler)
    app.state.records_context_payload = None

    def authenticated_override(request: Request):
        authorization_header = request.headers.get("Authorization", "")
        token = authorization_header.removeprefix("Bearer ")
        principal = TEST_PRINCIPALS.get(token)
        if principal is None:
            raise HTTPException(401)
        return principal

    app.dependency_overrides[authenticated_user] = authenticated_override
    monkeypatch.setattr(
        authorization,
        "service_token",
        lambda _config, _scope, target="patient": f"service-for-{target}",
    )
    monkeypatch.setattr(
        integrations,
        "service_token",
        lambda _config, _scope, target="patient": f"service-for-{target}",
    )
    try:
        with TestClient(app) as client:
            yield client, engine, app
    finally:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "TRUNCATE TABLE dispensing_items, dispensings, stock_movements, "
                    "reservation_items, reservations, prescription_item_snapshots, "
                    "prescription_snapshots, inventory_batches, medicines, "
                    "idempotency_requests, inbox_events, outbox_events, audit_entries, "
                    "audit_heads CASCADE"
                )
            )
        engine.dispose()


def _headers(actor="pharmacist", **extra):
    return {"Authorization": f"Bearer {actor}", **extra}


def _new_medicine(client):
    response = client.post(
        "/api/v1/pharmacy/medicines",
        json={"sku": "MED-101", "name": "  Amoxicillin  "},
        headers=_headers(**{"Idempotency-Key": "medicine-create-key-0001"}),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _add_stock(client, medicine_id, quantity, *, key="stock-adjustment-key-0001"):
    expiry = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()
    return client.post(
        "/api/v1/pharmacy/inventory-adjustments",
        json={
            "medicine_id": medicine_id,
            "batch_code": "LOT-101",
            "expires_on": expiry,
            "delta": quantity,
            "reason": "Initial synthetic stock",
            "expected_batch_version": 0,
        },
        headers=_headers(**{"Idempotency-Key": key}),
    )


def _set_prescription_context(app, medicine_id, *, state="issued", version=1):
    app.state.records_context_payload = {
        "prescription_id": "301",
        "consultation_id": "302",
        "appointment_id": "501",
        "patient_id": "201",
        "journey_id": None,
        "revision": 1,
        "state": state,
        "items": [{"id": "401", "medicine_id": medicine_id, "quantity": 5}],
        "version": version,
    }


def _reserve(client):
    return client.post(
        "/api/v1/pharmacy/reservations",
        json={"prescription_id": "301", "items": [{"prescription_item_id": "401", "quantity": 3}]},
        headers=_headers(
            "patient", **{"Idempotency-Key": "reservation-create-key-001"}
        ),
    )


def test_stock_adjustment_is_idempotent_audited_and_adjusted_under_version_lock(
    pharmacy_client,
):
    client, engine, _app = pharmacy_client
    medicine = _new_medicine(client)
    result = _add_stock(client, medicine["id"], 10)
    assert result.status_code == 201, result.text
    assert result.json()["batch"]["on_hand"] == 10

    replay = _add_stock(client, medicine["id"], 10)
    assert replay.status_code == 201
    assert replay.json() == result.json()

    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM stock_movements")) == 1
        assert connection.scalar(text("SELECT count(*) FROM outbox_events")) == 2
        assert connection.scalar(text("SELECT count(*) FROM audit_entries")) == 2
        assert connection.scalar(text("SELECT count(*) FROM idempotency_requests")) == 2

    def decrement(key):
        return client.post(
            "/api/v1/pharmacy/inventory-adjustments",
            json={
                "medicine_id": medicine["id"],
                "batch_code": "LOT-101",
                "expires_on": result.json()["batch"]["expires_on"],
                "delta": -7,
                "reason": "Concurrent stock issue",
                "expected_batch_version": 1,
            },
            headers=_headers(**{"Idempotency-Key": key}),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(
            pool.map(decrement, ["concurrent-adjust-key-01", "concurrent-adjust-key-02"])
        )
    assert sorted(reply.status_code for reply in replies) == [201, 412]
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT on_hand, reserved, version FROM inventory_batches")
        ).one()
        assert tuple(row) == (3, 0, 2)


def test_insufficient_stock_and_reserved_stock_cannot_be_adjusted_below_zero(
    pharmacy_client,
):
    client, engine, app = pharmacy_client
    medicine = _new_medicine(client)
    assert _add_stock(client, medicine["id"], 1).status_code == 201
    _set_prescription_context(app, medicine["id"])

    shortage = _reserve(client)
    assert shortage.status_code == 409
    assert shortage.json()["error"]["code"] == "insufficient_stock"
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT on_hand, reserved FROM inventory_batches")
        ).one()
        assert tuple(row) == (1, 0)
        assert connection.scalar(text("SELECT count(*) FROM reservations")) == 0

    # Replace the test batch with a larger amount for the reserved-stock check.
    update = client.post(
        "/api/v1/pharmacy/inventory-adjustments",
        json={
            "medicine_id": medicine["id"],
            "batch_code": "LOT-101",
            "expires_on": (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat(),
            "delta": 4,
            "reason": "Stock receipt",
            "expected_batch_version": 1,
        },
        headers=_headers(**{"Idempotency-Key": "stock-increase-key-0001"}),
    )
    assert update.status_code == 201
    reserved = _reserve(client)
    assert reserved.status_code == 201, reserved.text
    batch_version = update.json()["batch"]["version"] + 1
    blocked = client.post(
        "/api/v1/pharmacy/inventory-adjustments",
        json={
            "medicine_id": medicine["id"],
            "batch_code": "LOT-101",
            "expires_on": update.json()["batch"]["expires_on"],
            "delta": -3,
            "reason": "Would consume reserved units",
            "expected_batch_version": batch_version,
        },
        headers=_headers(**{"Idempotency-Key": "reserved-stock-key-0001"}),
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "stock_reserved"
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT on_hand, reserved FROM inventory_batches")
        ).one()
        assert tuple(row) == (5, 3)


def test_fulfillment_duplicate_retry_revocation_and_billing_context(pharmacy_client):
    client, engine, app = pharmacy_client
    medicine = _new_medicine(client)
    assert _add_stock(client, medicine["id"], 10).status_code == 201
    _set_prescription_context(app, medicine["id"])
    reservation = _reserve(client)
    assert reservation.status_code == 201, reservation.text
    reservation_id = reservation.json()["id"]

    headers = _headers(
        **{
            "If-Match": reservation.headers["etag"],
            "Idempotency-Key": "dispense-retry-key-0001",
        }
    )
    first = client.post(
        f"/api/v1/pharmacy/reservations/{reservation_id}/dispense",
        json={},
        headers=headers,
    )
    assert first.status_code == 201, first.text
    duplicate = client.post(
        f"/api/v1/pharmacy/reservations/{reservation_id}/dispense",
        json={},
        headers=headers,
    )
    assert duplicate.status_code == 201
    assert duplicate.json() == first.json()

    # A new key after response retention still resolves to the durable dispensing.
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE idempotency_requests SET expires_at = now() "
                "WHERE key = 'dispense-retry-key-0001'"
            )
        )
    after_retention = client.post(
        f"/api/v1/pharmacy/reservations/{reservation_id}/dispense",
        json={},
        headers=_headers(
            **{
                "If-Match": '"2"',
                "Idempotency-Key": "dispense-new-key-after-ttl",
            }
        ),
    )
    assert after_retention.status_code == 201, after_retention.text
    assert after_retention.json() == first.json()

    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT on_hand, reserved FROM inventory_batches")
        ).one()
        assert tuple(row) == (7, 0)
        assert connection.scalar(text("SELECT count(*) FROM dispensings")) == 1
        assert connection.scalar(text("SELECT count(*) FROM dispensing_items")) == 1
        event = connection.execute(
            text(
                "SELECT envelope->'payload'->>'appointment_id', "
                "envelope->'payload'->>'state', attempt_count, published_at "
                "FROM outbox_events WHERE event_type='pharmacy.reservation.dispensed.v1'"
            )
        ).one()
        assert tuple(event) == ("501", "dispensed", 0, None)

    charge = client.get(
        f"/internal/v1/dispensings/{first.json()['id']}/charge-context",
        headers={
            "Authorization": "Bearer billing-service",
            "X-Delegated-Authorization": "Bearer billing-access",
        },
    )
    assert charge.status_code == 200, charge.text
    assert charge.headers["etag"] == first.headers["etag"]
    assert charge.json()["appointment_id"] == "501"
    assert charge.json()["items"][0]["charge_code"] == f"medicine:{medicine['id']}"

    _set_prescription_context(app, medicine["id"], state="revoked", version=2)
    revalidation = client.post(
        f"/api/v1/pharmacy/reservations/{reservation_id}/revalidate",
        json={},
        headers=_headers(
            **{
                "If-Match": '"2"',
                "Idempotency-Key": "reservation-revalidate-key-01",
            }
        ),
    )
    assert revalidation.status_code == 200
    assert revalidation.json()["state"] == "dispensed"


def test_dispense_and_outbox_roll_back_together(pharmacy_client, monkeypatch):
    client, engine, app = pharmacy_client
    medicine = _new_medicine(client)
    assert _add_stock(client, medicine["id"], 10).status_code == 201
    _set_prescription_context(app, medicine["id"])
    reservation = _reserve(client)
    assert reservation.status_code == 201, reservation.text
    reservation_id = reservation.json()["id"]
    key = "dispense-rollback-atomic-key-1"
    headers = _headers(
        **{"If-Match": reservation.headers["etag"], "Idempotency-Key": key}
    )
    original_append_outbox = pharmacy_operations.append_outbox

    async def append_then_abort(session, request, **kwargs):
        await original_append_outbox(session, request, **kwargs)
        if kwargs.get("action") == "reservation.dispensed":
            raise HTTPException(503, "synthetic transactional rollback")

    with monkeypatch.context() as patch:
        patch.setattr(pharmacy_operations, "append_outbox", append_then_abort)
        failed = client.post(
            f"/api/v1/pharmacy/reservations/{reservation_id}/dispense",
            json={},
            headers=headers,
        )
    assert failed.status_code == 503
    with engine.connect() as connection:
        assert connection.scalar(
            text("SELECT state FROM reservations WHERE id=:id"),
            {"id": int(reservation_id)},
        ) == "reserved"
        assert connection.scalar(text("SELECT count(*) FROM dispensings")) == 0
        assert connection.scalar(
            text(
                "SELECT count(*) FROM outbox_events "
                "WHERE event_type='pharmacy.reservation.dispensed.v1'"
            )
        ) == 0
        assert tuple(connection.execute(
            text("SELECT on_hand, reserved FROM inventory_batches")
        ).one()) == (10, 3)

    retried = client.post(
        f"/api/v1/pharmacy/reservations/{reservation_id}/dispense",
        json={},
        headers=headers,
    )
    assert retried.status_code == 201, retried.text
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM dispensings")) == 1
        assert connection.scalar(
            text(
                "SELECT count(*) FROM outbox_events "
                "WHERE event_type='pharmacy.reservation.dispensed.v1'"
            )
        ) == 1
def test_revoked_prescription_revalidation_releases_unfilled_stock(pharmacy_client):
    client, engine, app = pharmacy_client
    medicine = _new_medicine(client)
    assert _add_stock(client, medicine["id"], 5).status_code == 201
    _set_prescription_context(app, medicine["id"])
    reservation = _reserve(client)
    assert reservation.status_code == 201, reservation.text

    _set_prescription_context(app, medicine["id"], state="revoked", version=2)
    released = client.post(
        f"/api/v1/pharmacy/reservations/{reservation.json()['id']}/revalidate",
        json={},
        headers=_headers(
            **{
                "If-Match": reservation.headers["etag"],
                "Idempotency-Key": "revalidate-revoked-key-001",
            }
        ),
    )
    assert released.status_code == 200, released.text
    assert released.json()["state"] == "released"
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT on_hand, reserved FROM inventory_batches")
        ).one()
        assert tuple(row) == (5, 0)
        assert connection.scalar(
            text("SELECT reserved_quantity FROM prescription_item_snapshots WHERE item_id = 401")
        ) == 0


def test_patients_can_read_only_their_own_reservations(pharmacy_client):
    client, engine, app = pharmacy_client
    medicine = _new_medicine(client)
    assert _add_stock(client, medicine["id"], 5).status_code == 201
    _set_prescription_context(app, medicine["id"])
    reservation = _reserve(client)
    assert reservation.status_code == 201, reservation.text
    reservation_id = reservation.json()["id"]

    hidden = client.get(
        f"/api/v1/pharmacy/reservations/{reservation_id}",
        headers=_headers("other_patient"),
    )
    assert hidden.status_code == 404
    owned = client.get(
        f"/api/v1/pharmacy/reservations/{reservation_id}",
        headers=_headers("patient"),
    )
    assert owned.status_code == 200
    assert owned.headers["cache-control"] == "no-store"
    assert owned.json()["patient_id"] == "201"
    with engine.connect() as connection:
        assert connection.scalar(
            text("SELECT count(*) FROM audit_entries WHERE canonical_metadata->>'result' = 'denied'")
        ) == 1


def test_authorization_current_role_and_database_constraints(pharmacy_client):
    client, engine, _app = pharmacy_client
    medicine = _new_medicine(client)
    denied = client.post(
        "/api/v1/pharmacy/inventory-adjustments",
        json={
            "medicine_id": medicine["id"],
            "batch_code": "LOT-101",
            "expires_on": (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat(),
            "delta": 2,
            "reason": "Patient cannot receive stock",
            "expected_batch_version": 0,
        },
        headers=_headers("patient", **{"Idempotency-Key": "forbidden-stock-key-01"}),
    )
    assert denied.status_code == 403

    inactive = client.get(
        "/api/v1/pharmacy/inventory",
        headers=_headers("inactive_pharmacist"),
    )
    assert inactive.status_code == 403

    stock = _add_stock(client, medicine["id"], 2)
    assert stock.status_code == 201
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE inventory_batches SET on_hand = -1")
            )

    with engine.connect() as connection:
        with connection.begin():
            connection.execute(text("SET ROLE pharmacy_app"))
            can_update_audit = connection.scalar(
                text("SELECT has_table_privilege(current_user, 'audit_entries', 'UPDATE')")
            )
            assert can_update_audit is False
            assert connection.scalar(
                text(
                    "SELECT has_column_privilege(current_user, 'outbox_events', "
                    "'claimed_by', 'UPDATE')"
                )
            ) is True
            assert connection.scalar(
                text(
                    "SELECT has_column_privilege(current_user, 'outbox_events', "
                    "'envelope', 'UPDATE')"
                )
            ) is False
            connection.execute(
                text("SELECT event_id FROM outbox_events ORDER BY event_id LIMIT 1 FOR UPDATE")
            ).all()
            connection.execute(
                text(
                    "UPDATE outbox_events SET claimed_by='privilege-check' "
                    "WHERE event_id=(SELECT event_id FROM outbox_events ORDER BY event_id LIMIT 1)"
                )
            )
            connection.execute(
                text(
                    "UPDATE outbox_events SET claimed_by=NULL "
                    "WHERE claimed_by='privilege-check'"
                )
            )
            with pytest.raises(DBAPIError):
                connection.execute(text("UPDATE audit_entries SET entry_hash = entry_hash"))


def test_records_medicine_validation_private_contract(pharmacy_client):
    client, _engine, _app = pharmacy_client
    medicine = _new_medicine(client)
    response = client.post(
        "/internal/v1/medicines/validate",
        json={"medicine_ids": [medicine["id"]]},
        headers={
            "Authorization": "Bearer records-service",
            "X-Delegated-Authorization": "Bearer doctor-access",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "items": [
            {
                "id": medicine["id"],
                "active": True,
                "catalog_version": 1,
                "name": "Amoxicillin",
            }
        ]
    }


def test_fulfillment_snapshot_and_patient_scope(pharmacy_client):
    client, _engine, app = pharmacy_client
    medicine = _new_medicine(client)
    assert _add_stock(client, medicine["id"], 5).status_code == 201
    _set_prescription_context(app, medicine["id"])
    reservation = _reserve(client)
    assert reservation.status_code == 201, reservation.text
    url = "/api/v1/pharmacy/prescriptions/301/fulfillment"
    own = client.get(url, headers=_headers("patient"))
    assert own.status_code == 200, own.text
    assert own.json()["items"][0]["reserved_quantity"] == 3
    assert own.json()["items"][0]["dispensed_quantity"] == 0
    assert client.get(url, headers=_headers("other_patient")).status_code == 404
    private_url = "/internal/v1/appointments/501/workflow-snapshot?patient_id=201&prescription_id=301"
    private = client.get(private_url, headers={"Authorization": "Bearer appointment-service"})
    assert private.status_code == 200, private.text
    assert private.json()["snapshot"]["fulfillment"]["prescription_id"] == "301"
    assert private.json()["next_cursor"] is None
    assert client.get(private_url, headers={"Authorization": "Bearer records-service"}).status_code == 403
    assert client.get(private_url.replace("patient_id=201", "patient_id=202"),
                      headers={"Authorization": "Bearer appointment-service"}).status_code == 404


def _publisher_test_event(event_id: int, aggregate_id: int) -> dict:
    return {
        "event_id": str(event_id),
        "event_type": "pharmacy.reservation.dispensed.v1",
        "schema_version": 1,
        "producer": "pharmacy",
        "aggregate_type": "reservation",
        "aggregate_id": str(aggregate_id),
        "aggregate_version": 1,
        "occurred_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "correlation_id": str(uuid4()),
        "request_id": str(uuid4()),
        "causation_id": None,
        "traceparent": None,
        "payload": {
            "resource_id": str(aggregate_id),
            "version": 1,
            "state": "dispensed",
            "appointment_id": str(aggregate_id + 1),
        },
    }


def _insert_publisher_test_outbox(engine, rows):
    now = datetime.now(timezone.utc)
    with engine.begin() as connection:
        for event_id, aggregate_id in rows:
            connection.execute(
                text(
                    "INSERT INTO outbox_events "
                    "(event_id, aggregate_type, aggregate_id, aggregate_version, event_type, "
                    "envelope, next_attempt_at, claimed_by, lease_expires_at) "
                    "VALUES (:event_id, 'reservation', :aggregate_id, 1, "
                    "'pharmacy.reservation.dispensed.v1', CAST(:envelope AS jsonb), "
                    ":next_attempt_at, :claimed_by, :lease_expires_at)"
                ),
                {
                    "event_id": event_id,
                    "aggregate_id": aggregate_id,
                    "envelope": json.dumps(_publisher_test_event(event_id, aggregate_id)),
                    "next_attempt_at": now,
                    "claimed_by": "crashed-worker" if event_id == rows[0][0] else None,
                    "lease_expires_at": now - timedelta(seconds=1) if event_id == rows[0][0] else None,
                },
            )


class _TimeoutExchange:
    async def publish(self, *_args, **_kwargs):
        raise asyncio.TimeoutError


class _ConfirmExchange:
    def __init__(self):
        self.messages = []

    async def publish(self, message, *, routing_key, mandatory):
        self.messages.append((message, routing_key, mandatory))
        return True


def test_publisher_recovers_expired_lease_and_retries_after_confirm_timeout(pharmacy_client):
    _client, engine, app = pharmacy_client
    event_id = secrets.randbelow(9_000_000_000_000_000_000) + 1
    aggregate_id = secrets.randbelow(9_000_000_000_000_000_000) + 1
    _insert_publisher_test_outbox(engine, [(event_id, aggregate_id)])

    async def work():
        database = Database(app.state.settings)
        await database.start()
        try:
            with pytest.raises(asyncio.TimeoutError):
                await event_delivery.publish_batch(
                    database.session_factory,
                    _TimeoutExchange(),
                    "publisher-retry-test",
                    app,
                )
            with engine.connect() as connection:
                failed = connection.execute(
                    text(
                        "SELECT attempt_count, published_at, claimed_by, last_error "
                        "FROM outbox_events WHERE event_id=:id"
                    ),
                    {"id": event_id},
                ).one()
                assert tuple(failed) == (1, None, None, "confirm_timeout")

            confirmed = _ConfirmExchange()
            with engine.begin() as connection:
                connection.execute(
                    text("UPDATE outbox_events SET next_attempt_at=now() WHERE event_id=:id"),
                    {"id": event_id},
                )
            count = await event_delivery.publish_batch(
                database.session_factory,
                confirmed,
                "publisher-retry-test",
                app,
            )
            assert count == 1
            assert len(confirmed.messages) == 1
            message, routing_key, mandatory = confirmed.messages[0]
            assert message.message_id == str(event_id)
            assert routing_key == "pharmacy.reservation.dispensed.v1"
            assert mandatory is True
        finally:
            await database.close()

    asyncio.run(work())
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT attempt_count, published_at IS NOT NULL, claimed_by, "
                "lease_expires_at, last_error FROM outbox_events WHERE event_id=:id"
            ),
            {"id": event_id},
        ).one()
    assert tuple(row) == (2, True, None, None, None)


def test_concurrent_publishers_claim_each_event_at_most_once(pharmacy_client):
    _client, engine, app = pharmacy_client
    first_id = secrets.randbelow(8_000_000_000_000_000_000) + 1
    rows = [
        (first_id + index, secrets.randbelow(8_000_000_000_000_000_000) + index + 1)
        for index in range(6)
    ]
    _insert_publisher_test_outbox(engine, rows)

    async def work():
        database = Database(app.state.settings)
        await database.start()
        try:
            first, second = await asyncio.gather(
                event_delivery.claim_batch(database.session_factory, "concurrent-a"),
                event_delivery.claim_batch(database.session_factory, "concurrent-b"),
            )
            first_ids = {int(row["event_id"]) for row in first}
            second_ids = {int(row["event_id"]) for row in second}
            assert not first_ids.intersection(second_ids)
            assert first_ids.union(second_ids) == {event_id for event_id, _ in rows}
        finally:
            await database.close()

    asyncio.run(work())
