# PulseGrid Pharmacy Service

## Phase 3 G1 fulfillment view

The public `GET /prescriptions/{prescription_id}/fulfillment` revalidates the
minimum Records context before returning patient or pharmacist status. The
private `GET /internal/v1/appointments/{appointment_id}/workflow-snapshot`
serves a bounded local projection to Appointment under its new service scope;
it does not call Records. PostgreSQL triggers advance the local episode
revision with prescription snapshot, reservation and dispensing changes.

Revocation with committed dispensing sets `review_required`. A revoked
prescription's active reservations still need the existing pharmacist
revalidation command to release stock. Records revocation and Pharmacy dispense
cannot commit atomically across services; later revalidation/reconciliation
detects a mismatch. Only committed dispensing item IDs are Billing charge
sources. The integrator must wire the new private scope before activation.

Phase 2 pharmacy operations for the synthetic educational prototype. The service owns its medicine catalog, stock batches, prescription snapshots, reservations, dispensing ledger, audit chain, and unpublished outbox rows. It never reads or modifies Records Service storage directly.

## Public API

All public routes require a valid Patient-issued Bearer access token. Current Patient authority is checked for pharmacist, hospital-admin, and patient operations as required by the frozen contract.

| Method | Path | Scope |
|---|---|---|
| GET | `/api/v1/pharmacy/medicines` | Authenticated medicine prefix search and bounded pagination |
| GET | `/api/v1/pharmacy/medicines/{medicine_id}` | Authenticated catalog detail |
| POST, PATCH | `/api/v1/pharmacy/medicines` and `/api/v1/pharmacy/medicines/{medicine_id}` | Current pharmacist or hospital admin catalog writes |
| GET | `/api/v1/pharmacy/inventory` | Current pharmacist batch inventory |
| POST | `/api/v1/pharmacy/inventory-adjustments` | Current pharmacist audited adjustment |
| GET, POST | `/api/v1/pharmacy/reservations` | Scoped reservation history and creation |
| GET, DELETE | `/api/v1/pharmacy/reservations/{reservation_id}` | Own patient reservation or pharmacist access |
| POST | `/api/v1/pharmacy/reservations/{reservation_id}/dispense` | Current pharmacist fulfillment |
| POST | `/api/v1/pharmacy/reservations/{reservation_id}/revalidate` | Current pharmacist prescription revalidation |
| GET | `/api/v1/pharmacy/dispensings` | Scoped dispensing history and filters |
| GET | `/api/v1/pharmacy/dispensings/{dispensing_id}` | Own patient dispensing or pharmacist access |

Single-resource responses use quoted version ETags. Conditional PATCH, DELETE, dispense, and revalidation require `If-Match`. Every public POST requires an `Idempotency-Key`; equal retries return the stored status, body, and ETag for at least 24 hours.

## Private API

Service-authenticated callers use the frozen Phase 2 scopes and delegated user token:

- Records: `POST /internal/v1/medicines/validate` returns catalog activity, version, and name for up to 50 distinct medicine IDs.
- Billing: `GET /internal/v1/dispensings/{dispensing_id}/charge-context` returns only the completed dispensing's appointment, patient, medicine charge codes, quantities, and source-item IDs.

Pharmacy reads live prescription context from Records before reservation, dispense, or revalidation. Dependency calls are bounded and happen before Pharmacy transactions. Dependency failure prevents a new reservation or dispense; staff can explicitly revalidate after Records recovers.

## Transactions and lifecycle

Stock, prescription allowance, reservation, dispensing, stock movement, append-only audit, unpublished outbox, and POST idempotency response writes commit in one Pharmacy transaction. PostgreSQL row locks are acquired in prescription, sorted allowance, sorted reservation, sorted batch, and audit-head order. FEFO batches are selected by expiry then ID, with lock acquisition kept in ID order. Checks prevent on-hand stock from going below reserved stock, below zero, or above one million units; prescription allowances cannot be over-reserved or over-dispensed. No database lock is held across a Records call.

Reservations expire 30 minutes after creation. Relevant stock and reservation commands release expired reservations once. Revoked prescriptions cannot be newly reserved or dispensed; explicit revalidation releases unfilled reserved quantities. Already dispensed quantities remain historical and require staff review after revocation. Repeating dispense returns the existing dispensing and never deducts stock twice. These are local guarantees; a Records revocation immediately after validation remains a cross-service race.

No RabbitMQ publisher or consumer is enabled. Outbox records remain unpublished. Trie autocomplete, invoice calculations, and category-specific catalog fields are outside the frozen Phase 2 Pharmacy contract. The contract provides medicine detail lookup but does not define a category field or category route, so category browsing needs a reviewed contract change before exposure.

## Configuration and verification

Database settings use `PULSEGRID_PHARMACY_DB_*`. Authentication and dependencies use `PULSEGRID_PHARMACY_AUTH_JWKS_PATH`, `SERVICE_JWKS_PATH`, `SERVICE_PRIVATE_KEY_PATH`, `SERVICE_KID`, `AUTHORITY_URL`, and `RECORDS_URL`, following the service-scoped conventions. Records defaults to `http://records:8000`.

Run package tests with `python -m pytest` from this directory. PostgreSQL integration tests require `PULSEGRID_PHARMACY_TEST_DATABASE_URL` to point to a dedicated database whose name ends in `_test`, plus a migration-capable database user and the `pharmacy_app` role; tests apply the service migrations and clear only that explicitly named test database. Without the URL, the integration tests are skipped. SQLite or mocked database tests do not claim PostgreSQL locking or constraint correctness.

This is a synthetic educational prototype, not a certified clinical or emergency-response system.
