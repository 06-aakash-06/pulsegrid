"""Real PostgreSQL and signed synthetic JWT fixtures. No foreign DBs."""

import json
import os
import time
import uuid
from pathlib import Path

import httpx
import jwt
import psycopg
import pytest
from alembic import command
from alembic.config import Config
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Request
from fastapi.testclient import TestClient
from psycopg import sql
from records_service.database import get_database_session
from records_service.main import create_app
from records_service.settings import Settings


@pytest.fixture(scope="session")
def cluster():
    port = os.environ.get("PULSEGRID_RECORDS_TEST_PORT")
    if not port:
        pytest.skip(
            "Run tests/run_isolated.py for disposable PostgreSQL integration tests"
        )
    password = os.environ["PULSEGRID_RECORDS_TEST_PASSWORD"]
    dsn = dict(
        host="127.0.0.1", port=int(port), dbname="postgres", user=os.environ.get("USER")
    )
    with psycopg.connect(**dsn, autocommit=True) as conn:
        directory = conn.execute("SHOW data_directory").fetchone()[0]
        expected = os.environ["PULSEGRID_RECORDS_TEST_CLUSTER"]
        assert Path(directory).resolve() == Path(expected).resolve()
        assert (
            Path(expected)
            .resolve()
            .is_relative_to(Path(__file__).resolve().parents[1] / ".test-resources")
        )
        for role in ("records_migration", "records_app"):
            conn.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(password)
                )
            )
    return dsn, password


@pytest.fixture
def database(cluster, monkeypatch):
    dsn, password = cluster
    name = "records_test_" + uuid.uuid4().hex
    with psycopg.connect(**dsn, autocommit=True) as conn:
        conn.execute(
            sql.SQL("CREATE DATABASE {} OWNER records_migration").format(
                sql.Identifier(name)
            )
        )
    admin_dsn = {**dsn, "dbname": name}
    with psycopg.connect(**admin_dsn, autocommit=True) as conn:
        conn.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        conn.execute("GRANT USAGE, CREATE ON SCHEMA public TO records_migration")
        conn.execute("GRANT USAGE ON SCHEMA public TO records_app")
        conn.execute(
            "ALTER DEFAULT PRIVILEGES FOR ROLE records_migration IN SCHEMA public GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO records_app"
        )
    for key, value in dict(
        DB_HOST="127.0.0.1",
        DB_PORT=dsn["port"],
        DB_NAME=name,
        DB_USER="records_migration",
        DB_PASSWORD=password,
    ).items():
        monkeypatch.setenv("PULSEGRID_RECORDS_" + key, str(value))
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[1] / "migrations")
    )
    command.upgrade(config, "0002_explicit_worker")
    # Upgrade retains a Phase 1 audit anchor.
    with psycopg.connect(**admin_dsn) as conn:
        conn.execute(
            "INSERT INTO audit_heads(chain_id,last_hash) VALUES ('phase1-anchor',%s)",
            ("0" * 64,),
        )
    command.upgrade(config, "head")
    monkeypatch.setenv("PULSEGRID_RECORDS_DB_USER", "records_app")
    yield admin_dsn, password
    with psycopg.connect(**dsn, autocommit=True) as conn:
        conn.execute(
            sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
        )


