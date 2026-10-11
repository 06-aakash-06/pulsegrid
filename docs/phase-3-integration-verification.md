# Phase 3 integration and verification

Completed, 2026-10-11. Synthetic single-hospital prototype. Checkpoints A–J and the applicable frozen/extended Phase 3 gates have passed; remaining verification limits and deferred scope are explicit below. Coordinator now owns sequential integration fixes following final agent commits; original branches/worktrees are preserved.

Checkpoint entries retain the results and outstanding work at the time of each
commit. The final results section is the authoritative completion status.

## Checkpoint A: source integration

Initial main clean at `b7f74cb9f47b764989d2540695b4ed05ed8c1b28`. All supplied objects exist. G0 source `20debbf` was already integrated as `b7f74cb`, with identical tree; it was not applied twice. All seven G1 commits directly descend from b7f74cb. Ordered cherry-picks were conflict-free:

| Module | Original | Integrated main |
|---|---|---|
| G0 | 20debbfa679b60ff3fe749d3d9103415e2819e13 | b7f74cb9f47b764989d2540695b4ed05ed8c1b28 |
| Waitlist | 0d661b1fd6565095d6faed1a500336b5c5535d7f | ccabd32aba7b24f2f3f28992ed8a340322f2df68 |
| Queue | 336594a053cdb690998dccb995a6b3eab38d304e | b23ecce3c5325040365be579866cbc4f573fbcbe |
| Check-in | ce4ef78b230561ab30098afa290c399b15ffad17 | ac876d1f8944072b1eb306723b901f1fb9e5ec8e |
| Journey | e6bf4d9873ded822c7fb2829510f199f55242bbc | 348360a4bebe730f179711dc143453554b3f241e |
| Records/Pharmacy | e6d66e4f2619b1ab2ff78b0cf544f804fead6003 | 495ca2ccfd8000a2ba36975299c1687a4ad4b07f |
| Patient frontend | a71cf8d4d7af4fef93caa84eae8b2674b53a84e4 | 5da71272518e94246080324f3215b32b1d751b5f |
| Staff frontend | 167876c88c0799497b9b932e43cfcafee509095a | 217a531bf9bf3bfd602eeb97c74139b02e2c383b |

Reviewed handoffs, schema manifests, runtime interfaces and ownership. Staff UI uses `frontend/src/hospital/staffAdvanced` and `frontend/tests/staff-advanced` instead of the reserved paths; these are isolated new files with no overlap, preserved at user-requested integration. No agent/worktree was reset or overwritten.

Frontend typecheck and tests pass: 107 tests in six files. Appointment integrated regression suite passed: 174 tests, including PostgreSQL tests. The suite uses isolated temporary PostgreSQL databases, never development databases. Compile and diff checks accompany checkpoint commits.

## Initial integration gaps (resolved at checkpoints B–J)

- Implement reviewed 0005–0008 forward chain; retain prior data and preflight dormant rows.
- Explicitly extend G1 freeze for durable temporary waitlist offers/accept/decline/expiry and queue skip/recall. Existing G1 implemented neither.
- Resolve queue allocator/check-in duplicate workflow update; supply complete doctor/day lock discovery.
- Complete journey list/history/reconciliation/discharge/worker and authoritative Patient/Billing leaves.
- Wire owner scopes/Records gate, feature registration/lifecycle hooks, frontend QR encoding/scanning/forms and real existing Compose stack.
- Execute full regressions, concurrency, gateway workflows and browser verification.

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

## Checkpoint J: gateway and browser demonstration

All six requested workflow groups passed with real synthetic owner HTTP calls
through the existing Traefik gateway. The retained demonstration consists of ten
Phase 3 gateway groups and three additional security/race groups, plus a fresh
rerun of **all eleven retained Phase 2 gateway groups** on the activated stack.
No mocked backend is substituted for these requests.

| Requested workflow | Executed result |
|---|---|
| 1: registration through prescription, dispensing, payment and discharge | Passed: current assigned doctor, real QR redemption/token, finalized Records, Pharmacy stock/dispensing, Billing source import/simulated success payment, fresh reconciliation and reception discharge |
| 2: full slot, waitlist, cancellation, offer acceptance | Passed: FIFO reservation; four competing gateway accepts yield one booking |
| 3: offer expiry and next patient | Passed: real five-minute persisted expiry, next FIFO patient's pending offer, production worker recovery across Appointment container replacement |
| 4: skip/recall/consultation completion | Passed: original token/FIFO restored, busy guard, finalized Records completes queue/history; also exercised browser skip/recall/call-next and clinical creation/finalization |
| 5: no prescription | Passed: authoritative finalized Records null prescription, Pharmacy skipped, consultation charges/payment and authorized discharge |
| 6: downstream unavailable/recovered | Passed: one bounded synthetic Billing stop/reconciliation, pending/failed stage with discharge denied, same container restored and reconciliation recovered; finally restoration is mandatory |

