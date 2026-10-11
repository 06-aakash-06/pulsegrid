# Phase 3.1A G0 framework verification

Base `6ac9c1c748a7cafde8f2cf8de5316faa458bbcb8`; local branch
`phase-3/appointment-waitlists`. Framework scope and exact Agent 2–4 exports are
in [FRAMEWORK_HANDOFF.md](FRAMEWORK_HANDOFF.md). The final commit is supplied in
the handoff report, not embedded into its own commit.

## Executed checks

From repository root, using existing `/tmp/pulsegrid-patient-venv` dependencies
(no installs), Python 3.14 and local Homebrew PostgreSQL:

```sh
env PYTHONPATH=services/appointment /tmp/pulsegrid-patient-venv/bin/python -m pytest services/appointment/tests --junitxml=/tmp/pulsegrid-phase31a.xml
env PYTHONPATH=services/appointment /tmp/pulsegrid-patient-venv/bin/python -m compileall -q services/appointment/appointment_service services/appointment/migrations services/appointment/tests
env PYTHONPATH=services/appointment /tmp/pulsegrid-patient-venv/bin/python -c 'from appointment_service import phase3_core; from appointment_service.main import create_app; app=create_app(); assert not app.state.appointment_extensions; print("PASS framework imports, disabled registration,", len(app.openapi()["paths"]), "existing OpenAPI paths")'
git diff --check
```

From `services/appointment/`:

```sh
/tmp/pulsegrid-patient-venv/bin/python -m alembic heads
/tmp/pulsegrid-patient-venv/bin/python -m alembic history
```

Final suite: **91 passed, zero failures/errors/skips** (58 unchanged baseline
cases and 33 new shared framework/migration cases). Two existing dependency
warnings: Starlette/httpx test-client deprecation and Alembic legacy config path
separator. Compile/import checks pass; 15 existing OpenAPI paths, no active new
workflow routes. Migration CLI passes: exactly one head `0004_phase3_core`, linear
0001_initial -> 0002_explicit_worker -> 0003_booking -> 0004_phase3_core.

New tests execute real PostgreSQL constraints, deferred binding on final atomic
schedule changes, workflow enums/versions/window/identity/FK/queue requirements,
parent drift denial, runtime DDL/audit denial, canonical lock ordering, immutable
context, foreign/finalized context rejection, disabled participant failure,
registration allowlist/export/metadata protocol, wire/schema compatibility,
ordered audit hash continuity, and rollback after participant/audit/outbox/saved
response failure. Equal-key replay has one feature effect. Existing baseline
HTTP, concurrency, idempotency/rollback/retry, schedule/hold/auth tests all pass.

Both empty migrations and retained **isolated synthetic 0003** upgrades execute.
Retained booking/slot/doctor/audit/head/outbox/idempotency rows compare byte-value
identically before/after upgrade. No workflow is backfilled. Unexpected data in
each of six dormant tables makes upgrade fail before table creation, preserving
0003 and all fixture rows. These are disposable test databases, not the retained
Compose topology. Test-created databases/clusters are torn down by their fixture.

A repository scope script ran `git diff --name-only <base>`, `git ls-files
--others --exclude-standard`, checked every changed path against Agent 1's
Appointment complement of six reserved directories, rejected symlinks, compared
0001–0003 for no diff and checked the ordinary branch. PASS. Local Markdown link
checks and `git diff --check` pass. No other service/frontend/root/docs/infra or
Agent 2–4 reserved directory was modified. Final staged ownership and clean-tree
checks are reported after the local commit. No merge, push or remote creation.

## Failures resolved during development

First sandboxed run: 26 passed, 32 fixture errors from denied loopback socket
binding. Approved rerun used the existing fixture's private disposable cluster;
all 58 baseline tests passed. Initial new fault tests expected DBAPI exceptions
but the command correctly converted constraint errors to safe 409; assertions
were corrected (79 passed/2 failed). A subsequent upgrade fixture needed explicit
text casts for jsonb_build_object parameters (81 passed/7 failed); corrected.
A 90-case rerun passed, then the final deferred-final-state case was added and
all 91 cases passed. No unresolved failure remains.

## Deliberately unavailable/not executed

No actual Patient/Doctor/Records/Pharmacy/Billing owner integration, gateway,
frontend/browser, retained Compose migrations, feature algorithms, worker lease
recovery, QR security, queue races, waitlist fairness or full journey acceptance.
No load/chaos/broker delivery/Mermaid results. These are future G1–G4 gates, not
G0 blockers. Runtime foreign-database privileges were not changed or retested
here; no cross-service database access exists in this framework. Later 0005–0008
revisions and their new constraints are absent until reviewed schema handoffs.

**READY FOR HANDOFF at G0**, with features disabled and later gates outstanding.
