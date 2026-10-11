# PulseGrid

PulseGrid is a single-hospital management prototype for the System Design Laboratory. Phase 3 integrates the advanced hospital workflows on main, preserving the Phase 2 domain/frontend foundation. Patient management, doctor profiles and schedules, protected appointment booking, clinical records and prescriptions, pharmacy inventory and fulfillment, invoices and simulated payments, and emergency requests now use real owner APIs. Existing registration, login, session rotation, logout and CSRF protection are preserved.

See the [Phase 2 integration verification](docs/phase-2-integration-verification.md) for executed PostgreSQL, security, concurrency, HTTP and browser checks, and the [Phase 2 API contracts](docs/phase-2-api-contracts.md) for the compatible baseline interface. See [Phase 3 contracts](docs/phase-3-api-contracts.md) and [Phase 3 verification](docs/phase-3-integration-verification.md) for activated waitlists and temporary offers, QR check-in, consultation queues, patient journeys and staff/patient UI. Older architecture documents describe the broader target; their future algorithms and event workflows are not current implementation claims.

Uses synthetic data exclusively. This is an educational prototype, not a certified clinical or emergency-response platform. Payments are simulated; insurance functionality is deferred.

## Architecture

Seven independently deployable FastAPI services: Patient, Doctor, Appointment, Records, Pharmacy, Billing, and Emergency. Each owns a separate PostgreSQL logical database, migrations and runtime credentials. React/TypeScript provides patient and staff workspaces. Traefik routes versioned public APIs; authenticated internal REST APIs stay private. The existing Docker Compose deployment also runs Redis and RabbitMQ, which are not yet business workflow dependencies.

PostgreSQL transactions and constraints enforce booking, inventory, payment and emergency claim correctness. Phase 2 cross-service workflows use bounded authenticated REST validation, explicit schedule reconciliation, durable clinical holds and manual charge imports. Audit chains and unpublished outbox rows persist locally. Broker publication/consumption, distributed caches, telemetry deployment, control room and Phase 4 algorithm components remain future work. Advanced journeys use authoritative owner snapshots and durable local polling, including exact charge-source validation before administrative discharge.

## Foundation documents

- [Architecture](docs/architecture.md): flows, resilience, consistency, scaling, algorithm integrations.
- [Service boundaries](docs/service-boundaries.md): responsibilities, ownership, dependencies.
- [Database design](docs/database-design.md): initial schema, keys, constraints and planned transactions.
- [API contracts](docs/api-contracts.md): versioned REST routes, schemas, authorization, failure semantics.
- [Event contracts](docs/event-contracts.md): event catalog, schemas, outbox, replay, dead letters.
- [Security](docs/security.md): identity, authorization, sensitive operations, privacy.
- [Local infrastructure](docs/infrastructure.md): startup, database isolation, migrations, gateway, tests and limits.
- [Roadmap](docs/development-roadmap.md): nine phases and acceptance gates.
- [Agent instructions](AGENTS.md): durable repository and parallel-work rules.

## Current layout

```text
PulseGrid/
  README.md
  AGENTS.md
  .gitignore
  docs/                         # architecture, contracts and development runbooks
  services/                     # seven independent FastAPI packages and migration histories
    patient/ doctor/ appointment/ records/ pharmacy/ billing/ emergency/
  frontend/                     # React/TypeScript hospital workflows and deferred route shells
  contracts/                    # future: reviewed OpenAPI and event JSON schemas
  infra/                        # Compose database bootstrap, Traefik and credential generation
  tests/                        # isolated backend suites and live infrastructure/auth/hospital verification
  experiments/                  # future: Locust, chaos, algorithm benchmarks
```

## Local development

With Docker running, from this directory:

```sh
python3 infra/scripts/init-env.py
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e 'services/patient[test]'
python services/patient/generate_auth_keys.py --directory secrets/auth
# Add services/patient/auth.env.example settings to the ignored root .env.
# Do not overwrite existing DB credentials or regenerate existing keys.
docker compose -f compose.yaml -f services/patient/compose.auth.yaml config --quiet
# Build each domain separately on small Docker VMs; migration jobs share these images.
for domain in patient doctor appointment records pharmacy billing emergency; do
  docker compose -f compose.yaml -f services/patient/compose.auth.yaml build "$domain" || exit 1
done
docker compose -f compose.yaml -f services/patient/compose.auth.yaml up -d --no-build
```

The script creates private, ignored credentials; never commit `.env`. All seven migration jobs must exit 0 before their APIs start. Gateway: `http://127.0.0.1:8080`; example readiness: `/api/v1/patients/health/ready`. PostgreSQL is required for readiness; Redis and RabbitMQ are not yet application dependencies.

```sh
cd frontend
npm ci
npm run dev -- --strictPort
```

Frontend: `http://127.0.0.1:5173`, with same-origin API requests proxied to the gateway. Stop infrastructure with `docker compose -f compose.yaml -f services/patient/compose.auth.yaml down` from the root; persistent volumes remain. See the [infrastructure runbook](docs/infrastructure.md) for configuration, logs, migrations, reset, tests, controlled failure checks and authentication prerequisites.

See [authentication integration](docs/authentication-integration.md) for CSRF, registration retry semantics, environment settings and verification. Phase 2 business routes are integrated. Shared executable contract artifacts and telemetry infrastructure remain future work. Backend and frontend tests are colocated with their packages. No remote publication is authorized.

## Hospital workflow verification

Install the seven service test extras in one local test environment, with local PostgreSQL `initdb` and `pg_ctl` on PATH. Run `python tests/run_phase2_regressions.py` from the root. It uses disposable service databases, including Patient authentication and Records/Appointment isolated clusters; it never truncates the Compose databases. Ignored development auth keys must already exist for the retained Patient authentication tests. Run frontend typecheck, test and build commands from `frontend/`.

With the existing authenticated Compose stack running, `python tests/verify_phase2_infrastructure.py` checks live migration heads, owned schemas, audit chains, database isolation, gateway routing and frozen endpoint presence without resetting data. `python tests/verify_authentication.py` exercises real authentication through Traefik; `--base-url http://127.0.0.1:5173` checks the frontend proxy. The hospital workflow verifier's operator bootstrap and private resume fixture are explained in the verification report. Synthetic test identities and audit history are retained.

## Development conventions

Python uses `snake_case`, TypeScript uses `camelCase` and PascalCase components. Service directories are singular lowercase names. Wire fields use `snake_case`; IDs are decimal strings. APIs start at `/api/v1/<domain>`. UTC timestamps use RFC 3339. Documentation and contracts precede implementation, and verification reports distinguish planned checks from executed checks.

Phase 3 verification reuses the disposable backend runner and read-only owner
schema/isolation checks. `python tests/verify_phase3_infrastructure.py` additionally
checks reviewed active routes and private-leaf protection. `tests/verify_phase3.py`
executes the six synthetic gateway workflows against the existing deployment,
including a bounded Billing outage with mandatory restoration; it requires the
existing private operator fixture described in the report. Supplemental
`tests/verify_phase3_security.py` uses a separate private fixture for QR races,
revocation and dispensing-history safety. Never run these writers concurrently
against a shared fixture or use real patient data. Browser camera hardware is
not certified or validated; QR encode/decode and manual/browser workflows are
covered as described in the report.
