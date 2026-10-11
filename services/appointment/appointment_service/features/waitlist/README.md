# Waitlist module: G1 handoff

Base/framework: `b7f74cb9f47b764989d2540695b4ed05ed8c1b28`.
Branch: `phase-3/appointment-waitlists-g1`.
Only Agent 1 Appointment paths are changed. No other feature module, service,
root contract, infrastructure or migration revision is edited.

## Contract and behavior

This module implements the frozen Phase 3 automatic confirmed-booking waitlist.
The dispatch also requests temporary offers, acceptance, decline and expiry.
That conflicts with `docs/phase-3-api-contracts.md`, which explicitly excludes
an acceptance-offer timer and fixes the four waitlist states. A clarification
was requested. Offers are not implemented or added to the v1 schema; that
decision remains unresolved, rather than silently changing the freeze.

Explicit registration exports frozen join/list/get/withdraw and slot-status
routes. Patient self, receptionist and assigned-doctor read scopes, current
authority, strict IDs/UTC/versions/body/query validation, filter/scope-bound FIFO
cursors, ETags and idempotency use G0 adapters. The wire representation has no
position field; FIFO is observable through the scoped list, while the slot
status resource exposes a count without patient identities.

Join requires an occupied accepted future bookable slot, real Patient/Doctor
checks before entering the transaction, and no duplicate waiting/own booking.
Withdrawal is waiting -> withdrawn; withdrawn is a stable no-op at its current
version. Other terminal changes fail. Reason content is hashed in audit only.
Public GETs never change waitlist state or perform promotion.

Promotion examines at most 50 FIFO `(joined_at,id)` entries per transaction.
Inactive patients and PostgreSQL patient-overlap insertion failures are skipped
with exact reasons. Unknown/stale eligibility stops at the head. Past/retired
slots drain in bounded batches. Copied appointment attributes, active-slot
uniqueness and patient-overlap exclusion remain the existing PostgreSQL guards.
An unchanged slot can promote at its current accepted schedule revision.
No Redis or network call enforces exclusivity.

`Prepared` is a service-local immutable discovery bundle of slot ID, entry
IDs/versions, patient IDs and a validated batch. `prepare` closes its read session
before calling the Patient adapter. Batch membership must exactly match the
discovered patients; missing/malformed/failed data is never treated as active.
Snapshots merge monotonically, never replacing a newer inactive status with an
older active version. Eligibility is valid for at most 60 seconds, including
the exact boundary; future timestamps are invalid. The service-only POST
adapter sends no delegated user token, validates the complete bounded response,
uses deadlines/retries/circuit state and one half-open waitlist probe.

## Transactions and locks

Idempotency advisory serialization precedes G0 `lock_context`. Complete plans
acquire sorted doctors, slots, bookings, holds/workflows/links, FIFO rows,
sorted patient status scopes/rows, promotion jobs, queue scopes and journeys.
Patient status advisory locks protect absent rows; job absence is serialized
by the slot parent. These are PostgreSQL transaction locks. Existing callers
with empty new plan fields never query the future job table.

`book_with_waitlist_guard` rejects direct arrivals when waiting entries or a
pending job exist. `change_with_promotion` uses one G0 context for the old and
target slots, preserves legacy hold/If-Match/state behavior, guards the target,
and stages old-slot release plus promotion atomically. Changed candidate
membership commits the permitted cancellation/move with pending work. Owner
timeouts similarly do not block that local release. Legacy response fields and
`journey_id: null` remain exact. Enrolled changes stay fail-closed pending the
other owners' token/queue/journey lifecycle assembly.

The episode creator is an explicit async G2 callback
`create_episode(session, context, new_booking) -> journey_id`. It must stage
Agent 4's real journey/stages and matching G0 workflow in the existing
transaction, without locks acquired in reverse order, network calls or commits.
The module checks local journey/workflow identity before marking promotion.
Missing creator leaves the slot pending; creator failure rolls back the booking,
entry, episode, effects and response. Tests use a clearly labeled fixture creator
with real local database rows; it is not production Agent 4 integration.

`on_slot_released(session, context, prepared)` uses the frozen hook signature.
G2 supplies its reviewed creator in `session.info['waitlist_episode_creator']`
and an explicit promotion lock plan. No successful journey reference is guessed.
Effects are staged using core and finalized once by `command`, after all
participants, with audit/outbox/idempotency response in the same transaction.

## Recovery and schema requirements

`schema_spec()` defines non-executable `0005_phase3_waitlist` requirements after
`0004_phase3_core`: per-slot durable jobs, lease/progress/backoff columns, local
slot FK, due index, outcome checks, unique promoted reference, snapshot source
checks, preflight and runtime grants. No final 0005–0008 migration file or
aggregate job Table is created in G1. The real head remains `0004_phase3_core`.
Tests apply explicit manifest DDL only to disposable databases after G0 migrations;
this is schema-requirement evidence, not a production migration upgrade result.

The one-shot worker claims one due job in a short job-only transaction using
`FOR UPDATE SKIP LOCKED`, a random lease identity and 30-second lease. It closes
the transaction before fetching eligibility, then applies under the canonical
G0 plan with lease fencing. Expired leases recover interrupted processing;
idempotent command results and slot constraints prevent duplicate promotion.
Failure leaves pending work with exponential 1..60-second retry. A bounded
five-second repair scan discovers free slots with waiting entries and repairs
lost wakeups without resetting pending-job backoff. Worker crashes before a
committed result retain the lease until expiry. No pending job is discarded.

## Deferred sequential assembly

G2 must review/implement aggregate job metadata and the real 0005 revision,
then assemble the remaining 0006–0008 chain from other owners' manifests.
Review promoted patient/slot cross-row constraints and retained-data preflight.
Wire the reviewed Agent 4 episode creator/new-insert context, cancellation and
reschedule lifecycle participants, guarded book/move commands, release hooks,
schedule-retirement wakeups and availability exclusion of waiting/pending slots.
Mount static routes before the legacy dynamic route only after those gates.
G1 registration alone is not a safe production activation.

G3 supplies actual Patient batch scope/key configuration and worker lifecycle;
G4 verifies owner HTTP, retained migrations/runtime grants, multi-app gateway
and browser behavior before activation. G1 imports no other feature and starts
no process/Compose stack. `create_app()` still registers no enabled features.
No real Patient leaf, Agent 4 stages, gateway/UI, load/chaos or broker delivery
integration is claimed. The worker lease recovery test expires persisted lease
state; it does not kill a production process.
