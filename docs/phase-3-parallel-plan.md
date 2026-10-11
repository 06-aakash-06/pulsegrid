# Phase 3 parallel development plan

Status: Phase 3.0 preparation only. No implementation agents, feature code, worktrees, dependencies, containers, migrations or remote publication are started by this plan. The current user's seven-agent assignment supersedes historical scaffold/Phase 2 assignments in [AGENTS.md](../AGENTS.md); no AGENTS edit is necessary. Contracts: [API freeze](phase-3-api-contracts.md), [acceptance tests](phase-3-acceptance-tests.md).

## Phase 2 prerequisite verification

Initial main was clean at `32cdbdbc9f7dd95503b62e53e3b4f44c96b53ab4`, the committed Phase 2 integration report/README update. All eight integrated service/frontend commits and subsequent fixes are in its history. Source inspection covered the requested architecture/boundary/database/security/API/event/Phase 2 plans, all domain route/state/authorization/transaction implementations, Appointment metadata/migrations/clinical holds, Records finalization, Pharmacy allowance/charge leaves, Billing source imports, and React route/navigation/client/page implementations. See [the committed integration report](phase-2-integration-verification.md) for source commit mapping and real workflow evidence.

| Check in Phase 3.0 | Result / scope |
|---|---|
| pwd, git branch --show-current, git status --porcelain=v1, git log, git rev-parse HEAD | PASS: requested checkout, main, clean tree, committed Phase 2 integration |
| Retained `/tmp/pulsegrid-phase29-backend.xml` and `/tmp/pulsegrid-phase29-records.xml`, parsed with ElementTree | PASS: root 453 collected, 0 failures/errors, 49 skipped; Records 75 tests, 0 failures/errors/skips. Matches committed report: 404+75 passing executions, 453 distinct tests; skipped Records cases subsequently executed in isolated Records run. Artifacts dated 2026-10-11 09:10/09:11 IST. Historical executed evidence, not a fresh backend rerun |
| `python3 tests/verify_phase2_infrastructure.py` | PASS fresh read-only verification: all seven live heads match source, owned tables/constraints/audit chains/outbox evidence, 42 foreign runtime connections denied, all fourteen roles deny foreign CONNECT, frozen route presence, gateway/internal-route protection and eleven healthy containers. Initial sandbox socket denial resolved by approved read-only execution; no environment repair/start/reset |
| `npm run typecheck`, `npm test`, `npm run build` in frontend | PASS fresh: 85 tests/four files, typecheck and build. Existing dependencies, no install |
| Critical HTTP/browser workflows | PASS recorded at current integrated baseline in committed report: 11 real gateway groups, booking competition, clinical holds/finalization, dispensing/revocation recovery, source imports/payment, ownership/RBAC, browser patient/Doctor/Pharmacy/Billing transactions and logout. Not rerun in Phase 3.0; avoid adding fixture transactions solely for documentation preparation |

No failed foundation prerequisite remains. Backend/HTTP/browser historical evidence is deliberately distinguished from fresh read-only/frontend checks. No new runtime feature results, load tests, chaos, multi-replica deployment or Mermaid rendering are claimed. Preparation checks are recorded in acceptance document after execution.

## Architectural decisions that constrain dispatch

1. Preserve all seven domain owners and plural public prefixes. Appointment v1 stays confirmed/cancelled with null journey_id; new workflow resources carry advanced states/real journey IDs. Enrolled clinical creation has an explicit queue-start gate, legacy unenrolled behavior is retained. Do not widen strict clients silently.
2. Existing dormant tables are reused with owned additive migrations. Agent 1 exclusively owns shared Appointment plumbing, aggregate metadata, all migrations and hook wiring. Other Appointment agents implement isolated modules; no concurrent edits to router/main/models/operations/initializers/migration environment/conftest.
3. Bounded REST projection workers provide Phase 3 automatic advancement/recovery. RabbitMQ remains unpublished, avoiding premature Phase 5 publishers/inboxes. Patient/Billing minimal snapshot leaves are integrator dependencies, not implicit work for the seven agents.
4. Polling drives live UI; secure QR fragment landing + authenticated explicit POST drives check-in. No shortener, camera scanner infrastructure, SSE/WebSocket, cache/distributed locks, redesign or infrastructure algorithms.
5. Activation is sequential and gated. Having seven agents finish their branches is not integration completion. Shared handlers remain disabled until owner APIs, migration upgrades, cross-service tests and browser workflows pass together.

