# Local infrastructure: Phase 1.4B, authentication, and Phase 5

Phase 4.0 was a documentation-only preparation step. Its
[component contract freeze](phase-4-component-contracts.md) and
[parallel plan](phase-4-parallel-plan.md) record the reviewed scope and
ownership; the preparation itself did not activate components. The separately
implemented Phase 4 features are summarized in the [README](../README.md) and
[Phase 4 verification](phase-4-integration-verification.md). Phase 2/3
contracts and actual owner code remain authoritative for existing hospital
workflows.

Implemented for synthetic development: one PostgreSQL 16 instance, seven owned databases, Redis 7, RabbitMQ 4, Traefik 3 and seven FastAPI processes. Each service has its own SQLAlchemy metadata, connection pool, session dependency, Dockerfile and Alembic history. Patient authentication is implemented using the service-owned auth overlay. Phase 5 activates two background outbox publishers and one Appointment consumer in the existing services; no worker container is added. For current launch commands use [README](../README.md) and [authentication integration](authentication-integration.md); the plain Compose commands below describe the unauthenticated infrastructure foundation. The frontend remains an independent Vite application.

## Start and stop

Prerequisites: Docker with a running daemon and Compose v2 or later, Python 3 for the credential/verification scripts, and Node/npm for the frontend. Run from the repository root:

```sh
python3 infra/scripts/init-env.py
python3 infra/scripts/configure-rabbitmq-events.py
docker compose config --quiet
docker compose up -d --build
docker compose ps -a
python3 tests/verify_infrastructure.py
```

The generator creates an ignored `.env` with random local passwords and mode 0600. It refuses to overwrite an existing file. Alternatively copy `.env.example` to `.env` and fill every password with a separate random value. Examples contain no credentials. Never attach `.env`, resolved Compose configuration, container environment dumps or raw database errors to reports: they can contain secrets. `configure-rabbitmq-events.py` starts the existing RabbitMQ service, waits for its health, creates separate non-administrator publisher and consumer users with resource-scoped permissions, and keeps their credentials in the ignored `.env`. `docker compose config --quiet` validates without printing the resolved configuration.

Startup waits for PostgreSQL health, runs each `*-migrate` job to completion, then starts its API. Migration jobs **exiting with code 0** are expected. Health checks take a few seconds to settle. PostgreSQL, Redis and RabbitMQ persist in named volumes; only Traefik publishes a host port, on loopback. The event workers reconnect if RabbitMQ is unavailable; the service APIs remain available and business transactions stay in their owner database outboxes.

```sh
docker compose logs --tail=100 patient patient-migrate postgres traefik
docker compose stop
docker compose up -d
docker compose down
```

`stop` preserves containers and volumes; `down` removes containers/networks while preserving volumes. To deliberately erase all synthetic development data, use `docker compose down --volumes`, then the startup commands. This destructive reset was not used in the outage verification. Changing `.env` does not automatically rotate passwords inside existing volumes. For PostgreSQL, recreate its container to load the new environment, rerun the bootstrap script below, then recreate API/migration containers. Redis requires container recreation; existing RabbitMQ users require deliberate credential rotation through RabbitMQ administration. Do not assume default-user initialization reruns on an existing broker volume.

## Database ownership and credentials

| Domain | Logical database | Runtime role | Migration owner | Initial tables, excluding Alembic |
|---|---|---|---|---:|
| Patient | `patient_db` | `patient_app` | `patient_migration` | 10 |
| Doctor | `doctor_db` | `doctor_app` | `doctor_migration` | 12 |
| Appointment | `appointment_db` | `appointment_app` | `appointment_migration` | 17 |
| Records | `records_db` | `records_app` | `records_migration` | 11 |
| Pharmacy | `pharmacy_db` | `pharmacy_app` | `pharmacy_migration` | 15 |
| Billing | `billing_db` | `billing_app` | `billing_migration` | 15 |
| Emergency | `emergency_db` | `emergency_app` | `emergency_migration` | 8 |

