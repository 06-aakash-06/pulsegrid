"""Lease-based publisher for the selected Billing Phase 5 event."""

from __future__ import annotations

import asyncio
import json
import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import aio_pika
from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.exc import SQLAlchemyError

from .models import outbox_events

EXCHANGE_NAME = "pulsegrid.events"
EVENT_TYPES = ("billing.payment.succeeded.v1",)
BATCH_SIZE = 5
LEASE_SECONDS = 60
PUBLISH_TIMEOUT_SECONDS = 5
IDLE_POLL_SECONDS = 0.5


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


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _observer(app, name: str, value: float = 1, *, outcome: str) -> None:
    observer = getattr(app.state, "phase4_observer", None)
    if observer is not None:
        observer.increment(
            name,
            {"component": "phase5", "owner": "billing", "outcome": outcome},
            value,
        )


def _worker_status(app, connected: bool) -> None:
    observer = getattr(app.state, "phase4_observer", None)
    if observer is not None:
        observer.gauge(
            "pulsegrid_event_worker_connected",
            int(connected),
            {"component": "phase5", "owner": "billing"},
        )


async def claim_batch(factory, claimed_by: str) -> list[dict]:
    """Claim selected events briefly, then return after the transaction commits."""
    earlier = outbox_events.alias("earlier_outbox")
    earlier_version = or_(
        earlier.c.aggregate_version < outbox_events.c.aggregate_version,
        and_(
            earlier.c.aggregate_version == outbox_events.c.aggregate_version,
            or_(
                earlier.c.created_at < outbox_events.c.created_at,
                and_(
                    earlier.c.created_at == outbox_events.c.created_at,
                    earlier.c.event_id < outbox_events.c.event_id,
                ),
            ),
        ),
    )
    predecessor = exists(
        select(1).select_from(earlier).where(
            earlier.c.aggregate_type == outbox_events.c.aggregate_type,
            earlier.c.aggregate_id == outbox_events.c.aggregate_id,
            earlier.c.event_type.in_(EVENT_TYPES),
            earlier.c.published_at.is_(None),
            earlier_version,
        )
    )
    async with factory() as session, session.begin():
        now = _now()
        rows = (
            await session.execute(
                select(outbox_events)
                .where(
                    outbox_events.c.event_type.in_(EVENT_TYPES),
                    outbox_events.c.published_at.is_(None),
                    outbox_events.c.next_attempt_at <= now,
                    or_(
                        outbox_events.c.lease_expires_at.is_(None),
                        outbox_events.c.lease_expires_at <= now,
                    ),
                    ~predecessor,
                )
                .order_by(
                    outbox_events.c.aggregate_type,
                    outbox_events.c.aggregate_id,
                    outbox_events.c.aggregate_version,
                    outbox_events.c.created_at,
                    outbox_events.c.event_id,
                )
                .limit(BATCH_SIZE)
                .with_for_update(skip_locked=True)
            )
        ).mappings().all()
        if not rows:
            return []
        event_ids = [int(row["event_id"]) for row in rows]
        await session.execute(
            update(outbox_events)
            .where(outbox_events.c.event_id.in_(event_ids))
            .values(
                claimed_by=claimed_by,
                lease_expires_at=now + timedelta(seconds=LEASE_SECONDS),
                updated_at=now,
            )
        )
        return [dict(row) for row in rows]


async def _record_attempt(factory, event_id: int, claimed_by: str) -> int:
    async with factory() as session, session.begin():
        result = await session.execute(
            update(outbox_events)
            .where(
                outbox_events.c.event_id == event_id,
                outbox_events.c.claimed_by == claimed_by,
                outbox_events.c.published_at.is_(None),
            )
            .values(attempt_count=outbox_events.c.attempt_count + 1, updated_at=_now())
            .returning(outbox_events.c.attempt_count)
        )
        attempt = result.scalar_one_or_none()
        if attempt is None:
            raise RuntimeError("outbox_claim_lost")
        return int(attempt)


async def _mark_published(factory, event_id: int, claimed_by: str) -> bool:
    async with factory() as session, session.begin():
        result = await session.execute(
            update(outbox_events)
            .where(
                outbox_events.c.event_id == event_id,
                outbox_events.c.claimed_by == claimed_by,
                outbox_events.c.published_at.is_(None),
            )
            .values(
                published_at=_now(),
                claimed_by=None,
                lease_expires_at=None,
                last_error=None,
                updated_at=_now(),
            )
            .returning(outbox_events.c.event_id)
        )
        return result.scalar_one_or_none() is not None