## Exact non-overlapping editable ownership

All listed directory ownership is recursive, including that directory's `__init__.py`, module schemas/models/routers/operations/adapters, nested fixtures and tests. Ownership grants no permission to another directory with a similar name. No symlinks/generated files may escape an assigned path. Reserved paths do not exist until later implementation is explicitly authorized.

For precise set arithmetic, let Appointment root A = `services/appointment/`; reserve the following six directories:

- A2 = `services/appointment/appointment_service/features/checkin/`
- T2 = `services/appointment/tests/phase3_checkin/`
- A3 = `services/appointment/appointment_service/features/queue/`
- T3 = `services/appointment/tests/phase3_queue/`
- A4 = `services/appointment/appointment_service/features/journey/`
- T4 = `services/appointment/tests/phase3_journey/`

| Agent | Exact exclusive edit set | Responsibility / ordinary branch |
|---|---|---|
| 1: Appointment waitlists + shared plumbing owner | All files under A **except** A2,T2,A3,T3,A4,T4 | `phase-3/appointment-waitlists`; waitlist feature under `appointment_service/features/waitlist/`, tests under `tests/phase3_waitlist/`; common extension package, metadata, lifecycle hooks, all Appointment migration revisions, parent initializers, router/main/operations/wire/errors/settings/dependencies/auth helpers, README/package metadata/base fixtures and shared tests |
| 2: Appointment QR/check-in | A2 and T2 only | `phase-3/appointment-checkin`; link issuance/redemption/security/staff fallback; module schema specification and feature-local contract/unit/DB tests |
| 3: Appointment live queues | A3 and T3 only | `phase-3/appointment-queue`; counter allocation, queue snapshots/FIFO start/no-show, position/privacy/polling response contracts; completion participant called from reconciliation |
| 4: Appointment journeys | A4 and T4 only | `phase-3/appointment-journey`; stage projection, owner adapters, reconcile worker, discharge gate; clinical completion orchestration invokes queue participant in one Appointment transaction |
| 5: Records/Pharmacy coordination | `services/records/` and `services/pharmacy/` only | `phase-3/clinical-pharmacy`; all existing/new files, migrations, package initializers, parent tests/fixtures within these two domains; Records queue eligibility gate/snapshots, Pharmacy fulfillment/snapshots, revocation/revalidation UI-facing states; no Appointment or Billing/Patient edits |
| 6: Patient frontend | `frontend/src/advanced/patient/` and `frontend/tests/advanced_patient/` only | `phase-3/frontend-patient`; waitlist/check-in/own queue/journey and prescription fulfillment panels; local clients/types/hooks/styles/tests and barrel `index.ts` within owned directory |
| 7: Staff frontend | `frontend/src/advanced/staff/` and `frontend/tests/advanced_staff/` only | `phase-3/frontend-staff`; reception coordination, assigned doctor queue, pharmacy fulfillment/revalidation and source-ID handoff; local clients/types/hooks/styles/tests and barrel `index.ts` within owned directory |

Integrator exclusively owns all paths outside those sets: root/docs/contracts/infra/tests/experiments; Patient, Doctor, Billing, Emergency; existing frontend files, `frontend/src/advanced/` parent files, tests parent files, package/lock/config, navigation, HospitalPage, auth/API shared client, App/layout/global styles. Integrator does not concurrently edit Agent 1 or Agent 5 files; shared changes inside those edit sets are handed to their owner. After an agent's final scoped commit and explicit ownership handoff, integrator may make integration fixes there, sequentially, with that transfer recorded. Never apply conflicting edits while that owner is active.

