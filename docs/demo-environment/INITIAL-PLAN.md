# Phase 11 rebuild checkpoint

## Selected target and safety boundary

The user designated the existing `pulsegrid` Compose project on `127.0.0.1:8080`. The independent `pulsegrid-audit-20261025` project is retained for Phase 10 evidence. Phase 11 reset only the selected project's PostgreSQL, Redis, RabbitMQ and two Phase 4 cache volumes. Prometheus, Tempo and Grafana volumes remain in place. Source, migrations, tests, Git history and audit evidence were not part of the reset.

Before reset, the nine PostgreSQL database archives were restored into an isolated PostgreSQL 16 container on `--network none`, without a published port. The final quiescent snapshot restored all nine databases, counted all 112 public tables and validated all 66 foreign keys. Redis, RabbitMQ and both cache volumes were stopped and archived; each archive passed checksum and extraction checks. The old `.env`, Patient signing material and Phase 4 Redis ACL/configuration files were separately archived and hash-verified. Archive contents and exact pre-reset table counts are in the private manifest outside the repository at `/Users/aakash/.codex/backups/pulsegrid-phase11/20261025T101732Z/private-deletion-manifest.json`.

The final dependency dry run named exactly five target-owned data volumes for retirement, three monitoring volumes to preserve, and the separate Phase 10 PostgreSQL volume to preserve. It also confirmed the target gateway project labels and the target-only Compose configuration files. Only after this check, the local `.env` passwords were rotated and the guarded reset was executed with the literal target confirmation.

## Current checkpoint

- [x] Confirm exact `pulsegrid` target and Phase 10 namespace/volume separation.
- [x] Inventory target databases, runtime volumes, services, port ownership and cross-service identifiers.
- [x] Back up and restore-verify PostgreSQL; archive/verify Redis, RabbitMQ, cache volumes and old local configuration.
- [x] Produce and execute the target-only dry run/reset; preserve the observability volumes and Phase 10 project.
- [x] Recreate the seven service databases with the existing migrations; verify all migration jobs and service readiness.
- [x] Seed owner records through the APIs; verify exactly eight enabled accounts, 40 patients, 20 doctors, 50 medicines, 43 appointments, 4 consultations, 3 prescriptions, 3 emergencies and 3 invoices.
- [x] Remove the temporary loopback PostgreSQL bootstrap port and rerun owner-API login and roster checks after a full application restart.
- [x] Run the Patient PostgreSQL regression, all 159 frontend tests, TypeScript/build checks, and live patient/pharmacy browser checks.
- [x] Fix browser cohort filters that hid current doctor and medicine records when seeded IDs/SKUs did not match presentation metadata.
- [x] Document backup, cleanup, reproduction and hosting boundaries; inspect and commit only Phase 11-owned changes locally.

Read-only browser logins covered all eight roles after restart: Patient doctor directory/records, Doctor schedule workspace, Receptionist patient directory, Pharmacist inventory, Billing invoices, Emergency cases, Administrator patient/medicine directories, and Operations Control Room. The Patient page displayed all 20 doctors and specialties, and the records page displayed the authorized consultation and prescription. Browser verification used the real Vite same-origin proxy; the API verifier also authenticated all eight accounts.

## Reproducibility and constraints

`infra/scripts/phase11_rebuild_local.py` defaults to a dry run. Destructive reset requires a verified private manifest, exact Compose ownership, isolated Phase 10 resources and both `--execute` and `--confirm-target pulsegrid`. Its readiness marker binds seeding to the new PostgreSQL volume creation time. `infra/scripts/phase11_seed_demo.py` uses stable idempotency keys and a mode-0600 checkpoint, and creates identities and domain records through owner APIs, except for the existing local-only Patient first-administrator bootstrap. It accepts loopback HTTP only. The local demo password is held only in ignored `secrets/phase11/credentials.json` and is not a production credential.

Do not run reset against another project or use either helper against public deployment infrastructure. Hosted deployment still needs its own securely provisioned first administrator and strong per-account secrets; no public host or cloud deployment has been configured or tested in this phase.

See [the cleanup report](CLEANUP-REPORT.md) for backup/reset evidence and exact seeded counts, [the local demo guide](README.md) for guarded reproduction commands, and [the Vercel/Render guide](../deployment/vercel-render.md) for the remaining hosted bootstrap gate.
