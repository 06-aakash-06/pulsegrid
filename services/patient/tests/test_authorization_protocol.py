"""The same security protocol is enforced independently in each owner package."""

import importlib
import json
import time
from pathlib import Path
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

DOMAINS = "patient doctor appointment records pharmacy billing emergency".split()


@pytest.fixture(scope="module")
def keys(tmp_path_factory):
    directory = tmp_path_factory.mktemp("jwt-keys")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    public.update(kid="test-1", alg="RS256", use="sig")
    (directory / "users.json").write_text(json.dumps({"keys": [public]}))
    service = {**public, "service": "doctor"}
    (directory / "services.json").write_text(json.dumps({"keys": [service]}))
    return directory, key, other


def token(key, **changes):
    n = int(time.time())
    claims = dict(
        iss="pulsegrid-patient",
        aud="pulsegrid-api",
        sub="123",
        patient_id="456",
        jti=uuid4().hex,
        iat=n,
        nbf=n,
        exp=n + 600,
        roles=["patient"],
        auth_version=1,
        token_use="access",
    )
    claims.update(changes)
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-1"})


@pytest.fixture(params=DOMAINS)
def verifier(request, keys):
    directory, key, other = keys
    module = importlib.import_module(request.param + "_service.authorization")
    v = module.Verifier(
        module.AuthConfig(
            jwks_path=str(directory / "users.json"),
            service_jwks_path=str(directory / "services.json"),
        )
    )
    return module, v, key, other, request.param


@pytest.mark.parametrize(
    "changes",
    [
        {"exp": int(time.time()) - 1, "iat": int(time.time()) - 601},
        {"aud": "other"},
        {"aud": ["pulsegrid-api"]},
        {"iss": "spoofed"},
        {"token_use": "service"},
        {"roles": ["admin"]},
        {"roles": []},
        {"roles": ["patient", "patient"]},
        {"auth_version": True},
        {"sub": "0"},
        {"patient_id": "9223372036854775808"},
        {"exp": int(time.time()) + 7200},
        {"iat": True},
    ],
)
def test_invalid_claims_rejected(verifier, changes):
    _, v, key, _, _ = verifier
    with pytest.raises(HTTPException) as error:
        v.user(token(key, **changes))
    assert error.value.status_code == 401


def test_valid_signature_algorithm_and_no_private_keys(verifier):
    _, v, key, other, _ = verifier
    p = v.user(token(key))
    assert p.user_id == "123" and p.patient_id == "456" and p.roles == {"patient"}
    assert "access_token=" not in repr(p)
    with pytest.raises(HTTPException):
        v.user(token(other))
    with pytest.raises(HTTPException):
        v.user(
            jwt.encode(
                {"sub": "123"},
                "untrusted secret that is at least 32 bytes",
                algorithm="HS256",
                headers={"kid": "test-1"},
            )
        )
    with pytest.raises(HTTPException):
        v.user(jwt.encode({"sub": "123"}, key=None, algorithm="none"))
    for malformed in ("nonsense", "a" * 17000):
        with pytest.raises(HTTPException):
            v.user(malformed)
        with pytest.raises(HTTPException):
            v.service(malformed, "jwks:read")


def test_http_role_and_scope_boundaries(verifier):
    module, v, key, _, _ = verifier
    app = FastAPI()
    app.state.auth_verifier = v

    @app.get("/protected")
    async def protected(p=Depends(module.authenticated_user)):
        return {"id": p.user_id}

    @app.get("/privileged")
    async def privileged(p=Depends(module.require_roles("hospital_admin"))):
        return {"id": p.user_id}

    with TestClient(app) as c:
        assert c.get("/protected").status_code == 401
        assert (
            c.get(
                "/protected", headers={"X-User-ID": "123", "X-Role": "hospital_admin"}
            ).status_code
            == 401
        )
        h = {"Authorization": "Bearer " + token(key)}
        assert c.get("/protected", headers=h).status_code == 200
        assert c.get("/privileged", headers=h).status_code == 403
    p = v.user(token(key))
    module.check_resource_scope(p, patient_id="456")
    module.check_resource_scope(p, owner_user_id="123")
    module.check_resource_scope(p, assignment_verified=True)
    with pytest.raises(HTTPException):
        module.check_resource_scope(p, patient_id="789", grant_verified="true")


def test_service_identity_is_bound_to_key_and_receiver(verifier):
    _, v, key, _, domain = verifier
    n = int(time.time())
    claims = dict(
        iss="pulsegrid-service:doctor",
        aud="pulsegrid-internal:" + domain,
        sub="doctor",
        jti=uuid4().hex,
        iat=n,
        nbf=n,
        exp=n + 60,
        token_use="service",
        scopes=["authorization:check"],
    )

    def signed(**changes):
        return jwt.encode(
            {**claims, **changes}, key, algorithm="RS256", headers={"kid": "test-1"}
        )

    assert v.service(signed(), "authorization:check") == "doctor"
    for changes in (
        {"sub": "billing", "iss": "pulsegrid-service:billing"},
        {"aud": "pulsegrid-api"},
        {"sub": ["doctor"]},
    ):
        with pytest.raises(HTTPException):
            v.service(signed(**changes), "authorization:check")
    with pytest.raises(HTTPException) as denied:
        v.service(signed(), "jwks:read")
    assert denied.value.status_code == 403
    with pytest.raises(HTTPException):
        v.user(signed())


