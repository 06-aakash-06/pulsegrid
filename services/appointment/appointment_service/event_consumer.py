"""Idempotent consumers that wake Appointment's owner-snapshot reconciler."""

from __future__ import annotations

import asyncio
import json
import os
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

import aio_pika
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from .event_tracing import consume_span
from . import models as m

EXCHANGE_NAME = "pulsegrid.events"
DLX_NAME = "pulsegrid.dlx"
MAX_RETRIES = 5
RETRY_DELAYS_SECONDS = (1, 5, 30, 120, 600)
PREFETCH_COUNT = 8
MAX_MESSAGE_BYTES = 262_144
MAX_QUEUE_LENGTH = 10_000


@dataclass(frozen=True, slots=True)
class Subscription:
    name: str
    queue_name: str
    dead_letter_queue: str
    routing_key: str
    producer: str
    aggregate_type: str


SUBSCRIPTIONS = (
    Subscription(
        name="appointment.journey.pharmacy.v1",
        queue_name="pulsegrid.appointment.journey.pharmacy.v1",
        dead_letter_queue="pulsegrid.dlq.appointment.journey.pharmacy.v1",
        routing_key="pharmacy.reservation.dispensed.v1",
        producer="pharmacy",
        aggregate_type="reservation",
    ),
    Subscription(
        name="appointment.journey.billing.v1",
        queue_name="pulsegrid.appointment.journey.billing.v1",
        dead_letter_queue="pulsegrid.dlq.appointment.journey.billing.v1",
        routing_key="billing.payment.succeeded.v1",
        producer="billing",
        aggregate_type="invoice",
    ),
)


@dataclass(frozen=True, slots=True)
class BrokerConfig:
    host: str
    port: int
    username: str
    password: str = field(repr=False)

    @classmethod
    def from_env(cls) -> BrokerConfig | None:
        enabled = os.environ.get("PULSEGRID_PHASE5_MESSAGING_ENABLED", "false")
        if enabled not in {"true", "false"}:
            raise ValueError("PULSEGRID_PHASE5_MESSAGING_ENABLED must be true or false")
        if enabled == "false":
            return None
        host = os.environ.get("PULSEGRID_MESSAGING_HOST", "").strip()
        username = os.environ.get("RABBITMQ_EVENTS_USER", "").strip()
        password = os.environ.get("RABBITMQ_EVENTS_PASSWORD", "")
        try:
            port = int(os.environ.get("PULSEGRID_MESSAGING_PORT", "5672"))
        except ValueError:
            raise ValueError("PULSEGRID_MESSAGING_PORT must be an integer") from None
        if not host or not username or not password or not 1 <= port <= 65535:
            raise ValueError("RabbitMQ event connection configuration is incomplete")
        return cls(host, port, username, password)


class PermanentEventError(ValueError):
    """The event cannot be repaired by retrying the same message."""


class EventEnvelopeError(PermanentEventError):
    """The envelope or event-specific payload violates the subscribed contract."""


def _positive_id(value, name: str) -> int:
    if (
        not isinstance(value, str)
        or not value.isascii()
        or not value.isdigit()
        or value.startswith("0")
    ):
        raise EventEnvelopeError(f"invalid_{name}")
    number = int(value)
    if number < 1 or number > 9_223_372_036_854_775_807:
        raise EventEnvelopeError(f"invalid_{name}")
    return number


