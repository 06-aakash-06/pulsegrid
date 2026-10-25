# Baseline, failures and final verification

25 October 2026. Started from clean local `main` at `99fd31b`. All tests below were actually executed. Historical results are kept separate from these runs. Final acceptance is [PARTIAL](FINAL-VERDICT.md).

## Automated execution

| Command / environment | Before repair | Final result | Evidence and limits |
|---|---|---|---|
| `.venv/bin/python tests/run_phase2_regressions.py` | 623 passed / 52 skipped in 675 collected; separate Records run 77 passed | Initial business suites passed; final affected Appointment rerun below replaces its old count | Disposable local PostgreSQL, never retained Compose DB. 51 Records skips were executed in the isolated Records run; 26 Records passes overlap. |
| `.venv/bin/python -m pytest services/appointment/tests -q -ra -o addopts= --junitxml=/tmp/pulsegrid-final-appointment.xml` with service import path | New transport tests fail with wrong SnapshotClient signature; new expiry scheduling test fails with retry beyond deadline | 219 passed, 1 skipped (220 collected) | Includes three new regression tests and real disposable PostgreSQL. Initial Appointment had 216 passed, 1 skipped. |
| `.venv/bin/python tests/phase4/run_components.py` | Collection failed because importlib mode could not resolve sibling `test_limiter` | 158 passed | Package-relative imports repaired. Default collection was also checked. |
| `npm test` in `frontend/` | 159 passed / 12 files | 159 passed / 12 files after CSS repairs | Frontend unit/component/mocked HTTP coverage; not real-service E2E. |
| `npm run build` in `frontend/` | PASS | PASS after repairs; `tsc --noEmit` plus normal Vite build, 811 modules | Normal backend-connected build. Static-demo build was not rerun. |
| `git diff --check` | PASS | PASS | Whitespace only; final documentation checks recorded separately. |

**Deduplicated final results: 677 service tests + 158 component tests = 835 distinct backend/component passes; one intentionally skipped adapter benchmark. Frontend: 159 passes.** Counts do not add repeated runs or the 26 overlapping Records passes. [Machine-readable counts](evidence/final-test-results.json). No final automated failures remain in these runs. Starlette/httpx and Alembic configuration deprecations were warnings, not failures.

## Real-service and browser execution

| Verification | Actual outcome | Evidence |
|---|---|---|
| Complete isolated gateway workflows | Ten groups complete: registration/schedules, FIFO offers, full prescription journey, no-prescription journey, offer acceptance race, skip/recall/start/complete, worker restart/expiry and access isolation | [Workflows](evidence/live-workflows.json), [workflow report](05-end-to-end-workflows.md) |
| Natural expiry | Successor created 5.185877 seconds after predecessor expiry; DB history retained | Same workflow evidence. Observed timing, not a general latency SLA. |
| Seven owner schemas, migration heads, constraints, audit chain/digests and least privilege | PASS; 42 foreign-database connection attempts denied | [Schema checks](evidence/schema-audit-isolation.json) |
| Real auth/authorization negative cases | PASS 17 checks, including refresh-family replay revocation | [Security checks](evidence/live-security-checks.json) |
| Insurance crawl/estimate | Allowlisted fixture refresh complete; rule revision 2; invoice/payments unchanged | [Insurance](evidence/insurance-http.json) |
| Distributed admission across Doctor replicas | 100 attempted: 72 admitted, 28 limited, 0 errors; metric totals agree; spoofed XFF cannot expand principal quota | [Admission](evidence/admission-http.json). This bounded correctness burst is not a capacity benchmark. |
| Emergency + secure aliases | Seven workflow groups pass, including claim replay, release/reclaim, resolve/history, patient cancellation, owner denial and revoked alias denial | [Emergency/aliases](evidence/live-emergency-shortlinks.json) |
| Cache and Surge | Both isolated caches stopped: authoritative directory result preserved; restored healthy. Manual SURGE → RECOVERY → NORMAL observed | [Cache/Surge](evidence/live-cache-surge-checks.json); one transient status 503 interrupted continuous polling. |
| RabbitMQ | Payment committed during broker outage; recovery published/consumed; two duplicates left one inbox effect; poison reached DLQ | [Broker](evidence/live-broker-checks.json) |
| Observability | Protected summary/search available; an explicitly correlated fresh request yielded 13 Doctor spans | [Observability](evidence/live-observability.json) |
| Real browser | All 35 workspace routes/eight roles visited; patient primary departments and Control Room sampled at four requested sizes; registration/login/logout, Emergency submit, booking/list/detail/cancellation, keyboard search/menu and settled Billing panels exercised | [Browser evidence](evidence/browser/browser-checks.json). Not every control/mutation/viewport combination was exercised. |
| Retained stack after repair | 8/8 readiness HTTP 200; 223 package source files match checkout; selected event queues have consumers and no backlog | [Final retained health](evidence/final-retained-health.json) |

## Failures preserved and explained

- Real cancellation with waiting patients returned 500: both integration paths called an incompatible optional SnapshotClient as though it were the Patient eligibility transport. Repaired using the existing bounded service-only eligibility client; two new wiring tests fail before/pass after.
- High-attempt promotion backoff scheduled past a pending offer's deadline. One live run promoted 34 seconds late and missed its verifier deadline. Repaired durable scheduling and added a real-DB deadline regression; final natural expiry delay was 5.19 seconds.
- Fresh broker consumers failed queue declaration with `ChannelAccessRefused` because DLX write permission was absent. Narrow permission repair passed outage, duplicate and DLQ checks.
- Staff directory hid three of six administrator links, and selected subtitles had dark-on-dark text. Browser computed styles/screenshots verified the CSS corrections.
- Admission verifier overwrote counters from different label series; schema verifier crashed on expression index metadata and could read audit rows/heads from different snapshots. Diagnostics were corrected while retaining their business assertions.
- One gateway consultation returned 504 `dependency_timeout`. The same fixture and idempotency keys completed after resume. Root cause was not established; not reported as a fixed timeout bug.
- One Surge status GET returned 503 `admission_unavailable` during recovery polling. Later reads confirmed NORMAL with `recovery_elapsed`; no continuous recovery/stability PASS claimed.
- Early isolated setup used overlapping Docker subnet ranges and a non-loopback bootstrap path. Docker rejected the subnet; Patient rejected remote bootstrap. Verified non-overlapping networks and the existing owner loopback bootstrap were then used. Neither was a retained-data failure.
- Two temporary audit helper assertions initially assumed response shapes (`succeeded` versus payment `success`, and a nonexistent trace-detail `status`). Corrected to the frozen response contract; these were verifier mistakes, not product defects.

## Remaining unavailable or unexecuted acceptance

Physical camera QR decoding, every role/control at all four dimensions, exhaustive browser mutation/error/keyboard/reduced-motion combinations, live alert firing/telemetry-outage injection, a long Tempo stability window, backup/restore, soak and a new broad performance campaign were not completed. Server QR/replay validation and PostgreSQL concurrency tests passed; neither proves physical decoding. No Mermaid render verification is claimed. Static-demo persistence remains backed by its current tests and historical browser report, not a fresh demo-browser run.

Raw local logs/XML remain under `/tmp/pulsegrid-final-*` and `/tmp/pulsegrid-phase29-*`; these are temporary diagnostics. The sanitized JSON and screenshots linked from this directory are the durable audit evidence. Credentials, JWTs, QR credentials and raw aliases are excluded.
