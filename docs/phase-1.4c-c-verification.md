# Phase 1.4C-C verification record

Executed on 2026-10-10 on local main. Synthetic identities only. No push, original worktree edits, volume deletion or environment reset. Phase 1.4C-C is complete; the Phase 1 architecture/scaffold/infrastructure/authentication foundation is complete. Hospital operations and later roadmap phases remain deferred.

## Integration and implementation

Initial main was clean at expected base `bd797050e097efecc5687a16b91c6bd37cf22976`. Both source commits exist and `git merge-base --is-ancestor` passed for that base.

| Source | Main cherry-pick | Result |
|---|---|---|
| `bc8826c3dd6761148736bf0cf37cff1b13b2e8d0` | `682abb139ab9a41f4e429dd3a81356a93db8148e` | Backend imported, no conflicts |
| `dfed3db7713ab1dfe5419aae94bc8468f8ba6f7e` | `07d7db74099358afbd7db0c0aaf5b9b0d90add3e` | Frontend imported, no conflicts |

Original `foundation/backend-auth` and `phase-1.4c-b-frontend-auth` refs still point to their supplied commits. Their worktrees were not modified. A subsequent local main commit contains integration fixes and this record; obtain its SHA with `git rev-parse HEAD` (also reported in the final completion message).

Implemented: actual CSRF response integration with credentialed requests, preserved host hook, scoped origin-only Referer for CSRF GET, serialized cookie mutations with same-origin Web Locks where supported, stable secure registration headers across ambiguous retries, and explicit new-attempt semantics. Existing memory-only JWT state, role hints, session epochs, single-flight refresh and safe duplicate-account feedback are preserved. Backend CSRF/Origin/CORS/JWT security was not relaxed.

## Executed checks and outcomes

| Check | Result and evidence |
|---|---|
| Initial Git branch/status/base/ancestry and source review | PASS; main, clean, expected base; both commits inspected before cherry-pick |
| Backend default run | PASS: 277 passed, 10 PostgreSQL tests explicitly skipped pending runtime; one existing Starlette/httpx deprecation warning |
| Full backend run with PostgreSQL opt-in | PASS: 287 passed, no skips, one existing deprecation warning; all seven protocol implementations plus ten real PostgreSQL tests |
| Frontend `npm run typecheck` | PASS |
| Frontend `npm test` | PASS: 49 tests across three files; original 45 plus four integration-regression checks |
| Frontend `npm run build` | PASS; production Vite bundle built |
| Compose quiet configuration | PASS; auth and optional local DB test overlays validated |
| Domain image builds | Initial multi-target build FAILED with Docker extraction parent-snapshot error; seven sequential domain builds PASSED without destructive cleanup |
| Runtime stack | PASS: PostgreSQL, Redis, RabbitMQ, Traefik and seven APIs all healthy; seven migration jobs exited zero |
| Patient Alembic current/check | PASS: `0003_auth_audit (head)`; `No new upgrade operations detected` |
| Infrastructure auth mode | PASS: schema/constraints for 10/12/17/11/15/15/8 domain tables, owned runtime access, session rollback, Doctor exclusion, 42 actual foreign-DB connection denials, all 14 role CONNECT boundaries, public gateway health and hidden internal/admin paths |
| Gateway HTTP journey | PASS: registration/retry/duplicate, payload role rejection, login/profile/ETag, actual access expiry, refresh rotation, logout/revocation and replay-family rejection |
| Vite proxy HTTP journey | PASS: real registration/login/profile/rotation/logout/replay and CSRF/Origin through frontend -> Traefik -> Patient; no mocked transport |
| Real browser journey | PASS: synthetic registration success, login, protected patient dashboard, reload restoration, patient redirect away from admin, logout, protected route redirect to login; timed refresh maintained dashboard after 60 seconds |
| Browser evidence | Restored-dashboard screenshot saved locally under ignored `artifacts/auth-integration/restored-dashboard.jpg`; no fabricated data or credentials in screenshot |
| Source hygiene | `git diff --check`, documentation relative links and secret/storage review PASS; final Git status checked after commit |

The backend command used this checkout's source paths with an existing `/tmp/pulsegrid-verify-venv` Python 3.14 environment:

```sh
PULSEGRID_AUTH_INTEGRATION=1 PYTHONPATH=services/patient:services/doctor:services/appointment:services/records:services/pharmacy:services/billing:services/emergency /tmp/pulsegrid-verify-venv/bin/python -m pytest --import-mode=importlib services -q
python3 tests/verify_infrastructure.py --authentication
/tmp/pulsegrid-verify-venv/bin/python tests/verify_authentication.py --expiry
/tmp/pulsegrid-verify-venv/bin/python tests/verify_authentication.py --base-url http://127.0.0.1:5173
```