def validate_event(
    body: bytes,
    message_id: str | None,
    subscription: Subscription,
    message_type: str | None = None,
) -> dict:
    if len(body) > MAX_MESSAGE_BYTES:
        raise EventEnvelopeError("event_too_large")
    try:
        envelope = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise EventEnvelopeError("invalid_json") from None
    if not isinstance(envelope, dict):
        raise EventEnvelopeError("invalid_envelope")
    required = {
        "event_id",
        "event_type",
        "schema_version",
        "producer",
        "aggregate_type",
        "aggregate_id",
        "aggregate_version",
        "occurred_at",
        "correlation_id",
        "request_id",
        "causation_id",
        "traceparent",
        "payload",
    }
    if not required.issubset(envelope):
        raise EventEnvelopeError("missing_envelope_fields")
    event_id = _positive_id(envelope["event_id"], "event_id")
    if message_id is not None and message_id != str(event_id):
        raise EventEnvelopeError("message_id_mismatch")
    if envelope["event_type"] != subscription.routing_key:
        raise EventEnvelopeError("unexpected_event_type")
    if message_type is not None and message_type != envelope["event_type"]:
        raise EventEnvelopeError("message_type_mismatch")
    if type(envelope["schema_version"]) is not int or envelope["schema_version"] != 1:
        raise EventEnvelopeError("unsupported_schema_version")
    if envelope["producer"] != subscription.producer:
        raise EventEnvelopeError("unexpected_producer")
    if envelope["aggregate_type"] != subscription.aggregate_type:
        raise EventEnvelopeError("unexpected_aggregate_type")
    _positive_id(envelope["aggregate_id"], "aggregate_id")
    if type(envelope["aggregate_version"]) is not int or envelope["aggregate_version"] < 1:
        raise EventEnvelopeError("invalid_aggregate_version")
    for field_name in ("correlation_id", "request_id"):
        try:
            if not isinstance(envelope[field_name], str):
                raise ValueError
            UUID(envelope[field_name])
        except (ValueError, AttributeError):
            raise EventEnvelopeError(f"invalid_{field_name}") from None
    try:
        occurred_at = envelope["occurred_at"]
        if not isinstance(occurred_at, str) or "T" not in occurred_at:
            raise ValueError
        timestamp = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
        if timestamp.tzinfo is None or timestamp.utcoffset() != timezone.utc.utcoffset(timestamp):
            raise ValueError
    except (ValueError, TypeError):
        raise EventEnvelopeError("invalid_occurred_at") from None
    if envelope["causation_id"] is not None and not isinstance(envelope["causation_id"], str):
        raise EventEnvelopeError("invalid_causation_id")
    traceparent = envelope["traceparent"]
    if traceparent is not None and (not isinstance(traceparent, str) or len(traceparent) > 128):
        raise EventEnvelopeError("invalid_traceparent")
    payload = envelope["payload"]
    if not isinstance(payload, dict):
        raise EventEnvelopeError("invalid_payload")

    if subscription.producer == "pharmacy":
        aggregate_id = str(envelope["aggregate_id"])
        if (
            payload.get("resource_id") != aggregate_id
            or type(payload.get("version")) is not int
            or payload.get("version") != envelope["aggregate_version"]
            or payload.get("state") != "dispensed"
        ):
            raise EventEnvelopeError("invalid_pharmacy_payload")
        if payload.get("appointment_id") is not None:
            _positive_id(payload["appointment_id"], "appointment_id")
    else:
        if payload.get("appointment_id") is not None:
            _positive_id(payload["appointment_id"], "appointment_id")
        elif not {
            "invoice_id",
            "patient_id",
            "payment_id",
            "amount_minor",
        }.issubset(payload):
            raise EventEnvelopeError("invalid_legacy_billing_payload")
        elif payload.get("invoice_id") != str(envelope["aggregate_id"]):
            raise EventEnvelopeError("invalid_legacy_billing_invoice")
    return envelope


async def _journey_for_event(session, envelope: dict, subscription: Subscription) -> int | None:
    payload = envelope["payload"]
    if subscription.producer == "pharmacy":
        appointment_value = payload.get("appointment_id")
        if appointment_value is None:
            return None
        appointment_id = _positive_id(appointment_value, "appointment_id")
        found = await session.scalar(
            select(m.appointments.c.id).where(m.appointments.c.id == appointment_id)
        )
        if found is None:
            raise PermanentEventError("unknown_appointment")
        journey_id = await session.scalar(
            select(m.journeys.c.id).where(m.journeys.c.appointment_id == appointment_id)
        )
        # Older appointments do not have a Phase 3 journey projection.
        return int(journey_id) if journey_id is not None else None

    appointment_value = payload.get("appointment_id")
    if appointment_value is None:
        # Previously persisted pre-Phase-5 events use a wider proposal payload
        # without the appointment reference. Current messages always include it.
        return None
    appointment_id = _positive_id(appointment_value, "appointment_id")
    found_appointment = await session.scalar(
        select(m.appointments.c.id).where(m.appointments.c.id == appointment_id)
    )
    if found_appointment is None:
        raise PermanentEventError("unknown_appointment")
    journey_id = await session.scalar(
        select(m.journeys.c.id).where(m.journeys.c.appointment_id == appointment_id)
    )
    # Legacy appointments were not backfilled into Phase 3 journeys.
    return int(journey_id) if journey_id is not None else None


