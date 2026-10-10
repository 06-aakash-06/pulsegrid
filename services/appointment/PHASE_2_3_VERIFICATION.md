# Phase 2.3 verification and handoff

Date: 2026-10-11 (Asia/Kolkata). Branch: `phase-2/appointment`. Reviewed base: `de63867adb7f5863c708ee19f4376ccbb49a0691`. Migration head: `0003_booking`. Exclusive changes: `services/appointment/**`. The final commit SHA is reported in the chat handoff; no merge/push is authorized.

## Executed checks

| Check | Result |
|---|---|
| `services/appointment/.venv/bin/python -m pytest services/appointment/tests` | PASS: 58 tests, including all 17 existing regressions; no skips. PostgreSQL 14.17, real Alembic migrations and restricted runtime connections in disposable databases. |
| `services/appointment/.venv/bin/python -m compileall -q services/appointment/appointment_service services/appointment/migrations services/appointment/tests` | PASS |
| `create_app().openapi()` assertions | PASS: 14 domain operations on 13 paths, booking 201 schema, null journey and forbidden extra request properties. No shared schema files written. |
| `git diff --check` | PASS |
| Base/ownership inspection | PASS: initially clean detached HEAD at the requested base; created ordinary `phase-2/appointment` branch; staged paths restricted to Appointment. |

One existing tooling warning: Starlette deprecates its httpx TestClient integration. Tests execute successfully with the service's existing dependency versions; no runtime dependencies or lockfile versions changed.

## What the tests establish

The concurrency suite uses independent PostgreSQL connections and production command functions. Twenty different patients race for one exclusive slot: exactly one 201 and nineteen `slot_occupied` conflicts; only one appointment/outbox/audit/response commits. Twelve concurrent identical retries return the same appointment/status and commit once. Same-patient bookings at overlapping times across doctors yield one success and one `patient_overlap`; adjacent intervals succeed. Direct SQL inserts separately prove the unique active slot index, patient exclusion, doctor slot exclusion and slot-copy trigger.

Concurrent cancellation/rescheduling under the same ETag yields one success and one 412. Cross-doctor moves use sorted locks and both succeed for distinct unoccupied targets. An occupied target leaves the original appointment slot/state/version untouched. Cancellation no-ops emit no duplicate event, reject resurrection, and permit a new patient's booking. A clinical hold racing cancellation yields one success/one 412; a retained hold blocks changes and finalization is versioned/repeat-safe. Schedule closure is rejected while a booked interval exists; after cancellation it can be accepted. Accepted replacements preserve booking revision and matching slot identity.

Injected failure after business/audit/outbox insertion rolls everything back, including idempotency. Injected real PostgreSQL serialization SQLSTATE exercises complete transaction retries and one final commit; this is retry fault injection, not a claim that a spontaneous serialization anomaly was observed. Generated-ID collision retries succeed after one collision and return 503 on exhaustion. Audit table writes and invalid audit-function actions are denied to runtime.

HTTP tests execute signed user/service JWT verification and local database operations. They check role/ownership/assignment concealment, revoked-authority fixture denial, inactive patient/doctor references, strict IDs/versions/extra fields, ETags, POST replay after resource changes, key/body conflict, filtered scope before pagination, cursor filter binding, UTC availability, staff cancellation, schedule decisions and every private leaf. Private leaves have a fixture that fails if they attempt a cross-service callback.

Dependency transport fixtures check exact identity schema and delegated headers, missing/denied references, invalid/oversized JSON, rejected redirects, timeout/5xx retries, and circuit opening after five failed attempts. These fixtures do not prove live Patient/Doctor integration.

## Unavailable or out-of-scope verification

- Live Patient/Doctor/Records/Billing and gateway integration: not executed; peer Phase 2 implementations and deployment wiring are outside exclusive ownership.
- Shared persistent development DB migrations: intentionally not run. Every test database belongs to a newly created disposable cluster. No existing DB is reset, truncated or dropped.
- Load/latency/throughput, process-replica deployment, broker delivery, clinical validity and Mermaid rendering: not run and not claimed.
- No waitlist, QR/check-in, queue, journey automation or RabbitMQ publisher/consumer is implemented.

## Integrator attention

The no-snapshot operational-status case lacks a trusted staff mapping for an own-doctor delegated caller. This leaf cannot call Doctor, and the access token lacks a doctor ID. It therefore fails closed with 404 for that case; admin gets the frozen zero counts/version 1. An approved mapping preparation contract or initial admin decision is required before own-doctor deactivation without any schedule. See [README](README.md) for the exact contract gap, transaction algorithm and recovery limits.

The migration owner needs `btree_gist` and `pgcrypto` extension privileges. Assignment backfill uses only local existing snapshots; missing mappings/overlapping legacy rows stop the migration safely. Remote account/doctor changes after prevalidation remain a bounded cross-service race. Orphan clinical holds remain safe and require retry/coordinator review, with no automatic timeout release. Outbox envelopes remain unpublished for later reviewed broker activation.
