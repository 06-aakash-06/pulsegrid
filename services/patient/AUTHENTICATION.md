# Phase 1.4C-A backend authentication and frontend handoff

This phase adds Patient-owned authentication, without hospital operations or frontend changes. Shared root documentation, infrastructure and contracts are reserved for the parallel-work integrator. This service-owned supplement records the decisions to incorporate during integration; it does not change domain ownership.

## Local startup

From the repository root, use the existing environment generator once:

```sh
python3 infra/scripts/init-env.py
python3 -m venv .venv-auth
. .venv-auth/bin/activate
python -m pip install -e 'services/patient[test]'
python services/patient/generate_auth_keys.py --directory secrets/auth
```

Add the settings from `services/patient/auth.env.example` to the ignored root `.env`. Keep the generated environment credentials. Choose origins matching the browser exactly, including ports. The key generator refuses to overwrite an existing directory. Private files are mode 0600 and the directory is mode 0700. Never commit `.env`, private keys, or the idempotency secret.

```sh
docker compose -f compose.yaml -f services/patient/compose.auth.yaml config --quiet
docker compose -f compose.yaml -f services/patient/compose.auth.yaml up -d --build
docker compose -f compose.yaml -f services/patient/compose.auth.yaml logs --tail=100 patient
docker compose -f compose.yaml -f services/patient/compose.auth.yaml run --rm patient-migrate
curl -fsS http://localhost:8080/api/v1/patients/health/ready
docker compose -f compose.yaml -f services/patient/compose.auth.yaml down
```

The existing gateway already routes `/api/v1/auth` and `/api/v1/patients` to Patient with no rewrite; `/internal/v1` remains unavailable through the public gateway. Other service routes and public health checks are unchanged. No additional authentication database is introduced.

The overlay gives each service its own service-signing key and public verification files. Only Patient receives the user-signing private key and idempotency secret. A small container entrypoint copies private operator files into tmpfs, then permanently becomes UID/GID 10001 before starting Uvicorn. Initial bootstrap capabilities allow only this credential handoff; the application runs without effective capabilities. Access logging is disabled to avoid accidental credential-bearing URL logging. Application error envelopes and structured request IDs remain in place.

## Endpoint and browser contract

| Endpoint | Authentication | Result |
| --- | --- | --- |
| GET `/api/v1/auth/csrf` | Explicit allowed Origin, or same-origin browser Referer | `{csrf_token,header_name:"X-CSRF-Token",expires_in:3600}` and HttpOnly CSRF cookie |
| POST `/api/v1/auth/register` | Allowed Origin; idempotency headers below | 201 `PatientProfile`; no token or login side effect |
| POST `/api/v1/auth/login` | Allowed Origin + CSRF header/cookie | 200 `TokenSet`, refresh cookie |
| POST `/api/v1/auth/refresh` | Allowed Origin + CSRF header/cookie + refresh cookie | 200 `TokenSet`, rotated refresh cookie |
| POST `/api/v1/auth/logout` | Allowed Origin + CSRF header/cookie | 204, family revocation and cookie removal |
| GET `/api/v1/patients/me` | Bearer access JWT plus current Patient account check | `PatientProfile`, ETag |
| GET `/internal/v1/auth/jwks` | Service JWT with `jwks:read` | Public-only JWKS |
| POST `/internal/v1/authorization/check` | Service JWT with `authorization:check` AND delegated user JWT | Current active/role/version decision |

Frontend sequence: GET CSRF with `credentials: 'include'`, keep the returned token in memory, then send `X-CSRF-Token` and `credentials: 'include'` on login, refresh and logout. The CSRF cookie is HttpOnly, so do not read it with JavaScript. All these POST requests must carry the browser's actual Origin. Same-origin GET may supply Referer instead because browsers can omit Origin on GET. A missing, null, foreign or unconfigured origin is rejected. CORS permits credentialed requests only for the exact configured origins and explicitly listed headers. No wildcard origin is accepted.

For registration generate a fresh `Idempotency-Key` (16–128 characters, e.g. UUID) and `X-Anonymous-Command-ID` (32 random bytes encoded as base64url without padding). Keep both stable only when retrying the same registration. The latter is a command nonce, not identity authority. This implements the documented anonymous idempotency requirement with a stronger 256-bit nonce. Public registration forbids unknown fields, including role assignment. Default role is the documented lowercase `patient`. Payload: `{email,password,display_name,date_of_birth?,synthetic_contact?}`. Response: `{id,user_id,display_name,version,date_of_birth?,synthetic_contact?}`. Optional absent values are omitted. There is no privileged-account provisioning endpoint in this phase.

