# Phase 2 parallel development plan

Status: Phase 2.0 preparation only. No agents have been launched and no hospital functionality has been added by this phase. The user-defined eight-agent ownership below replaces the historical two-agent scaffold assignment for later explicitly authorized Phase 2 work. It does not edit [AGENTS.md](../AGENTS.md) or authorize starting those tasks now. The [frozen API contract](phase-2-api-contracts.md) is normative for their later work.

## Inspected baseline and findings

Before changes, main was clean at `b88913f` (Phase 1 browser authentication integration). Inspection covered AGENTS.md, README, architecture, service boundaries, database/API/event/security documents and roadmap; Patient authentication/authorization/router/models/migrations; all seven service schemas, routing/settings foundations and migration histories; frontend API/auth clients, auth context, route/layout/page architecture; root Compose, auth overlays and Traefik routes. Findings are source inspection, not fresh runtime verification.

| Existing implementation | Preparation consequence |
|---|---|
| Seven independent packages with empty hospital API routers, health endpoints and owned PostgreSQL metadata | Add business endpoints only inside each owned service; retain health/readiness and packaging |
| Patient register/login/CSRF/refresh/logout/me; RS256 JWT, role/current-authority protocol, signed CSRF, Argon2id and sanitized registration replay | Preserve actual auth and all security regression tests; no replacement identity system |
| IDs currently generated for auth with CSPRNG positive BIGINT and PK collision retry; worker-state storage exists but Snowflake algorithm does not | Phase 2 uses the same bounded CSPRNG/PK-retry approach locally, no guessed worker assignments or collision-throughput claims |
| Patient/Appointment/Records/Pharmacy/Billing/Emergency heads `0003_auth_audit` / `0002_explicit_worker` / `0002_explicit_worker` / `0002_explicit_worker` / `0002_explicit_worker` / `0002_explicit_worker`; Doctor head `0003_explicit_worker` | Append migrations independently; never rewrite the Phase 1 revisions |
| Doctor interval GiST exclusion implemented in `0002_schedule_exclusion`; Appointment patient/slot overlap exclusions explicitly deferred | Agent 3 must implement and prove PostgreSQL exclusions before booking is accepted |
| Outbox/inbox/audit/idempotency tables already exist; no broker publishers/consumers | REST interim workflows, durable unpublished outbox; no fictional event integration |
| Runtime audit tables restricted; Patient auth-only constrained append function supports a fixed action allowlist | Every backend adds its own constrained domain audit function/grants in an owned migration; preserve Patient auth function and permissions |
| Required journey refs exist in Records/Pharmacy/Billing storage, but no journey behavior | Owned additive migrations allow nullable journey refs and explicit appointment/source refs; no dummy journey automation |
| Plural gateway prefixes; private internal routes not routed publicly; isolated credentials and separate migration/runtime roles | No gateway rewrite; internal APIs use existing private service DNS/auth, never a second full Compose stack |
| React/Vite shells, authenticated client with ETag/idempotency options and in-memory auth restoration | Connect owner APIs and forms, preserve layouts/auth; excluded shell pages remain explicitly unavailable |
| Old roadmap assigns booking/records/inventory/emergency to later phases | User's Phase 2 scope and new contracts explicitly override proposed sequencing; advanced roadmap algorithms remain future work |

The initial baseline is source evidence, not permission to regenerate keys, reset data, start containers, install packages or modify deployment during Phase 2.0.

## Common reviewed base and worktree discipline

The **completed Phase 2.0 preparation commit** on main is the common base for all eight future worktrees. Its SHA is recorded in the coordinator's final report; it cannot be embedded into its own commit without circularity. Before dispatch the coordinator resolves that commit once, records the same base SHA in all eight task messages and verifies their worktrees' HEAD equals it. Do not use a moving main as the base after dispatch.

No worktrees or branches are created by this preparation. Later dispatch uses ordinary branches `phase-2/patient`, `phase-2/doctor`, `phase-2/appointment`, `phase-2/records`, `phase-2/pharmacy`, `phase-2/billing`, `phase-2/emergency`, `phase-2/frontend` in distinct worktrees. Agent model labels are the user's requested labels below; coordinator resolves actual supported model identifiers at dispatch rather than guessing which Sol generation was meant.

