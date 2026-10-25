# Rebuilding the local Phase 11 demo

This procedure is for a **dedicated loopback development stack**. It is not a hosted seed tool. It resets the selected `pulsegrid` Compose data volumes after requiring a verified private backup, exact Compose ownership and a literal target confirmation. Never run it against Render, a public URL, or another Compose project.

## Current local accounts

The current rebuilt dataset has exactly eight enabled logins, one per role. The shared local-demo password is held only in the ignored `secrets/phase11/credentials.json`; this repository does not contain it.

| Role | Login |
| --- | --- |
| Patient | `patient@pulsegrid.demo` |
| Doctor | `doctor@pulsegrid.demo` |
| Receptionist | `reception@pulsegrid.demo` |
| Pharmacist | `pharmacy@pulsegrid.demo` |
| Billing staff | `billing@pulsegrid.demo` |
| Emergency staff | `emergency@pulsegrid.demo` |
| Administrator | `admin@pulsegrid.demo` |
| Operations | `ops@pulsegrid.demo` |

The application has 40 patient profiles and 20 doctor profiles. Additional schema identities needed for those owner records are disabled for login. The local shared password is for this loopback demo only; hosted accounts must use eight separate strong credentials outside Git.

## Guarded reproduction

Start with the [root local setup](../../README.md#run-locally), retain the ignored local `.env` and signing material for the current installation, and confirm that the target gateway belongs to the `pulsegrid` Compose project on `127.0.0.1:8080`. The reset helper's default is a read-only dry run:

```sh
python3 infra/scripts/phase11_rebuild_local.py --target pulsegrid
```

Review the printed target, backup verification and exact volume list. The script also requires the separate Phase 10 project and PostgreSQL volume to be present. Only a deliberate local rebuild uses both destructive flags:

```sh
python3 infra/scripts/phase11_rebuild_local.py \
  --target pulsegrid --execute --confirm-target pulsegrid
```

The helper archives its selected data state before retiring only target-owned PostgreSQL, Redis, RabbitMQ and the two Phase 4 cache volumes. It preserves Prometheus, Tempo, Grafana and the separate Phase 10 audit project. It requires the private, restore-verified archive used for this local run; that backup is outside Git at `/Users/aakash/.codex/backups/pulsegrid-phase11/20261025T101732Z`.

Bring the seven APIs up with the existing owner migrations, then let the guard verify readiness and all seven databases before enabling the seed:

```sh
docker compose \
  -f compose.yaml \
  -f services/patient/compose.auth.yaml \
  -f compose.phase4.yaml \
  up -d --no-build
python3 infra/scripts/phase11_rebuild_local.py --target pulsegrid --mark-ready
python3 infra/scripts/phase11_seed_demo.py --check-only
python3 infra/scripts/phase11_seed_demo.py
python3 infra/scripts/phase11_seed_demo.py --verify-existing
```

The seed command accepts loopback HTTP only. It provisions its initial local administrator through the existing Patient bootstrap path, then creates the eight intended accounts and domain records through the owner APIs. It uses a private, mode-0600 checkpoint and stable idempotency keys; an interrupted run can resume from that checkpoint. A completed checkpoint makes another seed invocation a no-op. Start a new run only after the guarded full rebuild, not by deleting checkpoint files.

The temporary database bootstrap port defaults to `55433`; the seed helper removes its temporary host-port overlay when it finishes. The permanent Compose gateway remains bound to loopback port `8080`. Run Vite on `127.0.0.1:5173` for the real browser application; it proxies `/api` to the gateway. Do not use `dev:mock` or `build:demo` to verify the seeded data.

## Boundaries

- `infra/scripts/phase11_rebuild_local.py` is destructive only with `--execute --confirm-target pulsegrid`; leave it in dry-run mode when checking the target.
- `infra/scripts/phase11_seed_demo.py` and its private credentials are loopback-only. Do not relax these guards to make hosted deployment work.
- Never commit `.env`, `secrets/phase11/credentials.json`, `secrets/phase11/seed-state.json`, signing keys, service credentials, or database backups.
- Vercel redeploys must run the normal `npm run build` only. They must not reset or seed databases.
- A hosted fictional dataset needs an independently reviewed first-admin procedure and eight separate strong credentials. That hosted bootstrap is intentionally not provided by these local helpers. See the [Vercel/Render runbook](../deployment/vercel-render.md).

See [the cleanup report](CLEANUP-REPORT.md) for the completed reset and verification evidence.
