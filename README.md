# PulseGrid

Surge-aware, fault-tolerant hospital management system for the System Design Laboratory. Phase 1.4C-C integrates patient authentication with the React frontend. PostgreSQL, service-owned migrations, Redis, RabbitMQ and Traefik support the seven FastAPI foundations. The UI provides registration, login, rotating session restoration and protected workspace shells. Hospital domain workflows remain unimplemented.

Uses synthetic data exclusively. This is an educational prototype, not a certified clinical or emergency-response platform. Payments and insurance providers are simulated.

## Architecture

Seven independently deployable FastAPI services: Patient, Doctor, Appointment, Records, Pharmacy, Billing, and Emergency. Each owns a separate PostgreSQL logical database. React/TypeScript provides patient and staff interfaces plus a restricted distributed systems control room. Traefik routes versioned APIs. Redis accelerates lookups and admission decisions; RabbitMQ carries durable outbox events. Prometheus, Grafana, and OpenTelemetry provide observability; Locust provides reproducible load experiments. Docker Compose is the prototype deployment target.

PostgreSQL transactions and constraints enforce booking, inventory, and payment correctness. Cross-service workflows use idempotent events, explicit pending states, reconciliation, and compensations rather than distributed database transactions.

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
  frontend/                     # React/TypeScript patient, staff, and ops shells
  contracts/                    # future: reviewed OpenAPI and event JSON schemas
  infra/                        # Compose database bootstrap, Traefik and credential generation
  tests/                        # real infrastructure and authentication HTTP verification
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

See [authentication integration](docs/authentication-integration.md) for CSRF, registration retry semantics, environment settings and verification. Service business routes, executable contract snapshots and telemetry infrastructure remain future work. Backend and frontend tests are colocated with their packages. No remote publication is authorized.

## Development conventions

Python uses `snake_case`, TypeScript uses `camelCase` and PascalCase components. Service directories are singular lowercase names. Wire fields use `snake_case`; IDs are decimal strings. APIs start at `/api/v1/<domain>`. UTC timestamps use RFC 3339. Documentation and contracts precede implementation, and verification reports distinguish planned checks from executed checks.