All eight agents inspect status before edits/commits, stage only owned paths, and report branch/base/latest SHA, migration head, executed checks and unavailable checks. Do not reset, clean or modify another checkout. Main integrator alone reviews/merges complete scoped work later; no implicit merge/push/publication permission. Unrelated pre-existing changes stop that agent's edit until ownership is resolved.

## Exact exclusive ownership and ready-to-dispatch tasks

Ownership is recursive and includes existing/new package code, migrations, colocated tests, README, package metadata, service-local fixture/test helpers and service-local verification records. No symlinks or generated artifacts may write outside the owned prefix. Even authorized local shell commands may not mutate shared files. Agents are forbidden to modify **any** path outside their single prefix.

| Agent / requested model | Exclusive editable prefix | Task and dependencies |
|---|---|---|
| 1 Patient / Luna | `services/patient/**` | Profiles/demographic management; existing-account role/state administration; exact internal status/staff APIs; safe explicit synthetic staff bootstrap helper and domain audit migration; preserve auth. No domain-service dependency. |
| 2 Doctor / Luna | `services/doctor/**` | Doctor/specialty CRUD, trusted user mapping, immutable proposal creation, private proposal/identity leaves, explicit decision reconciliation and deactivation check. Depends on Patient staff/authority leaves and Appointment decision/status leaves. |
| 3 Appointment / Sol High | `services/appointment/**` | Explicit schedule decisions/operational slots, scoped availability/book/cancel/reschedule, clinical holds and billing/assignment leaves. Add actual PostgreSQL exclusions; prove cross-replica correctness. Depends on Patient and Doctor leaves. No waitlists/check-in/queue/journey. |
| 4 Records / Sol Medium | `services/records/**` | Assignment-scoped consultations/history, immutable finalization/amendments, issued/revoked prescriptions, scoped grants and minimal private contexts; durable hold retry/recovery. Depends on Patient, Appointment hold/context and Pharmacy medicine-validation leaf. No queue completion. |
| 5 Pharmacy / Luna | `services/pharmacy/**` | Catalog, stock/batches/adjustments, partial reservations, expiry/revalidation, dispensing/charge leaves and actual stock/allowance concurrency tests. Depends on Patient and Records dispensing-context; catalog validation is independently implementable. No invoice math. |
| 6 Billing / Luna | `services/billing/**` | Immutable tariffs, explicit invoice creation/source import, unique source charges, simulated success/decline ledger and locked balances; minimal references only. Depends on Patient, Appointment/Records/Pharmacy charge contexts. No insurance/refunds or real payments. |
| 7 Emergency / Luna | `services/emergency/**` | Authenticated self submission/tracking, staff priority/claim/release/status/history with atomic leases and scope. Depends only on Patient. No dispatch, anonymous tracking or clinical-priority algorithm. |
| 8 Frontend / Luna | `frontend/**` | Implement frozen clients/types/forms/views in existing workspace shells, owner-scoped reads and explicit multi-step actions; preserve authentication/layouts/accessibility. Uses fixtures until real backends integrate; never simulate a production success. No major redesign. |

Coordinator exclusively reserves `AGENTS.md`, `README.md`, `.gitignore`, root `compose.yaml`/global configuration, `docs/**`, `contracts/**`, `infra/**`, root `tests/**`, `experiments/**`, secrets/env references and all other root paths. No backend edits frontend; no frontend edits backend. Agent 1 owns its existing auth Compose files **for preservation only**: no agent changes any Compose, Docker routing, Traefik, global config, shared credentials, auth keys or deployment topology. Service-local application settings may add bounded dependency URL defaults/private scopes as needed, preserving existing env names; coordinator wires deployment values later. No separate complete Compose stacks, copy of root infrastructure or new shared runtime package.

Each dispatch message must contain: exact prefix/model label/base SHA; task row above; required contract sections/private routes; exclusions; local checks and handoff gates below; instruction to stop at complete service-local work and report integration dependencies. This plan is the prepared task assignment; Phase 2.0 does not send these prompts or launch agents.

## Isolation, coding and contract freeze

