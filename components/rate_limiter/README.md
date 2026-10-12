# PulseGrid distributed admission

Independent technical package `pulsegrid_rate_limiter`, version 0.1.0. The
library remains disabled unless configured; the Phase 4 Compose overlay mounts
it in the seven owner services. Phase 6 extends this same component with
Redis-shared Surge Mode state and server-owned operation classes; it does not
add another limiter. Synthetic educational prototype.

Exports: `BucketSpec`, `BucketRequest`, `Admission`, `RateLimiter`, `LimiterConfig`,
`IdentityDeriver`, `RoutePolicy`, `build_buckets`, `operation_class_for`,
`AdmissionAdapter`, `SurgeModeSnapshot`, `SurgeModeUnavailable`,
`VerifiedIdentity`, `rejection_metadata`, `rejection_response`, `Observer`,
`NoopObserver`, `InvalidConfiguration`, `BUDGETS`.

`await RateLimiter.admit(buckets)` keeps the Phase 4 coroutine interface and
adds defaulted Surge Mode/class fields to its result. Supply 1–3 distinct compound buckets with server-owned policy
partitions and server-generated HMAC digests. `await health()` returns the frozen
shape; `await close()` closes the Redis pool. Use one instance per API process,
created after process fork, with the same configuration/secret across replicas.
A request costs tokens even if subsequent business validation fails or its
idempotency key replays. Denial debits none.

Redis Lua uses TIME in integer milliseconds, milli-token balances and a 0–999
refill remainder, keeping sub-milli credit across successful operations. Rejected
reads need no writes. Elapsed refill is clamped before multiplication; wall-clock
rollback earns no duplicate interval. Stored state/configuration/type validation
for all keys precedes any writes. TTL includes full refill time plus >=1000ms
slack. Unsafe exact-integer arithmetic, zero/negative values, duplicate keys and
costs above capacity are rejected. Request costs may vary within the validated bucket capacity. A capacity/refill/TTL
policy change with existing keys returns
unavailable: use a reviewed new policy/family namespace across **all replicas**,
never reset buckets on each process restart.

Redis connect/command deadlines default to 50ms each and decision deadline to
100ms (5ms reserved for bounded fallback work); no transport retry on an ambiguous consumption. Only NOSCRIPT proves
nonexecution and permits load/retry within the same decision deadline. OOM, BUSY,
connection error or timeout uses persistent local fallback. Corrupt Redis state, ACL/unsupported-command errors
or configuration fails closed with 503, never creates permissive fresh local
quota. Redis scripts cannot roll back allocation/runtime failure after a write;
such failures may conservatively charge a subset of buckets. They cannot justify
replaying consumption. Provision noeviction memory headroom and reviewed ACLs.

Fallback partitions integer token capacity and milli-token refill by
`floor(shared/max_replicas)`. A configuration with capacity below cost or refill
below one milli-token/s after partitioning fails closed. Existing accepted Redis
traffic shadows local balances. Local time is monotonic, fractional credit is
retained, and state is never cleared by an outage/recovery. Denied new identities are not allocated. Key cardinality is
bounded (default 10000); untracked keys at capacity return unavailable. Eviction
requires a fully replenished idle key, never an arbitrary LRU victim; at most32
rotating candidates are probed per decision, keeping saturation work bounded. Every
policy includes a local aggregate, bounding identity churn. Redis/local transitions,
process restarts and Redis state loss do **not** guarantee exact cluster quotas.
They may conservatively reject and Redis restart may grant its normal configured
capacity once; repeated transport errors never reset local state.

Seed budgets from the contract are available in immutable `BUDGETS`; custom
server-owned budgets can be passed to `build_buckets`. NORMAL preserves the
existing Phase 4 route keys and quotas. SURGE/RECOVERY use a separate class and
mode namespace, so policy changes never reinterpret existing bucket state.
Operation class is selected from an owner-reviewed method/template inventory;
request headers, bodies, query values, and token claims cannot select it.
Emergency-specific policies remain isolated. Seed capacities and 100%/60%/15%
SURGE scales (A/B/C) and 100%/80%/50% RECOVERY scales are prototype policy
settings, not clinically validated deployment limits.

The shared control hash lives below `pg:admission:v1:*` and uses only the
existing admission Redis ACL commands. Authorized manual changes use the
Appointment `hospital_admin` endpoint and existing Appointment audit chain.
Automatic activation is disabled because owner metrics are process-local and
cannot reliably distinguish general pressure from a single abusive client.
When the shared mode cannot be read, B/C use the protective SURGE profile while
A retains its finite bucket and the existing bounded local limiter fallback.
The profile builder receives the deployment replica ceiling. Tiny scaled
capacity/refill values are rounded up only enough to leave one local share per
replica, and never above the NORMAL budget; this keeps small authentication
buckets usable during failover without granting a fresh NORMAL-sized burst.

Identity derivation uses versioned length framing and HMAC-SHA256, canonical
positive signed-BIGINT user IDs and normalized ASGI peer IP addresses, including
IPv4-mapped IPv6. Missing/invalid peer addresses share a conservative unknown
source. No forwarded, actor, quota, body-role or unverified JWT headers are used.
The owner supplies normalized account digests and verified user/service identities
through trusted Python ports; existing owner auth and authorization still run.

Metrics: `pulsegrid_admission_requests_total`,
`pulsegrid_admission_duration_seconds`, `pulsegrid_admission_mode_transitions_total`,
`pulsegrid_surge_mode_state`, and `pulsegrid_surge_mode_transitions_total`.
Decision labels are bounded configured `policy`, `outcome`, `backend` (first
bucket policy is the representative label for heterogeneous compound calls); no identities,
keys, URLs or tokens. Observer exceptions are swallowed. Separate pre/post-auth
stage counters must not be summed to estimate final request rejection rates.
Health reflects disabled/last-decision mode without probing or changing readiness.

See [HANDOFF.md](HANDOFF.md) for coordinator registration, route/security ordering,
configuration and deployment work. Component tests and benchmark commands are in
[the experiment README](../../experiments/phase4/rate_limiter/README.md).