`TokenSet` is `{access_token,token_type:"Bearer",expires_in}`. Keep access tokens in memory and send `Authorization: Bearer ...`; role hints in the UI are never authorization. Do not retry login/refresh/logout automatically. Serialize refresh across requests/tabs: strict replay detection treats a concurrent second use as replay and revokes the winner's entire family. Require a fresh login after such a conflict. Registration does not return a fake login success.

Both cookies use Path `/api/v1/auth`, HttpOnly, SameSite=Lax, no Domain, and Secure by default. Only explicit development + loopback HTTP origins + `AUTH_ALLOW_HTTP=true` permit non-Secure cookies. Set `APP_ENVIRONMENT=production` for deployment. Production rejects that flag and requires real TLS, HTTPS origins and false. This phase does not provision production TLS. A 2 GiB VM running two full stacks concurrently can exhaust memory; build with COMPOSE_PARALLEL_LIMIT=1 and use a larger VM for parallel stacks. SameSite=Lax supports same-site development; cross-site frontend deployment is outside this cookie contract.

## Credentials, IDs and transactions

Email validation is shared by login and registration: trim surrounding whitespace, reject SMTPUTF8 local parts, use email-validator's normalized ASCII email and case-fold it with lowercase. The prototype intentionally treats the entire identifier as case-insensitive; DNS deliverability is not required for synthetic fixtures. Passwords are 12–256 characters on registration; a small explicit synthetic weak-password denylist applies. Argon2id uses 64 MiB, three passes, parallelism two by default; no passwords or raw tokens are stored, logged, audited or put in outbox/idempotency payloads. Password work is limited to two concurrent offloaded operations per process with a 250 ms admission deadline; overload returns 429 with Retry-After. This is resource admission, not a distributed brute-force quota. Missing-account login performs a dummy Argon2 verification and returns the same 401 envelope as an incorrect password or disabled account.

The architecture had reserved BIGINT IDs but did not define a temporary generator. `new_id()` therefore uses positive nonzero signed-63-bit CSPRNG integers, decimal strings on the API. PostgreSQL primary keys enforce uniqueness; registration retries ID conflicts up to three times. This is a temporary strategy, not a distributed Snowflake implementation or a mathematical guarantee of globally unique IDs. Replace this function during the dedicated ID phase.

Registration atomically inserts user, profile, PATIENT role, registration outbox, audit, and sanitized persisted idempotency response. A transaction advisory lock serializes equal anonymous command keys; the email unique constraint handles different keys and concurrent duplicate accounts. A keyed HMAC fingerprint prevents a password dictionary attack against persisted request fingerprints. Retain this dedicated secret across the idempotency retention window; automatic secret rotation/pruning is not implemented. Outbox records are persisted only: no RabbitMQ publishing is added.

Refresh tokens contain 256 random bits and only SHA-256 hashes are persisted. Lock order is user row, refresh row, audit chain head. All family mutations serialize under the owned user row across processes. Successful refresh atomically creates a child and revokes/replaces the parent. Reuse, expiry, disabled accounts and logout revoke the family and increment account auth_version when active sessions were revoked. Rejection is raised only after revocation commits. Idle expiry defaults to seven days, family absolute expiry to 30 days and never extends on rotation. Refresh and login do not persist token responses for replay. Account authority version changes persist `patient.account.changed.v1` in the same transaction; publishing remains deferred.

The existing refresh/session schema already supports this design. Only Patient migration `0003_auth_audit` is added: a constrained SECURITY DEFINER append function, owned by the migration role, serializes the immutable auth audit chain using PostgreSQL pgcrypto SHA-256. Runtime roles still cannot update/delete audit history or directly write heads/entries. All seven original schema histories and database boundaries remain independent.

## JWT and authorization protocol

User access tokens use RS256 with a configured kid, issuer `pulsegrid-patient`, exact audience `pulsegrid-api`, user subject, roles, auth_version, jti, iat, nbf and exp (default 600 seconds, maximum 600). Patient-issued tokens also contain their signed patient profile ID, enabling verified self-scope checks without foreign DB reads. The generic verifier permits an absent patient mapping for future staff accounts. Algorithms, signature, public key ownership, claim types, lifetime and mandatory claims are checked strictly. Private JWK material and untrusted embedded/remote key headers are rejected.

