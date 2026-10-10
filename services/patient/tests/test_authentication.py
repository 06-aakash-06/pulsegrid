"""Real PostgreSQL identity transactions; opt in only on an isolated auth stack."""

import asyncio
import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from uuid import uuid4
import httpx
import jwt
import pytest
from sqlalchemy import create_engine, text
from patient_service.main import create_app
from patient_service.settings import Settings

ROOT = Path(__file__).resolve().parents[3]
ORIGIN = "http://127.0.0.1:8081"
PASSWORD = "Synthetic test passphrase 2026!"
pytestmark = pytest.mark.skipif(
    os.environ.get("PULSEGRID_AUTH_INTEGRATION") != "1",
    reason="Requires isolated PostgreSQL auth stack; see AUTHENTICATION.md",
)


def run(function):
    asyncio.run(function())


@pytest.fixture
def setup(monkeypatch):
    values = dict(
        line.split("=", 1)
        for line in (ROOT / ".env").read_text().splitlines()
        if line and not line.startswith("#") and "=" in line
    )
    keys = ROOT / "secrets/auth"
    for field, value in {
        "JWKS_PATH": str(keys / "user-jwks.json"),
        "SERVICE_JWKS_PATH": str(keys / "service-jwks.json"),
        "PRIVATE_KEY_PATH": str(keys / "patient-signing.pem"),
        "IDEMPOTENCY_SECRET_PATH": str(keys / "idempotency.key"),
        "ORIGINS": ORIGIN,
        "ALLOW_HTTP": "true",
    }.items():
        monkeypatch.setenv("PULSEGRID_PATIENT_AUTH_" + field, value)
    settings = Settings(
        db_host="127.0.0.1",
        db_port=55433,
        db_name="patient_db",
        db_user="patient_app",
        db_password=values["PATIENT_DB_PASSWORD"],
    )
    app = create_app(settings)
    engine = create_engine(
        settings.database_url,
        connect_args=settings.connection_options,
        hide_parameters=True,
    )
    yield app, engine, keys
    engine.dispose()


async def client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url=ORIGIN,
        headers={"Origin": ORIGIN},
    )


async def csrf(c):
    result = await c.get("/api/v1/auth/csrf")
    assert result.status_code == 200
    return {"X-CSRF-Token": result.json()["csrf_token"]}


def registration(email=None):
    return {
        "email": email or ("synthetic-" + uuid4().hex + "@example.test"),
        "password": PASSWORD,
        "display_name": "Synthetic Patient",
    }


def registration_headers():
    return {
        "Idempotency-Key": str(uuid4()),
        "X-Anonymous-Command-ID": secrets.token_urlsafe(32),
    }


async def registered(c):
    body = registration()
    result = await c.post(
        "/api/v1/auth/register", json=body, headers=registration_headers()
    )
    assert result.status_code == 201
    return body, result.json()


async def logged(c, body):
    headers = await csrf(c)
    result = await c.post(
        "/api/v1/auth/login",
        json={"email": body["email"], "password": PASSWORD},
        headers=headers,
    )
    assert result.status_code == 200
    return headers, result.json()["access_token"]


