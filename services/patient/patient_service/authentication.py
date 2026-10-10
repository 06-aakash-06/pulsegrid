"""Patient-owned credentials, session transactions and signed browser tokens."""

from __future__ import annotations
import asyncio
import hashlib
import hmac
import json
import secrets
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
import anyio
import jwt
from argon2 import PasswordHasher, Type
from argon2.exceptions import VerificationError, InvalidHashError
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from email_validator import validate_email, EmailNotValidError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from sqlalchemy import select, insert, update, text
from sqlalchemy.exc import IntegrityError
from .authorization import (
    AUDIENCE,
    ISSUER,
    Principal,
    authenticated_user,
    bearer,
    require_roles,
    valid_id,
)
from .database import get_database_session
from .models import (
    users,
    patient_profiles,
    role_assignments,
    refresh_sessions,
    outbox_events,
    idempotency_requests,
)

router = APIRouter(tags=["identity"])
REFRESH_COOKIE = "pulsegrid_refresh"
CSRF_COOKIE = "pulsegrid_csrf"
COOKIE_PATH = "/api/v1/auth"


def new_id():
    """Temporary CSPRNG BIGINT; PKs enforce uniqueness and callers retry collisions."""
    return secrets.randbelow(2**63 - 1) + 1


def now():
    return datetime.now(timezone.utc)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=320)
    password: SecretStr = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        try:
            # Prototype identity is deliberately caseless ASCII, with IDNA domains.
            return validate_email(
                value.strip(),
                check_deliverability=False,
                allow_smtputf8=False,
                test_environment=True,
            ).normalized.lower()
        except EmailNotValidError:
            raise ValueError("Invalid email") from None


class RegistrationInput(LoginInput):
    display_name: str = Field(min_length=1, max_length=200)
    date_of_birth: date | None = None
    synthetic_contact: str | None = Field(default=None, max_length=256)

    @field_validator("display_name")
    @classmethod
    def name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Display name required")
        return value

    @field_validator("password")
    @classmethod
    def strong_password(cls, value):
        p = value.get_secret_value()
        if len(p) < 12 or p.casefold() in (
            "passwordpassword",
            "pulsegrid12345",
            "123456789012",
        ):
            raise ValueError("Use a passphrase of at least 12 characters")
        return value

    @field_validator("date_of_birth")
    @classmethod
    def valid_birth(cls, value):
        if value and value > now().date():
            raise ValueError("Date must not be in the future")
        return value


class AuthorityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject_user_id: str
    required_role: str
    auth_version: int = Field(strict=True, ge=1)

    @field_validator("subject_user_id")
    @classmethod
    def identifier(cls, value):
        if not valid_id(value):
            raise ValueError("Invalid ID")
        return value

    @field_validator("required_role")
    @classmethod
    def role(cls, value):
        from .authorization import ROLES

        if value not in ROLES:
            raise ValueError("Unknown role")
        return value


class Identity:
    def __init__(self, config, verifier):
        self.config = config
        self.verifier = verifier
        self.key = load_pem_private_key(
            Path(config.private_key_path).read_bytes(), password=None
        )
        if (
            not isinstance(self.key, RSAPrivateKey)
            or self.key.key_size < 2048
            or config.kid not in verifier.user_keys
            or self.key.public_key().public_numbers()
            != verifier.user_keys[config.kid].public_numbers()
        ):
            raise ValueError("Signing key does not match configured public key")
        self.idempotency_secret = Path(config.idempotency_secret_path).read_bytes()
        if len(self.idempotency_secret) < 32:
            raise ValueError("Idempotency secret must be at least 256 bits")
        self.passwords = PasswordHasher(
            type=Type.ID,
            time_cost=config.argon_time_cost,
            memory_cost=config.argon_memory_kib,
            parallelism=2,
        )
        self.dummy = self.passwords.hash(secrets.token_urlsafe(32))
        self.hash_slots = asyncio.Semaphore(2)

    async def password_work(self, function, *args):
        try:
            await asyncio.wait_for(self.hash_slots.acquire(), timeout=0.25)
        except TimeoutError:
            raise HTTPException(429, headers={"Retry-After": "1"}) from None
        try:
            return await anyio.to_thread.run_sync(function, *args)
        finally:
            self.hash_slots.release()

    async def hash(self, password):
        return await self.password_work(self.passwords.hash, password)

    async def verify(self, hash_value, password):
        def check():
            try:
                return self.passwords.verify(hash_value, password)
            except (VerificationError, InvalidHashError):
                return False

        return await self.password_work(check)

    def signed(self, subject, purpose, audience, lifetime, **claims):
        current = int(time.time())
        return jwt.encode(
            {
                "iss": ISSUER,
                "aud": audience,
                "sub": str(subject),
                "jti": secrets.token_urlsafe(32),
                "iat": current,
                "nbf": current,
                "exp": current + lifetime,
                "token_use": purpose,
                **claims,
            },
            self.key,
            algorithm="RS256",
            headers={"kid": self.config.kid},
        )

    def access(self, user, profile, roles):
        return {
            "access_token": self.signed(
                user["id"],
                "access",
                AUDIENCE,
                self.config.access_seconds,
                roles=roles,
                auth_version=user["auth_version"],
                patient_id=str(profile["id"]),
            ),
            "token_type": "Bearer",
            "expires_in": self.config.access_seconds,
        }