- Each backend implements its outbound adapter against exact frozen private schemas. Colocated deterministic fixture transports model valid responses, 4xx, timeout, oversized/invalid JSON and version changes. They are test-only, injected explicitly; production never falls back to fabricated data. No imports from another service package/models and no foreign DB credentials, joins, FDW or dblink.
- Frontend writes its own typed clients and colocated fixtures from the tables; uses `requestWithMetadata` for ETags. Backend agents test schemas using generated FastAPI OpenAPI locally under their owned directories; no writes to shared `contracts/`. Coordinator later collects/diffs specs there. Equal schema names do not imply shared ORM models or forced lockstep deployment.
- Python snake_case/PascalCase classes; TypeScript camelCase/PascalCase components; snake_case JSON, decimal-string IDs, UTC half-open intervals, integer minor units. Preserve existing safe error envelopes, middleware IDs/tracing, independent settings/packaging and readiness rules.
- Local CSPRNG ID helper returns positive signed BIGINT, retries PK collision at most three times, then 503. Domain IDs and request UUIDs are distinct. Every persisted domain entity source key is explicit; no fake event IDs/foreign IDs to fill old required columns. Snowflake/worker replication experiments remain later.
- Owned migrations add tables/indexes/checks/nullable refs/functions and restrictive grants. Run against that domain's DB with its migration role; runtime must lack DDL/audit update/delete and foreign DB access. Never edit applied initial migrations or shared bootstrap SQL. No DROP/clear/reset of Phase 1 auth/domain/audit data. Any backfill is explicit and synthetic, preserves rows and documents upgrade behavior.
- Audit functions use SECURITY DEFINER with fixed search_path, bounded allowlisted nonclinical metadata/actions, revoked PUBLIC execute and only owning runtime grant. Business code cannot bypass them. Patient uses a separate domain chain/function; do not expand auth_append_audit to accept arbitrary clinical payloads. All mutable aggregates have version checks; immutable revisions/tariffs/items are not overwritten.
- Dependency calls are before locks. Preserve Appointment sorted lock order; Pharmacy locks allowance/stock before audit; Billing invoice before audit; Emergency request before audit. A short Records command-preparation transaction may persist the prospective consultation ID keyed by principal/key before acquiring remote hold; it contains no clinical effect or success response. Retry must use that same ID. The final local business/audit/outbox/response transaction remains atomic.
- Frozen contracts cannot be silently edited or interpreted differently. Ambiguity or missing shared config is reported in the owned README/handoff with a proposed change. Implement independent parts using fixtures; affected production integration remains blocked. Coordinator reviews compatibility, updates shared contracts and notifies all consumers before any changed implementation is integrated. Agents never modify AGENTS.md or these docs.
- No new technology, dependency installation, containers, experiments or fixture credentials are authorized by Phase 2.0. Later implementation authorization must specify local verification infrastructure. Dependency declarations/lockfile changes within prefixes need purpose and coordinator review; no universal runtime domain package.

## Cross-service dependencies and integration order

The private route table in [the API freeze](phase-2-api-contracts.md) specifies owner, caller, exact scope/request/response and authorization. Every private context/catalog leaf reads only its own DB and never calls a remote dependency. Dependencies therefore describe endpoint edges rather than a recursively invoked service cycle:

1. Patient current authority/status/staff identity; synthetic admin and staff fixtures for integration.
2. Doctor specialty/profile/catalog and private identity/proposal leaves; Pharmacy medicine catalog/validation leaf; Emergency basic workflows can integrate independently here.
3. Appointment schedule acceptance/decision/status leaves, accepted availability and concurrency-safe booking; Doctor explicit reconcile/deactivation then test end to end.
4. Appointment clinical holds/context plus Records consultations/finalization/grants/prescriptions; Pharmacy medicine-validation contract already available. Prove orphan-hold recovery and finalized historical scope.
5. Pharmacy reservation/revalidation/dispense/charge context using Records live source. Verify stock and quantity correctness before exposing dispense UI.
6. Billing tariff setup, Appointment invoice context and Records/Pharmacy immutable charge contexts; source import and payment gates.
7. Frontend real-owner integration progressively in the same order, then complete gateway/browser journeys and cross-service authorization/contract regression gates. Mock tests can run throughout, but they do not prove integrated behavior.
8. Coordinator collects OpenAPI snapshots, deploys shared settings/routing only if needed, runs root infrastructure/auth verifiers and cross-service tests, updates docs/roadmap and records exact integrated commit/topology. Full event-driven messaging belongs to later reviewed integration, not these independent agents.

