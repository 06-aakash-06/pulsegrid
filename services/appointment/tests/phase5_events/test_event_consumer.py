"""Real PostgreSQL checks for Phase 5 inbox transactions and deduplication."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import psycopg
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from appointment_service import event_consumer
from ..phase3_journey.test_reconciliation import setup
from ..test_concurrency import run


def _envelope(event_id: int, appointment_id: int, journey_id: int, *, producer: str):
    if producer == "pharmacy":
        return {
            "event_id": str(event_id),
            "event_type": "pharmacy.reservation.dispensed.v1",
            "schema_version": 1,
            "producer": "pharmacy",
            "aggregate_type": "reservation",
            "aggregate_id": "7001",
            "aggregate_version": 2,
            "occurred_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "correlation_id": str(uuid4()),
            "request_id": str(uuid4()),
            "causation_id": None,
            "traceparent": None,
            "payload": {
                "resource_id": "7001",
                "version": 2,
                "state": "dispensed",
                "appointment_id": str(appointment_id),
            },
        }
    return {
        "event_id": str(event_id),
        "event_type": "billing.payment.succeeded.v1",
        "schema_version": 1,
        "producer": "billing",
        "aggregate_type": "invoice",
        "aggregate_id": "8001",
        "aggregate_version": 3,
        "occurred_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "correlation_id": str(uuid4()),
        "request_id": str(uuid4()),
        "causation_id": None,
        "traceparent": None,
        "payload": {"appointment_id": str(appointment_id)},
    }


def test_inbox_effect_is_atomic_and_duplicate_subscriptions_are_independent(database):
    async def work(database_instance):
        appointment, journey_id = await setup(database_instance, started=False)
        appointment_id = int(appointment["id"])
        journey_id = int(journey_id)
        factory = database_instance.session_factory
        async with factory() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE journey_snapshots SET next_attempt_at=:future "
                    "WHERE journey_id=:journey_id"
                ),
                {"future": datetime.now(timezone.utc) + timedelta(hours=1), "journey_id": journey_id},
            )

        pharmacy = event_consumer.SUBSCRIPTIONS[0]
        billing = event_consumer.SUBSCRIPTIONS[1]
        event_id = 991_000_001
        pharmacy_event = _envelope(
            event_id, appointment_id, journey_id, producer="pharmacy"
        )
        pharmacy_results = await asyncio.gather(
            event_consumer.process_event(factory, pharmacy_event, pharmacy),
            event_consumer.process_event(factory, pharmacy_event, pharmacy),
        )
        assert sorted(pharmacy_results) == ["duplicate", "processed"]

        # Producer-local IDs may collide; each subscription owns its own inbox key.
        billing_event = _envelope(
            event_id, appointment_id, journey_id, producer="billing"
        )
        assert await event_consumer.process_event(factory, billing_event, billing) == "processed"

        async with factory() as session:
            inbox = (
                await session.execute(
                    text(
                        "SELECT consumer_name FROM inbox_events WHERE event_id=:event_id "
                        "ORDER BY consumer_name"
                    ),
                    {"event_id": event_id},
                )
            ).scalars().all()
            snapshot = (
                await session.execute(
                    text(
                        "SELECT next_attempt_at, records_revision, pharmacy_revision, "
                        "billing_revision FROM journey_snapshots WHERE journey_id=:journey_id"
                    ),
                    {"journey_id": journey_id},
                )
            ).one()
        assert inbox == [billing.name, pharmacy.name]
        assert snapshot.next_attempt_at <= datetime.now(timezone.utc)
        assert tuple(snapshot[1:]) == (None, None, None)

        # A transient local failure after inbox insertion rolls back both writes.
        retry_id = event_id + 1
        retry_event = _envelope(retry_id, appointment_id, journey_id, producer="billing")
        connection_args = {
            "host": database_instance.settings.db_host,
            "port": database_instance.settings.db_port,
            "dbname": database_instance.settings.db_name,
            "user": "appointment_owner",
        }
        with psycopg.connect(**connection_args, autocommit=True) as connection:
            connection.execute(
                "CREATE FUNCTION phase5_test_fail_wakeup() RETURNS trigger "
                "LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'phase5 injected failure'; END $$"
            )
            connection.execute(
                "CREATE TRIGGER phase5_test_fail_wakeup_trigger "
                "BEFORE UPDATE ON journey_snapshots FOR EACH ROW "
                "EXECUTE FUNCTION phase5_test_fail_wakeup()"
            )
        try:
            with pytest.raises(SQLAlchemyError):
                await event_consumer.process_event(factory, retry_event, billing)
        finally:
            with psycopg.connect(**connection_args, autocommit=True) as connection:
                connection.execute(
                    "DROP TRIGGER phase5_test_fail_wakeup_trigger ON journey_snapshots"
                )
                connection.execute("DROP FUNCTION phase5_test_fail_wakeup()")
        async with factory() as session:
            assert await session.scalar(
                text("SELECT count(*) FROM inbox_events WHERE consumer_name=:name AND event_id=:id"),
                {"name": billing.name, "id": retry_id},
            ) == 0
        assert await event_consumer.process_event(factory, retry_event, billing) == "processed"

        # A permanent bad reference is not recorded as successfully processed.
        bad_id = event_id + 2
        bad_event = _envelope(bad_id, 9_999_999_999, journey_id, producer="pharmacy")
        with pytest.raises(event_consumer.PermanentEventError):
            await event_consumer.process_event(factory, bad_event, pharmacy)
        async with factory() as session:
            assert await session.scalar(
                text("SELECT count(*) FROM inbox_events WHERE consumer_name=:name AND event_id=:id"),
                {"name": pharmacy.name, "id": bad_id},
            ) == 0

    run(database, work)


def test_envelope_validation_rejects_version_and_amqp_type_mismatch():
    subscription = event_consumer.SUBSCRIPTIONS[0]
    envelope = _envelope(991_000_100, 101, 102, producer="pharmacy")
    body = json.dumps(envelope).encode()
    assert event_consumer.validate_event(
        body, str(envelope["event_id"]), subscription, envelope["event_type"]
    ) == envelope
    with pytest.raises(event_consumer.EventEnvelopeError):
        event_consumer.validate_event(
            body, str(envelope["event_id"]), subscription, "billing.payment.succeeded.v1"
        )
    envelope["schema_version"] = 2
    with pytest.raises(event_consumer.EventEnvelopeError):
        event_consumer.validate_event(
            json.dumps(envelope).encode(), str(envelope["event_id"]), subscription
        )
    boolean_version = _envelope(991_000_101, 101, 102, producer="pharmacy")
    boolean_version["aggregate_version"] = 1
    boolean_version["payload"]["version"] = True
    with pytest.raises(event_consumer.EventEnvelopeError):
        event_consumer.validate_event(
            json.dumps(boolean_version).encode(),
            str(boolean_version["event_id"]),
            subscription,
        )
