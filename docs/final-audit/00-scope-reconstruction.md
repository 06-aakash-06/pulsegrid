# Scope reconstruction from project history

Review date: 25 October 2026. Baseline: local `main`, `99fd31bce9001e48e7521b69d14551bae6d90dda`. The tree was clean before this review. This reconstructs settled intent before the attached audit/repair campaign. Subsequent runtime findings and the bounded final verdict are in [FINAL-VERDICT](FINAL-VERDICT.md). Historical scope reconstruction is complete within the accessible-history limits; exhaustive acceptance remains PARTIAL.

The [source register](05-history-source-register.md) identifies 42 Codex chats, 87 available turns, 92 user messages and ten historical pasted briefs. It also records the limited accessible ChatGPT context. No assumption is made that unavailable private teammate discussions or earlier ChatGPT content have been recovered.

## How requirements were decided

An explicit user requirement or approved phase extension establishes intent. Later explicit decisions and frozen integration contracts resolve older alternatives. An assistant plan, possible candidate, illustrative payload or reference image alone does not establish a new capability. Implementation establishes presence, not authorization or correctness. Historical test reports establish what was reported at that commit; they do not establish current runtime success.

Where an original target was narrowed for a phase without an explicit permanent cancellation, this report preserves the broader target as deferred or uncertain. It does not silently erase it or convert it into an immediate repair requirement. Current evidence is separated in the [matrix](02-feature-traceability.md) and [baseline results](03-baseline-results.md).

## Settled product and engineering scope

PulseGrid is a synthetic, single-hospital educational system. Its seven independently owned domains are Patient, Doctor, Appointment, Records, Pharmacy, Billing and Emergency. The original H34 brief requires real integrated workflows, all seven system-design components, local transactional correctness, authorized owner APIs, resilience, telemetry and reproducible measurements. It excludes multi-hospital networking, emergency bed management and family profiles.

| Domain | Finalized functionality | Important interpretation |
|---|---|---|
| Patient | Registration/login/logout, rotating sessions, own profile editing, authorized patient directory, staff/account/role administration, audit | Staff administration is identity/roles/account state, not workforce or bed scheduling. |
| Doctor | Directory, specialties, search/autocomplete, profiles, own/admin updates, schedule proposals and reconciliation | Doctor proposes; Appointment accepts/materializes operational slots. Availability comes from Appointment. Working/unavailable periods are represented by accepted intervals, not a separate invented leave subsystem. |
| Appointment | Availability, patient/receptionist booking, cancel/reschedule, details/history, conflicts, persisted idempotency, short links | Walk-in means booking an existing registered patient into an accepted slot; it does not authorize anonymous registration or bypass check-in. |
| Waitlist | Fully booked slot enrollment, FIFO eligibility, withdrawal, durable promotion, temporary offer, accept/decline/expiry and next offer | H11 explicitly extended the first freeze to include offers. Immediate automatic confirmation described in older architecture prose is superseded by the offer lifecycle. |
| Check-in/queue | Opaque expiring single-use QR credential, revocation on booking changes, manual fallback, daily tokens, own position, doctor queues, FIFO start, skip/recall, no-show/history | Polling is explicitly acceptable. A WebSocket/SSE requirement must not be invented. Physical camera decoding remains a separate unverified acceptance item. |
| Journey | Durable episode stages/history, versioned owner snapshots, optional prescription/pharmacy stages, reconciliation, pending/unknown/review states and authorized discharge | Original journey culminates in discharge. Zero invoice balance is insufficient without acknowledged expected charges. Registration need not create a synthetic journey before an appointment exists. Follow-up may use a new booking; no separate automated follow-up engine was finalized. |
| Records | Draft consultation creation/editing, finalization, immutable record revisions/amendments, history/visit detail, prescriptions/revocation, scoped grants/revocation | Clinical content is summary/assessment/plan and issued instructions. References do not add labs, imaging, vitals, treatment or diagnostic decision support. |
| Pharmacy | Catalog/search/autocomplete/maintenance, batches/expiry/stock, reservations, live prescription validation, revalidation/release, dispensing/history, minimum fulfillment snapshots and charge contexts | Prescription allowance, FEFO stock selection and duplicate protection remain owner transactions. This is not a retail cart, upload shop or independent prescribing system. |
| Billing | Tariffs, invoices/history/details, authoritative consultation/dispensing charge imports, exact minor-unit totals, simulated payments/history, source deduplication, fixture insurance estimates and refresh | No payment gateway, refunds, discounts, arbitrary lab/procedure/custom charges or insurer adjudication was finalized. Manual owner-source imports are intentional. An estimate must not change authoritative invoice/payment totals. |
| Emergency | Authenticated patient request/cancel/read, staff list/priority/claim/release/process/resolve, lease/version/concurrency protection and history | Staff assigns priority. No predictive triage, real dispatch, admission/bed management or clinical reliability claim. The older anonymous tracking proposal is not the current Phase 2 request contract. |