Merging whole branches need not follow code completion order if adapters are safely unavailable by default, but exposing any workflow must follow these gates. Records/Pharmacy bidirectional names are safe because validation and dispensing-context endpoints are leaves. Doctor reconcile -> Appointment decision is a separate public operation from Appointment acceptance -> Doctor proposal. No synchronous callback recursively reenters a dependency.

Local domain transactions provide strong stock/booking/payment/claim/record-version correctness. Profile/schedule display acknowledgements and multi-owner state converge through explicit retries/reconcile, not automatic event delivery. Patient authority checks and prescription validations have remote revocation race windows. Orphan clinical holds favor safety over availability. Billing imported balance is not automatic proof of all consultation/medicine charges. These are explicit integration limits, not hidden promises.

## Frontend page mapping

Use the existing workspace navigation and layouts. Add forms/data components inside these pages; a profile editor can live on patient dashboard rather than introducing a new visual system. Role hints control navigation only; every API remains server-authorized.

| Existing page group | Frozen functionality |
|---|---|
| Patient dashboard/doctors/appointments | GET/PATCH me, specialties/directory, accepted availability, own booking list and book/cancel/reschedule forms |
| Patient records/prescriptions | Own history, consultation/record detail, prescription list/detail, scoped historical-access grant form |
| Patient pharmacy/billing/emergency | Own reservations and release, medicine directory, invoice/payment views and simulated payments, request submit/tracking |
| Doctor dashboard/consultations/prescriptions | GET doctors/me; own profile name/schedule proposal/decision/reconcile controls; assigned appointment list; create/edit/finalize consultation and amend/revoke own documents |
| Pharmacist inventory/prescriptions | Catalog/stock forms, prescription ID lookup, reservation/revalidation/dispense forms; only minimum prescription view |
| Billing invoices/payments | Tariffs, create invoice by appointment ID, explicit consultation/dispensing ID import, invoice and payment list/detail; no clinical notes |
| Emergency requests | Staff request list/details, priority, claim/release and permitted transitions |
| Admin staff/doctors | Patient user role/account management; specialty/doctor administration and schedule acceptance controls; demographic management on dashboard |
| Reception appointments/dashboard | Authorized demographic lookup/update and patient-ID booking/cancel/reschedule |
| Waitlist/check-in/queues/journey, insurance, ops and unimplemented admin settings | Keep existing routes/layouts with explicit future/unavailable states and no Phase 2 command or fabricated data |

Frontends fetch profile ID from GET me (not user sub), doctor ID from GET doctors/me, and latest ETags through requestWithMetadata. Staff source-ID entry/import is explicit and owner-validated; IDs are never authorization. Backend failures or test fixtures cannot create UI success in production. Existing home/login/register layouts and session behavior are preserved.

## Acceptance criteria for later implementation

These are measurable future gates; none is reported as passed by Phase 2.0. Use real PostgreSQL for locks/exclusions/unique constraints, at least two independent app instances/connections for relevant races, and synthetic data only. Colocated tests must be deterministic and assert persisted row/ledger counts and balances, not only HTTP statuses. Coordinator runs cross-service scenarios against the single reviewed Compose project. No performance threshold is invented.