@pytest.mark.parametrize("domain", DOMAINS)
def test_configuration_requires_explicit_secure_origins(monkeypatch, domain):
    m = importlib.import_module(domain + "_service.authorization")
    prefix = "PULSEGRID_" + domain.upper() + "_AUTH_"
    monkeypatch.setenv(prefix + "ORIGINS", "http://localhost:5173")
    with pytest.raises(ValueError):
        m.AuthConfig.from_env("development")
    monkeypatch.setenv(prefix + "ALLOW_HTTP", "true")
    assert m.AuthConfig.from_env("development").allow_http
    with pytest.raises(ValueError):
        m.AuthConfig.from_env("production")
    for origin in ("*", "https://example.test/path", "http://remote.example", "null"):
        monkeypatch.setenv(prefix + "ORIGINS", origin)
        with pytest.raises(ValueError):
            m.AuthConfig.from_env("development")


def test_private_jwks_rejected(keys):
    directory, key, _ = keys
    from patient_service.authorization import read_keys

    private = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key))
    private.update(kid="private", alg="RS256", use="sig")
    path = directory / "invalid.json"
    path.write_text(json.dumps({"keys": [private]}))
    with pytest.raises(ValueError):
        read_keys(path)


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("allowed", 200),
        ("stale", 403),
        ("outage", 503),
        ("invalid", 503),
        ("timeout", 503),
    ],
)
def test_current_authority_fails_closed(verifier, monkeypatch, mode, expected):
    from types import SimpleNamespace
    import httpx

    module, v, key, _, _ = verifier
    monkeypatch.setattr(module, "service_token", lambda *a, **k: "service-credential")

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["timeout"] == 2 and kwargs["trust_env"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, *, json, headers):
            assert headers["X-Delegated-Authorization"].startswith("Bearer ")
            assert headers["traceparent"] == "reviewed-trace"
            assert json["subject_user_id"] == "123"
            if mode == "timeout":
                raise httpx.ConnectTimeout("controlled failure")
            if mode == "outage":
                return httpx.Response(503, json={})
            if mode == "invalid":
                return httpx.Response(200, json=[])
            return httpx.Response(
                200,
                json={
                    "active": True,
                    "allowed": mode == "allowed",
                    "current_auth_version": 1 if mode == "allowed" else 2,
                },
            )

    monkeypatch.setattr(module.httpx, "AsyncClient", Client)
    app = FastAPI()
    app.state.auth_verifier = v
    app.state.auth_config = v.config

    @app.middleware("http")
    async def context(request, call_next):
        request.state.request_id = uuid4()
        request.state.correlation_id = uuid4()
        request.state.traceparent = "reviewed-trace"
        return await call_next(request)

    @app.post("/current")
    async def protected(p=Depends(module.require_current_role("patient"))):
        return {"id": p.user_id}

    with TestClient(app) as c:
        assert (
            c.post(
                "/current", headers={"Authorization": "Bearer " + token(key)}
            ).status_code
            == expected
        )


def test_password_work_admission_is_bounded():
    import asyncio
    from types import SimpleNamespace
    from patient_service.authentication import Identity

    async def run():
        identity = SimpleNamespace(hash_slots=asyncio.Semaphore(0))
        with pytest.raises(HTTPException) as failure:
            await Identity.password_work(identity, lambda: None)
        assert (
            failure.value.status_code == 429
            and failure.value.headers["Retry-After"] == "1"
        )

    asyncio.run(run())


def test_signing_key_overlap_and_unknown_kid(keys):
    directory, key, other = keys
    from patient_service.authorization import AuthConfig, Verifier

    old = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    new = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(other.public_key()))
    old.update(kid="test-1", alg="RS256", use="sig")
    new.update(kid="next-1", alg="RS256", use="sig")
    path = directory / "overlap.json"
    path.write_text(json.dumps({"keys": [old, new]}))
    verifier = Verifier(AuthConfig(jwks_path=str(path)))
    original = token(key)
    assert verifier.user(original).user_id == "123"
    claims = jwt.decode(original, options={"verify_signature": False})
    assert (
        verifier.user(
            jwt.encode(claims, other, algorithm="RS256", headers={"kid": "next-1"})
        ).user_id
        == "123"
    )
    with pytest.raises(HTTPException):
        verifier.user(
            jwt.encode(claims, key, algorithm="RS256", headers={"kid": "unknown"})
        )


def test_jwks_serializes_only_validated_public_snapshot(keys):
    import asyncio
    from types import SimpleNamespace
    from starlette.requests import Request
    from patient_service.authentication import jwks

    _, key, _ = keys
    verifier = SimpleNamespace(
        user_keys={"test-1": key.public_key()}, service=lambda *args: None
    )
    app = SimpleNamespace(state=SimpleNamespace(auth_verifier=verifier))
    request = Request(
        {
            "type": "http",
            "app": app,
            "headers": [(b"authorization", b"Bearer service-token")],
        }
    )
    result = asyncio.run(jwks(request))
    assert result["keys"][0]["kid"] == "test-1"
    assert set(result["keys"][0]) == {
        "kty",
        "n",
        "e",
        "kid",
        "alg",
        "use",
        "key_ops",
    } or set(result["keys"][0]) == {"kty", "n", "e", "kid", "alg", "use"}
