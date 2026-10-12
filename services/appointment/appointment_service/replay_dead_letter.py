"""Inspect or replay one repaired Phase 5 dead-letter message."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys

import aio_pika

from .event_consumer import (
    EXCHANGE_NAME,
    SUBSCRIPTIONS,
    BrokerConfig,
    PermanentEventError,
    validate_event,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subscription", choices=("pharmacy", "billing"), required=True)
    parser.add_argument("--peek", action="store_true", help="Show safe head-message metadata")
    parser.add_argument("--event-id", help="Expected decimal event ID for a single replay")
    parser.add_argument("--operator", help="Operator identifier for the replay record")
    parser.add_argument("--reason", help="Why the repaired consumer/message is safe to replay")
    return parser


async def _run(args: argparse.Namespace) -> int:
    subscription = next(
        item for item in SUBSCRIPTIONS if item.producer == args.subscription
    )
    config = BrokerConfig.from_env()
    if config is None:
        raise SystemExit("Phase 5 messaging is disabled in this service")
    connection = await aio_pika.connect(
        host=config.host,
        port=config.port,
        login=config.username,
        password=config.password,
        virtualhost="/",
        timeout=3,
        heartbeat=30,
    )
    try:
        channel = await connection.channel(publisher_confirms=True, on_return_raises=True)
        exchange = await channel.declare_exchange(
            EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True
        )
        queue = await channel.get_queue(subscription.dead_letter_queue, ensure=True)
        message = await queue.get(no_ack=False, fail=False)
        if message is None:
            print(json.dumps({"action": "empty", "subscription": args.subscription}))
            return 0

        if args.peek:
            try:
                envelope = json.loads(message.body)
            except (UnicodeDecodeError, json.JSONDecodeError):
                envelope = {}
            print(
                json.dumps(
                    {
                        "action": "peek",
                        "subscription": args.subscription,
                        "message_id": message.message_id,
                        "event_id": envelope.get("event_id") if isinstance(envelope, dict) else None,
                        "event_type": envelope.get("event_type") if isinstance(envelope, dict) else None,
                        "dead_letter_reason": (message.headers or {}).get("x-first-death-reason"),
                    },
                    sort_keys=True,
                )
            )
            await message.nack(requeue=True)
            return 0

        try:
            event_id = int(args.event_id)
        except (TypeError, ValueError):
            await message.nack(requeue=True)
            raise SystemExit("--event-id must be a positive decimal integer") from None
        if event_id < 1 or str(event_id) != args.event_id:
            await message.nack(requeue=True)
            raise SystemExit("--event-id must be a positive decimal integer")
        if not args.operator or not re.fullmatch(r"[A-Za-z0-9_.@-]{1,128}", args.operator):
            await message.nack(requeue=True)
            raise SystemExit("--operator must be 1-128 safe identifier characters")
        if (
            not args.reason
            or len(args.reason) > 512
            or not args.reason.strip()
            or any(ord(character) < 32 for character in args.reason)
        ):
            await message.nack(requeue=True)
            raise SystemExit("--reason must be 1-512 printable characters")

        if message.message_id != str(event_id):
            await message.nack(requeue=True)
            print(
                json.dumps(
                    {"action": "head_mismatch", "expected_event_id": str(event_id)},
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            return 2
        try:
            envelope = validate_event(
                message.body, message.message_id, subscription, message.type
            )
        except PermanentEventError as error:
            await message.nack(requeue=True)
            print(
                json.dumps(
                    {"action": "not_replayable", "reason": str(error)}, sort_keys=True
                ),
                file=sys.stderr,
            )
            return 3

        headers = dict(message.headers or {})
        for name in (
            "x-delivery-count",
            "x-death",
            "x-first-death-exchange",
            "x-first-death-queue",
            "x-first-death-reason",
        ):
            headers.pop(name, None)
        for name in tuple(headers):
            if name.startswith("x-last-death-"):
                headers.pop(name, None)
        headers["pulsegrid-replay-operator"] = args.operator
        headers["pulsegrid-replay-reason"] = args.reason
        replay = aio_pika.Message(
            body=message.body,
            headers=headers,
            content_type=message.content_type or "application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            correlation_id=message.correlation_id or envelope["correlation_id"],
            message_id=message.message_id,
            type=message.type or envelope["event_type"],
        )
        confirmed = await exchange.publish(
            replay, routing_key=subscription.routing_key, mandatory=True
        )
        if confirmed is False:
            await message.nack(requeue=True)
            raise RuntimeError("RabbitMQ did not confirm the replay")
        await message.ack()
        print(
            json.dumps(
                {
                    "action": "replay_confirmed",
                    "subscription": args.subscription,
                    "event_id": str(event_id),
                    "operator": args.operator,
                    "reason": args.reason,
                },
                sort_keys=True,
            )
        )
        return 0
    finally:
        if not connection.is_closed:
            await connection.close()


def main() -> None:
    args = _parser().parse_args()
    if not args.peek and (args.event_id is None or args.operator is None or args.reason is None):
        raise SystemExit("Replay requires --event-id, --operator, and --reason")
    if args.peek and any(value is not None for value in (args.event_id, args.operator, args.reason)):
        raise SystemExit("--peek cannot be combined with replay arguments")
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