The task's `<domain>_db` names replace Phase 1.1's illustrative `pulsegrid_<domain>` names; ownership and external IDs do not change. PostgreSQL's bootstrap superuser is confined to initialization/administration. Neither API nor migration jobs use it. All fourteen service roles lack superuser, database creation, role creation and replication privileges. PUBLIC connection/temp rights are revoked across databases. Each role receives CONNECT only to its owned database. Runtime roles have schema USAGE and ordinary table DML, without schema CREATE, database TEMP, table ownership, TRUNCATE or migration ownership. No extension permitting cross-database access is installed. Doctor alone installs trusted `btree_gist` for its documented interval exclusion.

Runtime roles can SELECT, but cannot INSERT/UPDATE/DELETE/TRUNCATE audit tables or Alembic metadata. The later audit workflow must introduce a reviewed constrained append function and chain-head locking before mutations need auditing. This phase provides storage and prevents accidental audit rewriting; it does not implement the audit algorithm. Migration owners remain trusted administrators of their own schema.

PostgreSQL's entrypoint initializes a new volume. Bootstrap is also safe to rerun without dropping data:

```sh
docker compose exec -T postgres sh /docker-entrypoint-initdb.d/01-databases.sh
```

It reconciles owned roles/passwords, creates missing databases and applies grants/default privileges. Run it with the intended credential environment, and retain migration-owned schema names. No fixture data is retained; verification transactions roll back their small infrastructure/constraint checks.

## Connections and sessions