def test_registration_and_atomic_duplicate_idempotency(setup):
    app, engine, _ = setup

    async def exercise():
        async with app.router.lifespan_context(app), await client(app) as c:
            body = registration()
            headers = registration_headers()
            results = await asyncio.gather(
                *(
                    c.post("/api/v1/auth/register", json=body, headers=headers)
                    for _ in range(2)
                )
            )
            assert [r.status_code for r in results] == [201, 201]
            assert results[0].json() == results[1].json()
            profile = results[0].json()
            changed = {**body, "display_name": "Another name"}
            assert (
                await c.post("/api/v1/auth/register", json=changed, headers=headers)
            ).status_code == 409
            assert (
                await c.post(
                    "/api/v1/auth/register", json=body, headers=registration_headers()
                )
            ).status_code == 409
            assert (
                await c.post(
                    "/api/v1/auth/register",
                    json={**registration(), "roles": ["hospital_admin"]},
                    headers=registration_headers(),
                )
            ).status_code == 422
            assert (
                await c.post(
                    "/api/v1/auth/register",
                    json={**registration(), "password": "weak"},
                    headers=registration_headers(),
                )
            ).status_code == 422
            with engine.connect() as db:
                user = (
                    db.execute(
                        text("SELECT * FROM users WHERE id=:id"),
                        {"id": int(profile["user_id"])},
                    )
                    .mappings()
                    .one()
                )
                assert (
                    user["password_hash"].startswith("$argon2id$")
                    and PASSWORD not in user["password_hash"]
                )
                assert app.state.identity.passwords.verify(
                    user["password_hash"], PASSWORD
                )
                assert db.scalars(
                    text("SELECT role FROM role_assignments WHERE user_id=:id"),
                    {"id": user["id"]},
                ).all() == ["patient"]
                assert (
                    db.scalar(
                        text(
                            "SELECT count(*) FROM outbox_events WHERE aggregate_id=:id"
                        ),
                        {"id": int(profile["id"])},
                    )
                    == 1
                )
                assert (
                    db.scalar(
                        text("SELECT count(*) FROM patient_profiles WHERE user_id=:id"),
                        {"id": user["id"]},
                    )
                    == 1
                )

    run(exercise)


def test_concurrent_distinct_duplicate_registration(setup):
    app, engine, _ = setup

    async def exercise():
        async with app.router.lifespan_context(app), await client(app) as c:
            body = registration()
            results = await asyncio.gather(
                *(
                    c.post(
                        "/api/v1/auth/register",
                        json=body,
                        headers=registration_headers(),
                    )
                    for _ in range(2)
                )
            )
            assert sorted(r.status_code for r in results) == [201, 409]
            with engine.connect() as db:
                assert (
                    db.scalar(
                        text(
                            "SELECT count(*) FROM users WHERE email_normalized=:email"
                        ),
                        {"email": body["email"]},
                    )
                    == 1
                )

    run(exercise)


def test_login_current_identity_and_invalid_credentials(setup):
    app, _, _ = setup

    async def exercise():
        async with app.router.lifespan_context(app), await client(app) as c:
            body, profile = await registered(c)
            headers, token = await logged(c, body)
            response = await c.get(
                "/api/v1/patients/me", headers={"Authorization": "Bearer " + token}
            )
            assert (
                response.status_code == 200 and response.json()["id"] == profile["id"]
            )
            assert response.headers["etag"] == '"1"'
            assert (
                await c.get(
                    "/api/v1/patients/me",
                    headers={"X-User-ID": profile["user_id"], "X-Role": "patient"},
                )
            ).status_code == 401
            wrong = await c.post(
                "/api/v1/auth/login",
                json={"email": body["email"], "password": "Wrong synthetic password"},
                headers=headers,
            )
            absent = await c.post(
                "/api/v1/auth/login",
                json={
                    "email": "absent-" + uuid4().hex + "@example.test",
                    "password": "Wrong synthetic password",
                },
                headers=headers,
            )
            assert wrong.status_code == absent.status_code == 401
            assert wrong.json()["error"]["message"] == absent.json()["error"]["message"]
            cookie = c.cookies.get("pulsegrid_refresh")
            assert cookie and cookie not in response.text

    run(exercise)


