"""W3C trace-context propagation for asynchronous event delivery."""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.trace import SpanKind

_PROPAGATOR = TraceContextTextMapPropagator()


def _context(traceparent: str | None):
    if not isinstance(traceparent, str) or len(traceparent) > 128:
        return None
    context = _PROPAGATOR.extract({"traceparent": traceparent}, context=Context())
    return context if trace.get_current_span(context).get_span_context().is_valid else None


def publish_span(envelope: dict, event_type: str):
    """Continue an originating request trace and mark the broker publish."""
    return trace.get_tracer("pulsegrid.messaging").start_as_current_span(
        "rabbitmq publish",
        context=_context(envelope.get("traceparent")),
        kind=SpanKind.PRODUCER,
        attributes={
            "messaging.system": "rabbitmq",
            "messaging.destination.name": "pulsegrid.events",
            "messaging.operation.type": "publish",
            "messaging.message.type": event_type,
        },
    )


def inject_traceparent() -> dict[str, str]:
    carrier: dict[str, str] = {}
    _PROPAGATOR.inject(carrier)
    value = carrier.get("traceparent")
    return {"traceparent": value} if isinstance(value, str) else {}


def consume_span(traceparent: str | None, queue_name: str, event_type: str):
    """Start a bounded consumer span, continuing only valid W3C trace context."""
    return trace.get_tracer("pulsegrid.messaging").start_as_current_span(
        "rabbitmq process",
        context=_context(traceparent),
        kind=SpanKind.CONSUMER,
        attributes={
            "messaging.system": "rabbitmq",
            "messaging.destination.name": queue_name,
            "messaging.operation.type": "process",
            "messaging.message.type": event_type,
        },
    )
