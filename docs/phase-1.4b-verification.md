# Phase 1.4B verification record

Executed locally on 2026-10-10, starting from clean `main` at `ba777d84d6759423b73b498501af0b055b8c5a9a`. No original scaffold branch/worktree was changed and nothing was pushed. Scope: infrastructure and initial persistence only.

## Implemented and tested

| Check | Result |
|---|---|
| Compose configuration and seven service image builds | PASS; pinned base/infrastructure digests and service-local runtime locks |
| PostgreSQL, Redis, RabbitMQ, Traefik and seven APIs | All eleven long-running containers healthy; seven migration containers exited 0 |
| Databases/runtime roles/migration owners | All seven `<domain>_db`, `<domain>_app`, `<domain>_migration` created; bootstrap credentials absent from API jobs |
| Migrations | Six heads `0002_explicit_worker`; Doctor head `0003_explicit_worker`; 88 owned tables plus seven Alembic version tables |
| Migration repetition | Two repeat upgrades per service and `alembic check` passed; Final checks repeated after the Doctor exclusion and explicit-worker revisions |
| Bootstrap repetition | Rerun against the persistent instance passed without losing schema/data |
| Schema verification | Types, nullability, PKs, local RESTRICT FKs, unique/check constraints, indexes/partial indexes, Doctor exclusion and absence of ID sequences verified |
| Owned database queries | Seven SELECT checks passed with non-superuser runtime roles |
| Isolation | All 42 actual cross-domain connections denied by PostgreSQL; all fourteen roles have CONNECT only to their owned database |
| Restricted privileges | Runtime DDL/TEMP denied; audit/Alembic mutation privileges absent; domain DML available |
| Session cleanup | Seven async request-session dependencies roll back uncommitted infrastructure rows and dispose pools |
| Doctor overlap constraint | Overlapping intervals rejected with SQLSTATE 23P01; all test fixtures rolled back |
| Gateway | Seven domain prefixes preserve paths; auth and short-link reservations reach their owners and return 404; prefix collisions/internal/docs/admin paths rejected |
| Proxy boundaries | Aliased header rejected with 400; spoofed forwarded scheme/host does not alter successful health routing |
| Health | All seven liveness/readiness endpoints 200 with PostgreSQL available |
| Controlled PostgreSQL outage | All seven readiness endpoints 503/unavailable; liveness remains 200; same APIs recover to 200 after database restart; volumes preserved |
| Graceful shutdown | Seven application shutdown hooks completed, no tracebacks, normal SIGTERM container exit 143; restart and gateway checks passed |
| Redis/RabbitMQ | Authenticated Redis PONG and RabbitMQ diagnostics ping passed |
| Python dependency compatibility | `pip check` passed in all seven API containers |
| Backend regression | 119 passed, including all original 49; one upstream Starlette/httpx deprecation warning |
| Frontend regression | Typecheck passed, 27 tests passed, production build passed |
| Frontend connectivity | Vite root, proxied Patient liveness and Appointment readiness returned 200 |
| Secrets/ownership review | Private `.env` ignored with mode 0600; no generated passwords/private keys in proposed tracked files; imports remain in each owning domain |
| Diff whitespace | `git diff --check` passed |

## Commands executed

From repository root:

```sh
python3 infra/scripts/init-env.py
docker compose config --quiet
docker compose up -d --build
docker compose ps -a
docker compose exec -T postgres sh /docker-entrypoint-initdb.d/01-databases.sh
python3 tests/verify_infrastructure.py --failure --shutdown
```

For each of `patient`, `doctor`, `appointment`, `records`, `pharmacy`, `billing`, `emergency`, the migration and dependency checks were:

```sh
docker compose run --rm patient-migrate alembic upgrade head
docker compose run --rm patient-migrate alembic upgrade head
docker compose run --rm patient-migrate alembic check
docker compose exec -T patient python -m pip check
```

The backend checks used an isolated temporary verification environment:

```sh
PYTHONPATH=services/patient:services/doctor:services/appointment:services/records:services/pharmacy:services/billing:services/emergency /tmp/pulsegrid-verify-venv/bin/python -m pytest --import-mode=importlib services -q
docker compose exec -T redis sh -c 'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli ping'
docker compose exec -T rabbitmq rabbitmq-diagnostics -q ping
```

From `frontend/`:

```sh
npm run typecheck
npm test
npm run build
npm run dev -- --port 5173
```

The dev server was stopped after proxy verification. Compose remains running and healthy. The portable environment setup and normal frontend access commands are in [infrastructure.md](infrastructure.md).

## Not tested or implemented

No blockers remain for this phase. Authentication, business operations, event delivery, distributed caching, rate limiting, telemetry and production TLS are not implemented or tested. Appointment overlap exclusions and slot-copy consistency enforcement remain explicitly deferred prerequisites for booking. Normalized Doctor search, Snowflake allocation, constrained audit append functions, clinical/financial immutability enforcement and undefined workflow status vocabularies need the later reviewed workflow implementation. No concurrency safety, performance, backup restore or HA claim is made. Single-host/shared-instance failures remain correlated.

Phase 1.4C can begin with its own explicit scope. Authentication preparation requirements are documented in the infrastructure runbook. The test-client deprecation warning is nonblocking and should be addressed when the scaffold's test dependencies are deliberately updated.