@pytest.fixture
def clinical(database, tmp_path, monkeypatch):
    admin_dsn, password = database
    keys = {
        s: rsa.generate_private_key(public_exponent=65537, key_size=2048)
        for s in ("patient-user", "records", "pharmacy", "billing", "appointment")
    }
    user_jwks = tmp_path / "users.json"
    service_jwks = tmp_path / "services.json"

    def public(key, kid, owner=None):
        data = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
        data.update(kid=kid, alg="RS256", use="sig")
        if owner:
            data["service"] = owner
        return data

    user_jwks.write_text(json.dumps({"keys": [public(keys["patient-user"], "user")]}))
    service_jwks.write_text(
        json.dumps(
            {"keys": [public(keys[s], s, s) for s in keys if s != "patient-user"]}
        )
    )
    private = tmp_path / "records.pem"
    private.write_bytes(
        keys["records"].private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    for name, value in dict(
        JWKS_PATH=user_jwks,
        SERVICE_JWKS_PATH=service_jwks,
        SERVICE_PRIVATE_KEY_PATH=private,
        SERVICE_KID="records",
    ).items():
        monkeypatch.setenv("PULSEGRID_RECORDS_AUTH_" + name, str(value))

    def token(user="20", role="doctor", patient_id=None, **overrides):
        stamp = int(time.time())
        claims = dict(
            iss="pulsegrid-patient",
            aud="pulsegrid-api",
            sub=user,
            jti=uuid.uuid4().hex,
            iat=stamp,
            nbf=stamp,
            exp=stamp + 600,
            token_use="access",
            roles=[role],
            auth_version=1,
            patient_id=patient_id,
        )
        claims.update(overrides)
        return jwt.encode(
            claims, keys["patient-user"], algorithm="RS256", headers={"kid": "user"}
        )

    def service(
        caller="pharmacy",
        scope="prescriptions:dispensing-context",
        signer=None,
        **overrides,
    ):
        stamp = int(time.time())
        claims = dict(
            iss="pulsegrid-service:" + caller,
            aud="pulsegrid-internal:records",
            sub=caller,
            jti=uuid.uuid4().hex,
            iat=stamp,
            nbf=stamp,
            exp=stamp + 60,
            token_use="service",
            scopes=[scope],
        )
        claims.update(overrides)
        return jwt.encode(
            claims,
            keys[signer or caller],
            algorithm="RS256",
            headers={"kid": signer or caller},
        )

    app = create_app(Settings.from_env())
    state = {
        "active": True,
        "allowed": True,
        "fail": None,
        "inactive_medicine": False,
        "fail_finalize_hold": False,
        "hold": {},
        "replay": {},
        "calls": [],
        "inject_after_hold": False,
    }

    async def handler(request):
        state["calls"].append(request.url.path)
        # Check this request's transaction, not other concurrently running requests.
        session = sessions.get(request.headers.get("x-request-id"))
        if session is not None:
            assert not session.in_transaction()
        path = request.url.path
        domain = request.url.host
        service_claims = jwt.decode(
            request.headers["authorization"].split()[-1],
            keys["records"].public_key(),
            algorithms=["RS256"],
            issuer="pulsegrid-service:records",
            audience="pulsegrid-internal:" + domain,
        )
        assert (
            service_claims["sub"] == "records"
            and service_claims["token_use"] == "service"
        )
        assert service_claims["exp"] - service_claims["iat"] == 60
        expected_scope = (
            "authorization:check"
            if path.endswith("/authorization/check")
            else "patients:status"
            if "/patients/" in path
            else "users:staff-status"
            if path.endswith("/staff-status")
            else "medicines:validate"
            if path.endswith("/medicines/validate")
            else "appointments:consultation-context"
            if path.endswith("/consultation-context")
            else "appointments:clinical-hold"
        )
        assert service_claims["scopes"] == [expected_scope]
        delegated = request.headers.get("x-delegated-authorization", "").split()[-1]
        p = app.state.auth_verifier.user(delegated)
        if path.endswith("/authorization/check"):
            return httpx.Response(
                200,
                json={
                    "active": state["active"],
                    "allowed": state["allowed"],
                    "current_auth_version": 1,
                },
            )
        if state.get("response_mode") == "timeout":
            raise httpx.ReadTimeout("synthetic timeout")
        if state.get("response_mode") == "malformed":
            return httpx.Response(200, json={})
        if state.get("response_mode") == "oversized":
            return httpx.Response(200, content=b"x" * 262145)
        if state.get("response_mode") == "redirect":
            return httpx.Response(302, headers={"Location": "http://untrusted.invalid"})
        if state["fail"]:
            return httpx.Response(state["fail"], json={})
        if "/patients/" in path:
            if state.get("missing_patient"):
                return httpx.Response(404, json={})
            return httpx.Response(
                200,
                json={
                    "patient_id": path.split("/")[-2],
                    "active": not state.get("inactive_patient", False),
                    "version": 1,
                },
            )
        if "/staff-status" in path:
            if state.get("missing_staff"):
                return httpx.Response(404, json={})
            return httpx.Response(
                200,
                json={
                    "user_id": path.split("/")[-2],
                    "active": True,
                    "roles": ["patient"]
                    if state.get("non_doctor_grantee")
                    else ["doctor"],
                    "version": 1,
                },
            )
        if path.endswith("/medicines/validate"):
            data = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "items": [
                        dict(
                            id=i,
                            active=not state["inactive_medicine"],
                            catalog_version=1,
                            name="Synthetic medicine",
                        )
                        for i in data["medicine_ids"]
                    ]
                },
            )
        appointment = path.split("/")[4]
        context = dict(
            appointment_id=appointment,
            patient_id="10" if appointment != "101" else "11",
            doctor_id="30",
            doctor_user_id="20",
            journey_id=None,
            state="confirmed",
            clinical_hold=state["hold"].get(appointment, ("none", None, 1))[0],
            version=state["hold"].get(appointment, ("none", None, 1))[2],
        )
        if path.endswith("/consultation-context"):
            if p.user_id != "20" and p.patient_id != context["patient_id"]:
                return httpx.Response(404, json={})
            return httpx.Response(200, json=context)
        if state["fail_finalize_hold"] and path.endswith("/finalize"):
            return httpx.Response(503, json={})
        body = json.loads(request.content)
        key = request.headers["idempotency-key"]
        fingerprint = (request.content, request.headers.get("if-match"))
        if key in state["replay"]:
            previous, previous_fingerprint = state["replay"][key]
            assert fingerprint == previous_fingerprint
            return httpx.Response(200, json=previous)
        if context["doctor_user_id"] != p.user_id:
            return httpx.Response(404, json={})
        if request.headers["if-match"] != f'"{context["version"]}"':
            return httpx.Response(412, json={})
        if (
            context["clinical_hold"] == "active"
            and state["hold"][appointment][1] != body["consultation_id"]
        ):
            return httpx.Response(409, json={})
        context.update(
            clinical_hold="finalized" if path.endswith("/finalize") else "active",
            version=context["version"] + 1,
        )
        state["hold"][appointment] = (
            context["clinical_hold"],
            body["consultation_id"],
            context["version"],
        )
        state["replay"][key] = (dict(context), fingerprint)
        if state["inject_after_hold"]:
            state["inject_after_hold"] = False
            raise httpx.ReadTimeout("synthetic lost response")
        return httpx.Response(200, json=context)

    sessions = {}

    async def tracked_session(request: Request):
        async for session in get_database_session(request):
            sessions[str(request.state.request_id)] = session
            try:
                yield session
            finally:
                sessions.pop(str(request.state.request_id), None)

    app.dependency_overrides[get_database_session] = tracked_session
    original = httpx.AsyncClient

    def async_client(*args, **kwargs):
        return original(*args, **kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "AsyncClient", async_client)
    with TestClient(app) as client:
        yield client, app, state, token, service, admin_dsn, password
