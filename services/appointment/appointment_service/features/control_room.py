"""Read-only operational views backed by fixed Prometheus and Tempo queries."""

from __future__ import annotations

import asyncio
import json
import math
import re
from datetime import datetime, timezone
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ..authorization import Principal, require_current_role, require_roles

router = APIRouter()
BASE_PATH = "/api/v1/appointments/operations/control-room"
PROMETHEUS_URL = "http://prometheus:9090"
TEMPO_URL = "http://tempo:3200"
SERVICES = ("patient", "doctor", "appointment", "records", "pharmacy", "billing", "emergency")
EVENT_QUEUES = (
    "pulsegrid.appointment.journey.pharmacy.v1",
    "pulsegrid.dlq.appointment.journey.pharmacy.v1",
    "pulsegrid.appointment.journey.billing.v1",
    "pulsegrid.dlq.appointment.journey.billing.v1",
)
PROM_QUERIES = {
    "readiness": 'probe_success{job="pulsegrid_readiness"}',
    "request_rate": 'sum by (service) (rate(pulsegrid_http_requests_total{job="pulsegrid_api"}[5m]))',
    "error_rate": '100 * sum by (service) (rate(pulsegrid_http_requests_total{job="pulsegrid_api",status_class="5xx"}[5m])) / clamp_min(sum by (service) (rate(pulsegrid_http_requests_total{job="pulsegrid_api"}[5m])), 0.001)',
    "p95_latency": 'histogram_quantile(0.95, sum by (service, le) (rate(pulsegrid_http_request_duration_seconds_bucket{job="pulsegrid_api"}[5m]))) * 1000',
    "alerts": 'ALERTS{alertstate="firing"}',
    "admission": 'sum by (owner, outcome, class, state) (rate(pulsegrid_http_admission_requests_total[5m]))',
    "cache": 'sum by (owner, outcome) (rate(pulsegrid_cache_requests_total[5m]))',
    "breakers": 'max by (owner, dependency, state) (pulsegrid_dependency_circuit_breaker_state)',
    "bulkheads": 'max by (owner, dependency) (pulsegrid_bulkhead_in_flight)',
    "hashing_epoch": 'max by (owner) (pulsegrid_consistent_hashing_topology_epoch)',
    "hashing_nodes": 'max by (owner) (pulsegrid_consistent_hashing_configured_nodes)',
    "queue_ready": 'rabbitmq_detailed_queue_messages_ready{queue=~"pulsegrid[.]appointment.*"}',
    "queue_unacked": 'rabbitmq_detailed_queue_messages_unacked{queue=~"pulsegrid[.]appointment.*"}',
    "queue_consumers": 'rabbitmq_detailed_queue_consumers{queue=~"pulsegrid[.]appointment.*"}',
    "outbox_pending": 'pulsegrid_outbox_pending{component="phase5"}',
    "outbox_oldest": 'pulsegrid_outbox_oldest_pending_seconds{component="phase5"}',
    "publisher_failures": 'sum by (owner, outcome) (increase(pulsegrid_outbox_publish_failures_total[15m]))',
    "consumer_processed": 'sum by (owner, outcome) (increase(pulsegrid_consumer_processed_total[15m]))',
    "delivery_p95": 'histogram_quantile(0.95, sum by (owner, le) (rate(pulsegrid_event_delivery_seconds_bucket[5m])))',
}
TREND_QUERIES = {
    "request_rate": 'sum(rate(pulsegrid_http_requests_total{job="pulsegrid_api"}[5m]))',
    "error_rate": '100 * sum(rate(pulsegrid_http_requests_total{job="pulsegrid_api",status_class="5xx"}[5m])) / clamp_min(sum(rate(pulsegrid_http_requests_total{job="pulsegrid_api"}[5m])), 0.001)',
}


async def require_operator(
    request: Request,
    principal: Principal = Depends(require_roles("ops", "hospital_admin")),
) -> Principal:
    """Require a signed role and recheck that role with the Patient authority."""
    role = "ops" if "ops" in principal.roles else "hospital_admin"
    await require_current_role(role)(request, principal)
    return principal


