# Phase 11 rebuild and cleanup report

## Result

The existing `pulsegrid` project on `127.0.0.1:8080` was rebuilt from fresh storage for all seven service databases. The agreed fictional dataset was seeded through the existing owner workflows. The isolated `pulsegrid-audit-20261025` Phase 10 stack and its PostgreSQL volume remain present. No GitHub push or cloud deployment was made.

## Backup and target verification

The pre-reset PostgreSQL snapshot and runtime state are archived outside the repository at `/Users/aakash/.codex/backups/pulsegrid-phase11/20261025T101732Z`. Nine PostgreSQL archives, including the seven service databases and supporting databases, were restored in a temporary PostgreSQL 16 container on an isolated Docker network with no published port. Verification counted 112 public tables and validated all 66 foreign keys; all archives restored. The Redis, RabbitMQ and two cache-volume archives passed checksum and extraction checks. The old local environment, signing material and cache configuration were archived and hash-verified.

Before the reset, the service databases contained 10,116 Patient rows, 647 Doctor rows, 744,176 Appointment rows, 612,121 Records rows, 256,618 Pharmacy rows, 736,370 Billing rows and 137 Emergency rows. The exact per-table manifest is private and is retained beside the backups. The target-only dry run confirmed the `pulsegrid` gateway, its Compose configuration and five target-owned data volumes. It preserved the three monitoring volumes and the Phase 10 audit project/volume. The destructive reset was executed only after these checks and an exact `--confirm-target pulsegrid` argument.

The baseline had four durable RabbitMQ queues with zero queued messages. The Redis ACL denied key-count/INFO inventory commands, so an exact old Redis key count could not be recorded. The complete target-owned Redis volume was archived and recreated instead; no old Redis volume was reused. PostgreSQL outbox/inbox and audit tables were recreated by owner migrations, rather than truncated or edited across domains.

## Fresh dataset

After migration and owner-API seed, the local API verifier returned these counts after a full application restart:

| Owner/API view | Count |
| --- | ---: |
| Enabled login accounts | 8 |
| Disabled schema identity accounts | 59 |
| Patient profiles | 40 |
| Active doctor profiles | 20 |
| Appointments | 43 |
| Consultations | 4 |
| Prescriptions | 3 |
| Medicines | 50 |
| Inventory batches | 50 |
| Pharmacy reservations | 2 |
| Invoices | 3 |
| Emergency cases | 3 |

The eight enabled logins are `patient@pulsegrid.demo`, `doctor@pulsegrid.demo`, `reception@pulsegrid.demo`, `pharmacy@pulsegrid.demo`, `billing@pulsegrid.demo`, `emergency@pulsegrid.demo`, `admin@pulsegrid.demo`, and `ops@pulsegrid.demo`. Each has exactly its intended role. All eight authenticated successfully in the post-restart verifier. The local shared password remains in the ignored credential file and is not reproduced here.

The Pharmacy outcomes include one dispensed and one still-reserved prescription; Billing includes one fully paid invoice and a declined payment scenario; Emergency includes a case in processing. Four consultations and three prescriptions were created through Records workflows. One consultation and one prescription are visible to the patient demo account under current grant rules. Patient/doctor/medicine name sets returned by the owner APIs exactly match the 40-, 20- and 50-entry seed rosters; no additional old records are returned.

## Restart and application verification

The temporary `55433` host-port mapping was removed. The Compose application was stopped and recreated with the normal authentication, Phase 4 and observability overlays, retaining its rebuilt volumes. All seven migration jobs exited successfully and the seven APIs, gateway, PostgreSQL, Redis, RabbitMQ and Phase 4 caches returned healthy. Patient readiness returned HTTP 200. The Phase 10 project and `pulsegrid-audit-20261025_postgres_data` remained present.

The real Vite frontend used the same-origin `/api` proxy to the rebuilt gateway. A patient browser login reached `/patient/doctors`; its live Doctor API initially had 20 profiles, but stale presentation-ID filters hid them. The same presentation filter also hid owner records whose `PG-DEMO-*` SKUs did not match the old `DEMO-*` prefix. Those filters were removed while retaining the approved department layout and optional portrait metadata. The reloaded Patient page displayed all 20 doctors and 20 specialties, live availability and the patient-visible visit. The patient-authorized records page showed the consultation and issued prescription. The Pharmacist Inventory page displayed current generic medicines and an inventory batch.

Read-only browser login and workspace checks covered all eight roles: Patient (doctor directory and records), Doctor (profile and accepted/rejected schedules), Receptionist (patient directory), Pharmacist (inventory), Billing staff (three invoices, paid/unpaid balances and line items), Emergency staff (three synthetic cases), Administrator (patient and medicine directories), and Operations (7/7 service readiness and live component summaries). No domain mutations were submitted during these browser checks. The post-restart owner-API verifier covered the exact account set and cross-service reference checks listed above.

The Patient-owned user directory now excludes staff identities from the patient-profile list by checking the Patient-owned role assignment. Its PostgreSQL regression fixture confirms a receptionist identity is not returned as a patient. This preserves the service ownership boundary and keeps staff accounts out of patient search results.

## Checks recorded

- `python3 infra/scripts/phase11_seed_demo.py --check-only`: 40 patients, 20 doctors, 50 medicines and all eight role identifiers.
- `python3 infra/scripts/phase11_seed_demo.py --verify-existing`: passed after restart; exact active and disabled account counts, roster names, API counts, doctor self-profile, appointment/patient/doctor references, invoice/patient/appointment references, emergency/patient references, consultation/prescription/medicine/reservation references, payment outcomes and processing emergency state.
- Patient PostgreSQL tests against a disposable loopback PostgreSQL 16 database: **12 passed, 1 deprecation warning**.
- Frontend Vitest: **159 passed in 12 files** after the directory/catalog filtering fix.
- Frontend TypeScript check and production build: passed. The build used the regular API-connected application, not mock fixtures.
- Browser: real patient doctor directory and pharmacist inventory loaded through Vite's live API proxy after restart.
- Local Vercel configuration validation: HTTPS-only server-side backend origin and API/short-link rewrites. No Vercel or Render deployment was attempted.
- Python compilation, guarded seed size check, and final Git whitespace check: passed.

## Remaining gates

The dataset and application rebuild are verified for this local Compose demo. Hosted bootstrap is still a deployment gate: there is no Render service/database setup, secure hosted first-administrator procedure, separate hosted account credentials, live HTTPS/CORS/secure-cookie test, or production restore test. The local seed/reset guards intentionally reject public targets. The public deployment therefore remains **PARTIAL**, even though the local rebuild and its scoped regression checks passed. The [deployment runbook](../deployment/vercel-render.md) lists the remaining operator decisions.
