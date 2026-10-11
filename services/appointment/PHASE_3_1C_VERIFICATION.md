# Phase 3.1C G1 waitlist verification

Original/framework base: `b7f74cb9f47b764989d2540695b4ed05ed8c1b28`.
Independent branch: `phase-3/appointment-waitlists-g1`.
Final commit is reported after commit, without self-reference here.

Implemented frozen join/list/get/withdraw/status, FIFO promotion participants,
eligibility adapter/snapshot merge, guarded booking/release adapters, durable
lease/backoff/repair worker and G2 schema manifest. See the module README for
transaction order, callback contract and assembly requirements.

The dispatch's offer/accept/decline/expiry requirement conflicts with the
frozen automatic confirmed-booking contract. Clarification is pending; these
offer features are not implemented and the requested overall scope cannot
be called fully complete. No offer enum or endpoint is silently introduced.

## Executed checks

Final command from this worktree:

```sh
env PYTHONPATH=services/appointment /tmp/pulsegrid-patient-venv/bin/python -m pytest services/appointment/tests -q --junitxml=/tmp/pulsegrid-phase31c.xml
git diff --check
```

PASS: JUnit contains **141 tests, 0 failures, 0 errors, 0 skipped**.
50 are waitlist feature tests; 91 retained Appointment/G0 executions pass.
Two existing deprecation warnings concern Starlette/httpx and Alembic's
path separator. No dependency installation or configuration churn was needed.
PASS: whitespace/diff checks. Branch/base and permitted-path checks are
performed before the scoped commit; clean-tree/SHA checks follow the commit.

The first sandboxed feature command executed 21 non-DB cases but could not
bind the fixture's loopback port (six PostgreSQL fixture setup errors).
After explicit execution approval, the existing fixture created disposable
random-port PostgreSQL clusters and per-test databases, ran real G0 migrations,
applied feature-local manifest DDL where required, and removed test databases
and clusters. Subsequent feature and full-suite runs passed. No persistent
development database or Compose stack was accessed/changed/launched.

## Evidence and limits

- Twelve simultaneous equal-key joins yield one entry/effect and saved response.
  Duplicate/own-booking/free-slot/stale-schedule/input/identity failures covered.
- Three FIFO candidates exercise inactive, real GiST overlap/savepoint rejection,
  then one promoted booking with matching local workflow/journey and event ref.
- Fifty direct arrivals across two independent Database instances/pools race
  atomic cancellation/promotion; no arrival bypasses the FIFO candidate, and
  exactly one active booking/workflow remains. Withdrawal/promotion races retain
  one terminal entry outcome. These are real PostgreSQL module-adapter races,
  not two deployed HTTP application/gateway instances.
- Unknown/stale eligibility blocks at the head, source versions merge
  monotonically, and newer inactive status beats older active refresh. Batches
  of 53 drain as 50 then 3 for inactive, retired and past slots.
- Cancellation survives owner timeout and changed candidate membership by
  committing pending work. Reschedule source promotion preserves legacy wire
  fields. Episode failure rolls back booking/entry/journey/workflow changes.
- Expired persisted leases, two concurrent claimers, lost-wakeup repair and
  preserved backoff are verified. Recovery is a deterministic lease-state
  simulation in disposable PostgreSQL, not a production process kill.
- HTTP module fixtures verify scoped reads, staff/doctor rules, exact fields,
  ETags/no-store, strict errors, cursor/filter/scope binding, If-Match and
  authorized replay after mutation; revoked authority denies saved replay.
- Strict service-only Patient transport fixtures verify membership, malformed
  data, response bounds, two attempts, timeout status and single half-open probe.
  Eligibility fetch fixtures assert no pool connection remains checked out
  at the network boundary. No real Patient batch leaf integration is claimed.
- Every disallowed waitlist transition is rejected; successful transitions
  execute in real database workflows. Existing G0 tests retain atomic
  participant/audit/outbox/result failure and audit-chain/grant coverage.

## Deferred checks

NOT EXECUTED: final 0005–0008 production revisions, retained-data upgrades,
real Patient eligibility/Agent 4 stage integration, enrolled cancellation/token/
queue/journey assembly, production availability filtering, worker deployment,
two HTTP apps/gateway/browser integration, root cross-service suite, performance,
load/chaos, broker publication or clinical validation. There are no migration
placeholders; actual Alembic head remains `0004_phase3_core`, verified by the
retained core migration tests. Registration remains disabled in `create_app()`.

No merge or push is authorized/performed. Stop after the scoped G1 commit.
