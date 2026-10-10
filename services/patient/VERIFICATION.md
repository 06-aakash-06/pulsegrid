# Phase 1.4C-A verification record

Worktree branch: `foundation/backend-auth`. Base: `bd797050e097efecc5687a16b91c6bd37cf22976`.
All changes are service-owned. Main and frontend sources were untouched. No merge or push was performed. The final commit is reported by `git rev-parse HEAD` after this record is committed.

## Implemented

Patient registration, Argon2id login, short-lived RS256 access JWTs, public-only private JWKS, refresh rotation/replay/family revocation/logout, signed CSRF token delivery, exact-origin credentialed CORS and current authenticated profile. Registration preserves local audit/outbox/idempotency atomicity. Authority version invalidation has a local account-changed outbox record, without publishing.

Seven independent service-owned verifiers, RBAC/self/resource-proof dependencies and bounded authenticated current-authority calls. User and service credentials have separate keys, issuers, audiences and token-use claims; service keys are bound to caller identity. Patient owns all credentials and session database operations; other services use its internal authenticated API.

Patient migration `0003_auth_audit` adds a constrained append-only audit function and pgcrypto hashing. No new tables or foreign database connections. Existing seven schema histories remain separate. See [the frontend contract and runbook](AUTHENTICATION.md).

## Tested

- **287 backend tests passed**, with no skips: original 119 + 158 protocol/security checks + 10 real PostgreSQL transaction/integration tests. One existing Starlette/httpx deprecation warning remains.
- Actual PostgreSQL: concurrent same-key registration replay, distinct-key duplicate conflict, normalization, ID-collision retry, forced rollback without partial user insertion, Argon2id persistence/verification, login failure parity, session rotation, strict concurrent refresh 200/401 with whole-family revocation, replay, idle/absolute expiry, logout, disabled-account and auth-version revocation, account invalidation outbox, private-service JWT boundaries and immutable audit-chain checks.
- All seven independent JWT verifiers: valid tokens, expiry, signature, algorithm, audience/issuer, malformed claims, role denial, spoofed public headers, resource scope, service identity pinning, current-authority denial/outage/invalid response/deadline, production configuration rejection, key overlap and unknown kid. Bounded password admission and public-only JWKS snapshot tested.
- Production cookie flags and HTTP rejection tested with HTTPS ASGI requests. This is not a production TLS deployment test.
- Compose configuration validated; all seven images built. An isolated stack started PostgreSQL, Traefik, Redis, RabbitMQ and seven APIs successfully; all eleven containers were healthy in the complete-stack snapshot.
- All seven gateway liveness/readiness endpoints returned 200. Gateway registration/login/me/refresh/logout passed; public `/internal/v1/auth/jwks` returned 404. All seven service containers exercised their own service credentials and a signed delegated user token against the real Patient authority, including Patient itself.
- Each application process ran as UID 10001 with zero effective capabilities after credential bootstrap.
- All seven installed container environments passed `python -m pip check`.
- Each migration history passed repeated `alembic upgrade head` and `alembic check`, without ORM drift.
- Each runtime role queried its owned database, was not superuser, was denied an actual connection to a foreign service database, and lacked audit UPDATE permission.
- Original main remained at its base SHA with a clean tree. After recovery, all seven original gateway live/ready endpoints returned 200. Original image tags were restored from an archive of the unchanged baseline commit.
- `git diff --check` passed. Frontend diff against the base is empty.

## Exact verification commands

Commands were executed from the isolated worktree. Keys and the ignored `.env` were generated locally. Verification used gateway 8081, edge subnet 172.29.41.0/24 and localhost-only PostgreSQL port 55433.

```sh
COMPOSE_PARALLEL_LIMIT=1 docker compose -p pulsegrid-auth -f compose.yaml -f services/patient/compose.auth.yaml -f services/patient/compose.auth-test.yaml build patient doctor appointment records pharmacy billing emergency
docker compose -p pulsegrid-auth -f compose.yaml -f services/patient/compose.auth.yaml -f services/patient/compose.auth-test.yaml config --quiet
docker compose -p pulsegrid-auth -f compose.yaml -f services/patient/compose.auth.yaml -f services/patient/compose.auth-test.yaml up -d --no-build
PULSEGRID_AUTH_INTEGRATION=1 PYTHONPATH=services/patient:services/doctor:services/appointment:services/records:services/pharmacy:services/billing:services/emergency /tmp/pulsegrid-verify-venv/bin/python -m pytest --import-mode=importlib services -q
/tmp/pulsegrid-verify-venv/bin/python /tmp/pulsegrid-auth-runtime.py
/tmp/pulsegrid-verify-venv/bin/python /tmp/pulsegrid-auth-migrations.py
/tmp/pulsegrid-verify-venv/bin/python /tmp/pulsegrid-auth-isolation.py
docker compose -p pulsegrid-auth -f compose.yaml -f services/patient/compose.auth.yaml -f services/patient/compose.auth-test.yaml down
git diff --check
```