async def process_event(factory, envelope: dict, subscription: Subscription) -> str:
    """Atomically deduplicate a signal and schedule one local source refresh."""
    async with factory() as session, session.begin():
        event_id = int(envelope["event_id"])
        inserted = await session.execute(
            insert(m.inbox_events)
            .values(consumer_name=subscription.name, event_id=event_id)
            .on_conflict_do_nothing(
                index_elements=[m.inbox_events.c.consumer_name, m.inbox_events.c.event_id]
            )
            .returning(m.inbox_events.c.event_id)
        )
        if inserted.scalar_one_or_none() is None:
            return "duplicate"
        journey_id = await _journey_for_event(session, envelope, subscription)
        if journey_id is None:
            return "legacy_noop"
        now = datetime.now(timezone.utc)
        updated = await session.execute(
            update(m.journey_snapshots)
            .where(m.journey_snapshots.c.journey_id == journey_id)
            .values(next_attempt_at=func.least(m.journey_snapshots.c.next_attempt_at, now))
            .returning(m.journey_snapshots.c.journey_id)
        )
        if updated.scalar_one_or_none() is None:
            raise PermanentEventError("journey_snapshot_missing")
        return "processed"


def _observer(app, name: str, outcome: str, value: float = 1) -> None:
    observer = getattr(app.state, "phase4_observer", None)
    if observer is not None:
        observer.increment(
            name,
            {"component": "phase5", "owner": "appointment", "outcome": outcome},
            value,
        )


def _worker_status(app, connected: bool) -> None:
    observer = getattr(app.state, "phase4_observer", None)
    if observer is not None:
        observer.gauge(
            "pulsegrid_event_worker_connected",
            int(connected),
            {"component": "phase5", "owner": "appointment"},
        )


def _retry_count(message) -> int | None:
    headers = message.headers or {}
    value = headers.get("x-delivery-count", 0)
    if type(value) is not int or value < 0 or value > 100:
        return None
    return value


async def _process_message(message, subscription: Subscription, factory, app) -> None:
    started = time.perf_counter()
    try:
        envelope = validate_event(
            message.body, message.message_id, subscription, message.type
        )
    except PermanentEventError as error:
        _observer(app, "pulsegrid_consumer_failures_total", type(error).__name__)
        _observer(app, "pulsegrid_dead_letter_total", "permanent")
        await message.reject(requeue=False)
        return

    try:
        result = await process_event(factory, envelope, subscription)
    except asyncio.CancelledError:
        raise
    except PermanentEventError as error:
        _observer(app, "pulsegrid_consumer_failures_total", type(error).__name__)
        _observer(app, "pulsegrid_dead_letter_total", "permanent")
        await message.reject(requeue=False)
        return
    except (SQLAlchemyError, TimeoutError, OSError) as error:
        retry_count = _retry_count(message)
        if retry_count is None or retry_count >= MAX_RETRIES:
            _observer(app, "pulsegrid_consumer_failures_total", "retry_exhausted")
            _observer(app, "pulsegrid_dead_letter_total", "retry_exhausted")
            await message.reject(requeue=False)
            return
        delay = RETRY_DELAYS_SECONDS[retry_count] * random.uniform(0.8, 1.2)
        _observer(app, "pulsegrid_consumer_failures_total", type(error).__name__)
        _observer(app, "pulsegrid_consumer_retries_total", "scheduled")
        await asyncio.sleep(delay)
        await message.nack(requeue=True)
        return
    except Exception as error:
        # Unclassified handler failures are retried as transient, but still
        # bounded by the quorum queue delivery limit and explicit retry count.
        retry_count = _retry_count(message)
        if retry_count is None or retry_count >= MAX_RETRIES:
            _observer(app, "pulsegrid_consumer_failures_total", "retry_exhausted")
            _observer(app, "pulsegrid_dead_letter_total", "retry_exhausted")
            await message.reject(requeue=False)
            return
        delay = RETRY_DELAYS_SECONDS[retry_count] * random.uniform(0.8, 1.2)
        _observer(app, "pulsegrid_consumer_failures_total", type(error).__name__)
        _observer(app, "pulsegrid_consumer_retries_total", "scheduled")
        await asyncio.sleep(delay)
        await message.nack(requeue=True)
        return

    # The inbox/effect transaction has committed before the manual ack.
    await message.ack()
    if result == "duplicate":
        _observer(app, "pulsegrid_consumer_duplicates_total", subscription.producer)
    else:
        _observer(app, "pulsegrid_consumer_processed_total", subscription.producer)
    duration = time.perf_counter() - started
    observer = getattr(app.state, "phase4_observer", None)
    if observer is not None:
        labels = {"component": "phase5", "owner": subscription.producer}
        observer.observe("pulsegrid_event_processing_seconds", duration, labels)
        occurred_at = datetime.fromisoformat(envelope["occurred_at"].replace("Z", "+00:00"))
        observer.observe(
            "pulsegrid_event_delivery_seconds",
            max(0.0, (datetime.now(timezone.utc) - occurred_at).total_seconds()),
            labels,
        )


