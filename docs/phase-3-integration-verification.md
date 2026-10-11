# Phase 3 integration and verification

In progress, 2026-10-11. Synthetic single-hospital prototype. Phase 3 is **not complete** until checkpoints B–J and the frozen/extended acceptance gates pass. Coordinator now owns sequential integration fixes following final agent commits; original branches/worktrees are preserved.

## Checkpoint A: source integration

Initial main clean at `b7f74cb9f47b764989d2540695b4ed05ed8c1b28`. All supplied objects exist. G0 source `20debbf` was already integrated as `b7f74cb`, with identical tree; it was not applied twice. All seven G1 commits directly descend from b7f74cb. Ordered cherry-picks were conflict-free:

| Module | Original | Integrated main |
|---|---|---|
| G0 | 20debbfa679b60ff3fe749d3d9103415e2819e13 | b7f74cb9f47b764989d2540695b4ed05ed8c1b28 |
| Waitlist | 0d661b1fd6565095d6faed1a500336b5c5535d7f | ccabd32 |
| Queue | 336594a053cdb690998dccb995a6b3eab38d304e | b23ecce |
| Check-in | ce4ef78b230561ab30098afa290c399b15ffad17 | ac876d1 |
| Journey | e6bf4d9873ded822c7fb2829510f199f55242bbc | 348360a |
| Records/Pharmacy | e6d66e4f2619b1ab2ff78b0cf544f804fead6003 | 495ca2c |
| Patient frontend | a71cf8d4d7af4fef93caa84eae8b2674b53a84e4 | 5da7127 |
| Staff frontend | 167876c88c0799497b9b932e43cfcafee509095a | 217a531 |

Reviewed handoffs, schema manifests, runtime interfaces and ownership. Staff UI uses `frontend/src/hospital/staffAdvanced` and `frontend/tests/staff-advanced` instead of the reserved paths; these are isolated new files with no overlap, preserved at user-requested integration. No agent/worktree was reset or overwritten.

Frontend typecheck and tests pass: 107 tests in six files. Appointment integrated regression suite passed: 174 tests, including PostgreSQL tests. The suite uses isolated temporary PostgreSQL databases, never development databases. Compile and diff checks accompany checkpoint commits.

## Open integration work

- Implement reviewed 0005–0008 forward chain; retain prior data and preflight dormant rows.
- Explicitly extend G1 freeze for durable temporary waitlist offers/accept/decline/expiry and queue skip/recall. Existing G1 implemented neither.
- Resolve queue allocator/check-in duplicate workflow update; supply complete doctor/day lock discovery.
- Complete journey list/history/reconciliation/discharge/worker and authoritative Patient/Billing leaves.
- Wire owner scopes/Records gate, feature registration/lifecycle hooks, frontend QR encoding/scanning/forms and real existing Compose stack.
- Execute full regressions, concurrency, gateway workflows and browser verification. No claims of these gates passing yet.

No Phase 4 algorithm, RabbitMQ business delivery, predictive scaling, redesign or push. Final SHA and clean status are reported after final verification commit rather than embedded into their own commit.

## Checkpoint B: reviewed forward schema

Appointment has one linear head `0008_phase3_journey`, following 0001–0004, then waitlist/offers, check-in credential bindings, queue ranks/history and journey snapshots/history. Local foreign keys and runtime grants remain owner-specific. Cross-table offer guards acquire the slot parent; acceptance uses a deferred local appointment FK. History IDs use owner sequences; no custom distributed ID algorithm. Existing dormant credentials/queues are preflighted and rejected for explicit review rather than rewritten.

Executed: complete Appointment suite **174 passed** against disposable PostgreSQL after replacing G1 fixture DDL with real migrations. Found/fixed duplicate queue position selection when metadata includes the new column; test queue adapters now insert a valid waiting position. Re-ran seven upgrade checks after adding the offer audit allowlist and parent guard: **7 passed**, including retained 0003 bookings/audit/outbox/idempotency unchanged through 0008 and six dormant-data rejection cases. No persistent database was modified. Development migration remains pending operational activation at G.