| Area | Required pass conditions |
|---|---|
| Patient management | Self/admin/receptionist profile fields round-trip; no role/account changes through profile PATCH; wrong owner 404; invalid fields 422; one of two same-version edits succeeds and other 412. Role/state updates increment user/auth versions, revoke sessions and prevent privileged stale-token mutations; last active admin and self-disable protections hold under two concurrent admin commands. |
| Doctor management | Specialty/mapping uniqueness on real DB; inactive/non-doctor target rejected; self cannot change active/specialties; missing JWT doctor_id cannot grant access; proposals immutable, one pending per doctor, correct revision/ETag; rejection preserves accepted availability and reports conflicts; reconciliation recovers lost response; deactivation with live slots/bookings rejected. |
| Appointment booking | Slot generation exactly matches accepted proposal; inactive/missing patient/reference rejected; booking reads locked accepted revision, not cached availability; own/receptionist scope and doctor list scope enforced; cancelled booking releases capacity without waitlist; reschedule keeps same ID and original booking survives target conflict. |
| Concurrent booking correctness | Launch 50 distinct-key requests across two instances for one slot: exactly one committed confirmed booking/201, all others 409; concurrent equal-key requests return one identical outcome. Two different-doctor overlapping patient slots yield exactly one active booking; adjacent intervals both succeed. Racing closure/booking, cancel/book and cross-doctor reschedules preserve exclusions and lock order; bounded deadlock recovery produces no partial moves. PostgreSQL constraint tests directly reject bypass inserts. Redis/broker availability is irrelevant. |
| Medical records | Wrong doctor/unrelated patient/admin/pharmacist cannot read notes or prescribe; current assigned author can create exactly one consultation per appointment. Draft edits fail after finalize. Finalize creates exactly one immutable record and optional immutable prescription atomically; rollback leaves no partial record/outbox/audit/response. Invalid/inactive medicines rejected; revoke is durable. Active hold blocks cancel/reschedule races; interrupted hold acquisition recovers with same consultation ID; finalized hold ends broader historical access; grant expiry/revoke denies access. |
| Pharmacy inventory | Adjustment never makes on_hand<reserved; expired stock excluded; FEFO allocation correct. For stock 10, 50 competing one-unit reservations across two instances commit at most 10 reserved units and no negative availability. Different reservations for one prescribed item never exceed prescribed total. Duplicate dispense yields one immutable dispensing/deduction/charge-source set; racing expiration/release/dispense applies once. Revoked source fails new fulfillment; revalidate releases unfilled stock once; outage never treats cached prescription as current. |
| Billing | Invoice unique per appointment; only verified finalized consultation/completed dispensing contributes charges; wrong patient/appointment sources rejected atomically. Repeated import creates one charge per lifetime source key with immutable tariff price; missing tariff creates no charge. With balance 100, two concurrent 100-unit success requests yield one success and one 409; same-key payment replay has one ledger effect. Decline leaves paid balance unchanged, increments invoice version; currency/overflow/negative/real-card payload rejected; later verified import reopens paid invoice. |
| Emergency | Patient cannot submit for another or choose priority/staff; staff views omit clinical history. For two staff racing same-version claim, exactly one assignment commits (other 412 or state conflict); 50 distinct-key attempts still have one claim owner. Expired lease cannot start processing; normalization appends history once; release/reclaim follows states; unrelated staff cannot resolve; terminal requests cannot reopen; reads do not mutate. |
| Frontend integration | Existing registration/login/refresh/logout/reload/route restrictions still pass. Each new form uses exact wire schema and correct key/ETag. Every connected page has loading/empty/error/success states, stale conflict recovery and no fabricated production data. Real gateway flow: patient profile -> doctor discovery/accepted slot -> book/reschedule/cancel; staff schedule submit/decision/reconcile; assigned doctor finalize -> pharmacist dispense -> billing import/pay; emergency submit/claim/resolve. Retry ambiguous POST preserves body/key; decline shown as committed decline; unavailable owner does not report success. |

Every backend also requires:

- Authorization matrix tests for missing/expired/invalid signature/wrong issuer/audience, inactive/revoked current authority, cross-owner IDs, wrong roles, forged delegation, wrong service caller/scope/key/audience and user-only calls to private routes. Test leaf routes do not broaden clinical scope.
- Database migration upgrade from current Phase 1 head and empty DB; retained auth/audit rows; own runtime CRUD/append privileges and denied DDL/audit tampering/foreign DB access. No mocked database assertion counts as proof of constraints or atomicity.
- Idempotency same-key race/replay/body mismatch, stale/missing If-Match, rollback/restart after committed response, and duplicate source keys. Inject dependency failure before local transactions and verify no clinical/inventory/money effects; document remote committed holds separately.
- Exact request/response/status/header/pagination/filter checks against the freeze, including decimal-string IDs, unknown fields, safe money bounds, resource-concealing denial and cursor scope. Locally inspect generated OpenAPI and verify every owned public/private route.
- Existing service tests unchanged in intent and passing, plus service-local README/run instructions and actual executed/skipped-check report. Patient includes real PostgreSQL auth regression when infrastructure is authorized. Frontend includes existing tests, typecheck, build and accessible keyboard forms.