All seven runtime containers had `OOMKilled=false` and restart count zero in the observed post-update snapshot. Memory snapshot: Patient 71.55 MiB; Emergency 72.32 MiB; other APIs 73.82–84.87 MiB, each capped at 256 MiB. PostgreSQL was 73.95/512 MiB; RabbitMQ 75.54/512 MiB; Redis 4.49/128 MiB; Traefik 62.3/128 MiB. These are snapshots, not load, soak or HA results. Only one Compose project ran. Persistent volumes were preserved. The optional loopback database test port was removed after PostgreSQL testing; the final stack uses the ordinary auth overlay.

## Security evidence

- Real browser account persisted in Patient PostgreSQL with an Argon2id hash; sanitized read-only query returned only the boolean hash-kind result. No password/hash/token was printed. Full PostgreSQL tests also verify password and refresh-token hashing, audit immutability and transaction rollback/concurrency.
- Tokens have the expected Bearer response shape, roles and decimal subject/profile IDs. Invalid/expired JWTs and anonymous profile requests fail; unit/protocol checks across seven services cover role, signature, issuer, audience, algorithm, scope, revocation and service identity boundaries. Backend authorization remains separate from UI redirects.
- Public registration rejects privileged role fields and issues only the patient role. Duplicate account requests cannot create a second email identity. Same-command replay returns the original sanitized response.
- HttpOnly refresh/CSRF cookie flags, path and SameSite were checked on the real HTTP responses; production Secure behavior and refusal of HTTP exceptions were checked by the backend suite. Production transport/TLS was not deployed.
- Real gateway rejects missing/invalid CSRF, null/foreign Origin, and foreign credentialed CORS. Exact allowlisted CORS/preflight succeeds. Browser same-origin CSRF failed initially because document no-referrer suppressed the backend-supported GET Referer; request-scoped origin-only policy fixed it without changing the global policy or backend validation.
- Login, refresh, logout and replay checks used actual PostgreSQL sessions; refresh changes the cookie, consumed-parent reuse revokes the family, and the child then fails. Browser logout audit succeeded and left zero unrevoked refresh rows for its account in the checked snapshot. A separate bounded browser login at 16:46:26 UTC refreshed at 16:47:26 UTC with no navigation; the dashboard remained accessible and was signed out afterwards.
- Access tokens remain in React memory. Source review found no localStorage/sessionStorage token writes. Signing keys/idempotency secret remain ignored private files; public internal endpoints remain unreachable through Traefik. No cross-service DB reads, credentials or ORM sharing were introduced.

## Changed files

The two imported commits contain 58 service/frontend file changes as shown by their commit stats. The integration-fix commit changes only:

- README.md; docs/api-contracts.md; docs/development-roadmap.md; docs/infrastructure.md; docs/security.md; docs/authentication-integration.md; docs/phase-1.4c-c-verification.md.
- frontend/README.md; frontend/src/api/authApi.ts; frontend/src/api/client.ts; frontend/src/auth/authContext.tsx; frontend/src/pages/AuthPages.tsx.
- frontend/tests/api-client.test.ts; frontend/tests/authentication.test.tsx.
- services/patient/auth.env.example; tests/verify_authentication.py; tests/verify_infrastructure.py.

Ignored local runtime files include root credentials, generated key material, frontend build output and browser screenshot. None are committed. No remote or push was created.

## Not tested, deferred and remaining limitations

No open integration blocker remains. Browser concurrent-tab stress, browser separate-origin CORS, browsers without Web Locks, production TLS/deployment, production abuse protection, MFA/password reset, automatic public-key refresh, hospital workflows, distributed algorithms, broker publishing, telemetry deployment, performance and HA were not tested or implemented. Frontend tests demonstrate concurrent single-flight refresh with mocked transport; that evidence is distinct from actual gateway/PostgreSQL/browser integration. Real backend concurrent-refresh tests prove strict replay/family revocation, not browser multi-tab stress. No outage/chaos test was rerun in this phase. Mermaid rendering was not performed.

Per-tab serialization remains available without Web Locks, but cross-tab cookie races can fail closed and require login. Logout changes the current tab immediately; other tabs clear on the next refresh/request, without instant UI broadcast. Low-risk JWT reads in other domains have the documented bounded revocation window. The dashboard continues to display pending business data; authentication success is not a claim that hospital workflows work.

Stop after Phase 1.4C-C. See [integration runbook](authentication-integration.md) for launch, environment, API and manual browser instructions.