The temporary runtime harness tested real gateway flows, distinct service identities and current-authority calls from every service. The migration harness ran these commands sequentially for each domain:

```sh
docker compose -p pulsegrid-auth -f compose.yaml -f services/patient/compose.auth.yaml -f services/patient/compose.auth-test.yaml run --rm patient-migrate alembic upgrade head
docker compose -p pulsegrid-auth -f compose.yaml -f services/patient/compose.auth.yaml -f services/patient/compose.auth-test.yaml run --rm patient-migrate alembic check
docker exec pulsegrid-auth-patient-1 python -m pip check
```

Substitute each of doctor, appointment, records, pharmacy, billing, emergency for patient. The isolation harness connected with each owned runtime credential and attempted a foreign-database connection. Temporary harnesses/logs are local execution evidence; reproducible automated security tests are committed under `services/patient/tests/`.

## Failures encountered and recovery

The initial integration run could not reach host PostgreSQL because Docker does not publish ports for its internal-only network. The optional test overlay now attaches PostgreSQL to a dedicated test bridge while binding the published port only to 127.0.0.1. The tests then passed against PostgreSQL; the production overlay retains the internal database network without a published port.

Seven concurrent image builds plus two full stacks exhausted the available memory of the 2 GiB Colima VM. Builds were cancelled, only isolated test containers were stopped to release memory, and the baseline Emergency container (exit 137) was restarted. A startup probe immediately after container recreation also observed a transient gateway 502 before readiness; checks passed after waiting for startup. Final repeated gateway checks confirmed all seven baseline services recovered. No persistent volumes were removed, and no original checkout files were changed. Auth images use separate tags; original tags were rebuilt from unchanged committed source before completion.

## Not tested / outstanding

Actual production TLS, browser authentication UI, automatic remote JWKS refresh, production key rotation operations, multi-host deployment and distributed abuse quotas are not verified or implemented here. The implemented rotation foundation supports explicit kids, overlapping public keys and verifier restart. Privileged staff provisioning, account/role mutation endpoints and hospital operations remain outside this phase. Resource assignment/grant checks must be connected to their owner domains when those commands exist.

The integrator must incorporate the service-owned contract/setup supplement into coordinated root docs and deployment configuration. The frontend agent must add CSRF initialization/header handling, stable registration idempotency headers and serialized refresh. Source was not modified in frontend/. Test synthetic records and immutable audit history are retained only in the isolated project's persistent PostgreSQL volume; the test stack is stopped without deleting volumes. No implementation blocker remains for backend integration.

## Changed files

- `services/appointment/appointment_service/authorization.py`
- `services/appointment/appointment_service/main.py`
- `services/appointment/appointment_service/secure_entrypoint.py`
- `services/appointment/pyproject.toml`
- `services/appointment/requirements.lock`
- `services/billing/billing_service/authorization.py`
- `services/billing/billing_service/main.py`
- `services/billing/billing_service/secure_entrypoint.py`
- `services/billing/pyproject.toml`
- `services/billing/requirements.lock`
- `services/doctor/doctor_service/authorization.py`
- `services/doctor/doctor_service/main.py`
- `services/doctor/doctor_service/secure_entrypoint.py`
- `services/doctor/pyproject.toml`
- `services/doctor/requirements.lock`
- `services/emergency/emergency_service/authorization.py`
- `services/emergency/emergency_service/main.py`
- `services/emergency/emergency_service/secure_entrypoint.py`
- `services/emergency/pyproject.toml`
- `services/emergency/requirements.lock`
- `services/patient/AUTHENTICATION.md`
- `services/patient/README.md`
- `services/patient/VERIFICATION.md`
- `services/patient/auth.env.example`
- `services/patient/compose.auth-test.yaml`
- `services/patient/compose.auth.yaml`
- `services/patient/generate_auth_keys.py`
- `services/patient/migrations/versions/0003_auth_audit.py`
- `services/patient/patient_service/authentication.py`
- `services/patient/patient_service/authorization.py`
- `services/patient/patient_service/main.py`
- `services/patient/patient_service/secure_entrypoint.py`
- `services/patient/pyproject.toml`
- `services/patient/requirements.lock`
- `services/patient/tests/test_authentication.py`
- `services/patient/tests/test_authorization_protocol.py`
- `services/pharmacy/pharmacy_service/authorization.py`
- `services/pharmacy/pharmacy_service/main.py`
- `services/pharmacy/pharmacy_service/secure_entrypoint.py`
- `services/pharmacy/pyproject.toml`
- `services/pharmacy/requirements.lock`
- `services/records/pyproject.toml`
- `services/records/records_service/authorization.py`
- `services/records/records_service/main.py`
- `services/records/records_service/secure_entrypoint.py`
- `services/records/requirements.lock`