async def _on_message(message, subscription: Subscription, factory, app) -> None:
    """Continue W3C context around message handling without trusting baggage."""
    headers = message.headers if isinstance(message.headers, dict) else {}
    traceparent = headers.get("traceparent")
    if not isinstance(traceparent, str) and len(message.body) <= MAX_MESSAGE_BYTES:
        try:
            envelope = json.loads(message.body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            envelope = None
        if isinstance(envelope, dict):
            traceparent = envelope.get("traceparent")
    if not isinstance(traceparent, str) or len(traceparent) > 128:
        traceparent = None
    with consume_span(traceparent, subscription.queue_name, subscription.routing_key):
        await _process_message(message, subscription, factory, app)


async def _declare_topology(channel):
    events = await channel.declare_exchange(
        EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True
    )
    dead_letters = await channel.declare_exchange(
        DLX_NAME, aio_pika.ExchangeType.DIRECT, durable=True
    )
    queues = []
    dead_queues = []
    for subscription in SUBSCRIPTIONS:
        main = await channel.declare_queue(
            subscription.queue_name,
            durable=True,
            arguments={
                "x-queue-type": "quorum",
                "x-max-length": MAX_QUEUE_LENGTH,
                "x-overflow": "reject-publish",
                "x-delivery-limit": MAX_RETRIES + 1,
                "x-dead-letter-exchange": DLX_NAME,
                "x-dead-letter-routing-key": subscription.dead_letter_queue,
                "x-dead-letter-strategy": "at-least-once",
            },
        )
        await main.bind(events, routing_key=subscription.routing_key)
        dead = await channel.declare_queue(
            subscription.dead_letter_queue,
            durable=True,
            arguments={
                "x-queue-type": "quorum",
                "x-max-length": MAX_QUEUE_LENGTH,
                "x-overflow": "reject-publish",
            },
        )
        await dead.bind(dead_letters, routing_key=subscription.dead_letter_queue)
        queues.append((main, subscription))
        dead_queues.append((dead, subscription))
    return queues, dead_queues


async def _dead_letter_queue_depth(channel, queue_name: str) -> int:
    queue = await channel.declare_queue(queue_name, passive=True)
    return int(queue.declaration_result.message_count)


async def _consumer_session(app, config: BrokerConfig) -> None:
    factory = app.state.database.session_factory
    connection = await aio_pika.connect(
        host=config.host,
        port=config.port,
        login=config.username,
        password=config.password,
        virtualhost="/",
        timeout=3,
        heartbeat=30,
    )
    _worker_status(app, True)
    try:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=PREFETCH_COUNT)
        queues, dead_queues = await _declare_topology(channel)
        tags = []
        for queue, subscription in queues:
            tag = await queue.consume(
                lambda message, subscription=subscription: _on_message(
                    message, subscription, factory, app
                ),
                no_ack=False,
            )
            tags.append((queue, tag))
        try:
            while True:
                await asyncio.sleep(5)
                for _, subscription in dead_queues:
                    message_count = await _dead_letter_queue_depth(
                        channel, subscription.dead_letter_queue
                    )
                    observer = getattr(app.state, "phase4_observer", None)
                    if observer is not None:
                        observer.gauge(
                            "pulsegrid_dead_letter_queue_depth",
                            message_count,
                            {"component": "phase5", "owner": subscription.producer},
                        )
        finally:
            for queue, tag in tags:
                try:
                    await queue.cancel(tag)
                except Exception:
                    pass
            await channel.close()
    finally:
        _worker_status(app, False)
        if not connection.is_closed:
            await connection.close()


async def _consumer_loop(app, config: BrokerConfig) -> None:
    retry_delay = 1.0
    while True:
        _worker_status(app, False)
        try:
            await _consumer_session(app, config)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            app.state.logger.warning(
                f"event_consumer_retry:{type(error).__name__}",
                extra={"service": "appointment"},
            )
            _observer(app, "pulsegrid_consumer_failures_total", "connection_failure")
            await asyncio.sleep(retry_delay * random.uniform(0.8, 1.2))
            retry_delay = min(30.0, retry_delay * 2)
        else:
            retry_delay = 1.0


async def start(app) -> None:
    config = BrokerConfig.from_env()
    if config is None:
        return
    app.state.event_consumer_task = asyncio.create_task(_consumer_loop(app, config))


async def close(app) -> None:
    task = getattr(app.state, "event_consumer_task", None)
    if task is None:
        return
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