async def _get_json(base_url: str, path: str, *, params: dict[str, str] | None = None) -> dict:
    url = base_url + path
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(2.0, connect=0.5),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            async with client.stream("GET", url, params=params) as response:
                if response.status_code != 200:
                    raise RuntimeError("monitoring_backend_unavailable")
                raw = bytearray()
                async for part in response.aiter_bytes():
                    raw.extend(part)
                    if len(raw) > 1_000_000:
                        raise RuntimeError("monitoring_response_too_large")
        result = json.loads(raw)
    except (httpx.HTTPError, TimeoutError, ValueError, RuntimeError):
        raise HTTPException(503) from None
    if not isinstance(result, dict):
        raise HTTPException(503)
    return result


async def _prom_query(query: str) -> list[dict]:
    payload = await _get_json(PROMETHEUS_URL, "/api/v1/query", params={"query": query})
    data = payload.get("data")
    if payload.get("status") != "success" or not isinstance(data, dict):
        raise HTTPException(503)
    result = data.get("result")
    if data.get("resultType") != "vector" or not isinstance(result, list) or len(result) > 500:
        raise HTTPException(503)
    return [row for row in result if isinstance(row, dict)]


async def _prom_range(query: str) -> list[dict]:
    end = int(datetime.now(timezone.utc).timestamp())
    payload = await _get_json(
        PROMETHEUS_URL,
        "/api/v1/query_range",
        params={"query": query, "start": str(end - 1800), "end": str(end), "step": "60s"},
    )
    data = payload.get("data")
    if payload.get("status") != "success" or not isinstance(data, dict):
        raise HTTPException(503, detail={"code": "monitoring_unavailable"})
    rows = data.get("result")
    if data.get("resultType") != "matrix" or not isinstance(rows, list) or len(rows) > 10:
        raise HTTPException(503, detail={"code": "monitoring_unavailable"})
    points: dict[int, float] = {}
    for row in rows:
        values = row.get("values") if isinstance(row, dict) else None
        if not isinstance(values, list) or len(values) > 40:
            continue
        for value in values:
            if not isinstance(value, list) or len(value) != 2:
                continue
            try:
                timestamp, number = int(float(value[0])), float(value[1])
            except (TypeError, ValueError, OverflowError):
                continue
            if math.isfinite(number):
                points[timestamp] = points.get(timestamp, 0.0) + number
    return [{"timestamp": timestamp, "value": value} for timestamp, value in sorted(points.items())]


def _number(row: dict) -> float | None:
    value = row.get("value")
    if not isinstance(value, list) or len(value) != 2:
        return None
    try:
        number = float(value[1])
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _metric_label(row: dict, label: str) -> str | None:
    metric = row.get("metric")
    if not isinstance(metric, dict):
        return None
    value = metric.get(label)
    return value if isinstance(value, str) else None


def _by_service(rows: list[dict]) -> dict[str, list[dict]]:
    grouped = {service: [] for service in SERVICES}
    for row in rows:
        service = _metric_label(row, "service")
        if service in grouped:
            grouped[service].append(row)
    return grouped


def _service_summary(queries: dict[str, list[dict]]) -> list[dict]:
    readiness = _by_service(queries["readiness"])
    rates = _by_service(queries["request_rate"])
    errors = _by_service(queries["error_rate"])
    latencies = _by_service(queries["p95_latency"])
    services = []
    for name in SERVICES:
        ready_values = [_number(row) for row in readiness[name]]
        ready_values = [value for value in ready_values if value is not None]
        healthy_targets = sum(value >= 1 for value in ready_values)
        total_targets = len(ready_values)
        state = "no_data" if total_targets == 0 else ("healthy" if healthy_targets == total_targets else "degraded")
        service_rates = [_number(row) for row in rates[name]]
        service_errors = [_number(row) for row in errors[name]]
        service_latencies = [_number(row) for row in latencies[name]]
        rate = sum(value for value in service_rates if value is not None) if service_rates else None
        error_rate = sum(value for value in service_errors if value is not None) if service_errors else None
        p95 = max((value for value in service_latencies if value is not None), default=None)
        services.append({
            "name": name,
            "health": state,
            "healthy_instances": healthy_targets,
            "instance_count": total_targets,
            "request_rate_per_second": rate,
            "error_rate_percent": error_rate,
            "p95_latency_ms": p95,
            "recent_activity": "active" if rate is not None and rate > 0 else ("quiet" if rate is not None else "no_data"),
        })
    return services


