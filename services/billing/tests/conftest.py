"""Fixtures for isolated PostgreSQL and mocked private owner APIs."""

from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import jwt
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from billing_service.authorization import AuthConfig
from billing_service.main import create_app
from billing_service.settings import Settings


def _jwk(private_key, kid: str) -> dict:
    value = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    value.update({"kid": kid, "alg": "RS256", "use": "sig"})
    return value


@pytest.fixture(scope="session")
def database_url():
    value = os.environ.get("PULSEGRID_BILLING_TEST_DATABASE_URL")
    if not value:
        pytest.skip("PULSEGRID_BILLING_TEST_DATABASE_URL is not configured")
    return value


@pytest.fixture(scope="session")
def migrated_database(database_url):
    app_url = make_url(database_url)
    migration_url = app_url.set(username="billing_migration", password="migration-test")
    env = {
        "PULSEGRID_BILLING_DB_HOST": migration_url.host or "127.0.0.1",
        "PULSEGRID_BILLING_DB_PORT": str(migration_url.port or 5432),
        "PULSEGRID_BILLING_DB_NAME": migration_url.database or "billing_test",
        "PULSEGRID_BILLING_DB_USER": migration_url.username or "billing_migration",
        "PULSEGRID_BILLING_DB_PASSWORD": migration_url.password or "migration-test",
    }
    previous = {key: os.environ.get(key) for key in env}
    os.environ.update(env)
    try:
        config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
        command.upgrade(config, "head")
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return database_url


@dataclass
class OwnerServices:
    appointments: dict[str, dict] = field(default_factory=dict)
    consultations: dict[str, dict] = field(default_factory=dict)
    dispensings: dict[str, dict] = field(default_factory=dict)
    failures: dict[str, int] = field(default_factory=dict)
    authority_active: bool = True
    current_auth_version: int = 1


@dataclass
class BillingTestEnvironment:
    client: TestClient
    owners: OwnerServices
    user_private_key: object
    user_id: str
    patient_id: str
    staff_user_id: str
    database_url: str

    def token(self, role: str, *, user_id: str | None = None, patient_id: str | None = None) -> str:
        private_key = self.user_private_key
        now = int(time.time())
        subject = user_id or (self.staff_user_id if role == "billing_staff" else self.user_id)
        claims = {
            "iss": "pulsegrid-patient",
            "aud": "pulsegrid-api",
            "sub": subject,
            "jti": secrets.token_urlsafe(16),
            "iat": now,
            "nbf": now,
            "exp": now + 300,
            "token_use": "access",
            "roles": [role],
            "auth_version": 1,
        }
        chosen_patient = patient_id
        if role == "patient":
            claims["patient_id"] = chosen_patient or self.patient_id
        return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "user-test"})

    def headers(self, role: str, *, key: str = "test-idempotency-key-0001", etag: str | None = None, **kwargs):
        result = {"Authorization": "Bearer " + self.token(role, **kwargs), "Idempotency-Key": key}
        if etag is not None:
            result["If-Match"] = etag
        return result


