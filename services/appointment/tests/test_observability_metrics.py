from fastapi import FastAPI
from fastapi.testclient import TestClient

from appointment_service.phase4_metrics import mount


def test_http_metrics_use_route_templates_and_bounded_labels() -> None:
    app = FastAPI()
    mount(app)

    @app.get("/synthetic/items/{item_id}")
    async def get_item(item_id: str):
        return {"received": bool(item_id)}

    @app.get("/health/ready")
    async def ready():
        return {"status": "ready"}

    with TestClient(app) as client:
        response = client.get("/synthetic/items/private-id?token=private-value")
        client.get("/health/ready")
        exposition = client.get("/metrics")

    assert response.status_code == 200
    assert exposition.status_code == 200
    assert exposition.headers["content-type"].startswith("text/plain; version=0.0.4")
    body = exposition.text
    assert "pulsegrid_http_requests_total{method=\"GET\",route=\"/synthetic/items/{item_id}\",status_class=\"2xx\"} 1" in body
    assert "pulsegrid_http_request_duration_seconds_bucket{method=\"GET\",route=\"/synthetic/items/{item_id}\",status_class=\"2xx\",le=\"+Inf\"} 1" in body
    assert "/health/ready" not in body
    assert "private-id" not in body
    assert "private-value" not in body


def test_component_observer_escapes_label_values() -> None:
    app = FastAPI()
    mount(app)
    app.state.phase4_observer.increment(
        "pulsegrid_synthetic_checks_total", {"outcome": 'quoted"line\n'}
    )

    body = app.state.phase4_observer.render()
    assert 'outcome="quoted\\"line\\n"' in body
