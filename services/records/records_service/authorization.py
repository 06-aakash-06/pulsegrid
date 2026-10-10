"""Local verifier of the reviewed auth protocol; no foreign database access."""

from __future__ import annotations
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit
import httpx
import jwt
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from fastapi import Depends, HTTPException, Request

ROLES = frozenset(
    "patient doctor receptionist pharmacist billing_staff emergency_staff hospital_admin ops".split()
)
DOMAINS = frozenset(
    "patient doctor appointment records pharmacy billing emergency".split()
)
ISSUER = "pulsegrid-patient"
AUDIENCE = "pulsegrid-api"
ID = re.compile(r"^[1-9][0-9]{0,18}$")


def valid_id(value):
    return isinstance(value, str) and bool(ID.fullmatch(value)) and int(value) < 2**63


@dataclass(frozen=True)
class AuthConfig:
    jwks_path: str = ""
    service_jwks_path: str = ""
    private_key_path: str = ""
    idempotency_secret_path: str = ""
    kid: str = "patient-dev-1"
    service_private_key_path: str = ""
    service_kid: str = ""
    origins: tuple[str, ...] = ()
    allow_http: bool = False
    access_seconds: int = 600
    refresh_idle_seconds: int = 604800
    refresh_absolute_seconds: int = 2592000
    argon_memory_kib: int = 65536
    argon_time_cost: int = 3
    authority_url: str = "http://patient:8000/internal/v1/authorization/check"

    @classmethod
    def from_env(cls, environment):
        prefix = "PULSEGRID_RECORDS_AUTH_"

        def get(name, default=""):
            return os.environ.get(prefix + name, default)

        raw = get("ALLOW_HTTP", "false")
        if raw not in ("true", "false"):
            raise ValueError("AUTH_ALLOW_HTTP must be true or false")
        origins = tuple(v.strip() for v in get("ORIGINS").split(",") if v.strip())
        config = cls(
            jwks_path=get("JWKS_PATH"),
            service_jwks_path=get("SERVICE_JWKS_PATH"),
            private_key_path=get("PRIVATE_KEY_PATH"),
            idempotency_secret_path=get("IDEMPOTENCY_SECRET_PATH"),
            kid=get("KID", "patient-dev-1"),
            service_private_key_path=get("SERVICE_PRIVATE_KEY_PATH"),
            service_kid=get("SERVICE_KID"),
            origins=origins,
            allow_http=raw == "true",
            access_seconds=int(get("ACCESS_SECONDS", "600")),
            refresh_idle_seconds=int(get("REFRESH_IDLE_SECONDS", "604800")),
            refresh_absolute_seconds=int(get("REFRESH_ABSOLUTE_SECONDS", "2592000")),
            argon_memory_kib=int(get("ARGON_MEMORY_KIB", "65536")),
            argon_time_cost=int(get("ARGON_TIME_COST", "3")),
            authority_url=get(
                "AUTHORITY_URL", "http://patient:8000/internal/v1/authorization/check"
            ),
        )
        if config.allow_http and environment != "development":
            raise ValueError(
                "Insecure cookies require explicit development environment"
            )
        for origin in origins:
            u = urlsplit(origin)
            if (
                u.scheme not in ("https", "http")
                or not u.hostname
                or u.username
                or u.password
                or u.path
                or u.query
                or u.fragment
            ):
                raise ValueError("AUTH_ORIGINS must contain exact origins")
            if u.scheme == "http" and not (
                config.allow_http and u.hostname in ("localhost", "127.0.0.1", "::1")
            ):
                raise ValueError(
                    "HTTP origins are allowed only for explicit loopback development"
                )
        if (
            not 60 <= config.access_seconds <= 600
            or not 60
            <= config.refresh_idle_seconds
            <= config.refresh_absolute_seconds
            <= 2592000
        ):
            raise ValueError("Invalid session lifetime")
        if (
            not 19456 <= config.argon_memory_kib <= 131072
            or not 2 <= config.argon_time_cost <= 6
        ):
            raise ValueError("Invalid Argon2 cost")
        return config


