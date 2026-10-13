from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from appointment_service.features import control_room


def _series(metric, value):
    return {"metric": metric, "value": [1, str(value)]}


def test_service_summary_aggregates_doctor_replicas_and_preserves_no_data():
    queries = {
        "readiness": [
            _series({"service": "doctor", "replica_source": "doctor"}, 1),
            _series({"service": "doctor", "replica_source": "doctor_replica"}, 1),
            _series({"service": "patient", "replica_source": "patient"}, 0),
        ],
        "request_rate": [
            _series({"service": "doctor"}, 2.5),
            _series({"service": "patient"}, 1),
        ],
        "error_rate": [_series({"service": "doctor"}, 4)],
        "p95_latency": [_series({"service": "doctor"}, 125)],
    }

    result = control_room._service_summary(queries)

    doctor = next(row for row in result if row["name"] == "doctor")
    patient = next(row for row in result if row["name"] == "patient")
    records = next(row for row in result if row["name"] == "records")
    assert doctor["health"] == "healthy"
    assert doctor["instance_count"] == 2
    assert doctor["request_rate_per_second"] == 2.5
    assert doctor["error_rate_percent"] == 4
    assert patient["health"] == "degraded"
    assert records["health"] == "no_data"
    assert records["request_rate_per_second"] is None


def test_hashing_topology_uses_fixed_queries_and_bounded_output():
    assert control_room.PROM_QUERIES["hashing_epoch"] == (
        "max by (owner) (pulsegrid_consistent_hashing_topology_epoch)"
    )
    assert control_room.PROM_QUERIES["hashing_nodes"] == (
        "max by (owner) (pulsegrid_consistent_hashing_configured_nodes)"
    )
    result = control_room._safe_component_rows(
        [_series({"owner": "doctor", "node_id": "private-node-name"}, 17)],
        ("owner",),
    )
    assert result == [{"owner": "doctor", "value": 17.0}]


def test_trace_summaries_allow_only_safe_operation_and_span_fields():
    assert control_room._safe_operation("GET /api/v1/doctors/{doctor_id}") == "GET /api/v1/doctors/{doctor_id}"
    assert control_room._safe_operation("GET /api/v1/doctors/12345") == "GET request"
    assert control_room._safe_operation("GET /api/v1/doctors/7a11cfa0-2333-49ad-a4c5-45f2c74ed344") == "GET request"
    assert control_room._safe_operation("GET /api/v1/doctors/4bf92f3577b34da6a3ce929d0e0e4736") == "GET request"
    assert control_room._safe_operation("SELECT patient_name FROM records") == "operation"

    payload = {
        "batches": [{
            "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "appointment"}}]},
            "scopeSpans": [{"spans": [{
                "name": "POST /api/v1/appointments",
                "startTimeUnixNano": "1000000",
                "endTimeUnixNano": "3000000",
                "attributes": [
                    {"key": "patient.name", "value": {"stringValue": "Synthetic Example"}},
                    {"key": "db.statement", "value": {"stringValue": "sensitive query"}},
                ],
            }]}],
        }]
    }
    spans = control_room._trace_spans(payload)
    assert spans == [{
        "service": "appointment",
        "operation": "POST /api/v1/appointments",
        "start_time_unix_nano": 1_000_000,
        "duration_ms": 2,
    }]
    assert "patient.name" not in repr(spans)
    assert "db.statement" not in repr(spans)


def test_trace_detail_has_a_hard_span_limit():
    payload = {
        "resourceSpans": [{
            "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "appointment"}}]},
            "scopeSpans": [{"spans": [{"name": "POST /api/v1/appointments"} for _ in range(600)]}],
        }]
    }

    assert len(control_room._trace_spans(payload)) == 500


def test_event_trace_context_uses_only_valid_traceparent():
    from appointment_service.event_tracing import _context
    from opentelemetry import trace

    assert _context(None) is None
    assert _context("not-a-traceparent") is None

    context = _context("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
    span_context = trace.get_current_span(context).get_span_context()
    assert span_context.is_valid
    assert f"{span_context.trace_id:032x}" == "4bf92f3577b34da6a3ce929d0e0e4736"


def test_control_room_api_rejects_anonymous_requests():
    app = FastAPI()
    class RejectingVerifier:
        def user(self, _token):
            raise HTTPException(401)

    app.state.auth_verifier = RejectingVerifier()
    app.include_router(control_room.router)
    client = TestClient(app)

    response = client.get(control_room.BASE_PATH + "/summary")

    assert response.status_code == 401
