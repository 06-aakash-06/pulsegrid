# Phase 4 parallel development plan

Status: preparation complete when committed locally, 2026-10-12; **no agents
launched, no component implemented**. Start only after a separate implementation
request. Inspected main: `340909aade79b23a3ffb99ade8d9863bd0a6b928`, clean.
Binding [contracts](phase-4-component-contracts.md),
[benchmarks](phase-4-benchmark-plan.md), and
[machine-readable ownership](phase-4-ownership.json). Preserve
[Phase 3](phase-3-integration-verification.md), all older branches and worktrees.

## Eight assignments and exclusive ownership

The following prefixes include new source, colocated unit/contract/DB tests,
README/handoff, local schema manifests and package metadata **inside that prefix
only**. Every unlisted path belongs exclusively to the coordinator. No agent
creates a ninth domain service or takes a broad service/frontend grant.
Model labels are requested dispatch preferences, not tools launched here.
Agent 8 uses the coordinator's default Sol Medium unless the user selects another
model; this preparation does not change any session model.

| Agent | Assignment | Requested model | Ordinary branch | Exclusive recursive prefixes |
|---|---|---|---|---|
| 1 | Distributed rate limiter | Sol High | phase4/rate-limiter | `components/rate_limiter/**`<br>`experiments/phase4/rate_limiter/**` |
| 2 | Consistent hashing | Sol Medium | phase4/consistent-hashing | `components/consistent_hashing/**`<br>`experiments/phase4/consistent_hashing/**` |
| 3 | Key-value caching | Sol Medium | phase4/key-value-cache | `components/key_value_cache/**`<br>`services/doctor/doctor_service/features/directory_cache/**`<br>`services/doctor/tests/phase4_directory_cache/**`<br>`experiments/phase4/key_value_cache/**` |
| 4 | Unique ID generator | Sol Medium | phase4/unique-id | `components/unique_id/**`<br>`experiments/phase4/unique_id/**` |
| 5 | URL shortener | Luna | phase4/short-links | `services/appointment/appointment_service/features/short_links/**`<br>`services/appointment/tests/phase4_short_links/**`<br>`experiments/phase4/short_links/**` |
| 6 | Insurance crawler | Luna | phase4/insurance-crawler | `services/billing/billing_service/features/insurance/**`<br>`services/billing/tests/phase4_insurance/**`<br>`experiments/phase4/insurance_crawler/**` |
| 7 | Autocomplete | Luna | phase4/autocomplete | `components/autocomplete/**`<br>`services/doctor/doctor_service/features/autocomplete/**`<br>`services/doctor/tests/phase4_autocomplete/**`<br>`services/pharmacy/pharmacy_service/features/autocomplete/**`<br>`services/pharmacy/tests/phase4_autocomplete/**`<br>`experiments/phase4/autocomplete/**` |
| 8 | Frontend feature integration | Sol Medium (coordinator default; user may override) | phase4/frontend | `frontend/src/phase4/**`<br>`frontend/tests/phase4/**` |

Agent 1 builds script/algorithm and standalone admission adapter, not seven
middleware edits. Agent 2 builds only deterministic placement. Agent 3 builds
Redis client/cache-aside and Doctor read adapter, not directory mutation hooks.
Agent 4 builds generator/store, not existing ID call sites. Agent 5 builds routes,
transaction participants and short_links schema_spec, not QR module edits.
Agent 6 builds crawler/extractor/worker/routes/schema_spec and small fixture
truth within its experiment prefix, not billing invoice/payment handlers.
Agent 7 builds trie plus owner-specific unmounted routers/snapshot loaders,
not shared owner routers or revision migrations. Agent 8 builds unmounted panels,
API types/adapters and tests using frozen HTTP fixtures, not App/navigation/auth
foundation. Agent paths are new and absent at preparation; creation is authorized
only by the later component implementation request.

### Coordinator-only paths and responsibilities

All root files, docs, contracts, infra, compose files, Dockerfiles, service package
pyproject/requirements locks/settings/main/secure_entrypoint/middleware/router/
authentication/authorization/models, **all** existing migrations and new owner
Alembic revisions, existing service tests, cross-owner tests, frontend package
files/locks/App.tsx/workspaces/auth/API foundation and existing hospital panels.
Also `tests/phase4/`, `experiments/phase4/integration/` and any future common
benchmark runner. Agents may read these files but must hand off required edits.
No modifying sibling feature paths, `features/__init__.py`, shared test conftest,
or claiming parent prefixes. No dependency installation into a shared venv;
each worktree uses its own ignored venv, temporary DBs/ports and benchmark namespace.