def read_keys(path):
    if not path:
        return {}
    raw = Path(path).read_bytes()
    if len(raw) > 65536:
        raise ValueError("JWKS exceeds configured size bound")
    data = json.loads(raw)
    keys = {}
    for entry in data["keys"]:
        if (
            entry.get("kty") != "RSA"
            or entry.get("alg") != "RS256"
            or entry.get("use") != "sig"
            or any(k in entry for k in ("d", "p", "q", "dp", "dq", "qi"))
        ):
            raise ValueError("Only public RS256 signing keys are accepted")
        kid = entry.get("kid")
        if not isinstance(kid, str) or not kid or len(kid) > 128 or kid in keys:
            raise ValueError("Invalid or duplicate key identifier")
        key = jwt.PyJWK.from_dict(entry, algorithm="RS256").key
        if key.key_size < 2048:
            raise ValueError("RSA key must be at least 2048 bits")
        keys[kid] = key
    return keys


class Verifier:
    def __init__(self, config):
        self.config = config
        self.user_keys = read_keys(config.jwks_path)
        self.service_keys = read_keys(config.service_jwks_path)
        self.service_key_owners = (
            {
                e["kid"]: e.get("service")
                for e in json.loads(Path(config.service_jwks_path).read_text())["keys"]
            }
            if config.service_jwks_path
            else {}
        )
        if any(owner not in DOMAINS for owner in self.service_key_owners.values()):
            raise ValueError("Service JWKS must bind every key to a service")

        if config.service_private_key_path:
            key = load_pem_private_key(
                Path(config.service_private_key_path).read_bytes(), password=None
            )
            if (
                not isinstance(key, RSAPrivateKey)
                or key.key_size < 2048
                or self.service_key_owners.get(config.service_kid) != "records"
                or config.service_kid not in self.service_keys
                or key.public_key().public_numbers()
                != self.service_keys[config.service_kid].public_numbers()
            ):
                raise ValueError(
                    "Service signing key must match its configured owner and public kid"
                )

    def decode(self, token, keys, issuer, audience, purpose, max_lifetime=600):
        if len(token) > 16384:
            raise HTTPException(401, headers={"WWW-Authenticate": "Bearer"})
        try:
            header = jwt.get_unverified_header(token)
            if (
                header.get("alg") != "RS256"
                or header.get("kid") not in keys
                or any(k in header for k in ("jku", "jwk", "x5u", "crit"))
            ):
                raise jwt.InvalidTokenError()
            claims = jwt.decode(
                token,
                keys[header["kid"]],
                algorithms=["RS256"],
                issuer=issuer,
                audience=audience,
                options={
                    "require": [
                        "iss",
                        "aud",
                        "sub",
                        "jti",
                        "iat",
                        "nbf",
                        "exp",
                        "token_use",
                    ],
                    "strict_aud": True,
                },
            )
            if (
                claims["token_use"] != purpose
                or not isinstance(claims["jti"], str)
                or not claims["jti"]
            ):
                raise jwt.InvalidTokenError()
            if (
                any(type(claims[k]) is not int for k in ("iat", "nbf", "exp"))
                or not 0 < claims["exp"] - claims["iat"] <= max_lifetime
            ):
                raise jwt.InvalidTokenError()
            return claims
        except (jwt.PyJWTError, KeyError, TypeError, ValueError):
            raise HTTPException(401, headers={"WWW-Authenticate": "Bearer"}) from None

    def user(self, token):
        if not self.user_keys:
            raise HTTPException(503)
        c = self.decode(token, self.user_keys, ISSUER, AUDIENCE, "access")
        if (
            not valid_id(c["sub"])
            or (c.get("patient_id") is not None and not valid_id(c["patient_id"]))
            or type(c.get("auth_version")) is not int
            or c["auth_version"] < 1
        ):
            raise HTTPException(401)
        roles = c.get("roles")
        if (
            not isinstance(roles, list)
            or not roles
            or any(not isinstance(r, str) or r not in ROLES for r in roles)
            or len(set(roles)) != len(roles)
        ):
            raise HTTPException(401)
        return Principal(
            c["sub"], c.get("patient_id"), frozenset(roles), c["auth_version"], token
        )

    def service(self, token, scope):
        if not self.service_keys:
            raise HTTPException(503)
        if len(token) > 16384:
            raise HTTPException(401)
        # Issuer is chosen only from the reviewed service allowlist, then signature verified.
        try:
            untrusted = jwt.decode(token, options={"verify_signature": False})
            caller = untrusted.get("sub")
            if caller not in DOMAINS:
                raise HTTPException(401)
        except (jwt.PyJWTError, TypeError, ValueError):
            raise HTTPException(401) from None
        c = self.decode(
            token,
            self.service_keys,
            "pulsegrid-service:" + caller,
            "pulsegrid-internal:records",
            "service",
            120,
        )
        # A key is pinned to its caller; a service cannot claim another service's identity.
        if (
            self.service_key_owners.get(jwt.get_unverified_header(token)["kid"])
            != caller
            or c["sub"] != caller
        ):
            raise HTTPException(401)
        if c.get("scopes") != [scope]:
            raise HTTPException(403)
        return caller