Additional gateway checks passed: cancellation and reschedule revoke old
credentials, twelve competing QR redemptions produce exactly one queue entry,
wrong patient access/check-in denied, patient discharge denied, private owner
leaves blocked at gateway, and late prescription revocation preserves committed
dispensing while flagging review and blocking discharge. Earlier successful full
journey is intentionally left requiring review after that negative test; this is
expected safe behavior, not a failed primary workflow.

Real in-app browser (Chrome connector unavailable) used actual Vite/API proxy:
patient sign-in, QR generation/render and confirmed check-in (token 5), live queue
position, waitlist offers and journey/history; assigned doctor skip/recall/FIFO
start plus real clinical create/finalize without prescription; reception manual
check-in (token 7). Browser discharge review exposed version churn on unchanged
worker heartbeats; fixed it to retain review versions while updating freshness,
with a ten-test journey rerun passing. Fresh source/version checks remain on every
discharge, and actual source changes still invalidate a review. Final reception
discharge/browser evidence and final clean-tree check are recorded below.

Temporary verification helpers were corrected for plain-text Traefik 404s and
FastAPI included-router introspection (use generated OpenAPI); those helper
failures are not represented as application passes. Supplemental security uses
a separate private fixture file so verification writers do not share state.
No credentials, raw tokens or private fixture files are committed.

## Final results and operational status

Reception browser discharge passed after the heartbeat correction: journey
2228637984549656965 is `discharged`, its prescription/Pharmacy stages are
authoritatively skipped, and timestamped history includes the new discharge.
Actual browser history paging also passed. The browser-started consultation 404
was finalized as record 433 without prescription, and owner reconciliation
completed its queue. No physical camera permission/capture was attempted.

Final review also mounted reception's audited no-show command. A real browser
command for an elapsed checked-in appointment returned `no_show`; no-show controls
disappear on the terminal workflow. The new disposable PostgreSQL test verifies
queue/journey terminal state and both timestamped histories. Existing window/hold
guards remain authoritative; no persistent clock or appointment was rewritten.

Final full Appointment regression: **186 passed** (including stable
heartbeat/review and completed no-show history regressions). Combined unique backend coverage is **586 passed**:
Patient 200, Doctor 29, Appointment 186, Records 77, Pharmacy 25, Billing 35,
Emergency 34. Shared runner's 51 Records skips are all covered by the isolated
77-test run; its 26 duplicated Records unit cases are counted once. Final
frontend typecheck, **110 tests/seven files**, production build and Python
compilation pass. There are no unresolved required test failures/skips.

| Owner | Single migration head verified in disposable and retained development databases |
|---|---|
| Patient | `0005_waitlist_eligibility` |
| Doctor | `0004_doctor_management` |
| Appointment | `0009_phase3_registration_history` |
| Records | `0005_phase3_workflow` |
| Pharmacy | `0004_phase3_workflow` |
| Billing | `0004_phase3_workflow` |
| Emergency | `0003_emergency_workflow` |

Appointment chain: 0001_initial -> 0002_explicit_worker -> 0003_booking ->
0004_phase3_core -> 0005_phase3_waitlist -> 0006_phase3_checkin ->
0007_phase3_queue -> 0008_phase3_journey -> 0009_phase3_registration_history.
No merge head, legacy reset or fabricated historical enrollment. Runtime cannot
edit audit/history or migrations. Source branches/eight Phase 3 worktrees retain
their original supplied commits and are clean. Main is the integration branch.

Read-only live infrastructure checks passed: all seven owner schemas/heads,
foreign-key/constraint semantics and runtime privileges; audit-chain integrity;
42 foreign runtime database connections denied and all fourteen DB roles
isolated; seven gateway APIs/eleven healthy containers; seven migration jobs
exit zero. Generated OpenAPI contains all 24 reviewed Phase 3 producer routes
checked by the helper; all four Appointment extensions are activated, Records
consultation gate is operational, and private leaves remain inaccessible at the
gateway. Fresh Phase 2 real HTTP compatibility rerun: **11 groups passed**.
Phase 3 real HTTP demonstration: **10 groups passed**, covering all six requested
workflows; supplemental real HTTP **3 security/race groups passed**.

Compatibility extension: newly enrolled bookings expose their real nullable
`journey_id`, superseding the preparation freeze's null-only response assertion
as explicitly recorded in the extended contract. Existing unenrolled bookings
retain null; v1 booking states remain confirmed/cancelled and advanced states
remain separate workflow resources. Retained Phase 2 clients/workflows passed.