def _safe_component_rows(rows: list[dict], labels: tuple[str, ...]) -> list[dict]:
    output = []
    for row in rows[:100]:
        value = _number(row)
        if value is None:
            continue
        metric = row.get("metric") if isinstance(row.get("metric"), dict) else {}
        entry = {key: metric[key] for key in labels if isinstance(metric.get(key), str) and len(metric[key]) <= 64}
        entry["value"] = value
        output.append(entry)
    return output


def _alert_rows(rows: list[dict]) -> list[dict]:
    alerts = []
    for row in rows[:100]:
        if (_number(row) or 0) < 1:
            continue
        alert_name = _metric_label(row, "alertname")
        if not alert_name or len(alert_name) > 96:
            continue
        service = _metric_label(row, "service")
        severity = _metric_label(row, "severity")
        alerts.append({
            "name": alert_name,
            "service": service if service in SERVICES else None,
            "severity": severity if severity in {"warning", "critical", "info"} else "warning",
        })
    return alerts


def _queue_rows(queries: dict[str, list[dict]]) -> list[dict]:
    parts = {key: { _metric_label(row, "queue"): _number(row) for row in queries[key] }
             for key in ("queue_ready", "queue_unacked", "queue_consumers")}
    return [{
        "name": name,
        "ready": max(0, int(parts["queue_ready"].get(name) or 0)),
        "unacknowledged": max(0, int(parts["queue_unacked"].get(name) or 0)),
        "consumers": max(0, int(parts["queue_consumers"].get(name) or 0)),
    } for name in EVENT_QUEUES]


async def _surge_state(request: Request) -> dict:
    limiter = getattr(request.app.state, "admission_limiter", None)
    if limiter is None:
        return {"state": "UNKNOWN", "changed_at": None}
    try:
        snapshot = await limiter.surge_mode()
    except Exception:
        return {"state": "UNKNOWN", "changed_at": None}
    if snapshot.state not in {"NORMAL", "SURGE", "RECOVERY"}:
        return {"state": "UNKNOWN", "changed_at": None}
    changed_at = None
    if snapshot.entered_at_ms:
        changed_at = datetime.fromtimestamp(snapshot.entered_at_ms / 1000, timezone.utc).isoformat().replace("+00:00", "Z")
    return {"state": snapshot.state, "changed_at": changed_at}


async def _recent_events(request: Request) -> tuple[list[dict], bool]:
    factory = getattr(getattr(request.app.state, "database", None), "session_factory", None)
    if factory is None:
        return [], False
    try:
        async with factory() as session:
            rows = (await session.execute(text(
                "SELECT canonical_metadata FROM public.audit_entries "
                "WHERE chain_id='appointment' AND canonical_metadata->>'action' IN "
                "('surge_mode_transition_applied','surge_mode_transition_noop') "
                "ORDER BY sequence DESC LIMIT 20"
            ))).scalars().all()
    except SQLAlchemyError:
        return [], False
    events = []
    for metadata in rows:
        if not isinstance(metadata, dict):
            continue
        action = metadata.get("action")
        if action not in {"surge_mode_transition_applied", "surge_mode_transition_noop"}:
            continue
        events.append({
            "action": action,
            "previous_state": metadata.get("previous_state") if metadata.get("previous_state") in {"NORMAL", "SURGE", "RECOVERY"} else None,
            "new_state": metadata.get("new_state") if metadata.get("new_state") in {"NORMAL", "SURGE", "RECOVERY"} else None,
            "reason_code": metadata.get("reason_code") if metadata.get("reason_code") in {"capacity_pressure", "dependency_degraded", "planned_recovery", "incident_override"} else None,
            "occurred_at": metadata.get("occurred_at") if isinstance(metadata.get("occurred_at"), str) else None,
        })
    return events, True