def test_refresh_rotation_reuse_family_revocation_logout(setup):
    app, engine, _ = setup

    async def exercise():
        async with app.router.lifespan_context(app), await client(app) as c:
            body, profile = await registered(c)
            headers, token = await logged(c, body)
            old = c.cookies.get("pulsegrid_refresh")
            assert (
                await c.post("/api/v1/auth/refresh", headers=headers)
            ).status_code == 200
            rotated = c.cookies.get("pulsegrid_refresh")
            assert rotated != old
            raw_cookies = {
                "pulsegrid_refresh": old,
                "pulsegrid_csrf": c.cookies.get("pulsegrid_csrf"),
            }
            async with await client(app) as replay:
                replay.cookies.update(raw_cookies)
                assert (
                    await replay.post("/api/v1/auth/refresh", headers=headers)
                ).status_code == 401
            assert (
                await c.post("/api/v1/auth/refresh", headers=headers)
            ).status_code == 401
            assert (
                await c.get(
                    "/api/v1/patients/me", headers={"Authorization": "Bearer " + token}
                )
            ).status_code == 401
            headers, new_token = await logged(c, body)
            refresh = c.cookies.get("pulsegrid_refresh")
            assert (
                await c.post("/api/v1/auth/logout", headers=headers)
            ).status_code == 204
            assert c.cookies.get("pulsegrid_refresh") is None
            c.cookies.set(
                "pulsegrid_refresh", refresh, domain="127.0.0.1", path="/api/v1/auth"
            )
            assert (
                await c.post("/api/v1/auth/refresh", headers=headers)
            ).status_code == 401
            assert (
                await c.get(
                    "/api/v1/patients/me",
                    headers={"Authorization": "Bearer " + new_token},
                )
            ).status_code == 401
            with engine.connect() as db:
                records = db.execute(
                    text(
                        "SELECT token_hash,revoked_at FROM refresh_sessions WHERE user_id=:id"
                    ),
                    {"id": int(profile["user_id"])},
                ).all()
                assert all(r.revoked_at is not None for r in records)
                assert all(r.token_hash not in (old, rotated, refresh) for r in records)
                assert hashlib.sha256(old.encode()).hexdigest() in [
                    r.token_hash for r in records
                ]

    run(exercise)


def test_concurrent_refresh_strict_replay_policy(setup):
    app, engine, _ = setup

    async def exercise():
        async with app.router.lifespan_context(app), await client(app) as c:
            body, profile = await registered(c)
            headers, _ = await logged(c, body)
            cookie = c.cookies.get("pulsegrid_refresh")
            csrf_cookie = c.cookies.get("pulsegrid_csrf")

            async def attempt():
                async with await client(app) as contender:
                    contender.cookies.update(
                        {"pulsegrid_refresh": cookie, "pulsegrid_csrf": csrf_cookie}
                    )
                    return await contender.post("/api/v1/auth/refresh", headers=headers)

            results = await asyncio.gather(attempt(), attempt())
            assert sorted(r.status_code for r in results) == [200, 401]
            with engine.connect() as db:
                assert (
                    db.scalar(
                        text(
                            "SELECT count(*) FROM refresh_sessions WHERE user_id=:id AND revoked_at IS NULL"
                        ),
                        {"id": int(profile["user_id"])},
                    )
                    == 0
                )

    run(exercise)


def test_expiry_disabled_account_csrf_origin_cors(setup):
    app, engine, _ = setup

    async def exercise():
        async with app.router.lifespan_context(app), await client(app) as c:
            body, profile = await registered(c)
            headers, token = await logged(c, body)
            assert (await c.post("/api/v1/auth/refresh")).status_code == 403
            assert (
                await c.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": "forged"})
            ).status_code == 403
            assert (
                await c.post(
                    "/api/v1/auth/refresh",
                    headers={**headers, "Origin": "https://attacker.example"},
                )
            ).status_code == 403
            assert (
                await c.post(
                    "/api/v1/auth/refresh", headers={**headers, "Origin": "null"}
                )
            ).status_code == 403
            assert (
                await c.get(
                    "/api/v1/auth/csrf", headers={"Origin": "https://attacker.example"}
                )
            ).status_code == 403
            allowed = await c.options(
                "/api/v1/auth/login",
                headers={
                    "Origin": ORIGIN,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type,x-csrf-token",
                },
            )
            assert (
                allowed.status_code == 200
                and allowed.headers["access-control-allow-origin"] == ORIGIN
            )
            denied = await c.options(
                "/api/v1/auth/login",
                headers={
                    "Origin": "https://attacker.example",
                    "Access-Control-Request-Method": "POST",
                },
            )
            assert (
                denied.status_code == 400
                and "access-control-allow-origin" not in denied.headers
            )
            with engine.begin() as db:
                db.execute(
                    text(
                        "UPDATE refresh_sessions SET expires_at=now()-interval '1 second' WHERE user_id=:id"
                    ),
                    {"id": int(profile["user_id"])},
                )
            assert (
                await c.post("/api/v1/auth/refresh", headers=headers)
            ).status_code == 401
            headers, token = await logged(c, body)
            with engine.begin() as db:
                db.execute(
                    text(
                        "UPDATE users SET account_state='disabled',auth_version=auth_version+1 WHERE id=:id"
                    ),
                    {"id": int(profile["user_id"])},
                )
            assert (
                await c.get(
                    "/api/v1/patients/me", headers={"Authorization": "Bearer " + token}
                )
            ).status_code == 401
            assert (
                await c.post("/api/v1/auth/refresh", headers=headers)
            ).status_code == 401
            assert (
                await c.post(
                    "/api/v1/auth/login",
                    json={"email": body["email"], "password": PASSWORD},
                    headers=headers,
                )
            ).status_code == 401

    run(exercise)