## Checkpoint C: temporary offer backend

Added patient/reception offer list/detail/accept/decline contracts and transactional operations. Five-minute offers (bounded by slot start) reserve capacity; acceptance releases the offer and creates booking/journey/workflow atomically under deferred local FK. Decline/expiry wakes durable promotion work. Worker policy is injectable so the final activation will use offers; G1 direct-promotion regression adapters remain available for compatibility testing and are not selected by production assembly. Unknown/stale first-patient eligibility blocks FIFO.

Executed **54 waitlist tests passed** against real disposable PostgreSQL, including four new offer tests: twelve competing accepts produce exactly one booking, declined offer selects successor, durable expired offer rejects acceptance, competing expiry workers reserve only the next patient, wrong patient rejected, raw SQL booking blocked by offered capacity, identical-key acceptance replays. G1 enrollment/worker/50-arrival protections still pass. Public activation and offer frontend mounting remain scheduled for G/H.

## Checkpoint D: check-in participant and QR verification

Check-in now discovers complete doctor/day queue membership before canonical locking. It consumes the credential and delegates the single workflow mutation to the real queue allocator, validates the resulting binding/version, and records local journey check-in in the same transaction. QR issuance is audited without raw secret persistence. Added actual in-memory SVG QR encoding (`qrcode`) and ZXing decoder fallback when native BarcodeDetector is absent, retaining manual entry and explicit camera permission.

