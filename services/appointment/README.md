# PulseGrid Appointment Service

Independent FastAPI application for the **appointment** domain. Phase 2.3 implements the frozen [Phase 2 contract](../../docs/phase-2-api-contracts.md) under `/api/v1/appointments`. Appointment owns operational schedules and capacity; Doctor owns immutable schedule proposals.

## Run locally

From this directory, create an isolated environment, install the package and its test extra, then start the ASGI app:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
uvicorn appointment_service.main:app --host 127.0.0.1 --port 8000
```

Configuration is read from `PULSEGRID_APPOINTMENT_ENVIRONMENT` and `PULSEGRID_APPOINTMENT_LOG_LEVEL`. Defaults are `development` and `INFO`. Database configuration uses the same service prefix with `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` and pool/deadline settings. See [the infrastructure runbook](../../docs/infrastructure.md).

`GET /health/live` reports process liveness. `GET /health/ready` checks PostgreSQL with a bounded SELECT: 200 when connected, 503 when unconfigured/unavailable. Redis and RabbitMQ are not yet required. The same routes are exposed through the gateway under the domain API prefix.

This package owns `appointment_db`, `appointment_app` runtime credentials and an independent Alembic history. Compose runs `appointment-migrate` with the separate `appointment_migration` owner before starting the API. From the repository root, run `docker compose run --rm appointment-migrate` to apply outstanding revisions. Do not use runtime schema creation or another service's models/database.

Run the colocated tests with `python -m pytest`. Build an independent container from this directory with `docker build -t pulsegrid-appointment .`.

This is a synthetic educational prototype, not a clinical or emergency-response system.


## Implemented interfaces

Public routes:

- `POST /api/v1/appointments/schedule-decisions`: explicitly accept/reject a Doctor proposal; return a durable decision (201).
- `GET /api/v1/appointments/schedule-decisions/{proposal_id}`: scoped decision lookup.
- `GET /api/v1/appointments/availability?doctor_id=...&from=...&to=...`: unoccupied, future bookable slots; a hint, with accepted revision.
- `POST /api/v1/appointments`: patient self/receptionist booking (201).
- `GET /api/v1/appointments` and `GET /api/v1/appointments/{appointment_id}`: scoped retrieval; patient/doctor/state filters and stable bounded cursor pagination.
- `POST /api/v1/appointments/{appointment_id}/cancel` and `/reschedule`: patient self/receptionist commands, exact quoted `If-Match` required.

Private, service-authenticated leaves:

- Doctor: `GET /internal/v1/schedule-decisions/{proposal_id}` (`schedule-decisions:read`); `GET /internal/v1/doctors/{doctor_id}/operational-status` (`schedules:status`).
- Records: `GET /internal/v1/appointments/{appointment_id}/consultation-context` (`appointments:consultation-context`); `POST /internal/v1/appointments/{appointment_id}/clinical-hold` and `/clinical-hold/finalize` (`appointments:clinical-hold`).
- Billing: `GET /internal/v1/appointments/{appointment_id}/billing-context` (`appointments:billing-context`).

All private routes require the exact allowed caller/scope plus a verified delegated user JWT. Private leaves perform only local checks/audit; they never call Patient or Doctor. The initiating service must check current authority. No public actor headers or service-only clinical access. Public mutations and sensitive reads check current authority through the existing Patient protocol. The existing JWT verifier pins issuer/audience/RS256/key ownership and validates expiration. Patient ownership and the stored accepted doctor staff mapping constrain resource access; denied resource access returns 404. Receptionists manage appointment resources; admins manage schedule decisions, with no broad clinical context access. Public availability requires an authenticated token.

Every POST requires a printable 16..128-character idempotency key. Storage scope includes user (and private caller), POST, actual resource path and key; the digest includes the normalized body and If-Match. Replay follows current authorization and precedes stale-version rejection. Response JSON stores its original version, so replay returns the original ETag even after cancellation/finalization. Records remain retained indefinitely in this phase (at least the required 24 hours); there is no cleanup worker. All success responses use `Cache-Control: no-store`. Single-resource responses carry quoted version ETags. Unknown body/query fields and non-UTC times are rejected.

## Concurrency and transaction boundaries

READ COMMITTED is the PostgreSQL default and the intended isolation level. No cache or process lock enforces capacity. Commands acquire a PostgreSQL transaction advisory lock for their idempotency identity, then doctor snapshot rows in doctor-ID order, slots in slot-ID order, appointment rows, clinical hold, and finally the audit chain head. Schedule decisions initialize a missing snapshot under a per-doctor transaction advisory lock before locking that snapshot. Slot/appointment discovery is provisional; a changed source slot after rescheduling causes a complete transaction restart, never a reverse-order lock acquisition.

Booking locks the owning doctor snapshot and slot, validates accepted revision, future cutoff, bookable state and the validated remote staff mapping, then copies doctor/time/revision from that slot. The `ix_appointments_active_slot` partial unique index allows exactly one active appointment per slot. Migration `0003_booking` adds `btree_gist` and these half-open `[start,end)` GiST exclusions:

- `slots_doctor_overlap`: a doctor's nonretired slots cannot overlap.
- `appointments_patient_overlap`: a patient's confirmed/checked_in/in_consultation appointments cannot overlap across doctors. Adjacent intervals are valid.

A database trigger rejects inconsistent appointment slot copies on insert/move. Existing bookings retain their booking revision when a schedule decision updates the preserved slot to a newer accepted revision. Runtime endpoints expose only confirmed/cancelled states; the database retains legacy states for future compatibility. Cancelled cannot be resurrected by a state update.

Rescheduling locks both source/target doctors and slots in sorted order, then the appointment and hold, checks ETag/state and updates the same appointment ID in one transaction. A failed reservation, exclusion, stale version or audit/outbox failure rolls back the move, preserving the original slot/state/version. Cancellation changes confirmed to cancelled and releases the unique active reservation. A current-ETag repeated cancellation is a no-op without another event. No waitlist promotion occurs. Snapshot operational versions increment with booking/cancellation/moves so count changes invalidate their ETag.

Schedule acceptance locks the doctor and all affected local slots/bookings. It rejects removal/shift of confirmed intervals with durable conflicting appointment IDs and leaves accepted slots unchanged. It records every accepted/rejected proposal revision, rejects revision gaps and stale accepted-revision expectations, and atomically retires replacement slots, preserves matching slot IDs, creates new slots and records the decision. No booked interval can be silently removed by closure.

Clinical holds serialize with cancellation/rescheduling using exactly the same lock order. Acquisition binds one consultation ID, increments appointment version and blocks both booking changes. Finalization changes active to finalized and increments version once; repeated same-consultation acquisition/finalization is a no-op with current ETag. There is no timeout or public unlock for an orphan hold. Records must retry/reconcile its own durable prospective consultation ID; authorized coordinator review of absence is a later integration operation.

Business mutation, unpublished immutable event envelope, constrained ordered audit append and persisted success response commit in one local transaction. Audit uses a SECURITY DEFINER function with fixed search path, allowlisted bounded metadata, hashed reason, revoked PUBLIC execution and owning runtime grant. Runtime has read-only audit tables. PostgreSQL uniqueness/exclusion violations become 409 (`slot_occupied`/`patient_overlap`); deadlock/serialization SQLSTATEs and generated-ID collisions receive at most two retries, then 503. Lock/statement timeouts fail safely as 503 through the existing database handler. Each retry releases all previous locks via rollback and uses the same idempotency identity. Unsuccessful commands do not leave partial appointments, outbox rows, audit rows or success responses.

## Remote coordination and integration limits

Before booking/rescheduling transactions, Patient's status leaf validates the patient and Doctor's identity leaf validates the doctor. Schedule decision uses Doctor's exact proposal leaf. Signed service tokens plus delegated user tokens, request/correlation IDs and trace context accompany calls. No other service database is queried. New calls have a five-second aggregate dependency budget, one-second per-call bound and at most two safe read attempts with jitter. The existing authority helper retains its two-second bound; timeouts now report 504. Transport/5xx failures open a per-process circuit after five consecutive attempts with a probe after 15 seconds. Redirects, invalid/oversized (>256 KiB) schemas fail closed; 4xx is never retried. No production fixture fallback exists. Network calls finish before any command lock/transaction opens.

Remote authority/status can change immediately after validation; this is bounded validation, not a distributed transaction or instantaneous remote revocation. Local accepted schedules remain authoritative. Dependency failure prevents a new mutation; same-key retry after recovery returns the committed response or safely completes once. No remote schedule reconciliation occurs automatically. Doctor explicitly reads the durable decision and reconciles its own state. Outbox events remain unpublished; no RabbitMQ business producer/consumer, journey, waitlist, QR/check-in or consultation queue was added. Event payloads preserve existing catalog names with nullable Phase 2 journey references; new clinical-hold events contain only resource ID/version/state. Shared schemas and broker activation belong to the integrator/later phases.

**Frozen-contract gap:** when no local doctor snapshot exists, the operational-status leaf has no trusted staff mapping to authorize an own-doctor caller. A Doctor callback is forbidden for a leaf, and user JWTs contain no doctor ID. This implementation returns 404 for that own-doctor case, while an admin receives the documented zero counts/version 1. The integrator must approve a trusted mapping preparation contract or require an initial admin decision before own-doctor deactivation; the service does not invent a mapping or trust a raw header.

Live multi-service/gateway integration was not run: Patient status and Doctor proposal/identity implementations and shared deployment wiring are outside this worktree's ownership. Tests explicitly fixture those frozen APIs. Shared development databases, Compose topology and auth keys were untouched. Migration backfills doctor assignment only from existing owned snapshots; missing mappings or pre-existing interval conflicts fail migration instead of fabricating data. The migration owner must have permission to install `btree_gist`/`pgcrypto`. Do not deploy through the runtime role.

## Verification

Run from the repository root:

```sh
services/appointment/.venv/bin/python -m pytest services/appointment/tests
services/appointment/.venv/bin/python -m compileall -q services/appointment/appointment_service services/appointment/migrations services/appointment/tests
```

The PostgreSQL fixture starts a separate temporary cluster on a dynamically allocated loopback port, with no Unix socket, and creates a random database for each test. It applies the real Alembic chain and uses `appointment_app` for application transactions, with audit writes/DDL denied. It stops/removes its own cluster and never loads shared DB credentials or connects to an existing instance. `initdb`, `pg_ctl` and PostgreSQL extensions must be available; missing PostgreSQL is a reported blocker/skip, not concurrency proof. Generated database files stay within the ignored service-local `.test-runtime/` directory. External authorization/owner responses are test-only fixtures, while user/service JWT signature and scope verification execute normally in HTTP tests.

The service-local [verification record](PHASE_2_3_VERIFICATION.md) lists executed results and skipped integration checks. No throughput, latency, availability, clinical or broker-delivery claims are made.

## Phase 3.1A shared framework

The G0 [framework handoff](FRAMEWORK_HANDOFF.md) supplies disabled feature
registration, shared workflow storage/locks and deferred command effects.
The migration head is `0004_phase3_core`; future 0005–0008 revisions require
feature manifest handoffs. Existing Phase 2 APIs remain active; no new feature
endpoint or automatic enrollment is enabled. See [verification](PHASE_3_1A_VERIFICATION.md).