async def _summary(request: Request) -> dict:
    keys = tuple(PROM_QUERIES)
    semaphore = asyncio.Semaphore(4)

    async def query(key: str) -> list[dict]:
        async with semaphore:
            return await _prom_query(PROM_QUERIES[key])

    values = await asyncio.gather(*(query(key) for key in keys))
    queries = dict(zip(keys, values, strict=True))
    trends = await asyncio.gather(*(_prom_range(query) for query in TREND_QUERIES.values()))
    services = _service_summary(queries)
    alerts = _alert_rows(queries["alerts"])
    request_rate = sum(row["request_rate_per_second"] or 0 for row in services)
    observed_errors = [row["error_rate_percent"] for row in services if row["error_rate_percent"] is not None]
    aggregate_error_rate = None
    if observed_errors and request_rate > 0:
        error_events_per_second = sum(
            (row["request_rate_per_second"] or 0) * (row["error_rate_percent"] or 0) / 100
            for row in services
        )
        aggregate_error_rate = error_events_per_second / request_rate * 100
    p95s = [row["p95_latency_ms"] for row in services if row["p95_latency_ms"] is not None]
    health_states = [row["health"] for row in services]
    overall = "unknown" if "no_data" in health_states else ("degraded" if "degraded" in health_states or alerts else "healthy")
    outbox_pending = _safe_component_rows(queries["outbox_pending"], ("owner",))
    outbox_oldest = _safe_component_rows(queries["outbox_oldest"], ("owner",))
    events, audit_available = await _recent_events(request)
    return {
        "status": "available",
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "system": {
            "health": overall,
            "request_rate_per_second": request_rate,
            "error_rate_percent": aggregate_error_rate,
            "p95_latency_ms": max(p95s, default=None),
            "active_alert_count": len(alerts),
            "surge_mode": await _surge_state(request),
        },
        "services": services,
        "trends": dict(zip(TREND_QUERIES, trends, strict=True)),
        "alerts": alerts,
        "components": {
            "rate_limiter": _safe_component_rows(queries["admission"], ("owner", "outcome", "class", "state")),
            "cache": _safe_component_rows(queries["cache"], ("owner", "outcome")),
            "consistent_hashing": {
                "topology_epoch": _safe_component_rows(queries["hashing_epoch"], ("owner",)),
                "configured_nodes": _safe_component_rows(queries["hashing_nodes"], ("owner",)),
            },
            "circuit_breakers": _safe_component_rows(queries["breakers"], ("owner", "dependency", "state")),
            "bulkheads": _safe_component_rows(queries["bulkheads"], ("owner", "dependency")),
        },
        "messaging": {
            "queues": _queue_rows(queries),
            "outbox_pending_by_owner": outbox_pending,
            "outbox_oldest_seconds_by_owner": outbox_oldest,
            "publisher_failures_15m": _safe_component_rows(queries["publisher_failures"], ("owner", "outcome")),
            "consumer_processed_15m": _safe_component_rows(queries["consumer_processed"], ("owner", "outcome")),
            "delivery_p95_seconds": _safe_component_rows(queries["delivery_p95"], ("owner",)),
        },
        "recent_events": {"available": audit_available, "items": events},
    }


@router.get(BASE_PATH + "/summary")
async def get_summary(request: Request, _principal: Principal = Depends(require_operator)):
    if request.query_params:
        raise HTTPException(422, detail="validation_error")
    return await _summary(request)


def _safe_service(value: object) -> str:
    return value if isinstance(value, str) and value in SERVICES else "unknown"


def _safe_operation(value: object) -> str:
    if not isinstance(value, str) or len(value) > 160:
        return "operation"
    if re.fullmatch(r"(?:GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD) /[A-Za-z0-9_/{}/.:-]+", value):
        path = value.partition(" ")[2]
        if any(
            segment.isdigit()
            or re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,}", segment)
            or re.fullmatch(r"[0-9a-fA-F]{16,}", segment)
            for segment in path.split("/")
        ):
            return value.split(" ", 1)[0] + " request"
        return value
    if value in {"rabbitmq publish", "rabbitmq process"}:
        return value
    return "operation"


async def _trace_search(service: str, start: int, end: int, limit: int) -> list[dict]:
    payload = await _get_json(
        TEMPO_URL,
        "/api/search",
        params={"tags": f"service.name={service}", "start": str(start), "end": str(end), "limit": str(limit)},
    )
    traces = payload.get("traces")
    if not isinstance(traces, list):
        raise HTTPException(503)
    safe = []
    for trace in traces[:limit]:
        if not isinstance(trace, dict):
            continue
        trace_id = trace.get("traceID")
        if not isinstance(trace_id, str) or not re.fullmatch(r"[0-9a-f]{32}", trace_id):
            continue
        try:
            duration_ms = float(trace.get("durationMs", 0))
            start_time = int(trace.get("startTimeUnixNano", 0))
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(duration_ms) or duration_ms < 0 or duration_ms > 86_400_000:
            continue
        safe.append({
            "trace_id": trace_id,
            "service": _safe_service(trace.get("rootServiceName")) if trace.get("rootServiceName") else service,
            "operation": _safe_operation(trace.get("rootTraceName")),
            "duration_ms": duration_ms,
            "start_time_unix_nano": max(0, start_time),
        })
    return safe