Executed commands: `python tests/run_phase2_regressions.py`; final complete
`python -m pytest -q` from `services/appointment` (real isolated PostgreSQL); Records
`tests/run_isolated.py`; `python -m compileall services tests`; frontend
`npm run typecheck`, `npm test -- --run`, `npm run build`;
`python tests/verify_phase3_infrastructure.py`; `python tests/verify_phase3.py`;
`python tests/verify_phase3_security.py`; `python tests/verify_phase2.py`;
Compose config/build/forward migration/health checks; documentation link/fence/
route/ownership checks and `git diff --check`. Checkpoint commits retain coherent
source/schema/activation/UI/fix changes. Private credentials, fixtures and raw
QR tokens remain outside Git. Retained logs/JUnit files are under private /tmp;
the scripts and safe browser evidence below are committed for reproducibility.

Final documentation checks passed: 45 local link targets, 17 rectangular tables,
balanced fences, retained source objects and eight clean original Phase 3
worktrees. Shared ownership review confirms sequential coordinator edits after
agent handoff; no concurrent file ownership or schema writer was introduced.

### Bugs discovered and fixed

- Missing G1 offers and skip/recall: explicitly extended contracts and implemented
  durable PostgreSQL reservations/expiry plus scoped transitions/UI.
- Duplicate check-in/queue workflow update and incomplete queue lock discovery:
  one real allocator owns the atomic workflow transition; discover parents and
  all affected queue days/children before canonical locking.
- Missing source leaves, episode enrollment and real journey handlers/workers:
  exact owner-authenticated snapshots, durable history/recovery, expected-charge
  membership and fresh source-version checks; no global atomicity claim.
- Cancellation hooks accidentally could affect all bookings in a discovered
  doctor queue: target-scoped revocation/journey hooks; preserve legacy repeated
  cancellation and permit safe release when Patient eligibility is unavailable.
- Metadata/DDL parity, deferred offer FK/trigger ordering and dormant migrations:
  real migration fixtures, preflights, local capacity guards, strict owner grants.
- Missing-resource circuit breaker, repeated RSA parsing and unchanged heartbeat
  version churn: corrected and regression/gateway/browser verified.
- Old migration-job image after Billing recovery and stale frontend deferred
  text: refreshed existing jobs and current workflow copy.
- Missing reception no-show control: mounted the existing scoped backend command,
  tested current ETag/reason/confirmation, durable terminal histories and live browser success.

### Limits and deferred functionality

Physical camera/device scanning is **implemented but hardware-unverified**. Real
QR encoding/pixel decoding, camera/manual fallback component tests and actual
browser reception fallback passed. Chrome connector was unavailable; the in-app
browser supplied live verification. Browser exercised patient/doctor/reception
flows; full pharmacy/payment and all six journeys were exercised through actual
HTTP, complemented by frontend component tests. No claim that all six complete
workflows were replayed entirely by clicks.

Owner validation is bounded REST/eventual consistency, not a distributed atomic
snapshot. A downstream change just after validation is detected on reconciliation
and can reopen discharge. Committed dispensing survives revocation; review cases
stay flagged for staff resolution and cannot be automatically discharged. Billing
charge import/payment remain explicit owner commands; payments are simulated.
Prototype polling/batch/deadline settings are not measured scalability/HA claims.
Frontend build emits a non-fatal bundle-size warning; existing dependency
deprecation warnings remain. No throughput/load benchmark, Mermaid rendering or
physical/clinical certification was executed.

Broker business delivery, Phase 4 system-design algorithms, Surge Mode, Control
Room, predictive scaling, multi-hospital, beds, family profiles and final redesign
are **deferred**, as requested. No push or volume/database reset. There are no
remaining integration blockers or disabled required Phase 3 modules. **Phase 3 is
complete within its authorized educational-prototype scope.** Main's final
clean status and exact report commit SHA are confirmed after committing this
report; its own hash cannot be embedded recursively in its contents. The latest
implementation/verification anchor is
`8cb4bbbc2784ff17af69dcde60b11981db8f0c2b`; the final report commit SHA is provided
in the coordinator's final response and resolves as `git rev-parse main`.

### Safe browser evidence

- [Patient QR check-in receipt](evidence/phase-3/patient-checkin.png) (raw credential already cleared).
- [Doctor queue controls](evidence/phase-3/doctor-queue.png).
- [Reception discharge](evidence/phase-3/reception-discharge.png).
- [Reception no-show](evidence/phase-3/reception-no-show.png).
