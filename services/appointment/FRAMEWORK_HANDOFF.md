# Phase 3.1A Appointment framework handoff (G0)

Original base: `6ac9c1c748a7cafde8f2cf8de5316faa458bbcb8`.
Branch: `phase-3/appointment-waitlists`. Synthetic prototype only.
The coordinator distributes the final commit SHA after review; Agents 2–4
record both original base and this immutable framework SHA before integration.

## Scope and gates

G0 supplies shared interfaces, workflow storage, locks and finalization. No
feature routes, worker processes, automatic booking enrollment or business
algorithms are activated. `create_app()` calls explicit disabled registration
before the legacy router so future static routes precede `/{appointment_id}`.
There is no configuration switch that bypasses review. Legacy bookings remain
confirmed/cancelled with `journey_id: null`, including private contexts/events.

The frozen plan requires the intermediate head `0004_phase3_core` now.
`0005_phase3_waitlist -> 0006_phase3_checkin -> 0007_phase3_queue ->
0008_phase3_journey` remain reserved, absent files until reviewed manifests are
available. No placeholders or merge revisions. Historical 0001–0003 are
unchanged. Core migration refuses unexpected dormant feature data before DDL;
it preserves bookings/audit/outbox/idempotency, never backfills episodes, grants
runtime SELECT/INSERT/UPDATE on the new table and is forward-only.

G1 implements features in their owned directories. G2 assembles queue before
real check-in; journey creation before booking enrollment; Records gate before
clinical queue use. Agent 1 alone reviews metadata/manifests, creates revisions,
wires hooks and extends locks for new snapshot/job tables. G3 owner leaves and
infrastructure lifecycle are integrator work. G4 verifies real cross-service
integration and retained upgrades before activation. G0 readiness does not
claim Phase 3 feature/integration readiness.

## Module exports and ownership

Each module supplies `registration.py` in its reserved feature directory:

| Agent | Directory | Required exports |
|---|---|---|
| 2 | `appointment_service/features/checkin/` | `register_routes(app, core) -> None`, `register_tables(metadata) -> None`, `schema_spec() -> dict`, async `revoke_for_booking_change(session, context) -> None` |
| 3 | `appointment_service/features/queue/` | same three registration functions; async `allocate_on_checkin(session, context) -> dict`, async `complete_from_records(session, context, records_snapshot) -> None` |
| 4 | `appointment_service/features/journey/` | same registration functions; async `on_booking_created(session, context) -> None`, async `on_booking_changed(session, context) -> None` |

Agent 1's future waitlist module supplies those three registration functions and
async `on_slot_released(session, context, eligibility_snapshot) -> None`.
Queue allocation returns exactly the frozen `CheckinResult.queue_entry` shape.
Void hooks stage effects through `core.stage_effect`; the transaction's ordered
effect buffer is the effect list collected by core, preserving frozen signatures.
No ad hoc return shape is substituted for the allocation response.

`extensions.register_extensions(app, core, enabled=())` accepts only the fixed
allowlist waitlist/checkin/queue/journey. It validates exports before registration,
calls `register_tables` on the existing `core.metadata`, verifies existing Table
identities, then mounts routes. Missing enabled modules are errors, never ignored.
The immutable registry is `app.state.appointment_extensions`.
Feature agents do not call registration from main or edit parent initializers.
Agent 1 passes reviewed names only during sequential assembly.

`register_tables` reuses objects from `appointment_service.models`; never
redefines existing tables, uses `create_all`, or imports foreign metadata.
`schema_spec()` returns a non-executable dict manifest with `tables`, `columns`,
`indexes`, `constraints`, `preflight` and `runtime_grants` sections. Each entry
names its table/object, types/nullability/defaults and exact SQL expressions or
local FK targets. Document retained-data checks and revision expectations.
Agent 1 reviews this manifest before shared metadata/migration edits. G0 validates
the return is a dict; manifest review is a coordinator gate, not automatic DDL.

