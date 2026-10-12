# Coordinator integration guide

Agent 1 owns only `components/rate_limiter/**` and
`experiments/phase4/rate_limiter/**`. Branch `phase4/rate-limiter`; preparation
base `45273ea7fd1ea53e335942b6c38f2d81d38856ee`. Commit SHAs are reported after
committing rather than embedded recursively. No shared files, existing migrations,
authentication helpers, service entry points, gateway configuration or main edits.
No new schema/migrations or cross-owner access. No sibling algorithm dependency.

## Exact configuration seam

Frozen contract supplies semantic configuration keys, not environment-variable
spellings. The exported immutable `LimiterConfig` uses `enabled=false`,
`redis_endpoint`, `redis_username`, `redis_password`, `connect_timeout_ms=50`,
`command_timeout_ms=50`, `decision_timeout_ms=100`, `policy_version="v1"`,
`hmac_secret`, `max_replicas=4`, `local_bounded_key_capacity=10000`;
`max_connections=128` is a bounded pool tuning option. Endpoint/credentials/secret
are repr-redacted. Read secret and Redis credentials from coordinator-managed
references/files; do not put raw values in Git, logs, metrics or health.
No credentials are generated here. Budget keys are exactly the frozen
`BucketSpec` names. Redis namespace is exactly
`pg:admission:v1:<policy_id>:<HMAC-SHA256(identity)>`.

All replicas of an owner/policy use the same secret, partition, budgets and policy
version. Each **process** counts toward max_replicas, including Uvicorn workers,
rolling replacement overlap and worker replicas. Enforce the deployment count;
do not reduce max_replicas to increase local availability. Validate all route
budgets are partitionable before activation. Default preauth source/aggregate
30/2 and 300/30 use separate `_preauth` policy keys and must be reviewed in the
route inventory; the freeze specifies distinct preauth keys but no numeric
preauth budgets. No same-bucket debit in both stages.

## Coordinator-owned changes required

1. Package `components/rate_limiter` as a reviewed wheel in each consuming service
   image, or explicitly allowlist root-context copies. Existing service-only
   Docker contexts cannot see the package. Pin redis-py 5.2.1; local test dependency
   lock is `requirements-test.lock`. No universal shared runtime/domain package.
2. Add **dedicated standalone admission Redis 7**, private reachability from APIs,
   separate from directory cache/general Redis; use noeviction, adequate bounded
   memory, persistence/operational monitoring and a dedicated credential/ACL.
   Current compose Redis is on backbone while APIs are not: coordinator must
   explicitly connect APIs to the admission network. Never expose Redis publicly.
   Cluster/sharded Redis is unsupported because all buckets must execute together.
   Runtime ACL needs TIME, TYPE, HMGET, HSET, PEXPIRE, EVALSHA, SCRIPT LOAD and
   key access only to `pg:admission:v1:*`; do not give CONFIG/FLUSH to API identities.
   Tests use administrative commands only in their owned disposable instance.
3. In each `services/<owner>/<owner>_service/main.py` lifespan create one limiter
   after fork and close it on shutdown. Preserve process liveness/owner DB readiness.
   Configure observer bridging existing private metrics; do not expose private
   diagnostics or metrics through Traefik. Check all policy parameters at startup;
   malformed policies remain 503 when passed to the decision port.
4. Freeze a complete `(method, matched route template) -> RoutePolicy` inventory
   before enabling. Include Records reads/writes, auth endpoints, unknown routes,
   verified internal worker/current-authority checks, check-in/consultation/
   dispensing/payment families and all three Emergency partitions. `family`
   is a reviewed bounded ASCII identifier, never a raw route ID/path. No global
   hospital bucket. Existing `POST /api/v1/emergencies` requires the current
   Patient role: assign `emergency_authenticated` and retain that dependency.
   `emergency_public` is a supported/tested component partition, not authorization
   to create an anonymous endpoint or weaken the existing protected submission. Health/ping exact reviewed GET templates and OPTIONS exempt;
   unknown/unmatched routes use source+aggregate preauth gates.
