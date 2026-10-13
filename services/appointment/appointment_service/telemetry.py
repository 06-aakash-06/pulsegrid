"""Optional OpenTelemetry wiring kept outside business readiness paths."""

from __future__ import annotations

import math
import os


_EXCLUDED_URLS = r"/metrics(?:\?.*)?$|/health/(?:live|ready)(?:\?.*)?$|/api/v1/health/(?:live|ready)(?:\?.*)?$"


def configure(app, service_name: str) -> bool:
    if os.environ.get("PULSEGRID_TELEMETRY_ENABLED", "false") != "true":
        return False

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "").strip()
    if not endpoint:
        return False

    try:
        from opentelemetry import propagate, trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        sample_ratio = float(os.environ.get("PULSEGRID_TRACE_SAMPLE_RATIO", "0.1"))
        if not math.isfinite(sample_ratio):
            sample_ratio = 0.1
        sample_ratio = max(0.0, min(1.0, sample_ratio))
        provider = TracerProvider(
            resource=Resource.create({SERVICE_NAME: service_name}),
            sampler=ParentBased(TraceIdRatioBased(sample_ratio)),
        )
        exporter = OTLPSpanExporter(endpoint=endpoint, timeout=2.0)
        provider.add_span_processor(
            BatchSpanProcessor(
                exporter,
                max_queue_size=1024,
                max_export_batch_size=128,
                schedule_delay_millis=1000,
                export_timeout_millis=2000,
            )
        )
        trace.set_tracer_provider(provider)
        propagate.set_global_textmap(TraceContextTextMapPropagator())

        FastAPIInstrumentor.instrument_app(
            app,
            tracer_provider=provider,
            excluded_urls=_EXCLUDED_URLS,
        )
        HTTPXClientInstrumentor().instrument(tracer_provider=provider)
        SQLAlchemyInstrumentor().instrument(
            tracer_provider=provider,
            enable_commenter=False,
        )
        RedisInstrumentor().instrument(tracer_provider=provider)
        app.state.otel_tracer_provider = provider
        return True
    except Exception as error:
        app.state.otel_tracer_provider = None
        app.state.logger.warning(
            "telemetry_setup_unavailable",
            extra={"service": service_name, "reason": type(error).__name__},
        )
        return False


def shutdown(app) -> None:
    provider = getattr(app.state, "otel_tracer_provider", None)
    if provider is None:
        return
    try:
        provider.force_flush(timeout_millis=2000)
    except Exception:
        pass
    try:
        provider.shutdown()
    except Exception:
        pass
