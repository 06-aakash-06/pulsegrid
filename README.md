# PulseGrid

PulseGrid is a single-hospital management prototype for the System Design Laboratory. Phase 5 adds reliable, asynchronous Pharmacy and Billing signals that wake Appointment's existing journey reconciler. Phase 6 extends the shared Redis admission component with Surge Mode and adds bounded resilience around optional Appointment journey snapshots. Patient management, doctor profiles and schedules, protected appointment booking, clinical records and prescriptions, pharmacy inventory and fulfillment, invoices and simulated payments, and emergency requests continue to use their owning APIs. Existing registration, login, session rotation, logout and CSRF protection are preserved.

See the [Phase 2 integration verification](docs/phase-2-integration-verification.md) for executed PostgreSQL, security, concurrency, HTTP and browser checks, and the [Phase 2 API contracts](docs/phase-2-api-contracts.md) for the compatible baseline interface. See [Phase 3 contracts](docs/phase-3-api-contracts.md) and [Phase 3 verification](docs/phase-3-integration-verification.md) for activated waitlists and temporary offers, QR check-in, consultation queues, patient journeys and staff/patient UI. Older architecture documents describe the broader target; their future algorithms and event workflows are not current implementation claims.

Uses synthetic data exclusively. This is an educational prototype, not a certified clinical or emergency-response platform. Payments and insurance fixtures/estimates are simulated; no real insurer integration.

## Phase 4 integration

All eight agent implementations are integrated locally. The opt-in Phase 4
configuration activates seven components in the existing owner services and
hospital pages. See [integration verification](docs/phase-4-integration-verification.md)
for executed evidence, limits and the completion verdict. Frozen
[component contracts](docs/phase-4-component-contracts.md),
[parallel plan](docs/phase-4-parallel-plan.md),
[benchmark plan](docs/phase-4-benchmark-plan.md) and
[preparation verification](docs/phase-4-preparation-verification.md) retain the
reviewed preparation baseline.

## Phase 5 event delivery

Pharmacy reservation dispenses and successful Billing payments publish from
their existing PostgreSQL outboxes to Appointment. Appointment deduplicates each
subscription in its inbox and asks its existing worker to fetch fresh owner
snapshots. No event changes inventory, money, access decisions or discharge
eligibility. See [Phase 5 contracts](docs/phase-5-event-contracts.md) and the
[Phase 5 verification report](docs/phase-5-integration-verification.md).

After `python3 infra/scripts/init-env.py`, start RabbitMQ and create its scoped
accounts before starting the service containers:

```sh
python3 infra/scripts/configure-rabbitmq-events.py
```

Then use the regular authenticated/Phase 4 Compose command below. RabbitMQ stays
private. APIs continue to commit local business transactions if the broker is
unavailable; the outbox workers retry publication in the background.

Private cache/admission configuration is initialized by
`python infra/phase4/init_config.py` (existing keys are retained). Add
`-f compose.phase4.yaml` after the existing Compose and auth files when building
and starting the existing project. Do not create a second retained stack or reset
volumes. Fixture providers are synthetic4101–4103/policyDEMO. Appointment/Billing
worker identities are explicitly bound to their owner/replica allocations.

## Phase 6 resilience

Surge Mode uses the existing shared admission Redis and server-assigned A/B/C
route classes. Manual control requires current `hospital_admin` authorization and
is audited by Appointment. Automatic activation remains disabled because current
metrics are process-local. Appointment's Records, Pharmacy, and Billing journey
snapshot reads use bounded GET retries, per-owner circuit breakers, pooled HTTP,
and two-request bulkheads. See the [Phase 6 design](docs/phase-6-resilience-design.md)
and [verification report](docs/phase-6-integration-verification.md) for actual
checks and limitations.

## Architecture

Seven independently deployable FastAPI services: Patient, Doctor, Appointment, Records, Pharmacy, Billing, and Emergency. Each owns a separate PostgreSQL logical database, migrations and runtime credentials. React/TypeScript provides patient and staff workspaces. Traefik routes versioned public APIs; authenticated internal REST APIs stay private. Redis supports existing Phase 4 components and Phase 6 Surge Mode. RabbitMQ carries only the selected Phase 5 events and does not gate API transactions.

PostgreSQL transactions and constraints enforce booking, inventory, payment and emergency claim correctness. Phase 2 cross-service workflows use bounded authenticated REST validation, explicit schedule reconciliation, durable clinical holds and manual charge imports. Phase 5 publishes two existing outbox transitions and uses Appointment's existing journey reconciliation as the safe asynchronous effect. Phase 7 adds private metrics and tracing collection, provisioned Grafana dashboards and alerts, and a role-protected Control Room. Phase 4 adds private cache/admission, hashing placement, additive IDs, short aliases, synthetic crawler and autocomplete; PostgreSQL remains business authority. Advanced journeys use authoritative owner snapshots and durable local polling, including exact charge-source validation before administrative discharge.

## Foundation documents

- [Architecture](docs/architecture.md): flows, resilience, consistency, scaling, algorithm integrations.
- [Service boundaries](docs/service-boundaries.md): responsibilities, ownership, dependencies.
- [Database design](docs/database-design.md): initial schema, keys, constraints and planned transactions.
- [API contracts](docs/api-contracts.md): versioned REST routes, schemas, authorization, failure semantics.
- [Event contracts](docs/event-contracts.md): event catalog, schemas, outbox, replay, dead letters.
- [Phase 5 event contracts](docs/phase-5-event-contracts.md): active event paths, ownership and delivery/recovery behavior.
- [Phase 5 integration verification](docs/phase-5-integration-verification.md): reliability and failure-recovery evidence.
- [Phase 7 observability design](docs/phase-7-observability-design.md): metrics, tracing, dashboards, alerts, security and resource limits.
- [Phase 7 integration verification](docs/phase-7-integration-verification.md): live workflow, outage, regression and configuration evidence.
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
python3 infra/scripts/configure-rabbitmq-events.py
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

The script creates private, ignored credentials; never commit `.env`. Provision the RabbitMQ event users as described above before starting the APIs. All seven migration jobs must exit 0 before their APIs start. Gateway: `http://127.0.0.1:8080`; example readiness: `/api/v1/patients/health/ready`. PostgreSQL is required for readiness. Redis supports existing Phase 4 features; the selected RabbitMQ workers reconnect independently and do not block API readiness or local commits.

```sh
cd frontend
npm ci
npm run dev -- --strictPort
```

Frontend: `http://127.0.0.1:5173`, with same-origin API requests proxied to the gateway. Stop infrastructure with `docker compose -f compose.yaml -f services/patient/compose.auth.yaml down` from the root; persistent volumes remain. See the [infrastructure runbook](docs/infrastructure.md) for configuration, logs, migrations, reset, tests, controlled failure checks and authentication prerequisites.

See [authentication integration](docs/authentication-integration.md) for CSRF, registration retry semantics, environment settings and verification. Phase 2–7 backend paths are integrated. Shared executable contract artifacts remain future work. Backend and frontend tests are colocated with their packages. No remote publication is authorized.

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