Each service owns a local `authorization.py` with the same narrow reviewed protocol, not shared domain models. Use `authenticated_user`, `require_roles(...)`, and `check_resource_scope(...)` on future routes. Assignment/grant proofs must come from the owner service's verified local data or authenticated owner API, never public request flags. Client X-User-ID/X-Role headers convey no authority. Health remains public. Business route authorization is prepared; business routes are not implemented.

For future sensitive writes use `require_current_role(...)`. It obtains a separate 60-second service JWT and calls Patient with a bounded two-second request. The delegated user JWT is separately verified, bound to subject/version/role, and current state is read only in Patient. Unavailable Patient fails closed with 503, denied current authority with 403. No locks are held over that network call. Final owner transaction and additional care/resource checks remain mandatory for future business commands; this check is not a distributed transaction or universal instantaneous revocation.

Service JWTs have issuer `pulsegrid-service:<caller>`, audience `pulsegrid-internal:<receiver>`, token_use `service`, and an explicit singleton scope. Each public service key is pinned to its caller. A service key cannot impersonate another service; user JWTs cannot authenticate internal service routes and service JWTs cannot authenticate users. Request/correlation IDs and traceparent propagate to the authority call.

Public verification files are mounted and loaded on startup. The private service-authenticated JWKS endpoint supports future dynamic verifier refresh; automatic network JWKS refresh is **not implemented**. Rotation currently requires a reviewed public-file update containing old and new keys, a new signing kid, and service restart with overlap of at least the longest outstanding token lifetime (including one-hour CSRF tokens if rotating that key). Signing secrets must match the configured public kid. Unknown kids fail closed. There is no distributed rate limiter, breached-password service or MFA in this phase; production abuse controls and production transport deployment remain outstanding.

## Environment reference

Under each service prefix `PULSEGRID_<DOMAIN>_AUTH_`: `JWKS_PATH`, `SERVICE_JWKS_PATH`, `SERVICE_PRIVATE_KEY_PATH`, `SERVICE_KID`, `ORIGINS`, `ALLOW_HTTP` and `AUTHORITY_URL` (suffix includes AUTHORITY_URL, yielding `...AUTH_AUTHORITY_URL`). Patient additionally uses `PRIVATE_KEY_PATH`, `KID`, `IDEMPOTENCY_SECRET_PATH`, `ACCESS_SECONDS` (60–600), `REFRESH_IDLE_SECONDS`, `REFRESH_ABSOLUTE_SECONDS` (maximum 30 days), `ARGON_MEMORY_KIB` (19456–131072) and `ARGON_TIME_COST` (2–6). The overlay maps `APP_ENVIRONMENT` and the bounded Patient settings from `auth.env.example` into these service variables. Existing DB/pool/deadline configuration is unchanged. Without keys auth routes fail closed with 503; public health/scaffold deployment continues to work.

## Real PostgreSQL verification

Use an isolated project and ignored environment, not a shared database. Change GATEWAY_PORT to 8081, EDGE_SUBNET to `172.29.41.0/24`, GATEWAY_IP to `172.29.41.2`, and allowed loopback origins to match. The optional test overlay exposes only PostgreSQL on 127.0.0.1:55433 for the host integration tests. It is not a deployment requirement.

```sh
docker compose -p pulsegrid-auth -f compose.yaml -f services/patient/compose.auth.yaml -f services/patient/compose.auth-test.yaml up -d --build
export PYTHONPATH=services/patient:services/doctor:services/appointment:services/records:services/pharmacy:services/billing:services/emergency
python -m pytest --import-mode=importlib services -q
PULSEGRID_AUTH_INTEGRATION=1 python -m pytest --import-mode=importlib services -q
docker compose -p pulsegrid-auth -f compose.yaml -f services/patient/compose.auth.yaml -f services/patient/compose.auth-test.yaml down
```

Install the other six service packages with their test extras into the same verification venv if testing all services. Integration tests use fresh unique synthetic identities and retain audit/domain history; do not run them on shared data or automatically delete persistent volumes. The actual results and commands are recorded in the completion report. Unit protocol checks run against all seven independently owned verifiers; PostgreSQL tests exercise duplicate registration, rotation/replay races, revocation, hashing, CSRF/CORS, authority and audit privileges.

## Library references

The maintained library APIs used here are [PyJWT verification](https://pyjwt.readthedocs.io/en/stable/usage.html) and [argon2-cffi PasswordHasher](https://argon2-cffi.readthedocs.io/en/stable/api.html). Cryptographic signing, verification, hashing and constant-time comparison use libraries rather than custom primitives.