async def _mark_failed(
    factory, event_id: int, claimed_by: str, attempt: int, error_code: str
) -> None:
    backoff = min(60.0, 2.0 ** min(max(attempt - 1, 0), 6))
    backoff *= random.uniform(0.8, 1.2)
    async with factory() as session, session.begin():
        await session.execute(
            update(outbox_events)
            .where(
                outbox_events.c.event_id == event_id,
                outbox_events.c.claimed_by == claimed_by,
                outbox_events.c.published_at.is_(None),
            )
            .values(
                claimed_by=None,
                lease_expires_at=None,
                next_attempt_at=_now() + timedelta(seconds=backoff),
                last_error=error_code,
                updated_at=_now(),
            )
        )


async def _release_claims(factory, claimed_by: str) -> None:
    async with factory() as session, session.begin():
        await session.execute(
            update(outbox_events)
            .where(
                outbox_events.c.claimed_by == claimed_by,
                outbox_events.c.published_at.is_(None),
            )
            .values(claimed_by=None, lease_expires_at=None, updated_at=_now())
        )


async def pending_metrics(factory, app) -> None:
    async with factory() as session:
        row = (
            await session.execute(
                select(
                    func.count().label("pending"),
                    func.min(outbox_events.c.created_at).label("oldest"),
                ).where(
                    outbox_events.c.event_type.in_(EVENT_TYPES),
                    outbox_events.c.published_at.is_(None),
                )
            )
        ).mappings().one()
    observer = getattr(app.state, "phase4_observer", None)
    if observer is None:
        return
    labels = {"component": "phase5", "owner": "billing"}
    observer.gauge("pulsegrid_outbox_pending", int(row["pending"]), labels)
    oldest_age = max(0.0, (_now() - row["oldest"]).total_seconds()) if row["oldest"] else 0.0
    observer.gauge("pulsegrid_outbox_oldest_pending_seconds", oldest_age, labels)


def _error_code(error: BaseException) -> str:
    if isinstance(error, asyncio.TimeoutError):
        return "confirm_timeout"
    if isinstance(error, aio_pika.exceptions.DeliveryError):
        return "unroutable"
    if isinstance(error, SQLAlchemyError):
        return "database_unavailable"
    return "broker_unavailable"


async def publish_batch(factory, exchange, claimed_by: str, app) -> int:
    rows = await claim_batch(factory, claimed_by)
    for row in rows:
        event_id = int(row["event_id"])
        attempt = await _record_attempt(factory, event_id, claimed_by)
        event_type = str(row["event_type"])
        body = json.dumps(row["envelope"], separators=(",", ":"), sort_keys=True).encode()
        message = aio_pika.Message(
            body=body,
            message_id=str(event_id),
            type=event_type,
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        try:
            async with asyncio.timeout(PUBLISH_TIMEOUT_SECONDS):
                confirmed = await exchange.publish(message, routing_key=event_type, mandatory=True)
            if confirmed is False:
                raise RuntimeError("publisher_nack")
            marked = await _mark_published(factory, event_id, claimed_by)
            if marked:
                _observer(app, "pulsegrid_outbox_published_total", outcome="confirmed")
        except asyncio.CancelledError:
            raise
        except Exception as error:
            error_code = _error_code(error)
            await _mark_failed(factory, event_id, claimed_by, attempt, error_code)
            _observer(app, "pulsegrid_outbox_publish_failures_total", outcome=error_code)
            _observer(app, "pulsegrid_outbox_publish_retries_total", outcome="scheduled")
            raise
    return len(rows)


async def _publish_loop(app, config: BrokerConfig) -> None:
    factory = app.state.database.session_factory
    claimed_by = "billing:" + uuid4().hex
    retry_delay = 1.0
    while True:
        connection = None
        _worker_status(app, False)
        try:
            await pending_metrics(factory, app)
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
            channel = await connection.channel(publisher_confirms=True, on_return_raises=True)
            exchange = await channel.declare_exchange(
                EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True
            )
            retry_delay = 1.0
            while True:
                await pending_metrics(factory, app)
                count = await publish_batch(factory, exchange, claimed_by, app)
                if not count:
                    await asyncio.sleep(IDLE_POLL_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            code = _error_code(error)
            app.state.logger.warning(
                f"event_publisher_retry:{code}",
                extra={"service": "billing"},
            )
            _observer(app, "pulsegrid_outbox_publish_failures_total", outcome=code)
            await asyncio.sleep(retry_delay * random.uniform(0.8, 1.2))
            retry_delay = min(30.0, retry_delay * 2)
        finally:
            _worker_status(app, False)
            if connection is not None and not connection.is_closed:
                await connection.close()
            try:
                await _release_claims(factory, claimed_by)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass


async def start(app) -> None:
    config = BrokerConfig.from_env()
    if config is None:
        return
    app.state.event_publisher_task = asyncio.create_task(_publish_loop(app, config))


async def close(app) -> None:
    task = getattr(app.state, "event_publisher_task", None)
    if task is None:
        return
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