Examples: Agent 2 may create `features/checkin/__init__.py` and its own tests/conftest.py; cannot edit `features/__init__.py`, top-level models.py, tests/conftest.py or migrations/versions. Agent 3 cannot change checkin router even though queue allocation is triggered there. Agent 4 cannot patch operations.book or queue completion internals. Agent 6 cannot change HospitalPage, patientDoctor.tsx, workspaces.ts, global.css or package.json. Agent 7 cannot edit Agent 6 types. Initializers are explicit file ownership, never exempt glue.

All branches start from the **same completed Phase 3.0 main commit**, resolved once after this preparation is committed and included verbatim in later authorized dispatch messages. No branch/worktree/agent is created now. Each agent records original base, later shared framework commit (if rebased), branch, final SHA, files, migration expectations and executed/skipped tests. Stage only owned files, preserve others' work; no reset/clean/merge/push. Seven logical assignments do not imply seven simultaneous workers; dispatch capacity is scheduled separately when authorized.

## Shared Appointment extension contract and dependency gates

No common executable framework is created in Phase 3.0. The chosen safe alternative is exclusive Agent 1 shared ownership plus sequential framework/integration gates. Feature work may use local fixtures until the framework is available; it cannot claim real integration from those fixtures.

**G0, sequential Agent 1 framework handoff:** after later implementation authorization, Agent 1 prepares and commits the extension interface, disabled registration, workflow table/common schemas, shared lock helper, transaction/audit hook sequencing and isolated test support. Agent 1 is the only editor of these files:

- `appointment_service/extensions.py`: explicit registration function called from main; imports fixed allowlisted module names only. No filesystem plugin discovery/import magic.
- `appointment_service/features/__init__.py`: parent package only.
- `appointment_service/phase3_core.py`: workflow enrollment/read helpers, canonical locks, service-only worker actor and envelope/audit helper. No separate shared domain runtime package.
- Existing `models.py`, `operations.py`, `api/router.py`, `main.py`, `wire.py`, `errors.py`, `dependencies.py`, `authorization.py`, `settings.py`; service package/API initializers and `migrations/env.py`.
- `tests/phase3_core/` and existing `tests/conftest.py`, package metadata, README; existing Phase 2 tests preserved in intent.

Feature modules expose this exact Python protocol through their own `registration.py`:

```python
# Structural signatures; no executable implementation is created here.
register_routes(app, core) -> None
register_tables(metadata) -> None
schema_spec() -> dict
# queue module only:
allocate_on_checkin(session, context) -> dict
complete_from_records(session, context, records_snapshot) -> None
# checkin module only:
revoke_for_booking_change(session, context) -> None
# journey module only:
on_booking_created(session, context) -> None
on_booking_changed(session, context) -> None
# waitlist module only:
on_slot_released(session, context, eligibility_snapshot) -> None
```

`context` is a service-local immutable value containing request/correlation/trace IDs, verified actor scope, locked booking/workflow identifiers and versions, and now UTC. It is built by core, never browser-supplied. Participant methods accept an existing owner transaction, never commit, open a second session, acquire earlier locks, append audit prematurely or perform network I/O. They stage local effects and return an effect list to core for final ordered audit/outbox append. Dict return schemas are CheckinResult.queue_entry for allocation; schema_spec is non-executable table/index/constraint/column manifest for Agent 1 migration review. Core owns idempotency, final audit/outbox and response persistence once per command; feature effect IDs remain distinct. Register_tables reuses core metadata and dormant table objects; a feature cannot redefine the same Table or import another service's metadata. The shared signature document/fixtures must be committed at G0 before feature branches consume it.