async def identity(request: Request):
    auth = request.app.state.identity
    if auth is None:
        raise HTTPException(503)
    return auth


def origin(request):
    value = request.headers.get("origin")
    if value is None and request.method == "GET":
        referer = request.headers.get("referer", "")
        try:
            u = urlsplit(referer)
            value = u.scheme + "://" + u.netloc if u.scheme and u.netloc else None
        except ValueError:
            raise HTTPException(403) from None
    if value not in request.app.state.auth_config.origins:
        raise HTTPException(403)
    if not request.app.state.auth_config.allow_http and request.url.scheme != "https":
        raise HTTPException(403)
    return value


async def csrf(request: Request, auth=Depends(identity)):
    source = origin(request)
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get("X-CSRF-Token", "")
    if (
        not cookie
        or not header
        or len(cookie) > 16384
        or len(header) > 16384
        or not cookie.isascii()
        or not header.isascii()
        or not hmac.compare_digest(cookie, header)
    ):
        raise HTTPException(403)
    try:
        claims = auth.verifier.decode(
            header, auth.verifier.user_keys, ISSUER, "pulsegrid-csrf", "csrf", 3600
        )
        if claims.get("origin") != source:
            raise HTTPException(403)
    except HTTPException:
        raise HTTPException(403) from None
    return auth


def set_cookie(response, name, value, auth, max_age):
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        httponly=True,
        secure=not auth.config.allow_http,
        samesite="lax",
        path=COOKIE_PATH,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


async def audit(session, request, action, user_id=None, result="success"):
    metadata = {
        "action": action,
        "result": result,
        "request_id": str(request.state.request_id),
        "correlation_id": str(request.state.correlation_id),
        "occurred_at": now().isoformat(),
    }
    if user_id is not None:
        metadata["actor_user_id"] = str(user_id)
    await session.execute(
        text("SELECT auth_append_audit(:entry_id, CAST(:metadata AS jsonb))"),
        {
            "entry_id": new_id(),
            "metadata": json.dumps(metadata, sort_keys=True, separators=(",", ":")),
        },
    )


async def account(session, user_id, lock=False):
    query = select(users).where(users.c.id == user_id)
    if lock:
        query = query.with_for_update()
    user = (await session.execute(query)).mappings().first()
    if user is None:
        return None, None, []
    profile = (
        (
            await session.execute(
                select(patient_profiles).where(patient_profiles.c.user_id == user_id)
            )
        )
        .mappings()
        .first()
    )
    roles = list(
        (
            await session.execute(
                select(role_assignments.c.role)
                .where(role_assignments.c.user_id == user_id)
                .order_by(role_assignments.c.role)
            )
        ).scalars()
    )
    return user, profile, roles


async def create_session(session, user_id, auth, family_id=None, absolute=None):
    raw = secrets.token_urlsafe(32)
    current = now()
    absolute = absolute or current + timedelta(
        seconds=auth.config.refresh_absolute_seconds
    )
    expiry = min(
        absolute, current + timedelta(seconds=auth.config.refresh_idle_seconds)
    )
    session_id = new_id()
    await session.execute(
        insert(refresh_sessions).values(
            id=session_id,
            user_id=user_id,
            family_id=family_id or new_id(),
            token_hash=digest(raw),
            expires_at=expiry,
            family_expires_at=absolute,
        )
    )
    return session_id, raw, max(0, int((expiry - current).total_seconds()))


