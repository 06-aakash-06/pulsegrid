# PulseGrid Emergency Service

Independent FastAPI service for synthetic emergency-request workflow management. It is an educational prototype, not a real emergency dispatch, medical triage, or clinical service. Requests do not allocate beds or trigger dispatch. Phase 6 assigns Emergency request and staff lifecycle routes a protected finite admission class through the existing limiter; it does not create public priority escalation.

## API

All business routes use the existing Patient-issued Bearer access token and the `/api/v1/emergencies` prefix.

| Method and path | Purpose | Access |
|---|---|---|
| `POST /api/v1/emergencies` | Submit a request | Current patient self; validates Patient status |
| `GET /api/v1/emergencies` | List and filter requests | Current patient self or current emergency staff |
| `GET /api/v1/emergencies/{request_id}` | Track one request | Owner or current emergency staff |
| `GET /api/v1/emergencies/{request_id}/history` | Paginated lifecycle history | Owner or current emergency staff; reason and actor fields are staff-only |
| `PATCH /api/v1/emergencies/{request_id}/priority` | Assign severity 1–5, where 1 is highest | Current emergency staff; requires `If-Match` |
| `POST /api/v1/emergencies/{request_id}/claim` | Claim work for the current staff member | Current emergency staff; requires `If-Match` and `Idempotency-Key` |
| `POST /api/v1/emergencies/{request_id}/release` | Release the caller's active claim | Current claiming staff; requires `If-Match` and `Idempotency-Key` |
| `POST /api/v1/emergencies/{request_id}/transitions` | Start processing, resolve, or cancel | Current claiming staff for processing/resolution; owner or current emergency staff for cancellation; requires `If-Match` and `Idempotency-Key` |

List and history pages use `limit` from 1 to 100, default 20, stable ascending `(timestamp,id)` ordering, and opaque cursors bound to the normalized filters and caller. Patient views contain request status and reported urgency only. Current emergency staff can see the submitted description, synthetic contact, claim, and staff history reasons. All request and history reads are audited before data is returned and use `Cache-Control: no-store`.

`reported_urgency` is patient-provided advisory information. It never sets `assigned_priority`. Only a currently authorized `emergency_staff` user can assign priority or claim a request. A claim belongs to the caller, has a 15-minute lease, and uses a row lock so competing staff claims serialize. Processing claims retain their staff owner without expiring automatically.

Valid state changes are:

```text
submitted --staff assigns priority--> triaged
triaged --staff claims--> claimed --claiming staff starts--> processing --claiming staff resolves--> resolved
claimed --claiming staff releases--> triaged
submitted/triaged --patient owner or staff cancels--> cancelled
claimed --staff cancels--> cancelled
```

Resolved and cancelled are terminal. Invalid edges return 409. A claim or transition command that finds an expired claim records `claimed -> triaged` and returns a persisted `claim_expired` conflict when processing the expired claim. Claiming can then be retried against the current version. GET requests never normalize expired claims.

The `/history` route exposes persisted status history for the service requirement; it is an additive service-owned route beyond the frozen Phase 2 route table. Patient history omits internal reasons and actor IDs.

## Patient Service interaction

Emergency never reads Patient's database. Before each privileged operation and sensitive read, it calls Patient's existing private `POST /internal/v1/authorization/check` using a short-lived service JWT plus the delegated user token. On request submission, it also calls the documented private `GET /internal/v1/patients/{patient_id}/status` with scope `patients:status` and the delegated token. A missing or inactive patient reference is rejected; Patient outage prevents submission. Calls use private service DNS, bounded timeouts, no redirects or environment proxy, and carry request, correlation, and trace context.

The Patient status route is part of the frozen Phase 2 private contract. It is not yet implemented in the Patient package at the Phase 2.7 base commit, so submission remains unavailable until that Patient-owned route is delivered. Staff authorization uses the existing Phase 1 Patient authority protocol.

## Persistence and limits

Emergency owns its request rows and references Patient IDs without a cross-database foreign key. A state or priority mutation, immutable history row, status outbox event, hash-chained audit append, and POST replay response share one PostgreSQL transaction. Audit writes use a constrained SECURITY DEFINER append function; the runtime role has no direct audit-table mutation rights. Events remain in the local outbox; Phase 2 does not publish to RabbitMQ. Status and submission events omit descriptions, contact values, and reasons.

Phase 2 IDs use positive CSPRNG BIGINT candidates with three bounded local collision checks and database primary keys as the final uniqueness backstop. The retained worker-state schema/configuration is unused; custom Snowflake generation is deferred. The 15-minute claim lease, 24-hour idempotency retention, retry limits, and service deadlines are prototype contract settings, not measured operational targets.

Anonymous tracking tokens, clinical triage, dispatch, ambulance coordination, emergency bed management, telemetry dashboards, and production/clinical validation are not implemented.

## Local development and tests

From this directory, create an isolated environment, install the package and test extra, then start the ASGI app:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
uvicorn emergency_service.main:app --host 127.0.0.1 --port 8000
```

Database configuration uses `PULSEGRID_EMERGENCY_DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, and pool/deadline settings. Apply owned migrations with migration-owner credentials before starting the service. Run package tests with `python -m pytest`.

PostgreSQL workflow integration tests require `PULSEGRID_EMERGENCY_TEST_DATABASE_URL` to point to a dedicated database whose name ends in `_test`. Tests use synthetic identities and are skipped when that explicit isolated resource is not configured. The database must already be migrated to `0003_emergency_workflow`; the test URL must have permission to use the service tables and `append_emergency_audit` function. Never point it at a development or production service database.

This package owns `emergency_db`, `emergency_app` runtime credentials and an independent Alembic history. See [the infrastructure runbook](../../docs/infrastructure.md) for the Compose deployment and database ownership model.