Agent 2 owns only checkin module and `tests/phase3_checkin/`; Agent 3 only queue
and `tests/phase3_queue/`; Agent 4 only journey and `tests/phase3_journey/`.
No reserved directories were created or edited at G0.

## Core adapters

`register_routes(app, core)` receives the `appointment_service.phase3_core`
module. Available adapters:

- `metadata`, `Workflow`, `CheckinWindow`, `ResourceEffect`, `PromotionPayload`:
  shared SQLAlchemy metadata and strict frozen wire types. IDs are decimal
  strings, UTC timestamps, versions bounded to safe positive integers.
- `authenticated_user`, `current`, `private_principal`: existing verified JWT,
  current-authority and delegated internal authentication. `authorize(request,
  principal, roles, appointment_id=None, write=False)` performs current authority
  and optional booking scope before replay/owner requests. Role-specific rules
  (assigned doctor start, receptionist enrollment etc.) remain feature-owned.
  Public actor headers never establish identity. `ActorScope.user(principal)`
  copies verified identity without raw credentials; `worker_actor()` is an
  internal appointment scheduler identity with no user/clinical authority.
- `session_factory(request)`: returns the owner async session factory or 503.
  `get_database_session(request)`: existing FastAPI yielded session dependency;
  uncommitted work rolls back. Never keep its transaction open during HTTP.
- `execute(request, principal, body, work, caller=None)`: existing idempotent
  POST wrapper. Call authorization before this wrapper. `precondition` parses
  If-Match; validate the locked aggregate version inside work. Replay precedes
  stale version rejection, after current authority and scope. Hash only token
  digests in normalized input; issuance must persist sanitized outcomes and
  implement its frozen nonsecret replay exception in Agent 2 code.
- `command(factory, identity, fingerprint, work)`: owns transaction, advisory
  idempotency lock, replay, bounded three attempts, effect flush and saved
  response. `work(session)` returns `(HTTP status, JSON-compatible result)`.
  Existing retry/error mapping remains. Future workers use service-scoped
  durable identities and explicit lease/progress in their feature revisions;
  they never create a pretend user Principal.
- `response(code, value)`, `query_keys(request, allowed)`, `can_access(principal,
  booking, write=False)`: no-store/version ETag, strict query-key checks and
  existing patient/reception/assigned-doctor scope. Static feature routes must
  mount before legacy dynamic routes; no fake successful endpoints.

## Locks, context and transaction participation

`LockPlan` is an immutable complete discovered resource set: `doctor_ids`,
`slot_ids`, `appointment_ids`, `checkin_link_ids`, `waitlist_slot_ids`,
`queue_days` (doctor ID/local date), `queue_entry_ids`, `journey_ids`.
All domain IDs here are database integers. Discover affected resources before
locking; include all doctor/day scopes for existing queue rows, both doctors/
slots on moves and every FIFO/active entry needed by the operation.

`await lock_context(session, request, actor, plan)` requires a fresh owner
transaction, derives booking parents and children, sorts/deduplicates IDs and
returns `Context` after acquiring:

1. Doctor snapshots, then slots, then bookings.
2. Clinical holds, workflows, links, FIFO waitlist rows.
3. Doctor/day counters, queue entries, journeys/stages.
4. Audit head is acquired only later by command finalization.

Missing doctor/slot/booking is 404; changed discovery raises `operations.Restart`
so command rolls back and retries rather than extending locks in reverse order.
Parent locks serialize inserts where child/counter rows do not exist. G0 does
not yet have queue snapshot/promotion job tables: Agent 1 must extend this helper
at their reviewed migrations before their activation. Return `context.plan`
contains the full acquired sets. One context per transaction; do not first use
legacy `lock_resources` then request a new context.