Core lock helper accepts complete discovered doctor/slot/appointment sets and feature lock requirements. It returns a context only after the canonical locks listed in API freeze have been acquired. Feature allocation/completion cannot acquire queue locks after core already locked journey/audit. Agent 1 must refactor existing effect() call timing so all participants finish before audit head lock. Existing clinical_hold gate reads workflow under the same order. Agent 2 delegates allocation to Agent 3; Agent 4 delegates queue completion to Agent 3; no duplicate authority.

All agents share initial preparation base. After G0 review, coordinator distributes one immutable framework SHA; feature branches update sequentially to it (or cherry-pick the exact commit) before real framework tests. Record both base SHAs; no moving main dependency. Shared files are not cherry-picked piecemeal from unrelated feature branches. Missing signature/table gate is reported and blocks real integration, not patched by an unauthorized agent.

**G1, isolated implementation:** Agent 1 implements waitlists; Agents 2/3/4 implement isolated features against G0 interfaces; Agent 5 implements clinical/pharmacy owner leaves; frontend agents work on separate modules with clearly labeled test fixtures. No shared route wiring changes by feature agents. Agent 1 remains shared owner and incorporates reviewed schema manifests only after the relevant module handoff; no concurrent metadata merge.

**G2, sequential assembly:** Agent 3 queue allocation/start contract and migrations before Agent 2 real check-in integration. Agent 4 journey creation hook before enabling new booking enrollment; Agent 5 Records eligibility/hold recovery before queue clinical use. Agent 1 wires reviewed module registration/hooks and assembles final schema revisions. No cancellation hook can make a remote call or lose fairness.

**G3, integrator owner leaves/configuration:** Patient waitlist eligibility and Billing workflow snapshot implemented exclusively by integrator, preserving existing response schemas. Integrator wires private scopes/credentials and worker process lifecycle/deployment in existing infrastructure only when separately authorized. Doctor/Emergency business behavior unchanged. Agent 5 remains exclusive Records/Pharmacy editor until handoff. Frozen leaf consumer tests precede exposure.

**G4, integration/activation:** all service migrations/constraints and retained-data checks pass; old APIs remain compatible; real PostgreSQL multi-instance races, real owner calls and gateway/auth isolation pass; UI routing activates after owner tests. Integrator enables new booking enrollment and worker jobs together, runs browser/full regression gates and documents failures/recovery. Stop on a critical failure, fix under transferred scope; never label the phase complete just because branch tasks ended.

## Appointment migration revision strategy

Only Agent 1 creates/edits `services/appointment/migrations/**` and aggregate `models.py`. Historical revisions 0001/0002/`0003_booking` remain immutable. Reserve one linear chain, no parallel Alembic heads and no merge revision:

| File / revision | down_revision | Contents / gate |
|---|---|---|
| `0004_phase3_core.py` / `0004_phase3_core` | `0003_booking` | workflow table/core constraints, shared metadata/lock support; G0, features disabled |
| `0005_phase3_waitlist.py` / `0005_phase3_waitlist` | `0004_phase3_core` | promotion jobs/lease/eligibility metadata and promoted uniqueness; Agent 1 |
| `0006_phase3_checkin.py` / `0006_phase3_checkin` | `0005_phase3_waitlist` | live-link uniqueness, workflow binding/window fingerprint; Agent 2 reviewed schema_spec handoff |
| `0007_phase3_queue.py` / `0007_phase3_queue` | `0006_phase3_checkin` | queue snapshot revision/constraints/indexes; Agent 3 handoff |
| `0008_phase3_journey.py` / `0008_phase3_journey` | `0007_phase3_queue` | journey snapshot vectors/stage constraints/worker progress; Agent 4 handoff |

Intermediate core migration can be committed at G0; future files are reserved names, not empty placeholder migrations. Schema definition/manifests for A2/A3/A4 live inside those modules' schema_spec.py; **no SQL Alembic revision from those agents**, no autogenerate command that writes shared files. Agent 1 imports complete feature metadata only after owned modules exist; G0 does not import missing modules. Tests cannot invoke head with absent module definitions. Final schema and `alembic heads` must show exactly `0008_phase3_journey`. On retained data, probe duplicate/live rows before adding constraints; unexpected rows stop upgrade for review. No deletes/resets/default fabricated episodes. Enrollment is an explicit command, not an automatic migration backfill.