Coordinator integration additionally checks real delegated private calls, gateway internal-route denial, migration privileges with shared topology, all existing root infrastructure/auth verifiers and browser authentication journey. Later event reliability tests are required when broker consumers are implemented; duplicate/out-of-order broker delivery is **skipped as unimplemented** here, not mocked into a Phase 2 delivery claim. No load/chaos containers or destructive resets without explicit later scope/stop/recovery plan.

## Known risks and coordinator responsibilities

| Risk/conflict | Required mitigation/owner |
|---|---|
| Older AGENTS two-agent notes and roadmap differ from eight-agent Phase 2 scope | Explicit current user instructions and this frozen plan take precedence; coordinator owns future shared updates |
| Existing audit grants do not permit direct append, auth function accepts auth actions only | Service-owned domain audit migration/function; coordinator verifies permissions rather than relaxing shared grants |
| Existing schema includes unimplemented journey and event refs | Owned nullable/ref migrations, retained old rows; no fake IDs; coordinator reviews compatibility/backfills |
| btree_gist/pgcrypto extension privileges may vary on target DB | Agent reports migration requirement in owned README; coordinator configures prerequisites later, never agent edits bootstrap/Compose |
| Different worktrees share ignored-key relative paths and Compose project/volumes | Agents do not copy/regenerate secrets or launch full stacks; coordinator owns runtime checkout, single topology and environment wiring |
| Shared DB service-test fixtures can collide | Distinct synthetic IDs/test namespaces; service-owned test DB only when provisioned; coordinator serializes migration/global-runtime checks |
| Schedule decisions and Doctor pending status can diverge after interruption | Explicit GET decision/reconcile; one pending proposal blocks unsafe replacement; no event-delivery fiction |
| Durable orphan clinical hold after Records failure | Persist stable prepared consultation ID; replay safely; coordinator reviews owner absence before any release; no time-based automatic unlock |
| Records finalized but hold remains active after downstream outage | Retry explicit finalize-hold, verify state; coordinator treats recovery as integration gate, no false Appointment completion |
| Remote account/doctor/prescription revocation between checks/commit | Fail closed on unavailable checks; current scope validation and explicit reconciliation/staff review; no global revocation guarantee |
| Billing ignores sources not explicitly imported; later charge reopens balance | Manual source selection/import displayed clearly; stable source keys; no discharge/all-charges-complete claim |
| Eight implementations choose divergent schemas/errors/pagination/auth | Freeze and colocated contract fixtures now; coordinator diffs specs and runs producer-consumer checks before exposure |
| Model label Sol is generation-ambiguous | Preserve user labels; resolve configured supported generation at dispatch without changing ownership or effort |

## Phase 2.0 verification and stop boundary

Preparation checks are documentation/source consistency, local Markdown link targets, schema/route table completeness, eight disjoint prefixes, common base rule, `git diff --check`, documentation-only changed paths, local main commit and clean final tree. Executed preparation checks: 8 local Markdown link targets exist; 16 Markdown tables have consistent column counts (including escaped enum unions); 75 method/path table rows use versioned public/private prefixes; code fences are balanced; all eight ownership prefixes exactly match the requested disjoint directories; branch is main; only these two new documents are present and tracked Phase 1 files are unchanged; `git diff --check` passes. A separate source cross-check verifies all seven gateway prefixes, migration heads and existing authentication route names. These checks validate documentation structure and selected source consistency, not formal schema completeness or runtime behavior. Final commit/clean-tree verification is recorded in the final report. Runtime tests, database migrations, containers, application builds, browser workflows, performance and Mermaid rendering are not executed by this preparation and must not be reported as passed.

The preparation commit is ready as a shared starting point for eight independently authorized worktrees. It is not a claim that Phase 2 APIs already work or that integrated functionality is verified. Stop after Phase 2.0; no agent dispatch, worktree creation, dependency installation, deployment, remote creation or push.