@router.get("/api/v1/auth/csrf")
async def csrf_token(request: Request, response: Response, auth=Depends(identity)):
    source = origin(request)
    token = auth.signed("csrf", "csrf", "pulsegrid-csrf", 3600, origin=source)
    set_cookie(response, CSRF_COOKIE, token, auth, 3600)
    return {"csrf_token": token, "header_name": "X-CSRF-Token", "expires_in": 3600}


@router.post("/api/v1/auth/register", status_code=201)
async def register(
    payload: RegistrationInput,
    request: Request,
    response: Response,
    auth=Depends(identity),
    session=Depends(get_database_session),
):
    origin(request)
    response.headers["Cache-Control"] = "no-store"
    key = request.headers.get("Idempotency-Key", "")
    nonce = request.headers.get("X-Anonymous-Command-ID", "")
    if not 16 <= len(key) <= 128 or not __import__("re").fullmatch(
        r"[A-Za-z0-9_-]{43,128}", nonce
    ):
        raise HTTPException(400)
    scope = "anonymous:" + digest(nonce)
    request_data = {
        **payload.model_dump(mode="json"),
        "password": payload.password.get_secret_value(),
    }
    fingerprint = hmac.new(
        auth.idempotency_secret,
        json.dumps(request_data, sort_keys=True).encode(),
        hashlib.sha256,
    ).hexdigest()
    password_hash = await auth.hash(payload.password.get_secret_value())
    for attempt in range(3):
        try:
            async with session.begin():
                lock = int.from_bytes(
                    hashlib.sha256((scope + key).encode()).digest()[:8],
                    "big",
                    signed=True,
                )
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock}
                )
                old = (
                    (
                        await session.execute(
                            select(idempotency_requests).where(
                                idempotency_requests.c.principal_scope == scope,
                                idempotency_requests.c.method == "POST",
                                idempotency_requests.c.route_template
                                == "/api/v1/auth/register",
                                idempotency_requests.c.key == key,
                            )
                        )
                    )
                    .mappings()
                    .first()
                )
                if old:
                    if not hmac.compare_digest(old["request_hash"], fingerprint):
                        raise HTTPException(409)
                    return old["response"]
                user_id, profile_id = new_id(), new_id()
                await session.execute(
                    insert(users).values(
                        id=user_id,
                        email_normalized=payload.email,
                        password_hash=password_hash,
                        account_state="active",
                    )
                )
                await session.execute(
                    insert(patient_profiles).values(
                        id=profile_id,
                        user_id=user_id,
                        display_name=payload.display_name,
                        date_of_birth=payload.date_of_birth,
                        synthetic_contact=payload.synthetic_contact,
                    )
                )
                await session.execute(
                    insert(role_assignments).values(
                        id=new_id(), user_id=user_id, role="patient"
                    )
                )
                result = {
                    "id": str(profile_id),
                    "user_id": str(user_id),
                    "display_name": payload.display_name,
                    "version": 1,
                }
                if payload.date_of_birth:
                    result["date_of_birth"] = payload.date_of_birth.isoformat()
                if payload.synthetic_contact is not None:
                    result["synthetic_contact"] = payload.synthetic_contact
                event_id = new_id()
                envelope = {
                    "event_id": str(event_id),
                    "event_type": "patient.registered.v1",
                    "schema_version": 1,
                    "occurred_at": now().isoformat(),
                    "producer": "patient",
                    "aggregate_type": "patient",
                    "aggregate_id": str(profile_id),
                    "aggregate_version": 1,
                    "request_id": str(request.state.request_id),
                    "correlation_id": str(request.state.correlation_id),
                    "causation_id": None,
                    "traceparent": request.state.traceparent,
                    "payload": {
                        "patient_id": str(profile_id),
                        "user_id": str(user_id),
                        "active": True,
                        "patient_version": 1,
                    },
                }
                await session.execute(
                    insert(outbox_events).values(
                        event_id=event_id,
                        aggregate_type="patient",
                        aggregate_id=profile_id,
                        aggregate_version=1,
                        event_type="patient.registered.v1",
                        envelope=envelope,
                    )
                )
                await audit(session, request, "auth.register", user_id)
                await session.execute(
                    insert(idempotency_requests).values(
                        principal_scope=scope,
                        method="POST",
                        route_template="/api/v1/auth/register",
                        key=key,
                        request_hash=fingerprint,
                        response_code=201,
                        response=result,
                        expires_at=now() + timedelta(days=1),
                    )
                )
            response.headers["Cache-Control"] = "no-store"
            return result
        except IntegrityError as error:
            if (
                getattr(getattr(error.orig, "diag", None), "constraint_name", "")
                == "uq_users_email_normalized"
            ):
                raise HTTPException(409) from None
            if getattr(error.orig, "sqlstate", None) != "23505" or attempt == 2:
                raise HTTPException(503) from None
    raise HTTPException(503)