FastAPI uses SQLAlchemy 2 async engines and async sessions with Psycopg 3. Alembic uses Psycopg's synchronous connection through a short-lived SQLAlchemy `NullPool`; it is a separate process using migration-owner credentials. This keeps request I/O asynchronous without creating shared runtime domain code. See [SQLAlchemy's async API](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) and [PostgreSQL privilege semantics](https://www.postgresql.org/docs/16/ddl-priv.html).

Every package reads `PULSEGRID_<DOMAIN>_DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` with that same prefix. Compose supplies only the owning service's runtime password to its API; only the migration job receives that domain's migration password. Password-safe SQLAlchemy URLs avoid string interpolation and escape special characters. Partial/invalid configuration fails explicitly; entirely unconfigured local scaffolds still start and report not ready.

| Setting, after service prefix | Default | Purpose |
|---|---:|---|
| `DB_PORT` | 5432 | PostgreSQL TCP port |
| `DB_POOL_SIZE` | 3 | Persistent connections per API process |
| `DB_MAX_OVERFLOW` | 2 | Maximum extra connections per process |
| `DB_POOL_TIMEOUT` | 2 s | Wait for a pooled connection |
| `DB_CONNECT_TIMEOUT` | 2 s | Driver connection deadline |
| `DB_STATEMENT_TIMEOUT_MS` | 2000 ms | PostgreSQL query deadline |
| `DB_HEALTH_TIMEOUT` | 3 s | Whole readiness-check deadline |

Connection pre-ping and 300 s recycling handle stale connections. PostgreSQL lock timeout is 1 s; session timezone is UTC. The seven single-process APIs can open at most 35 connections; scaling requires revisiting the PostgreSQL budget. Startup creates pools lazily; shutdown disposes them. Request sessions close and roll back uncommitted work. Future commands must explicitly manage their local transaction and commit business changes, outbox, audit and idempotency together. Infrastructure exceptions return a sanitized 503 envelope. Future domain integrity conflicts need specific 409 handling rather than this generic dependency handler.

## Schema and migrations

Each `services/<domain>/migrations/versions/0001_initial.py` contains frozen initial DDL. Current metadata is in that service's `models.py`; historical migrations do not import mutable metadata. There is no runtime `create_all()`. IDs are nonnegative BIGINTs without database sequence generation. Timestamps use timezone-aware PostgreSQL types. Local FKs use RESTRICT; external IDs have no FKs. Documented uniqueness, partial uniqueness, indexes, quantity/money bounds and explicit state enums are included. All six common infrastructure tables exist in every database, without worker logic.

Every service additionally owns an explicit-worker revision that removes the accidental SERIAL worker default from the initial SQL and preserves existing worker-state rows. Final worker IDs are explicitly assigned, with no sequences; the Snowflake algorithm is still deferred. Doctor also owns `0002_schedule_exclusion`, enforcing nonoverlapping intervals within one proposal. Appointment does not install this extension yet. Each migration applies transactionally and Alembic records the completed revision. Repeat `upgrade head` is a no-op. From the root:

```sh
docker compose run --rm patient-migrate
docker compose run --rm patient-migrate alembic current
docker compose run --rm patient-migrate alembic check
```

Replace `patient` with another domain. `alembic check` checks metadata drift. For future schema work, generate/review a **new** service-owned revision; do not edit applied initial revisions. Downgrade removes owned tables and is destructive; this task did not run downgrade against persistent data. Changing bootstrap alone does not migrate an existing schema.

### Decisions and deferred invariants

The source documents list abbreviated entities rather than complete storage types. Initial DDL resolves these details without inventing operations:

- Patient refresh families include `family_expires_at` for security's absolute lifetime and a session expiry bound. Password/token columns store hashes; no password hashing or token issue logic exists yet.
- Records stores documented consultation `clinical_content` and immutable medical-record `revision` from API/service contracts. Clinical content and external snapshots use JSONB without invented clinical fields.
- Pharmacy retains both display `name` from its API and `normalized_name` from database design. Billing payments retain API `currency`; runtime currency equality with invoice is a later transactional invariant.
- Waitlist `skip_reason` preserves the explicitly required rejected-candidate explanation. Optional dates/contact/revocation/acknowledgement/error fields allow documented pending or absent values.
- Explicitly documented state enums have CHECKs. Undefined status vocabularies remain bounded strings pending a reviewed workflow contract; initial migrations do not silently invent enums.
- The existing Appointment database design explicitly defers its `btree_gist` exclusions to a later migration. Appointment slot and patient-booking overlap exclusions are therefore reserved for that reviewed migration before booking commands. Doctor has no such deferral; its own database enforces the documented per-proposal interval exclusion now. Initial interval bounds and partial slot/queue uniqueness **do not prove overlap safety**. Slot-copy consistency triggers, state transitions, normalized Doctor search policy, immutable clinical/financial write enforcement, Snowflake allocation, audit append functions and transactional algorithms also remain later work. No commands using those incomplete invariants are exposed.
- `updated_at` has an insertion default; future writers must update it and versions explicitly. A readiness SELECT proves connectivity, not business correctness or every future schema requirement.

## Gateway and frontend

Traefik uses the file provider with container DNS discovery, no Docker socket, no path stripping and no public administrative API. The API gateway is `http://127.0.0.1:8080` by default (`GATEWAY_PORT` in root `.env`). Its path rules match an exact prefix or prefix followed by `/`, preventing collisions such as `patients-extra`.

| Paths | Destination |
|---|---|
| `/api/v1/patients`, `/api/v1/auth` and descendants | Patient |
| `/api/v1/doctors` and descendants | Doctor |
| `/api/v1/appointments` and descendants; `/s/…` | Appointment |
| `/api/v1/records` and descendants | Records |
| `/api/v1/pharmacy` and descendants | Pharmacy |
| `/api/v1/billing` and descendants | Billing |
| `/api/v1/emergencies` and descendants | Emergency |

Auth routes operate when the auth overlay and keys are configured. Short-link routes remain reserved and return the owning application's safe 404 envelope. Service-local `/health/live` and `/health/ready` remain available inside containers. Additive gateway aliases are `<domain-prefix>/health/live` and `<domain-prefix>/health/ready`. No `/internal/v1`, `/docs`, `/metrics` or dashboard routes are exposed by the gateway. Traefik ping uses a private health entrypoint. Redis/RabbitMQ have no published ports and live on private networks; Appointment, Pharmacy and Billing join the existing RabbitMQ backbone for the selected Phase 5 event paths.

Traefik rejects aliased header names and ignores untrusted incoming forwarded headers, following its [entrypoint configuration](https://doc.traefik.io/traefik/routing/entrypoints/). Uvicorn trusts proxy headers only from Traefik's configured IP (`GATEWAY_IP` inside `EDGE_SUBNET`). Change both together if the subnet conflicts locally. Gateway/API access logs are disabled so future opaque token paths are not automatically logged. This is loopback HTTP development only, with no TLS or production authentication policy.

Frontend development:

```sh
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

Open `http://127.0.0.1:5173`. `VITE_API_BASE_URL` defaults to the current origin. Vite proxies `/api` and `/s/` to `PULSEGRID_GATEWAY_URL` (default `http://127.0.0.1:8080`). That variable is server configuration and is not a browser secret. Override it in `frontend/.env.local` if the gateway port changes. Same-origin proxying avoids a permissive CORS policy. A production frontend host must likewise proxy those paths, or implement a reviewed separate-origin CORS/cookie policy later; Vite's production build does not start a gateway.

Authentication now uses the Patient-owned overlay `services/patient/compose.auth.yaml`. See [the authentication runbook](authentication-integration.md) for exact origins, keys, secure cookie exceptions, CSRF delivery and real browser checks. The original infrastructure verifier has empty-foundation assumptions, including reserved auth routes and audit grants; it must not be treated as an authentication-stack verifier. The new HTTP verifier and Patient PostgreSQL tests cover the integrated auth stack.

## Verification commands

Backend regression tests (from root, Python 3.12+):

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e 'services/patient[test]' -e 'services/doctor[test]' -e 'services/appointment[test]' -e 'services/records[test]' -e 'services/pharmacy[test]' -e 'services/billing[test]' -e 'services/emergency[test]'
python -m pytest --import-mode=importlib services -q
python3 tests/verify_infrastructure.py
python3 tests/verify_infrastructure.py --failure --shutdown
```

The infrastructure verifier requires the **empty synthetic foundation databases**. It checks actual types/nullability, keys/FKs/checks/indexes, runtime privileges, SELECTs, session rollback/cleanup, Doctor interval exclusion with rolled-back fixtures, all 42 cross-domain connection denials, fourteen role ownership grants, gateway aliases/reserved paths/collisions and hidden administration. `--failure` stops only this Compose project's PostgreSQL, checks seven 503 readiness/200 liveness responses, then restores PostgreSQL in `finally` and waits for recovery. `--shutdown` additionally stops/restarts the seven API containers, verifies their shutdown logs and normal SIGTERM exits (143), then checks recovery. Both preserve volumes. Do not run this controlled outage against shared or nondevelopment environments. Later seeded/business tests need their own scoped verifier.

```sh
curl -fsS http://127.0.0.1:8080/api/v1/patients/health/live
curl -fsS http://127.0.0.1:8080/api/v1/patients/health/ready
cd frontend
npm run typecheck
npm test
npm run build
```

## Limits

One host and PostgreSQL instance are correlated failure points. Volumes are persistence, not backups; restore/HA/performance have not been evaluated. Redis and RabbitMQ support selected application workflows but do not own business truth. Application image bases and infrastructure images are pinned by digest; per-service runtime requirements are pinned to verified versions, without cross-service runtime packages. Updates must be reviewed and retested deliberately. Compose environment credentials are a local convenience, not a production secret manager. Telemetry collectors, production TLS/CORS, rate limiting and all other hospital workflows remain outside this phase.
