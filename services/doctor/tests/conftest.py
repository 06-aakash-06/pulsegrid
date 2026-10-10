"""Fixtures that keep API tests on an explicitly isolated local PostgreSQL DB."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import httpx
import jwt
import pytest
from alembic import command
from alembic.config import Config
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

from doctor_service.authorization import AuthConfig
from doctor_service.main import create_app
from doctor_service.settings import Settings

SERVICE_ROOT = Path(__file__).resolve().parents[1]
TEST_DATABASE_PREFIX = "pulsegrid_doctor_test_"


@dataclass(frozen=True)
class TokenKit:
    user_private_key: object
    appointment_private_key: object
    user_kid: str = "test-user"
    appointment_kid: str = "test-appointment"

    def user(
        self,
        user_id: str,
        roles: list[str],
        *,
        patient_id: str | None = None,
        auth_version: int = 1,
        issuer: str = "pulsegrid-patient",
        audience: str = "pulsegrid-api",
    ) -> str:
        import time
        import secrets

        now = int(time.time())
        payload = {
            "iss": issuer,
            "aud": audience,
            "sub": user_id,
            "jti": secrets.token_urlsafe(18),
            "iat": now,
            "nbf": now,
            "exp": now + 300,
            "token_use": "access",
            "patient_id": patient_id,
            "roles": roles,
            "auth_version": auth_version,
        }
        return jwt.encode(
            payload,
            self.user_private_key,
            algorithm="RS256",
            headers={"kid": self.user_kid},
        )

    def appointment_service(self, scope: str) -> str:
        import time
        import secrets

        now = int(time.time())
        return jwt.encode(
            {
                "iss": "pulsegrid-service:appointment",
                "aud": "pulsegrid-internal:doctor",
                "sub": "appointment",
                "jti": secrets.token_urlsafe(18),
                "iat": now,
                "nbf": now,
                "exp": now + 60,
                "token_use": "service",
                "scopes": [scope],
            },
            self.appointment_private_key,
            algorithm="RS256",
            headers={"kid": self.appointment_kid},
        )


@dataclass
class TestResources:
    url: URL
    settings: Settings
    auth_config: AuthConfig
    tokens: TokenKit


@pytest.fixture(scope="session")
def test_database_url() -> URL:
    raw_url = os.environ.get("PULSEGRID_DOCTOR_TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip(
            "set PULSEGRID_DOCTOR_TEST_DATABASE_URL to a disposable local test database"
        )
    url = make_url(raw_url)
    if (
        url.drivername not in {"postgresql", "postgresql+psycopg"}
        or url.host not in {"127.0.0.1", "localhost"}
        or not (url.database or "").startswith(TEST_DATABASE_PREFIX)
    ):
        raise RuntimeError(
            "Doctor integration tests require a loopback database named "
            f"{TEST_DATABASE_PREFIX}<unique-suffix>"
        )
    return url.set(drivername="postgresql+psycopg")


@pytest.fixture(scope="session")
def test_resources(test_database_url: URL, tmp_path_factory) -> TestResources:
    user_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    doctor_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    appointment_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_dir = tmp_path_factory.mktemp("doctor-test-keys")

    def public_jwk(key, kid: str, service: str | None = None) -> dict[str, str]:
        value = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
        value.update({"kid": kid, "alg": "RS256", "use": "sig"})
        if service:
            value["service"] = service
        return value

    user_jwks = key_dir / "user-jwks.json"
    service_jwks = key_dir / "service-jwks.json"
    doctor_key_path = key_dir / "doctor-service-key.pem"
    user_jwks.write_text(json.dumps({"keys": [public_jwk(user_key, "test-user")]}))
    service_jwks.write_text(
        json.dumps(
            {
                "keys": [
                    public_jwk(doctor_key, "test-doctor", "doctor"),
                    public_jwk(appointment_key, "test-appointment", "appointment"),
                ]
            }
        )
    )
    doctor_key_path.write_bytes(
        doctor_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    test_url = test_database_url
    settings = Settings(
        environment="test",
        db_host=test_url.host or "127.0.0.1",
        db_port=test_url.port or 5432,
        db_name=test_url.database or "",
        db_user=test_url.username or "",
        db_password=test_url.password or "test-only",
    )
    auth_config = AuthConfig(
        jwks_path=str(user_jwks),
        service_jwks_path=str(service_jwks),
        service_private_key_path=str(doctor_key_path),
        service_kid="test-doctor",
        authority_url="http://patient.test/internal/v1/authorization/check",
        patient_staff_status_url=(
            "http://patient.test/internal/v1/users/{user_id}/staff-status"
        ),
        appointment_schedule_decision_url=(
            "http://appointment.test/internal/v1/schedule-decisions/{proposal_id}"
        ),
        appointment_operational_status_url=(
            "http://appointment.test/internal/v1/doctors/{doctor_id}/operational-status"
        ),
    )
    tokens = TokenKit(user_key, appointment_key)

    env = {
        "PULSEGRID_DOCTOR_DB_HOST": settings.db_host,
        "PULSEGRID_DOCTOR_DB_PORT": str(settings.db_port),
        "PULSEGRID_DOCTOR_DB_NAME": settings.db_name,
        "PULSEGRID_DOCTOR_DB_USER": settings.db_user,
        "PULSEGRID_DOCTOR_DB_PASSWORD": settings.db_password,
    }
    with patch.dict(os.environ, env):
        command.upgrade(Config(str(SERVICE_ROOT / "alembic.ini")), "head")
    return TestResources(test_url, settings, auth_config, tokens)


@pytest.fixture
def fake_dependencies(monkeypatch):
    state = {
        "authority_allowed": True,
        "staff_active": True,
        "staff_roles": ["doctor"],
        "operational": {"bookable_slot_count": 0, "confirmed_booking_count": 0},
        "decisions": {},
    }
    original_async_client = httpx.AsyncClient

    async def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/authorization/check"):
            payload = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "active": state["authority_allowed"],
                    "allowed": state["authority_allowed"],
                    "current_auth_version": payload["auth_version"],
                },
            )
        if "/users/" in path and path.endswith("/staff-status"):
            user_id = path.split("/users/", 1)[1].split("/", 1)[0]
            return httpx.Response(
                200,
                json={
                    "user_id": user_id,
                    "active": state["staff_active"],
                    "roles": state["staff_roles"],
                    "version": 1,
                },
            )
        if path.endswith("/operational-status"):
            doctor_id = path.split("/doctors/", 1)[1].split("/", 1)[0]
            return httpx.Response(
                200,
                json={
                    "doctor_id": doctor_id,
                    **state["operational"],
                    "version": 1,
                },
            )
        if "/schedule-decisions/" in path:
            proposal_id = path.rsplit("/", 1)[-1]
            decision = state["decisions"].get(proposal_id)
            if decision is None:
                return httpx.Response(404, json={"error": {"code": "not_found"}})
            return httpx.Response(200, json=decision)
        return httpx.Response(404, json={"error": {"code": "not_found"}})

    def fake_async_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_async_client)
    return state


@pytest.fixture
def test_db(test_database_url: URL, test_resources: TestResources) -> TestResources:
    engine = create_engine(test_database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "TRUNCATE TABLE audit_entries,audit_heads,outbox_events,inbox_events,"
                    "idempotency_requests,schedule_acknowledgements,schedule_intervals,"
                    "schedule_versions,doctor_specialties,doctors,specialties,id_worker_state"
                )
            )
    finally:
        engine.dispose()
    return test_resources


@pytest.fixture
def doctor_client(
    test_db: TestResources, fake_dependencies, test_resources: TestResources
):
    app = create_app(test_db.settings, test_db.auth_config)
    with TestClient(app) as client:
        client.app.state._test_tokens = test_db.tokens
        client.app.state._test_dependency_state = fake_dependencies
        yield client