@router.post("/api/v1/auth/login")
async def login(
    payload: LoginInput,
    request: Request,
    response: Response,
    auth=Depends(csrf),
    session=Depends(get_database_session),
):
    candidate = (
        (
            await session.execute(
                select(users).where(users.c.email_normalized == payload.email)
            )
        )
        .mappings()
        .first()
    )
    await session.rollback()
    verified = await auth.verify(
        candidate["password_hash"] if candidate else auth.dummy,
        payload.password.get_secret_value(),
    )
    replacement = (
        await auth.hash(payload.password.get_secret_value())
        if verified and auth.passwords.check_needs_rehash(candidate["password_hash"])
        else None
    )
    failed = True
    async with session.begin():
        if candidate:
            user, profile, roles = await account(session, candidate["id"], lock=True)
            if (
                verified
                and user["password_hash"] == candidate["password_hash"]
                and user["account_state"] == "active"
                and profile
                and roles
            ):
                if replacement:
                    await session.execute(
                        update(users)
                        .where(users.c.id == user["id"])
                        .values(password_hash=replacement, updated_at=now())
                    )
                _, raw, age = await create_session(session, user["id"], auth)
                result = auth.access(user, profile, roles)
                failed = False
        await audit(
            session,
            request,
            "auth.login",
            candidate["id"] if candidate else None,
            "denied" if failed else "success",
        )
    if failed:
        raise HTTPException(401)
    set_cookie(response, REFRESH_COOKIE, raw, auth, age)
    return result


async def account_changed(session, request, user, profile):
    """Persist authority invalidation alongside revocation; no broker workflow."""
    event_id = new_id()
    payload = {
        "user_id": str(user["id"]),
        "active": user["account_state"] == "active",
        "auth_version": user["auth_version"] + 1,
    }
    if profile:
        payload.update(
            patient_id=str(profile["id"]), patient_version=profile["version"]
        )
    version = user["version"] + 1
    envelope = {
        "event_id": str(event_id),
        "event_type": "patient.account.changed.v1",
        "schema_version": 1,
        "producer": "patient",
        "occurred_at": now().isoformat(),
        "aggregate_type": "user",
        "aggregate_id": str(user["id"]),
        "aggregate_version": version,
        "request_id": str(request.state.request_id),
        "correlation_id": str(request.state.correlation_id),
        "causation_id": None,
        "traceparent": request.state.traceparent,
        "payload": payload,
    }
    await session.execute(
        insert(outbox_events).values(
            event_id=event_id,
            aggregate_type="user",
            aggregate_id=user["id"],
            aggregate_version=version,
            event_type="patient.account.changed.v1",
            envelope=envelope,
        )
    )