Context contains immutable request/correlation/trace IDs, actor snapshot, UTC
`now`, locked `bookings`/`workflows`/`holds` keyed by integer booking ID and plan.
Rows contain IDs/versions/state/identity; there is no browser-provided context.
`require_context(session, context)` rejects another session/finalized context.
`invoke_participant(app, feature, export, session, context, *args)` accepts only
fixed hooks and fails 503 for disabled modules. Agent 2 invokes queue allocation;
Agent 4 invokes queue completion with validated Records metadata. Participants
never commit, open another session, acquire earlier locks, append audit directly
or perform HTTP. This is a programming contract; Python does not sandbox
feature code. Feature tests must assert transports see no active transaction.

`read_workflow(session, appointment_id)` never enrolls or authorizes a read.
`workflow_view(row)` returns the frozen wire shape. `schedule_fingerprint(booking)`
SHA-256 hashes canonical slot/doctor/revision/UTC interval fields.
`enroll_workflow(session, context, appointment_id, journey_id)` stages shared
storage for an already locked confirmed future booking without holds, after a
real identity-matching journey has been inserted by Agent 4. Agent 4 owns the
six stages and journey creation effects. This helper is not a public command or
an enrollment policy bypass; no route calls it at G0. Booking creation's new
insert/context enrollment path is wired by Agent 1 at G2, after journey hooks.

`stage_effect(session, context, action, resource_id, version, payload, reason=None)`
validates allowlisted events, IDs/version and nonsecret payload shape, then adds
an immutable snapshot to the transaction buffer. `FEATURE_EVENTS` lists exact
frozen outbox names; ordinary payload is `{resource_id, version, state}`;
promotion uses `PromotionPayload` with real journey ID. Reason is hashed.
`command` flushes legacy/feature effects in staging order after all participants,
then saves the response in the same transaction. Feature audit uses the existing
single chain and a constrained SECURITY DEFINER function with user OR scheduler
identity, never fabricated user ID. Nothing is marked published. Do not call
`flush_effects` from features. Runtime cannot directly update/delete audit.

Legacy `effect()` now stages; it no longer appends success at call time. Existing
Phase 2 work goes through `command`, so its committed wire/events remain exact.
Existing locks now include workflow after hold. Enrolled clinical hold acquisition
requires in_consultation. At G0, cancel/reschedule of any enrolled workflow fails
closed with workflow_locked until Agent 1 wires all token/queue/journey hooks;
legacy unenrolled commands are unchanged.

## Verification and unresolved dependencies

Tests use existing local Python dependencies and the service's disposable
PostgreSQL fixture (random port/database, no retained DB connections). See
[the verification record](PHASE_3_1A_VERIFICATION.md) for exact commands/results.

Remaining prerequisites: feature module implementations/schema manifests;
0005–0008 and lock/schema extensions; new booking/change lifecycle orchestration;
Records queue eligibility/finalized snapshots; Pharmacy fulfillment snapshots;
integrator Patient eligibility/Billing snapshots, private scopes/configuration,
worker lifecycle and real owner/gateway/browser activation checks. No full
waitlist, QR, queue or journey algorithms are supplied or claimed.

## Additive G1 waitlist interface handoff

The historical G0 evidence above remains unchanged. G1 module scope and gates
are documented in `appointment_service/features/waitlist/README.md`.
`LockPlan` now has optional trailing `waitlist_patient_ids` and
`promotion_slot_ids`, both defaulting to empty tuples. Existing feature plans
remain compatible. Explicit promotion plans acquire sorted patient status
advisory scopes/rows and job rows after FIFO, before queue/journey/audit. Jobs
are queried only when requested; G0 migrations and disabled registration are
unchanged. G2 must provide the job schema before using those plans.

Legacy `operations.book` and `change` accept an optional owner-validated
`phase3_context`, so the gated waitlist adapters can reuse one canonical
context rather than acquiring legacy locks again. Their existing public
callers still use the original paths. No Agent 2–4 code is imported or wired.
Promotion episode creation is an explicit G2 dependency and fails closed to
pending work if absent. See `PHASE_3_1C_VERIFICATION.md` for G1 tests and limits.
