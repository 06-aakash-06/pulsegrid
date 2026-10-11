# Phase 3.3 queue G1 handoff

This module is disabled in the G0 app factory. It makes no schema changes at
runtime. `registration.py` exports `register_routes`, `register_tables`,
`schema_spec`, `allocate_on_checkin`, and `complete_from_records`. It also
exports `cancel_for_booking_change` for the G2 booking-cancellation hook.

## Transaction and ordering

The doctor snapshot row is the parent serialization point for allocation,
start, no-show, cancellation and completion. G2 must extend `lock_context` to
lock the queue snapshot row after the doctor/day counter and before queue entry
rows. The caller discovers every affected doctor/day, waiting and active entry,
and affected booking/workflow before requesting a context. A changed discovery
restarts the whole transaction. Queue code never commits, opens a second
transaction, performs HTTP, or publishes notifications under locks. G0 command
finalization flushes staged audit/outbox events and the idempotent response.

Check-in calls `allocate_on_checkin` while the workflow is still `booked`. The
hook inserts the queue entry, binds it to the workflow, changes that workflow
to `checked_in`, increments its version, and stages the checked-in effect in
the same transaction. This order is required by G0's non-deferrable
`queue_required` check. The check-in owner consumes the link and updates the
journey in that same command; it must not also stage a duplicate checked-in
effect. Check-in must supply all existing waiting queue row IDs in the lock
plan, plus the doctor's local day derived from the accepted IANA policy.

The start endpoint is the frozen **call next** operation: it accepts only the
oldest waiting token for that doctor/day. A doctor already consulting on any
day remains busy. Starting a token nulls its position and renumbers waiting
entries, incrementing the affected entry versions and day snapshot revision.
The partial unique doctor index is the final database guard against two
active consultations. A stale If-Match returns 412; same-key replay returns
the persisted result after current authorization.

Completion requires a finalized Records consultation snapshot whose
appointment/patient/doctor and consultation ID match the local finalized hold.
An attempted HTTP finalize, draft, mismatched source, or active hold leaves the
doctor busy. Repeating an already completed matching snapshot is a no-op.
No-show is receptionist-only, after the window end, without a hold. A booked
appointment has no queue row; a checked-in waiting appointment becomes
terminal and the remaining waiting positions close. Cancellation uses the
separate participant before the booking update. An active consultation or
terminal workflow cannot be cancelled through that hook.

## G2 assembly requirements

1. Agent 1 reviews `schema_spec.py` and owns migration `0007_phase3_queue`:
   `queue_snapshots`, `queue_entries.position`, safe bounds and FIFO index.
   Review retained dormant rows before adding rank constraints; do not
   fabricate workflow or history. Apply runtime grants for the new table.
2. Agent 1 extends G0 metadata and `lock_context` in its owned files, then
   enables fixed queue registration ahead of legacy dynamic routes. Add the
   queue cancellation hook to its booking command and the queue completion
   hook to the journey reconciliation command. Keep the event flush after all
   participants.
3. Agent 2 calls allocation in its check-in transaction. Agent 4 invokes
   completion only after an authenticated, validated Records snapshot and
   finalized local hold. Neither caller should issue network requests while
   holding a queue lock.
4. Run real migration upgrade, retained-data checks, multi-instance PostgreSQL
   races, current-authority HTTP tests, and browser polling tests before
   activation. G1 tests use a disposable PostgreSQL cluster and a test-local
   schema extension because the production migration is reserved for Agent 1.

The live transport is authenticated polling. Staff snapshots carry a versioned
cursor; a later page returns `queue_changed` when the revision changed, so the
client restarts at page one. Patient reads expose only their entry plus counts.
No SSE/WebSocket publication or network update is performed by this module.

The frozen Phase 3 API defines no `called`, `skipped`, or `recalled` queue state
and no skip/recall command. This G1 module therefore implements the approved
FIFO start and terminal no-show transitions. Adding a reversible skip/recall
workflow would require a separately reviewed v2 contract, state machine,
fairness rule, schema change and owner tests before activation.