@dataclass(frozen=True)
class Principal:
    user_id: str
    patient_id: str | None
    roles: frozenset[str]
    auth_version: int
    access_token: str = field(repr=False)


def bearer(request, header="Authorization"):
    parts = request.headers.get(header, "").split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(401, headers={"WWW-Authenticate": "Bearer"})
    return parts[1]


async def authenticated_user(request: Request):
    return request.app.state.auth_verifier.user(bearer(request))


def require_roles(*roles):
    if not roles or any(r not in ROLES for r in roles):
        raise ValueError("Unknown required role")

    async def dependency(principal: Principal = Depends(authenticated_user)):
        if not principal.roles.intersection(roles):
            raise HTTPException(403)
        return principal

    return dependency


def check_resource_scope(
    principal,
    *,
    owner_user_id=None,
    patient_id=None,
    assignment_verified=False,
    grant_verified=False,
):
    # Assignment/grant booleans must come from the owner service's verified DB/API result.
    if (
        (owner_user_id is not None and principal.user_id == str(owner_user_id))
        or (
            patient_id is not None
            and "patient" in principal.roles
            and principal.patient_id == str(patient_id)
        )
        or assignment_verified is True
        or grant_verified is True
    ):
        return
    raise HTTPException(403)


def service_token(config, scope, target="patient"):
    if not config.service_private_key_path or not config.service_kid:
        raise HTTPException(503)
    now = int(time.time())
    key = Path(config.service_private_key_path).read_bytes()
    return jwt.encode(
        {
            "iss": "pulsegrid-service:records",
            "aud": "pulsegrid-internal:" + target,
            "sub": "records",
            "jti": __import__("secrets").token_urlsafe(24),
            "iat": now,
            "nbf": now,
            "exp": now + 60,
            "token_use": "service",
            "scopes": [scope],
        },
        key,
        algorithm="RS256",
        headers={"kid": config.service_kid},
    )


def require_current_role(role):
    async def dependency(
        request: Request, principal: Principal = Depends(require_roles(role))
    ):
        config = request.app.state.auth_config
        token = service_token(config, "authorization:check")
        try:
            async with httpx.AsyncClient(
                timeout=2, follow_redirects=False, trust_env=False
            ) as client:
                result = await client.post(
                    config.authority_url,
                    json={
                        "subject_user_id": principal.user_id,
                        "required_role": role,
                        "auth_version": principal.auth_version,
                    },
                    headers={
                        "Authorization": "Bearer " + token,
                        "X-Delegated-Authorization": "Bearer " + principal.access_token,
                        "X-Request-ID": str(request.state.request_id),
                        "X-Correlation-ID": str(request.state.correlation_id),
                        **(
                            {"traceparent": request.state.traceparent}
                            if getattr(request.state, "traceparent", None)
                            else {}
                        ),
                    },
                )
            if result.status_code != 200:
                raise HTTPException(503 if result.status_code >= 500 else 403)
            if len(result.content) > 4096:
                raise HTTPException(503)
            c = result.json()
            if not isinstance(c, dict):
                raise HTTPException(503)
            if (
                c.get("active") is not True
                or c.get("allowed") is not True
                or c.get("current_auth_version") != principal.auth_version
            ):
                raise HTTPException(403)
        except httpx.TimeoutException:
            raise HTTPException(504) from None
        except (httpx.HTTPError, ValueError, KeyError):
            raise HTTPException(503) from None
        return principal

    return dependency