@router.get(BASE_PATH + "/traces")
async def get_recent_traces(request: Request, _principal: Principal = Depends(require_operator)):
    if request.query_params:
        raise HTTPException(422, detail="validation_error")
    end = int(datetime.now(timezone.utc).timestamp())
    start = end - 3600
    try:
        semaphore = asyncio.Semaphore(3)

        async def search(service: str) -> list[dict]:
            async with semaphore:
                return await _trace_search(service, start, end, 20)

        results = await asyncio.gather(*(search(service) for service in SERVICES))
    except HTTPException:
        raise
    traces = {}
    for rows in results:
        for row in rows:
            traces[row["trace_id"]] = row
    ordered = sorted(traces.values(), key=lambda row: row["start_time_unix_nano"], reverse=True)[:50]
    return {"status": "available", "window_minutes": 60, "traces": ordered}


def _attribute_value(attributes: object, key: str) -> str | None:
    if not isinstance(attributes, list):
        return None
    for entry in attributes:
        if not isinstance(entry, dict) or entry.get("key") != key:
            continue
        value = entry.get("value")
        if isinstance(value, dict):
            value = value.get("stringValue")
        if isinstance(value, str) and len(value) <= 160:
            return value
    return None


def _trace_spans(payload: dict) -> list[dict]:
    spans = []
    resources = payload.get("resourceSpans", payload.get("batches", []))
    if not isinstance(resources, list):
        return spans
    for resource in resources[:100]:
        if not isinstance(resource, dict):
            continue
        resource_attrs = resource.get("resource", {}).get("attributes", []) if isinstance(resource.get("resource"), dict) else []
        service = _safe_service(_attribute_value(resource_attrs, "service.name"))
        scopes = resource.get("scopeSpans", resource.get("instrumentationLibrarySpans", []))
        if not isinstance(scopes, list):
            continue
        for scope in scopes[:100]:
            batch = scope.get("spans", []) if isinstance(scope, dict) else []
            if not isinstance(batch, list):
                continue
            for span in batch[:500]:
                if len(spans) >= 500:
                    break
                if not isinstance(span, dict):
                    continue
                try:
                    start_nano = int(span.get("startTimeUnixNano", 0))
                    end_nano = int(span.get("endTimeUnixNano", start_nano))
                except (TypeError, ValueError, OverflowError):
                    continue
                spans.append({
                    "service": service,
                    "operation": _safe_operation(span.get("name")),
                    "start_time_unix_nano": max(0, start_nano),
                    "duration_ms": max(0, min(86_400_000, (end_nano - start_nano) / 1_000_000)),
                })
            if len(spans) >= 500:
                break
        if len(spans) >= 500:
            break
    return sorted(spans, key=lambda span: span["start_time_unix_nano"])


@router.get(BASE_PATH + "/traces/{trace_id}")
async def get_trace(
    trace_id: Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")],
    request: Request,
    _principal: Principal = Depends(require_operator),
):
    if request.query_params:
        raise HTTPException(422, detail="validation_error")
    payload = await _get_json(TEMPO_URL, "/api/traces/" + trace_id)
    return {"trace_id": trace_id, "spans": _trace_spans(payload)}


async def surge_metrics_loop(app) -> None:
    """Refresh process-local control gauges without entering request paths."""
    observer = getattr(app.state, "phase4_observer", None)
    limiter = getattr(app.state, "admission_limiter", None)
    if observer is None or limiter is None:
        return
    labels = {"owner": "appointment"}
    while True:
        try:
            async with asyncio.timeout(1.0):
                snapshot = await limiter.surge_mode()
            if snapshot.state in {"NORMAL", "SURGE", "RECOVERY"}:
                observer.gauge("pulsegrid_surge_mode_active", int(snapshot.state == "SURGE"), labels)
                entered = (snapshot.entered_at_ms or 0) / 1000 if snapshot.state == "SURGE" else 0
                observer.gauge("pulsegrid_surge_mode_entered_timestamp_seconds", entered, labels)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Stale/unknown monitoring state must not block hospital work.
            pass
        await asyncio.sleep(15)