Executed **21 check-in tests passed** using the actual queue allocator (including concurrent redemption, replay, window boundaries, revocation and rollback). Frontend typecheck and **108 tests passed**, including an actual QR encode/decode round-trip with ZXing and manual camera fallback. Camera hardware itself has not been tested. Library integration follows [qrcode documentation](https://github.com/soldair/node-qrcode) and [ZXing browser documentation](https://github.com/zxing-js/browser). Booking-change hooks and public deployment activation remain dependent on G assembly; this record does not claim deployed QR workflows yet.

## Checkpoint E: queue extensions

Authorized skip changes waiting -> skipped; recall changes skipped -> waiting with the original daily token/rank. Neither grants an active consultation or clinical hold. FIFO start and the PostgreSQL one-active-consultation constraint remain. Queue transition history is immutable to the runtime role and exposed through scoped bounded reads. Cancellation/no-show support skipped entries. Fixed mixed-role command scope: assigned doctor identity is checked directly even when that user also has receptionist role.

Executed **8 queue tests passed** on disposable PostgreSQL, including skip/recall history/FIFO, doctor-busy prevention, allocation and competing starts/completion. Public deployment, polling UI buttons and complete Records reconciliation remain G/H dependencies.

## Checkpoint F: durable journey completion

Implemented journey list/detail/history, explicit idempotent reconciliation/discharge, timestamped stages, retained owner snapshots/version vectors, pending failure metadata, fenced leases/backoff and continued discharged-episode checks. Reconciliation completes the queue only from finalized Records and matching finalized local hold. Optional no-prescription stages skip only on that authoritative finalized snapshot. Discharge requires completed queue/workflow, exact charge-source membership, valid Billing arithmetic, no review and fresh complete sources; a late source change reopens discharge. No global atomic snapshot is claimed. Registration prerequisite history uses narrow owner append function in additional forward revision `0009_phase3_registration_history` so runtime cannot edit history.

Executed **7 journey tests passed**, including real PostgreSQL clinical/queue completion, no-prescription progression, eight competing discharges (one success/seven stale versions), source outage/recovery, zero balance without charge acknowledgments, older revisions rejected and late billing change reopening with history. Full Appointment regression run: 180 passed/one outdated lock-order assertion failed after new offer/snapshot locks; updated that assertion and its isolated rerun passed. Complete combined regressions will run again at G/I. Owner leaf deployment, real service HTTP and browser gates remain pending.

## Checkpoint G: owner HTTP assembly and operational activation

Mounted the reviewed four Appointment modules, production durable offer/journey
workers, atomic booking episode creation and target-scoped revocation/queue/
journey change hooks. Added Patient eligibility and Billing workflow leaves with
exact service scopes and current owner data. Records gate now has its operational
Appointment dependency. Existing legacy bookings remain unenrolled. Corrected
metadata/DDL constraint parity and preserved repeated cancellation behavior.

Disposable full regressions: **530 passed, 51 Records PostgreSQL cases skipped**
in the shared runner; separate Records isolated run **77 passed**, covering those
51 cases (26 non-PostgreSQL cases overlap). Frontend at assembly: **109 passed**,
typecheck and production build passed. Python compilation/diff checks passed.
Applied forward migrations successfully to the existing development stack after
these disposable checks; recreated only five changed business-service containers.
No volume/database reset or duplicate full deployment. Read-only live schema
verification passed for all seven owner heads, constraint/FK metadata, immutable
audit digest chains, runtime privileges, all **42 foreign service database
connections denied** (all fourteen app/migration roles also deny foreign CONNECT),
Traefik route isolation and all eleven container health checks. Real Phase 3
workflow verification remains checkpoint I/J work, not claimed by this gate.

## Checkpoint H: frontend mounting

Mounted distinct patient waitlists/offers, check-in, live queue, journey/history
and fulfillment panels; reception QR/manual check-in and discharge inspection;
doctor queues with skip/recall/history and consultation controls. Pharmacy staff
uses one fulfillment panel around the existing forms, preserving Phase 2 stock
and dispensing screens. Offer decisions retain the original idempotency key and
version on ambiguous failures. Queue polling remains three seconds for staff,
five seconds for patients; hidden documents pause polling. Real in-memory QR
encoding/native-or-ZXing scanning and manual fallback remain. No redesign.

Executed typecheck, **109 frontend tests** across seven files and production
build successfully. Added offer ambiguous-response retry/receipt coverage and
updated the prior intentionally-deferred UI assertion for authorized activation.
Production bundle size warning is recorded; runtime/browser checks follow at J.

## Checkpoint I: complete regressions and concurrency

Complete shared backend runner: **531 passed**, 51 Records database cases
intentionally delegated to the isolated Records runner; **77 Records passed**
(26 overlap). After final Appointment fixes, its complete suite **184 passed**,
including the two additional snapshot/signing tests not collected in the earlier
shared run. There are **584 distinct passed backend tests**, no unresolved skips
or failures. Frontend **109 passed**, typecheck/build passed. Deprecation and
bundle-size warnings remain non-fatal. Python compilation and diff checks pass.

Real PostgreSQL tests cover enrollment races, FIFO, competing offer acceptance
(twelve commands/one booking), expiry/accept and competing expiry workers,
simultaneous token redemption, concurrent daily allocation, competing starts,
exactly-one completion transition under eight concurrent reconciliations, and
eight competing discharges (one success/seven stale versions). Constraint,
rollback/idempotency, duplicate/older snapshots, revocation and worker lease/
restart tests also pass. Disposable clusters only for destructive cases.

Gateway testing exposed and fixed a Records circuit-breaker issue: a normal
missing resource (404) now remains unknown/pending without treating the owner as
down or delaying other completed consultations. Added a targeted transport test.
The twelve-request gateway QR race exposed repeated RSA private-key parsing that
blocked the async service. Parsed-key reuse retains fresh JWT jti/expiry/exact
scopes and reads the key file each call so rotation selects a new cached key;
no authority decision or token is cached. Rotation regression passes. Measured
in the same Appointment container: twelve signatures took 6.595 seconds before,
0.079 seconds warm after. The rerun produced exactly **one successful redemption
and one queue entry across twelve gateway requests**. Initial timeouts are not
reported as passes. Also tightened query rejection on new offer/queue commands.

Refreshed existing migration-job containers after an outage recovery attempt
found their old image could not recognize the new Billing head. All seven jobs
now exit zero; the same Billing container was immediately restored, no reset or
replacement deployment. Remaining J work is browser/staff evidence and final
report/clean-tree checks; Phase 3 is not yet declared complete by this entry.
