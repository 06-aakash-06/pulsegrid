# Phase 4.5 short-link handoff

Base: `45273ea7fd1ea53e335942b6c38f2d81d38856ee`
Owned implementation: `services/appointment/appointment_service/features/short_links/`,
`services/appointment/tests/phase4_short_links/`, and
`experiments/phase4/short_links/`.

## Exports and ports

- `register_routes(app, ports)` mounts the frozen POST create, POST revoke, and
  GET `/s/{alias}` handlers. The coordinator must mount the literal `/s/` route
  before the legacy `/{appointment_id}` route and pass the frozen Phase 4 ports.
- `register_tables(metadata)` attaches `short_links` to the Appointment metadata;
  it does not create or migrate a database table.
- `schema_spec()` hands off the exact forward migration requirements for
  `0010_phase4_short_links`.
- `revoke_for_booking_change(session, context, appointment_id)` is the local
  participant for lifecycle revocation.
- `ShortLinkRepository` owns digest lookup, DB-clock lookup, insert, revoke and
  appointment-local read operations. It never commits or opens a connection.

## Required migration work

Coordinator writes `0010_phase4_short_links` only. It adds `short_links` with a
local restricted FK to `appointments`, positive signed-BIGINT IDs, purpose/hash/
workflow/fingerprint/version checks, unique digest, the partial unique
`(appointment_id,purpose) WHERE revoked_at IS NULL`, and the appointment lookup
index. Grant `appointment_app` SELECT/INSERT/UPDATE. No QR, alias, or patient data
backfill is needed. Preserve all 0001–0009 revisions and one Alembic head.

The migration must add `short_link_created` and `short_link_revoked` to the
Appointment feature-effect/audit allowlists. Add a safe outbox event mapping for
each action, with link ID/version and state only. Resolution uses the existing
`read` audit action and carries no alias.

## Route and Appointment wiring

1. Register the table and mount this feature through the coordinator-owned
   Appointment extension registration. Supply `authorize`, `allocate_id`,
   `command`, `read_session`, `observer`, `read_workflow`, `lock_context`,
   `stage_effect`, and `token_response` adapters exactly as frozen.
2. In the complete canonical lock plan, discover and lock every short-link row
   for target appointments immediately after existing check-in link locks and
   before waitlist, queue, journey and audit locks. Parent appointment locks
   serialize absent-row reissue and creation.
3. Register `revoke_for_booking_change` for cancel, reschedule, no-show and
   workflow completion transitions. The lifecycle caller must already have the
   complete appointment lock context. Do not let this participant acquire late
   locks after queue/journey/audit locks.
4. Inject Agent 4's owner ID allocator. It must allocate before the business
   command transaction; an unused ID on an idempotency replay is an acceptable
   gap. Keep the existing owner CSPRNG and all Phase 3 IDs unchanged.
5. Make `token_response` overlay `short_path` only when the command operation
   committed in this request. The route independently returns the safe 409
   replay response if the operation did not execute.
6. Keep `/s/` same-origin at Traefik and Vite. Mount the SPA literal landing
   route outside patient-only workspace gates. The frontend holds the alias
   only in memory and clears the fragment before authentication. Redact the
   `/s/{alias}` path from application logs, traces and metrics; do not add a
   redirect destination parameter or QR issuance/consumption to GET.

## Current limits and validation

The component has no migration, shared Appointment route, check-in edit, gateway
edit, or production route mount by design. The local benchmark uses disposable
PostgreSQL and fake principal/effect adapters; it is not integrated API latency.
After wiring, run the low/medium/high workloads and seeds 404/405/406, plus the
retained Phase 3 QR race/window/stale-ETag/idempotency checks and browser fragment
clearing validation. Keep baseline and proposed paths authenticated and use the
same fixture hardware, pool, clients, timing and owner data.