async def rotate_or_revoke(request, response, auth, session, logout=False):
    raw = request.cookies.get(REFRESH_COOKIE, "")
    if len(raw) > 128:
        raise HTTPException(401)
    discovered = (
        (
            await session.execute(
                select(refresh_sessions).where(
                    refresh_sessions.c.token_hash == digest(raw)
                )
            )
        )
        .mappings()
        .first()
        if raw
        else None
    )
    await session.rollback()
    failed = True
    result = None
    async with session.begin():
        if discovered:
            user, profile, roles = await account(
                session, discovered["user_id"], lock=True
            )
            stored = (
                (
                    await session.execute(
                        select(refresh_sessions)
                        .where(refresh_sessions.c.id == discovered["id"])
                        .with_for_update()
                    )
                )
                .mappings()
                .one()
            )
            expired = (
                stored["expires_at"] <= now() or stored["family_expires_at"] <= now()
            )
            if (
                logout
                or stored["revoked_at"]
                or expired
                or user["account_state"] != "active"
            ):
                affected = await session.execute(
                    update(refresh_sessions)
                    .where(
                        refresh_sessions.c.user_id == user["id"],
                        refresh_sessions.c.family_id == stored["family_id"],
                        refresh_sessions.c.revoked_at.is_(None),
                    )
                    .values(revoked_at=now(), updated_at=now())
                )
                if affected.rowcount:
                    await session.execute(
                        update(users)
                        .where(users.c.id == user["id"])
                        .values(
                            auth_version=users.c.auth_version + 1,
                            version=users.c.version + 1,
                            updated_at=now(),
                        )
                    )
                if affected.rowcount:
                    await account_changed(session, request, user, profile)
                await audit(
                    session,
                    request,
                    "auth.logout" if logout else "auth.refresh_rejected",
                    user["id"],
                    "success" if logout else "denied",
                )
            elif profile and roles:
                child, raw, age = await create_session(
                    session,
                    user["id"],
                    auth,
                    stored["family_id"],
                    stored["family_expires_at"],
                )
                await session.execute(
                    update(refresh_sessions)
                    .where(refresh_sessions.c.id == stored["id"])
                    .values(revoked_at=now(), replaced_by_id=child, updated_at=now())
                )
                result = auth.access(user, profile, roles)
                await audit(session, request, "auth.refresh", user["id"])
                failed = False
        else:
            await audit(
                session,
                request,
                "auth.logout" if logout else "auth.refresh_rejected",
                result="denied",
            )
    if logout:
        response.delete_cookie(
            REFRESH_COOKIE,
            path=COOKIE_PATH,
            secure=not auth.config.allow_http,
            httponly=True,
            samesite="lax",
        )
        response.headers["Cache-Control"] = "no-store"
        return
    if failed:
        raise HTTPException(401)
    set_cookie(response, REFRESH_COOKIE, raw, auth, age)
    return result


@router.post("/api/v1/auth/refresh")
async def refresh(
    request: Request,
    response: Response,
    auth=Depends(csrf),
    session=Depends(get_database_session),
):
    return await rotate_or_revoke(request, response, auth, session)


@router.post("/api/v1/auth/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    auth=Depends(csrf),
    session=Depends(get_database_session),
):
    await rotate_or_revoke(request, response, auth, session, logout=True)


@router.get("/api/v1/patients/me")
async def me(
    request: Request,
    response: Response,
    principal: Principal = Depends(require_roles("patient")),
    session=Depends(get_database_session),
):
    async with session.begin():
        user, profile, roles = await account(session, int(principal.user_id))
        if (
            not user
            or user["account_state"] != "active"
            or user["auth_version"] != principal.auth_version
            or "patient" not in roles
            or not profile
            or str(profile["id"]) != principal.patient_id
        ):
            raise HTTPException(401)
        await audit(session, request, "auth.profile_read", user["id"])
        result = {
            k: profile[k]
            for k in (
                "id",
                "user_id",
                "display_name",
                "version",
                "date_of_birth",
                "synthetic_contact",
            )
        }
        result["id"], result["user_id"] = str(result["id"]), str(result["user_id"])
        if result["date_of_birth"]:
            result["date_of_birth"] = result["date_of_birth"].isoformat()
        result = {k: v for k, v in result.items() if v is not None}
    response.headers["Cache-Control"] = "no-store"
    response.headers["ETag"] = '"' + str(result["version"]) + '"'
    return result


@router.get("/internal/v1/auth/jwks")
async def jwks(request: Request):
    request.app.state.auth_verifier.service(bearer(request), "jwks:read")
    return {
        "keys": [
            {
                **json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key)),
                "kid": kid,
                "alg": "RS256",
                "use": "sig",
            }
            for kid, key in request.app.state.auth_verifier.user_keys.items()
        ]
    }


@router.post("/internal/v1/authorization/check")
async def current_authority(
    payload: AuthorityInput, request: Request, session=Depends(get_database_session)
):
    verifier = request.app.state.auth_verifier
    verifier.service(bearer(request), "authorization:check")
    delegated = verifier.user(bearer(request, "X-Delegated-Authorization"))
    if (
        payload.subject_user_id != delegated.user_id
        or payload.auth_version != delegated.auth_version
        or payload.required_role not in delegated.roles
    ):
        raise HTTPException(403)
    async with session.begin():
        user, _, roles = await account(session, int(payload.subject_user_id))
        active = bool(user and user["account_state"] == "active")
        version = user["auth_version"] if user else 0
        allowed = (
            active
            and version == payload.auth_version
            and payload.required_role in roles
        )
        await audit(
            session,
            request,
            "auth.authority_check",
            payload.subject_user_id,
            "success" if allowed else "denied",
        )
    return {"active": active, "allowed": allowed, "current_auth_version": version}