Component implementation produces algorithms/adapters/tests and schema manifests.
Deployment adds private Redis nodes, fixture servers, credentials, package image
builds, resource budgets and forward migrations. Integration connects ports,
mounts hooks/routes/UI and runs regression/gateway/browser acceptance. Only the
coordinator performs deployment and integration after reviewed handoff; eight
agents working concurrently does not mean simultaneous shared-stack activation.

## Frozen dependencies and independent start

| Producer | Consumer | Frozen seam / test substitute |
|---|---|---|
| Rate limiter | Coordinator, all APIs | admit bucket port; fake transport and route inventory until mounting |
| Ring | Coordinator cache adapter | immutable locate/snapshot; Agent 3 uses fake placement, no ring import |
| Cache | Doctor integration | Cache and revision-aware projection ports; isolated DB fixtures, fake placement |
| IDs | Appointment short links, Billing insurance | allocate_id coroutine; Agent 5/6 use deterministic test allocator |
| Short links | Frontend and Appointment core | frozen HTTP JSON and revoke participant; injected existing command/lock/auth ports |
| Crawler | Billing estimates, frontend | PolicyRule/EstimateResult and invoice snapshot ports; synthetic fixture HTTP and disposable Billing DB |
| Autocomplete | Doctor/Pharmacy, frontend | owner-only snapshot ports and SuggestionPage; DB baseline fixtures |
| Frontend | Coordinator mounting | default exports described below, HTTP fixtures; does not depend on live producer branches |

No agent imports unfinished sibling modules or cherry-picks another agent's
partial work. Python duck-typed ports are locally defined; test fakes assert
method names, argument names and result shape. Owned service modules may import
stable current owner helpers read-only. New schema_spec/metadata registration
can be tested in disposable PostgreSQL with test-only DDL inside owned tests;
clearly report that this is not a tested final Alembic migration. Coordinator
replaces test DDL with forward migration fixtures during integration. Critical
concurrency tests must still use PostgreSQL/Redis, not in-memory mocks.

Agent 8 exports `frontend/src/phase4/index.ts` with `DoctorAutocomplete`,
`MedicineAutocomplete`, `AppointmentShortLinkPanel`, `ShortLinkLanding`,
`InsuranceEstimatePanel`, `InsuranceRefreshPanel`, `AdmissionFeedback`.
Common props: existing `ApiClient`, user role/identity navigation hints,
appointmentId/invoiceId where applicable, onSelect for suggestions and existing
workflow callback; backend checks remain authority. API client uses
requestWithMetadata so response headers including Retry-After are readable on
success; a **local** wrapper retains safe failure status/Retry-After without
editing shared ApiError (coordinator may later extend metadata compatibly).
No automatic retry of token issuance/payments/mutations; same idempotency key
only on explicit safe retry. Debounce suggestions150ms, AbortSignal cancel,
drop stale responses and limit10, keyboard/screen-reader support and plain
text/prefix search fallback. Keep secrets in memory only, clear URL before
navigation, request confirmation for existing check-in POST. Show estimates as
synthetic with stale/version labels; 429/503 and backend retry delay in plain
language. Existing UI survives disabled new features. No control-room UI or
redesign. Agent 8 tests only inside its paths using existing frontend tooling.

## Contract freeze rules

Review contracts before coding; no changes to meaning, auth, enums, routes,
normalization, money units, token handling or ports without coordinator approval
and a reviewed docs/consumer update. Requests for a change go in owned HANDOFF.md,
with rationale and affected consumers; blocked seam uses the frozen fake while
other owned work continues. Do not silently revise interfaces in code. Runtime
packages are versioned independently and contain no shared business models.
New owner APIs are additive v1; old clients and decimal IDs remain valid.

Each handoff states branch, preparation base SHA, final SHA, every changed path,
exported symbols, exact tests/benchmarks run with pass/fail/skip, test-only DDL
limitations, proposed dependency locks, schema manifest, hooks/route order,
config and deployment needs. Agents stage only owned files and can make local
commits once the implementation task explicitly authorizes them. No merge,
push, credential generation, persistent migrations, production-like failures
or shared fixture writes by agents. Preparation authorizes only its local main
commit, not future implementation commits.

## Git and isolated resources

Coordinator records full preparation SHA before dispatch; all eight worktrees
start from it, not inspected pre-preparation SHA. Future commands (do not execute
in preparation): `git worktree add <new-path> -b <branch-above> <PREP_SHA>`.
Use unique nonexisting paths/branches; inspect existing worktrees and branches
first, never reset/clean/reuse somebody else's checkout. Each reports
`git status --short`, branch and `git merge-base HEAD <PREP_SHA>`.
No codex branch prefix under this repository's explicit instruction. Integrator
works on main and reviews changed paths against ownership JSON before imports.
Default integration cherry-picks complete reviewed commits sequentially; retain
source worktrees and branches. No remote operations or push without new approval.