## Architecture and correctness commitments

- Each domain owns its database, credentials, migrations, models and local audit chain. No cross-database queries or global transactions.
- PostgreSQL transactions, constraints and documented locks enforce booking, stock, payment and audit correctness. Redis admission/cache cannot authorize or reserve a slot.
- Retryable domain commands persist idempotency outcomes; aggregate mutations enforce versions. Token-issuing/auth flows have their own explicitly documented replay rules.
- Clinical and financial integrations use bounded authenticated owner APIs with delegated user scope and explicit source-version gaps. No database locks span network calls.
- At-least-once RabbitMQ delivery uses transactional outbox, durable inbox/effects, acknowledgement after commit, retry/DLQ and reconciliation. Events wake fresh owner reads and do not independently authorize discharge, payment or dispensing.
- Patient authority remains current on privileged writes. JWT/CSRF/refresh rotation, ownership/care/grant checks, minimum disclosure and safe telemetry are requirements.
- Optional telemetry failure must not stop hospital operations. Shared infrastructure remains a prototype failure domain; API replicas do not establish infrastructure HA.

## Seven required components, with actual adoption boundaries

| Component | Settled integration | What must not be inferred |
|---|---|---|
| Distributed token bucket | Redis atomic admission, identity-aware budgets and failure profiles across seven services | No unlimited emergency bypass, spoofable public priority or client-chosen class. |
| Consistent hashing | Virtual-node ring routes Doctor directory cache projections across cache Redis nodes; topology epoch namespaces cached content | Placement is not replication, live migration or automatic failover. There is no requirement to shard every service's business data. |
| Key-value/cache-aside | Redis projection cache, owner revision/TTL/invalidation and PostgreSQL fallback | No obligation to cache sensitive records or use stale cache as business authority. |
| Snowflake IDs | Additive use for new short links and Billing insurance run/rule/estimate resources; durable worker ranges/leases and rollback safeguards | H08 and the Phase 4 freeze preserve existing entity/audit/outbox identifiers. Not using Snowflake for every entity is intentional. |
| URL shortener | Authenticated appointment/check-in navigation aliases with expiry/revocation and safe fixed destinations | A short alias never authenticates a user or restores/bypasses a single-use QR credential. |
| Insurance crawler | Bounded asynchronous crawl of allowlisted synthetic fixtures, durable requested runs/recovery, immutable rule provenance and informational estimates | No arbitrary web crawler or real insurer connector. Periodically processing pending runs is not the same as periodically scheduling new provider refreshes. |
| Trie autocomplete | Doctor names/specialties and medicine prefixes; normalized/deduplicated deterministic suggestions, revision rebuild and DB fallback | The trie need not always outperform the baseline; oversized catalogs may deliberately fall back. |

## Decisions that changed during development

| Earlier discussion or plan | Later evidence and final treatment |
|---|---|
| Original roadmap assigned later numbers to cache/autocomplete, telemetry and final evaluation | H10/H11/H09 and A08/A07/A04 changed execution order: core hospital Phase 2, advanced workflows Phase 3, algorithms Phase 4, events Phase 5, resilience Phase 6, observability Phase 7, evaluation Phase 8, frontend Phase 9. Old roadmap numbering is not a second missing feature set. |
| Phase 1 documentation-only restrictions | Apply to that historical phase. They do not imply the current implemented repository is unauthorized or must be rolled back. Current task restrictions still apply. |
| G1 freeze omitted temporary offers and queue skip/recall | H11's G2/G3/G4 request explicitly restored both requirements. Current code and mounted APIs contain them. |
| Booking response `journey_id` and lifecycle proposals | Phase 3 preserves strict v1 confirmed/cancelled booking semantics and adds separate operational `/workflow` and journey resources. A null v1 journey field is not by itself a missing journey. |
| Broad initial event catalog including appointments, schedules, notifications and insurance | A10 deliberately selects two or three paths. Final Phase 5 implements Pharmacy dispense and Billing payment to Appointment reconciliation. Other catalog entries remain proposals/deferred; no generic notification microservice was approved. |
| Automatic Surge activation | A09 allowed a manual fallback if safe shared signals were absent; A08 explicitly prohibits automatic activation without separate review. Manual NORMAL/SURGE/RECOVERY is the current accepted scope. |
| Breakers/retries throughout all dependencies | Final resilience design places additional breakers/bulkheads on optional Appointment owner-snapshot reads. Auth, bookings, money and stock remain fail-closed owner operations; blindly retrying mutations is not required. |
| Full tracing-enabled/repeated performance campaign | A05 narrows the final Doctor matrix to exactly six matched tracing-disabled trials, with Prometheus/auth/admission preserved and tracing restored afterward. It does not complete every earlier workload or stability goal. |
| First Phase 9 generic cream/card layouts | Explicitly rejected in H37. Reception and Consultation were subsequently approved. The user then authorized all seven remaining departments, superseding the two-screen stop point. |
| Pharmacy marked unfinished in an older resume report | Later merged Phase 9 changes rebuild the cabinet/counters and add audit fixes. Do not reimplement an old checkpoint blindly. Current visual acceptance still needs a fresh browser gate. |
| Registration failure described as duplicate email/backend availability | Later `b2d3e3a` distinguishes real API errors and implements persistent browser-local demo registration. Static demo and real backend remain separate execution modes. Neither proves the other's workflows. |
| Earlier permission to push after fixes | Current audit brief says DO NOT PUSH. Historical publication instructions are evidence of chronology, not current publication authority. |