def test_internal_service_boundary_and_audit_permissions(setup):
    app, engine, keys = setup

    async def exercise():
        async with app.router.lifespan_context(app), await client(app) as c:
            body, profile = await registered(c)
            headers, token = await logged(c, body)
            assert (
                await c.get(
                    "/internal/v1/auth/jwks",
                    headers={"Authorization": "Bearer " + token},
                )
            ).status_code == 401

            def service(scope, audience="pulsegrid-internal:patient", subject="doctor"):
                n = int(time.time())
                return jwt.encode(
                    {
                        "iss": "pulsegrid-service:" + subject,
                        "aud": audience,
                        "sub": subject,
                        "jti": uuid4().hex,
                        "iat": n,
                        "nbf": n,
                        "exp": n + 60,
                        "token_use": "service",
                        "scopes": [scope],
                    },
                    (keys / "doctor-service.pem").read_bytes(),
                    algorithm="RS256",
                    headers={"kid": "doctor-service-1"},
                )

            public = await c.get(
                "/internal/v1/auth/jwks",
                headers={"Authorization": "Bearer " + service("jwks:read")},
            )
            assert public.status_code == 200 and all(
                "d" not in key for key in public.json()["keys"]
            )
            assert (
                await c.get(
                    "/internal/v1/auth/jwks",
                    headers={
                        "Authorization": "Bearer "
                        + service("jwks:read", subject="billing")
                    },
                )
            ).status_code == 401
            assert (
                await c.get(
                    "/internal/v1/auth/jwks",
                    headers={
                        "Authorization": "Bearer "
                        + service("jwks:read", audience="pulsegrid-api")
                    },
                )
            ).status_code == 401
            payload = {
                "subject_user_id": profile["user_id"],
                "required_role": "patient",
                "auth_version": 1,
            }
            checks = {
                "Authorization": "Bearer " + service("authorization:check"),
                "X-Delegated-Authorization": "Bearer " + token,
            }
            current = await c.post(
                "/internal/v1/authorization/check", json=payload, headers=checks
            )
            assert current.status_code == 200 and current.json()["allowed"] is True
            assert (
                await c.post(
                    "/internal/v1/authorization/check",
                    json={**payload, "subject_user_id": "1"},
                    headers=checks,
                )
            ).status_code == 403
            with engine.begin() as db:
                db.execute(
                    text("UPDATE users SET auth_version=auth_version+1 WHERE id=:id"),
                    {"id": int(profile["user_id"])},
                )
            current = await c.post(
                "/internal/v1/authorization/check", json=payload, headers=checks
            )
            assert current.status_code == 200 and current.json()["allowed"] is False

    run(exercise)
    with engine.connect() as db:
        assert not db.scalar(
            text("SELECT has_table_privilege(current_user,'audit_entries','UPDATE')")
        )
        rows = db.execute(
            text(
                "SELECT prev_hash,entry_hash,canonical_metadata::text FROM audit_entries WHERE chain_id='auth' ORDER BY sequence"
            )
        ).all()
        previous = "0" * 64
        for row in rows:
            assert row.prev_hash == previous
            assert (
                hashlib.sha256((previous + row[2]).encode()).hexdigest()
                == row.entry_hash
            )
            assert PASSWORD not in row[2]
            previous = row.entry_hash


