"""Smoke tests for the appointment application scaffold."""

from fastapi.testclient import TestClient

from appointment_service.constants import SERVICE_NAME
from appointment_service.main import app
from appointment_service.middleware import validate_traceparent
from appointment_service.settings import Settings

client = TestClient(app)


def test_liveness_reports_the_service() -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive", "service": SERVICE_NAME}
    assert response.headers["x-request-id"]
    assert response.headers["x-correlation-id"]


def test_readiness_does_not_claim_database_is_ready() -> None:
    response = client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["application"] == "ready"
    assert body["dependencies"]["database"] == {
        "status": "unconfigured",
        "required": True,
    }


def test_valid_request_ids_are_returned_in_response_headers() -> None:
    request_id = "1cd90062-a703-47f8-a700-8db24103bab8"
    correlation_id = "99c93160-76c4-4a0e-80bc-27f91a9af962"

    response = client.get(
        "/health/live",
        headers={
            "X-Request-ID": request_id,
            "X-Correlation-ID": correlation_id,
            "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
        },
    )

    assert response.status_code == 200
    assert response.headers["x-request-id"] == request_id
    assert response.headers["x-correlation-id"] == correlation_id


def test_invalid_request_id_returns_safe_error_envelope() -> None:
    response = client.get("/health/live", headers={"X-Request-ID": "not-a-uuid"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request_id"
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]



def test_unknown_route_uses_common_error_envelope() -> None:
    response = client.get("/not-a-route")

    assert response.status_code == 404
    body = response.json()["error"]
    assert body["code"] == "not_found"
    assert body["request_id"] == response.headers["x-request-id"]


def test_traceparent_validation_rejects_invalid_and_accepts_w3c_context() -> None:
    valid = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"

    assert validate_traceparent(valid) == valid
    assert validate_traceparent("00-00000000000000000000000000000000-00f067aa0ba902b7-01") is None
    assert validate_traceparent("invalid") is None


def test_settings_use_service_scoped_environment_variables() -> None:
    settings = Settings.from_env(
        {
            f"PULSEGRID_{SERVICE_NAME.upper()}_ENVIRONMENT": "test",
            f"PULSEGRID_{SERVICE_NAME.upper()}_LOG_LEVEL": "debug",
        }
    )

    assert settings.environment == "test"
    assert settings.log_level == "DEBUG"
