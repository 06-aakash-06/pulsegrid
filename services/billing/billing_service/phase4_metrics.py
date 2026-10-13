"""Bounded process-local diagnostics and Prometheus HTTP metrics."""

from __future__ import annotations

from collections import defaultdict
from threading import Lock
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response


_HTTP_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
_EXCLUDED_PATHS = {"/metrics", "/health/live", "/health/ready", "/api/v1/health/live", "/api/v1/health/ready"}


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _labels(labels: tuple[tuple[str, str], ...]) -> str:
    return "{" + ",".join(f'{key}="{_escape(value)}"' for key, value in labels) + "}"


class Observer:
    """Small process-local store for existing component observations."""

    def __init__(self):
        self.values = defaultdict(float)
        self.lock = Lock()

    def _key(self, name, labels):
        if not name.startswith("pulsegrid_"):
            raise ValueError("Invalid metric")
        allowed = {
            "component", "owner", "policy", "outcome", "backend", "kind",
            "node_id", "worker_id", "state", "class", "dependency",
        }
        if set(labels) - allowed:
            raise ValueError("Invalid metric labels")
        return name, tuple(sorted((key, str(value)) for key, value in labels.items()))

    def increment(self, name, labels, value=1):
        with self.lock:
            key = self._key(name, labels)
            if key not in self.values and len(self.values) >= 2048:
                return
            self.values[key] += value

    def observe(self, name, seconds, labels):
        self.increment(name + "_sum", labels, seconds)
        self.increment(name + "_count", labels)

    def gauge(self, name, value, labels):
        with self.lock:
            key = self._key(name, labels)
            if key not in self.values and len(self.values) >= 2048:
                return
            self.values[key] = value

    def render(self):
        with self.lock:
            rows = []
            for (name, labels), value in sorted(self.values.items()):
                rows.append(f"{name}{_labels(labels)} {value}")
            return "\n".join(rows) + ("\n" if rows else "")


class HttpMetrics:
    """Bounded RED metrics with framework route templates only."""

    def __init__(self):
        self.lock = Lock()
        self.requests = defaultdict(int)
        self.histograms = defaultdict(lambda: [0] * len(_HTTP_BUCKETS))
        self.duration_sum = defaultdict(float)
        self.in_flight = 0

    def start(self):
        with self.lock:
            self.in_flight += 1

    def finish(self, method: str, route: str, status_class: str, elapsed: float):
        labels = (method, route, status_class)
        with self.lock:
            self.in_flight = max(0, self.in_flight - 1)
            self.requests[labels] += 1
            self.duration_sum[labels] += elapsed
            buckets = self.histograms[labels]
            for index, boundary in enumerate(_HTTP_BUCKETS):
                if elapsed <= boundary:
                    buckets[index] += 1

    def render(self) -> str:
        with self.lock:
            rows = [
                "# HELP pulsegrid_http_requests_total Completed HTTP requests.",
                "# TYPE pulsegrid_http_requests_total counter",
                "# HELP pulsegrid_http_request_duration_seconds HTTP request duration in seconds.",
                "# TYPE pulsegrid_http_request_duration_seconds histogram",
                "# HELP pulsegrid_http_requests_in_flight HTTP requests currently executing in this process.",
                "# TYPE pulsegrid_http_requests_in_flight gauge",
            ]
            for labels, count in sorted(self.requests.items()):
                label_text = _labels(tuple(zip(("method", "route", "status_class"), labels)))
                rows.append(f"pulsegrid_http_requests_total{label_text} {count}")
                for boundary, bucket_count in zip(_HTTP_BUCKETS, self.histograms[labels]):
                    bucket_labels = _labels(tuple(zip(("method", "route", "status_class"), labels)) + (("le", str(boundary)),))
                    rows.append(f"pulsegrid_http_request_duration_seconds_bucket{bucket_labels} {bucket_count}")
                infinite_labels = _labels(tuple(zip(("method", "route", "status_class"), labels)) + (("le", "+Inf"),))
                rows.append(f"pulsegrid_http_request_duration_seconds_bucket{infinite_labels} {count}")
                rows.append(f"pulsegrid_http_request_duration_seconds_sum{label_text} {self.duration_sum[labels]}")
                rows.append(f"pulsegrid_http_request_duration_seconds_count{label_text} {count}")
            rows.append(f"pulsegrid_http_requests_in_flight {self.in_flight}")
            return "\n".join(rows) + "\n"


def _safe_method(value: str) -> str:
    method = value.upper()
    return method if method in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"} else "OTHER"


def _route_template(request: Request) -> str:
    route = getattr(request.scope.get("route"), "path", None)
    if not isinstance(route, str) or not route.startswith("/"):
        return "unmatched"
    return route[:160]


def mount(app: FastAPI):
    app.state.phase4_observer = Observer()
    app.state.http_metrics = HttpMetrics()

    @app.middleware("http")
    async def collect_http_metrics(request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if path in _EXCLUDED_PATHS:
            return await call_next(request)
        method = _safe_method(request.method)
        metrics: HttpMetrics = request.app.state.http_metrics
        metrics.start()
        started = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            metrics.finish(method, _route_template(request), f"{status_code // 100}xx", perf_counter() - started)

    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        body = app.state.phase4_observer.render() + app.state.http_metrics.render()
        return PlainTextResponse(body, media_type="text/plain; version=0.0.4; charset=utf-8")