No shared database reset or simultaneous writes to development fixtures.
Component databases are disposable owner-only test instances (unique DB name,
roles and port, migrations where available); Redis servers use isolated ports/
containers and unique namespaces. Crawler fixtures use dedicated local ports
with explicit allowlist. Tests clean up only resources they created. Every
failure-injection benchmark has owned target, bounded duration and finally-based
recovery; no Compose outage at agent time. Do not delete benchmark history or
retained audit rows to make reruns succeed.

## Sequential integration gates

1. Review all handoffs, ownership, dependency pins, correctness evidence and raw
   measurements before accepting a component. Validate contract vectors and
   no secret/generated bulk dataset tracked. Import pure ring/ID/trie/limiter/cache
   packages with features disabled; imports themselves must preserve old behavior.
2. Coordinator writes/reviews forward Doctor/Pharmacy revision, Appointment alias
   and Billing insurance migrations from manifests, using real upgrade fixtures
   retaining Phase 3 rows/audit/idempotency/PK/FKs/constraints/grants. Verify single
   heads and preflight dormant insurance data. No downgrade/reset.
3. Wire ring into cache through coordinator adapter; package images, two private
   cache Redis nodes and isolated admission Redis networking/ACLs; enforce process
   count budgets. Shadow ID worker reservation/restart and clock rollback tests,
   then inject only into new Phase 4 entity allocation before business locks.
4. Mount Doctor cache/revision hooks and Doctor/Pharmacy trie literal routes before
   ID routes; benchmark baseline parity, rename/deactivation/rebuild/node churn/
   cache outage and DB fallback. No auth/sensitive cache changes.
5. Mount alias participants and new Appointment routes; verify cancellation/
   reschedule/no-show/reissue lifecycle plus original QR races and explicit POST.
   Mount Billing crawler/leases/fixture networking and estimate endpoints;
   verify exact amounts and paid balances unchanged during failure/retry.
6. Wire per-route pre/post-auth admission, trusted source policy and CORS Retry-After;
   run real multi-replica Redis tests, emergency budget isolation and outage/recovery.
   Protect health/internal current-authority paths from accidental low-budget lockout.
7. Coordinator mounts frontend panels/literal landing routes and same-origin link
   navigation/resolution, preserving all existing paths and QR fallback. Run
   frontend tests/typecheck/build and real browser authentication/link/suggestion/
   estimate/429 workflows. No sensitive URL traces or local/session storage.
8. Run full retained backend coverage (current baseline586) plus new unique tests,
   frontend (baseline110) plus additions, all six Phase 3 gateway workflows,
   all eleven retained Phase 2 groups, security/isolation/audit/current-authority/
   concurrency checks. Use existing runners with disposable DBs; reexecute counts
   rather than treating old totals as fresh evidence. Validate auth+phase4 Compose
   config quietly, gateway private leaves and upgraded migration heads. Record
   exact skipped/unavailable checks and block required acceptance on missing evidence.

Integration can adjust this ordering only through a documented acyclic dependency
review; public functionality is activated after its complete owner/security/schema
prerequisites, never when just an algorithm benchmark passes.

## Acceptance and risks

All eight can **start independently** from the preparation commit with fake ports
and owner test fixtures. They cannot claim fully integrated acceptance without
coordinator deployment/mounting. Component performance evidence is required in
Phase 4 (not deferred to Phase 8); the benchmark plan defines data and reports,
not expected fabricated performance. Each algorithm must demonstrate its actual
hospital integration after sequential gates, not remain a demo.

Main risks: Redis restart/partition quotas are approximate in fallback; cache
node placement provides no replication; each cache/index request retains a DB
revision read; trie baseline parity needs identical normalization; dedicated ID
connections increase pool budget and reserved ranges cause restart delays;
legacy random IDs have no global collision guarantee; short links cannot recover
QR secrets; route ordering and SPA navigation are coordinator seams; dormant
insurance rows may block constraints; crawler duplicate/revision races need
leases and uniqueness; estimates must never affect payment/discharge authority.
Broker delivery remains deferred, so no invalidation/index dependency on events.
Physical camera, clinical certification, infrastructure HA and measured full
system scalability remain outside Phase 4 acceptance.

## Preparation verification record

See [preparation verification](phase-4-preparation-verification.md) for executed
checks, the unchanged Phase 1–3 source-tree proof and skipped runtime checks.
The record intentionally does not embed its own commit SHA. Final commit and
clean-main status are checked after committing and reported to the user.