def test_normalization_id_collision_and_atomic_rollback(setup, monkeypatch):
    from patient_service import authentication as auth
    from sqlalchemy.exc import SQLAlchemyError

    app, engine, _ = setup

    async def exercise():
        async with app.router.lifespan_context(app), await client(app) as c:
            body, profile = await registered(c)
            duplicate = {**body, "email": "  " + body["email"].upper() + "  "}
            assert (
                await c.post(
                    "/api/v1/auth/register",
                    json=duplicate,
                    headers=registration_headers(),
                )
            ).status_code == 409
            original = auth.new_id
            ids = iter([int(profile["user_id"]), original()])
            monkeypatch.setattr(auth, "new_id", lambda: next(ids, None) or original())
            result = await c.post(
                "/api/v1/auth/register",
                json=registration(),
                headers=registration_headers(),
            )
            assert result.status_code == 201
            monkeypatch.setattr(auth, "new_id", original)

            async def failed_audit(*args, **kwargs):
                raise SQLAlchemyError("controlled audit failure")

            monkeypatch.setattr(auth, "audit", failed_audit)
            body = registration()
            assert (
                await c.post(
                    "/api/v1/auth/register", json=body, headers=registration_headers()
                )
            ).status_code == 503
            with engine.connect() as db:
                assert (
                    db.scalar(
                        text(
                            "SELECT count(*) FROM users WHERE email_normalized=:email"
                        ),
                        {"email": body["email"]},
                    )
                    == 0
                )

    run(exercise)


def test_absolute_expiry_and_account_invalidation_outbox(setup):
    app, engine, _ = setup

    async def exercise():
        async with app.router.lifespan_context(app), await client(app) as c:
            body, profile = await registered(c)
            headers, _ = await logged(c, body)
            with engine.begin() as db:
                db.execute(
                    text(
                        "UPDATE refresh_sessions SET family_expires_at=now()-interval '1 second',expires_at=now()-interval '1 second' WHERE user_id=:id"
                    ),
                    {"id": int(profile["user_id"])},
                )
            assert (
                await c.post("/api/v1/auth/refresh", headers=headers)
            ).status_code == 401
            with engine.connect() as db:
                result = db.execute(
                    text(
                        "SELECT envelope FROM outbox_events WHERE aggregate_id=:id AND event_type='patient.account.changed.v1'"
                    ),
                    {"id": int(profile["user_id"])},
                ).scalar_one()
                assert (
                    result["payload"]["auth_version"] == 2
                    and result["payload"]["active"] is True
                )

    run(exercise)


def test_production_cookie_and_transport_contract(setup, monkeypatch):
    from dataclasses import replace

    original, _, _ = setup
    origin = "https://app.example.test"
    monkeypatch.setenv("PULSEGRID_PATIENT_AUTH_ORIGINS", origin)
    monkeypatch.setenv("PULSEGRID_PATIENT_AUTH_ALLOW_HTTP", "false")
    app = create_app(replace(original.state.settings, environment="production"))

    async def exercise():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=origin,
                headers={"Origin": origin},
            ) as c:
                result = await c.get("/api/v1/auth/csrf")
                assert result.status_code == 200
                cookie = result.headers["set-cookie"]
                assert (
                    "Secure" in cookie
                    and "HttpOnly" in cookie
                    and "SameSite=lax" in cookie
                    and "Path=/api/v1/auth" in cookie
                    and "Domain=" not in cookie
                )
                body, _ = await registered(c)
                headers, token = await logged(c, body)
                assert c.cookies.get("pulsegrid_refresh")
                result = await c.post("/api/v1/auth/refresh", headers=headers)
                assert (
                    result.status_code == 200
                    and "Secure" in result.headers["set-cookie"]
                )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://app.example.test",
                headers={"Origin": origin},
            ) as c:
                assert (await c.get("/api/v1/auth/csrf")).status_code == 403
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=origin,
                headers={"Referer": origin + "/login"},
            ) as c:
                assert (await c.get("/api/v1/auth/csrf")).status_code == 200
                assert (
                    await c.post("/api/v1/auth/logout", headers=await csrf(c))
                ).status_code == 403

    run(exercise)