Records Agent 5 reserves `0005_phase3_workflow.py` after `0004_clinical_integrity`; Pharmacy Agent 5 reserves `0004_phase3_workflow.py` after `0003_phase2_pharmacy`. Integrator reserves Patient `0005_phase3_eligibility.py` after `0004_patient_management_audit` if schema/grant change is required, and Billing `0004_phase3_workflow.py` after `0003_billing_phase2`. Each domain has one independent chain/credentials; identical numeric prefixes across databases are harmless. Snapshot revisions/grants must be tested with runtime DDL/audit/foreign-DB denial. Migrations are implemented only in later authorized work, never this preparation.

## Frontend ownership and integration

Existing navigation already reserves `/patient/waitlist`, `/patient/check-in`, `/patient/queue`, `/patient/journey` and `/doctor/queue`. Use these exact routes, keep layouts and auth. Reception tools extend `/receptionist/appointments`; pharmacy coordination extends `/pharmacist/prescriptions`; Doctor queue-to-existing consultation link extends `/doctor/queue`. Patient fulfillment panel is mounted on `/patient/prescriptions`/`/patient/pharmacy`. No new admin/ops/insurance functionality.

Agent 6 exports `PatientWaitlistPage`, `PatientCheckinPage`, `PatientQueuePage`, `PatientJourneyPage`, `PatientFulfillmentPanel` from its owned index.ts. Agent 7 exports `DoctorQueuePage`, `ReceptionWorkflowPanel`, `StaffFulfillmentPanel` from its owned index.ts. Each uses existing authenticated API client/auth hooks read-only and keeps its own typed contract adapter. Duplicate local wire types are acceptable if fixtures prove exact compatibility; neither agent creates a shared file. Agent 6/7 CSS is module-local or explicitly namespaced, no global reset. Keep keyboard labels/focus/loading/empty/error/stale/pending states and manual token fallback. No fabricated production data, guessed queue position, optimistic prescription/dispense/payment success or persistent raw tokens.

Integrator mounts exports in `frontend/src/hospital/HospitalPage.tsx`, preserves existing page forms, edits navigation copy only when needed and adds integration tests under root frontend tests outside the agents' test directories. Existing receptionist catch-all routing must be explicitly adjusted at assembly; otherwise it hides new tools. Agent 7 composes existing staff forms through exports when possible, never edits their source while active. Integrator handles package.json/lockfile changes for a reviewed QR encoder if needed later; no ad hoc QR image generator that produces undecodable symbols. Accessible copy/paste works independently of QR. Patient/staff tests/typecheck must pass before assembly, then full auth/UI regressions after wiring. No whole-app redesign.

## Safe concurrency and stop rule

**Safe now:** concurrent architecture review or isolated module work after explicit authorization, within the disjoint edit sets. **Not safe:** seven unrestricted agents editing Appointment or frontend root, independently generating migrations, wiring routers/hooks, or enabling features before G0–G4. Real feature integration is sequential at the specified gates. This plan does not assert that a framework exists yet.

Every later dispatch includes exact path set/exclusions, preparation SHA, framework SHA when available, relevant freeze routes/signatures/migration manifest, acceptance IDs, stop-at-scoped-commit/no merge/no push rule and test environment scope. Isolated DBs/ports/test namespaces are unique; no worker/full Compose stack in another worktree. Only integrator manages one reviewed runtime topology; schema upgrades/global checks serialize. If shared interface needs a change, stop dependent integration and send a proposed diff to its owner; reviewed freeze update and notification precede implementation.

Phase 3.0 changes exactly three documentation files and commits locally on main. No AGENTS.md change, agent launch, feature business logic, database reset, container start, dependency install or push. Final preparation SHA is reported after commit, avoiding self-reference.
