# PulseGrid

Surge-aware, fault-tolerant hospital management system for the System Design Laboratory. **Phase 1.1 is a documentation-only foundation.** No services, algorithms, containers, schemas, dependencies, or UI have been implemented or tested at runtime.

Uses synthetic data exclusively. This is an educational prototype, not a certified clinical or emergency-response platform. Payments and insurance providers are simulated.

## Architecture

Seven independently deployable FastAPI services: Patient, Doctor, Appointment, Records, Pharmacy, Billing, and Emergency. Each owns a separate PostgreSQL logical database. React/TypeScript provides patient and staff interfaces plus a restricted distributed systems control room. Traefik routes versioned APIs. Redis accelerates lookups and admission decisions; RabbitMQ carries durable outbox events. Prometheus, Grafana, and OpenTelemetry provide observability; Locust provides reproducible load experiments. Docker Compose is the prototype deployment target.

PostgreSQL transactions and constraints enforce booking, inventory, and payment correctness. Cross-service workflows use idempotent events, explicit pending states, reconciliation, and compensations rather than distributed database transactions.

## Foundation documents

- [Architecture](docs/architecture.md): flows, resilience, consistency, scaling, algorithm integrations.
- [Service boundaries](docs/service-boundaries.md): responsibilities, ownership, dependencies.
- [Database design](docs/database-design.md): proposed models, keys, constraints, transactions.
- [API contracts](docs/api-contracts.md): versioned REST routes, schemas, authorization, failure semantics.
- [Event contracts](docs/event-contracts.md): event catalog, schemas, outbox, replay, dead letters.
- [Security](docs/security.md): identity, authorization, sensitive operations, privacy.
- [Roadmap](docs/development-roadmap.md): nine phases and acceptance gates.
- [Agent instructions](AGENTS.md): durable repository and parallel-work rules.

## Planned layout

```text
PulseGrid/
  README.md
  AGENTS.md
  .gitignore
  docs/                         # implemented documentation only
  services/                     # future: seven independently packaged services
    patient/ doctor/ appointment/ records/ pharmacy/ billing/ emergency/
  frontend/                     # future: React/TypeScript, control room routes
  contracts/                    # future: reviewed OpenAPI and event JSON schemas
  infra/                        # future: Compose, Traefik, broker, monitoring config
  tests/                        # future: cross-service contract/integration tests
  experiments/                  # future: Locust, chaos, algorithm benchmarks
```

Only root foundation files and `docs/` exist in Phase 1.1. Do not run installation or container commands for this phase. Follow [the roadmap](docs/development-roadmap.md) for subsequent work; no remote publication is configured or authorized.

## Development conventions

Python uses `snake_case`, TypeScript uses `camelCase` and PascalCase components. Service directories are singular lowercase names. Wire fields use `snake_case`; IDs are decimal strings. APIs start at `/api/v1/<domain>`. UTC timestamps use RFC 3339. Documentation and contracts precede implementation, and verification reports distinguish planned checks from executed checks.