## Deferred targets and ambiguity that history exposes

1. **Hash-ring visualization/cache distribution:** H34 explicitly envisioned this in the Control Room. The final UI exposes ring epoch/configured-node counts and a service-topology diagram; it does not show virtual-node positions or measured cache-key distribution. Later Phase 7 requirements emphasize relevant metrics rather than the original detailed ring display. Preserve this as an unresolved original design target, not an urgent defect or permanently excluded feature.
2. **Live resource/emergency processing metrics:** H34 envisioned resource and emergency processing telemetry. Phase 7's infrastructure dashboard explicitly states no portable resource exporter is configured. Generic Emergency HTTP metrics exist; dedicated business processing-time/priority/backlog views were not identified in the bounded Control Room API. Resource export and more detailed emergency metrics remain partial/deferred telemetry goals, not permission to fabricate values.
3. **Periodic provider refresh:** H34 calls for periodic extraction. The frozen Phase 4 interface implements operator-requested provider refresh and a five-second pending-run worker. No periodic producer of new refresh runs was found in the inspected Billing composition. Whether scheduled refresh remains desired beyond this narrower contract is uncertain; do not confuse worker polling with delivery of this earlier target.
4. **Backup/restore/soak and broader evaluation:** These occur in the original roadmap, while later measurement campaigns are explicitly bounded. The Phase 8 reports remain partial beyond the completed Doctor matrix. No complete backup/restore or universal production stability claim is justified.
5. **Grant management across reload:** Creation and DELETE revocation are implemented. The frozen Records API has no grant list/detail endpoint; the UI retains the newly issued grant only while open. A persistent management screen would require an additive contract decision. This is a known usability/contract limitation, not a forgotten GET promised by the freeze.
6. **Standalone hospital settings, medicine categories, anonymous emergency tracking and automated follow-up:** Older generic language or proposals do not settle schemas or authorized operations. Current contracts respectively provide administration links, name/SKU catalog, authenticated requests and existing booking. Treat extensions as uncertain/proposed until explicitly agreed.

## Current reconciliation outcome

No feature is labelled working merely because its route or component exists. The current review found real implementation paths for all seven algorithms and the advanced waitlist/QR/queue/journey requirements. Doctor history/amendments are reachable through `Prescriptions doctor` → `RecordsPage doctor` at `/doctor/prescriptions`; a top-level router-only search would incorrectly report them missing.

The strongest current executed evidence is 159 passing frontend tests, a passing production build/typecheck, all eight API process readiness checks, current service-source hash equality, mounted OpenAPI inventory and three sampled unauthenticated 401 responses. It does not verify every role, data mutation or concurrency invariant.

Tempo is currently ready with a 512 MiB cap and restart count 4, but the sampled recent logs still contain scheduler warnings/errors. That observation does not resolve its historical restart cause or prove long-term stability. Physical QR decoding, fresh all-role browser acceptance, isolated patient/staff E2E, backend/DB regressions and controlled recovery remain verification work, separated from scope gaps in the [register](04-issue-register.md).

The subsequent authorized campaign repaired waitlist transport wiring, offer expiry scheduling, staff navigation/contrast and RabbitMQ dead-letter setup. It used separate synthetic databases/networks/volumes for mutations and failures. The retained stack received only the repaired Appointment image and narrow broker ACL change; no retained business records, credentials, schemas or volumes were reset. Local commits were made on `main`; nothing was pushed. See [issues](04-issue-register.md), [execution](03-baseline-results.md) and [infrastructure](08-infrastructure-and-observability.md).