@pytest.fixture
def billing_env(database_url, migrated_database, tmp_path, monkeypatch):
    database = make_url(database_url)
    test_owner = OwnerServices()
    user_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    service_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    user_jwks = tmp_path / "user-jwks.json"
    service_jwks = tmp_path / "service-jwks.json"
    user_jwks.write_text(json.dumps({"keys": [_jwk(user_private, "user-test")]}))
    service_entry = _jwk(service_private, "billing-test")
    service_entry["service"] = "billing"
    service_jwks.write_text(json.dumps({"keys": [service_entry]}))
    service_key_path = tmp_path / "billing-private.pem"
    service_key_path.write_bytes(
        service_private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    auth_config = AuthConfig(
        jwks_path=str(user_jwks),
        service_jwks_path=str(service_jwks),
        service_private_key_path=str(service_key_path),
        service_kid="billing-test",
    )
    settings = Settings(
        environment="test",
        db_host=database.host or "127.0.0.1",
        db_port=database.port or 5432,
        db_name=database.database or "billing_test",
        db_user=database.username or "billing_app",
        db_password=database.password or "app-test",
    )
    app = create_app(settings, auth_config)

    service_public = service_private.public_key()
    user_public = user_private.public_key()

    def handle_private(request: httpx.Request, owner: str, scope: str, mapping: dict):
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return httpx.Response(401)
        try:
            claims = jwt.decode(
                auth[7:],
                service_public,
                algorithms=["RS256"],
                issuer="pulsegrid-service:billing",
                audience=f"pulsegrid-internal:{owner}",
            )
            if claims.get("scopes") != [scope]:
                return httpx.Response(403)
        except jwt.PyJWTError:
            return httpx.Response(401)
        delegated = request.headers.get("x-delegated-authorization", "")
        if not delegated.startswith("Bearer "):
            return httpx.Response(401)
        try:
            user_claims = jwt.decode(
                delegated[7:],
                user_public,
                algorithms=["RS256"],
                issuer="pulsegrid-patient",
                audience="pulsegrid-api",
            )
        except jwt.PyJWTError:
            return httpx.Response(401)
        if "billing_staff" not in user_claims.get("roles", []):
            return httpx.Response(403)
        identifier = request.url.path.rsplit("/", 2)[-2] if owner == "pharmacy" else request.url.path.rsplit("/", 2)[-2]
        value = mapping.get(identifier)
        if value is None:
            return httpx.Response(404)
        return httpx.Response(200, json=value)

    def transport_handler(request: httpx.Request):
        path = request.url.path
        if path == "/internal/v1/authorization/check":
            try:
                service_claims = jwt.decode(
                    request.headers["authorization"][7:],
                    service_public,
                    algorithms=["RS256"],
                    issuer="pulsegrid-service:billing",
                    audience="pulsegrid-internal:patient",
                )
                user_claims = jwt.decode(
                    request.headers["x-delegated-authorization"][7:],
                    user_public,
                    algorithms=["RS256"],
                    issuer="pulsegrid-patient",
                    audience="pulsegrid-api",
                )
                body = json.loads(request.content)
                allowed = (
                    service_claims.get("scopes") == ["authorization:check"]
                    and body["required_role"] in user_claims.get("roles", [])
                    and body["auth_version"] == user_claims.get("auth_version")
                )
                return httpx.Response(
                    200,
                    json={
                        "active": test_owner.authority_active,
                        "allowed": allowed,
                        "current_auth_version": test_owner.current_auth_version,
                    },
                )
            except (KeyError, ValueError, jwt.PyJWTError):
                return httpx.Response(401)
        if path.startswith("/internal/v1/appointments/"):
            if test_owner.failures.get("appointment"):
                return httpx.Response(test_owner.failures["appointment"])
            return handle_private(request, "appointment", "appointments:billing-context", test_owner.appointments)
        if path.startswith("/internal/v1/consultations/"):
            if test_owner.failures.get("records"):
                return httpx.Response(test_owner.failures["records"])
            return handle_private(request, "records", "consultations:charge-context", test_owner.consultations)
        if path.startswith("/internal/v1/dispensings/"):
            if test_owner.failures.get("pharmacy"):
                return httpx.Response(test_owner.failures["pharmacy"])
            return handle_private(request, "pharmacy", "dispensings:charge-context", test_owner.dispensings)
        return httpx.Response(404)

    real_async_client = httpx.AsyncClient

    def mocked_async_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(transport_handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mocked_async_client)
    client = TestClient(app)
    client.__enter__()
    try:
        yield BillingTestEnvironment(
            client,
            test_owner,
            user_private,
            str(secrets.randbelow(9_000_000_000_000_000_000) + 1),
            str(secrets.randbelow(9_000_000_000_000_000_000) + 1),
            str(secrets.randbelow(9_000_000_000_000_000_000) + 1),
            database_url,
        )
    finally:
        client.__exit__(None, None, None)