5. Register `AdmissionAdapter.pre_auth(request)` after request context and route
   matching, before expensive authentication/password/body work. Starlette's
   outer middleware generally has no matched route: use an owner APIRoute wrapper
   or a reviewed exact auth allowlist, **not raw dynamic paths**. The adapter
   deliberately treats unmatched requests as bounded unknown traffic. Admission
   rejection returns `rejection_response(..., error_response=owner.errors.error_response)`;
   use the retained safe envelope/context headers. Response is 429 `rate_limited`
   or 503 `admission_unavailable`, Retry-After ceil seconds minimum 1 and no-store.
6. Register `post_auth` after the owner's existing JWT verifier, RBAC/resource scope,
   CSRF and current-authority checks, before business transactions/locks. Pass a
   trusted callback returning `VerifiedIdentity(user_id)` from `Principal.user_id`;
   for staff, `current_staff=True` only after existing privileged current-role
   validation, never from a JWT role hint. Internal workers return
   `VerifiedIdentity(caller, kind="service")` after caller/scope/audience/delegation
   validation. Callback 401/403 exceptions propagate unchanged. Public/auth routes
   use source budgets and need no principal callback; invalid JWT is source-gated
   and then handled by existing 401 semantics. Preserve existing auth even when
   limiter is disabled/exempt. Logout's frozen seed is source+aggregate; verified
   principal gating on logout requires an explicit reviewed policy, not automatic
   JWT parsing. UI local session clearing remains possible.
7. Patient login's normalization must invoke the **existing** Patient helper.
   HMAC its normalized account via `adapter.deriver.digest("account", normalized)`
   and pass `normalized_account_digest` through the owner-only hook, never expose a
   request quota-identity parameter. Body parsing and duplicate/unknown-key/error
   rules remain owner-owned. Existing authorization/token verification never move
   into this library. Never log passwords or raw normalized account inputs.
8. Retain Traefik routing, token-path log suppression and trusted Uvicorn peer
   processing. Existing Uvicorn trust configuration must accept forwarded IP only
   from reviewed Traefik IP, never wildcard; gateway must strip/rebuild untrusted
   forwarded headers. Adapter reads only `request.scope["client"]`, ignores all
   X-Forwarded-For/Forwarded/actor headers. If proxy trust is unavailable, use
   conservative proxy-peer/unknown source quotas; no header fallback here.
9. Add Retry-After to each owner's CORS exposed headers, retain auth/CSRF/error
   semantics and idempotency behavior. Do not transparently retry mutations.
   Coordinator reruns retained Phase 2/3 gateway/security/browser/HTTP workflows,
   current-authority revocation, staff fallback/manual check-in, Emergency partition
   overload and dedicated Redis outage/recovery **after mounting**. No claim of
   hospital end-to-end acceptance from standalone component tests.

## Boundaries and limitations

Local partitioning is approximate during transitions, partitions and restarts.
Lost Redis responses can charge Redis and local state conservatively once each;
there is no Redis transport retry or exactly-once quota claim. Lua may partially
charge on allocation/runtime failure after first write; validate before writes
and reserve memory/ACL headroom. Redis restart/state loss allows its ordinary
configured burst; local process restarts reset only the partitioned local budget.
Bounded local key saturation returns safe 503, never an untracked fail-open.
Health is last observed decision state; it is not a background availability probe.
No clinical priority, predictive triage, dispatch reliability, infrastructure HA,
Surge Mode or RabbitMQ work. Admission cannot authorize a clinical/money operation.

Tests cover real Redis Lua concurrency, fractional credit, compound no-debit denial,
replica bounds, invalid/spoofed identity inputs, malformed JWT callback behavior,
Emergency isolation, real OOM/BUSY, 2s owned outage/restart, NOSCRIPT, ambiguous
response loss, bounded cardinality, safe eviction, 429/503 envelopes and observer
failures. Exact commands/counts and measured benchmark evidence are supplied in
`experiments/phase4/rate_limiter/VERIFICATION.md` and `results/`.