## Changed-file manifest

```text
.env.example
README.md
compose.yaml
docs/api-contracts.md
docs/architecture.md
docs/database-design.md
docs/development-roadmap.md
docs/infrastructure.md
docs/phase-1.4b-verification.md
docs/security.md
docs/service-boundaries.md
frontend/.env.example
frontend/README.md
frontend/vite.config.ts
infra/postgres/init/01-databases.sh
infra/scripts/init-env.py
infra/traefik/routes.yaml
infra/traefik/traefik.yaml
services/appointment/.dockerignore
services/appointment/Dockerfile
services/appointment/README.md
services/appointment/alembic.ini
services/appointment/appointment_service/api/health.py
services/appointment/appointment_service/database.py
services/appointment/appointment_service/main.py
services/appointment/appointment_service/models.py
services/appointment/appointment_service/schemas.py
services/appointment/appointment_service/settings.py
services/appointment/migrations/env.py
services/appointment/migrations/script.py.mako
services/appointment/migrations/versions/0001_initial.py
services/appointment/migrations/versions/0002_explicit_worker.py
services/appointment/pyproject.toml
services/appointment/requirements.lock
services/appointment/tests/test_database.py
services/billing/.dockerignore
services/billing/Dockerfile
services/billing/README.md
services/billing/alembic.ini
services/billing/billing_service/api/health.py
services/billing/billing_service/database.py
services/billing/billing_service/main.py
services/billing/billing_service/models.py
services/billing/billing_service/schemas.py
services/billing/billing_service/settings.py
services/billing/migrations/env.py
services/billing/migrations/script.py.mako
services/billing/migrations/versions/0001_initial.py
services/billing/migrations/versions/0002_explicit_worker.py
services/billing/pyproject.toml
services/billing/requirements.lock
services/billing/tests/test_database.py
services/doctor/.dockerignore
services/doctor/Dockerfile
services/doctor/README.md
services/doctor/alembic.ini
services/doctor/doctor_service/api/health.py
services/doctor/doctor_service/database.py
services/doctor/doctor_service/main.py
services/doctor/doctor_service/models.py
services/doctor/doctor_service/schemas.py
services/doctor/doctor_service/settings.py
services/doctor/migrations/env.py
services/doctor/migrations/script.py.mako
services/doctor/migrations/versions/0001_initial.py
services/doctor/migrations/versions/0002_schedule_exclusion.py
services/doctor/migrations/versions/0003_explicit_worker.py
services/doctor/pyproject.toml
services/doctor/requirements.lock
services/doctor/tests/test_database.py
services/emergency/.dockerignore
services/emergency/Dockerfile
services/emergency/README.md
services/emergency/alembic.ini
services/emergency/emergency_service/api/health.py
services/emergency/emergency_service/database.py
services/emergency/emergency_service/main.py
services/emergency/emergency_service/models.py
services/emergency/emergency_service/schemas.py
services/emergency/emergency_service/settings.py
services/emergency/migrations/env.py
services/emergency/migrations/script.py.mako
services/emergency/migrations/versions/0001_initial.py
services/emergency/migrations/versions/0002_explicit_worker.py
services/emergency/pyproject.toml
services/emergency/requirements.lock
services/emergency/tests/test_database.py
services/patient/.dockerignore
services/patient/Dockerfile
services/patient/README.md
services/patient/alembic.ini
services/patient/migrations/env.py
services/patient/migrations/script.py.mako
services/patient/migrations/versions/0001_initial.py
services/patient/migrations/versions/0002_explicit_worker.py
services/patient/patient_service/api/health.py
services/patient/patient_service/database.py
services/patient/patient_service/main.py
services/patient/patient_service/models.py
services/patient/patient_service/schemas.py
services/patient/patient_service/settings.py
services/patient/pyproject.toml
services/patient/requirements.lock
services/patient/tests/test_database.py
services/pharmacy/.dockerignore
services/pharmacy/Dockerfile
services/pharmacy/README.md
services/pharmacy/alembic.ini
services/pharmacy/migrations/env.py
services/pharmacy/migrations/script.py.mako
services/pharmacy/migrations/versions/0001_initial.py
services/pharmacy/migrations/versions/0002_explicit_worker.py
services/pharmacy/pharmacy_service/api/health.py
services/pharmacy/pharmacy_service/database.py
services/pharmacy/pharmacy_service/main.py
services/pharmacy/pharmacy_service/models.py
services/pharmacy/pharmacy_service/schemas.py
services/pharmacy/pharmacy_service/settings.py
services/pharmacy/pyproject.toml
services/pharmacy/requirements.lock
services/pharmacy/tests/test_database.py
services/records/.dockerignore
services/records/Dockerfile
services/records/README.md
services/records/alembic.ini
services/records/migrations/env.py
services/records/migrations/script.py.mako
services/records/migrations/versions/0001_initial.py
services/records/migrations/versions/0002_explicit_worker.py
services/records/pyproject.toml
services/records/records_service/api/health.py
services/records/records_service/database.py
services/records/records_service/main.py
services/records/records_service/models.py
services/records/records_service/schemas.py
services/records/records_service/settings.py
services/records/requirements.lock
services/records/tests/test_database.py
tests/verify_infrastructure.py
```
