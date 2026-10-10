"""Explicitly isolated PostgreSQL resources for emergency workflow tests."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

import emergency_service.authorization as authorization
from emergency_service.main import create_app
from emergency_service.settings import Settings


@pytest.fixture(scope="session")
def emergency_test_url():
    raw_url = os.environ.get("PULSEGRID_EMERGENCY_TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("set PULSEGRID_EMERGENCY_TEST_DATABASE_URL to a dedicated *_test database")
    url = make_url(raw_url)
    if not url.database or not url.database.endswith("_test"):
        pytest.fail("Emergency workflow tests require a database name ending in _test")
    if url.drivername not in {"postgresql", "postgresql+psycopg"}:
        pytest.fail("Emergency workflow tests require PostgreSQL with psycopg")
    return url.set(drivername="postgresql+psycopg")


@pytest.fixture()
def workflow_client(monkeypatch, tmp_path: Path, emergency_test_url):
    engine = create_engine(emergency_test_url, hide_parameters=True)
    try:
        with engine.connect() as connection:
            current_user = connection.scalar(text("SELECT current_user"))
            revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
            function_exists = connection.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM pg_proc "
                    "WHERE proname = 'append_emergency_audit')"
                )
            )
        if revision != "0003_emergency_workflow" or not function_exists:
            pytest.fail(
                "Migrate the dedicated emergency test database to "
                "0003_emergency_workflow before running workflow tests"
            )
        if current_user != "emergency_app":
            pytest.fail("Use the emergency_app runtime role for workflow integration tests")
    finally:
        engine.dispose()

    public_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(public_key.public_key()))
    public_jwk.update(kid="emergency-test", alg="RS256", use="sig")
    jwks_path = tmp_path / "user-jwks.json"
    jwks_path.write_text(json.dumps({"keys": [public_jwk]}))
    monkeypatch.setenv(
        "PULSEGRID_EMERGENCY_AUTH_JWKS_PATH", str(jwks_path)
    )
    monkeypatch.setenv("PULSEGRID_EMERGENCY_AUTH_SERVICE_JWKS_PATH", "")
    monkeypatch.setenv("PULSEGRID_EMERGENCY_AUTH_SERVICE_PRIVATE_KEY_PATH", "")

    settings = Settings(
        environment="test",
        db_host=emergency_test_url.host or "127.0.0.1",
        db_port=emergency_test_url.port or 5432,
        db_name=emergency_test_url.database,
        db_user=emergency_test_url.username or "",
        db_password=emergency_test_url.password or "",
        id_worker_id=6,
    )

    class PatientAuthorityStub:
        calls: list[tuple[str, str]] = []
        allow_authority = True
        patient_active = True

        def __init__(self, **options):
            assert options["follow_redirects"] is False
            assert options["trust_env"] is False
            assert options["timeout"] in (1, 2)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, *, json, headers):
            assert url.endswith("/internal/v1/authorization/check")
            assert headers["Authorization"] == "Bearer synthetic-service-token"
            assert headers["X-Delegated-Authorization"].startswith("Bearer ")
            self.calls.append(("authorization", json["required_role"]))
            return httpx.Response(
                200,
                json={
                    "active": self.allow_authority,
                    "allowed": self.allow_authority,
                    "current_auth_version": 1,
                },
                request=httpx.Request("POST", url),
            )

        async def get(self, url, *, headers):
            assert "/internal/v1/patients/" in url
            assert headers["Authorization"] == "Bearer synthetic-service-token"
            assert headers["X-Delegated-Authorization"].startswith("Bearer ")
            patient_id = url.split("/")[-2]
            self.calls.append(("patient-status", patient_id))
            return httpx.Response(
                200,
                json={
                    "patient_id": patient_id,
                    "active": self.patient_active,
                    "version": 1,
                },
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(authorization, "service_token", lambda *_args, **_kwargs: "synthetic-service-token")
    monkeypatch.setattr(authorization.httpx, "AsyncClient", PatientAuthorityStub)
    app = create_app(settings)
    with TestClient(app) as client:
        yield client, public_key, PatientAuthorityStub


def access_token(private_key, user_id: str, roles: list[str], patient_id: str | None = None):
    now = int(time.time())
    claims = {
        "iss": "pulsegrid-patient",
        "aud": "pulsegrid-api",
        "sub": user_id,
        "jti": uuid4().hex,
        "iat": now,
        "nbf": now,
        "exp": now + 600,
        "roles": roles,
        "auth_version": 1,
        "token_use": "access",
    }
    if patient_id is not None:
        claims["patient_id"] = patient_id
    return jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": "emergency-test"},
    )


def auth_headers(private_key, user_id: str, roles: list[str], patient_id: str | None = None):
    return {
        "Authorization": "Bearer " + access_token(private_key, user_id, roles, patient_id)
    }
