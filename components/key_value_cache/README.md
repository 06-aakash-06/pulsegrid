# PulseGrid key-value cache

Independently packaged Redis technical library; no business authority or service
entry-point wiring. Frozen base: `45273ea7fd1ea53e335942b6c38f2d81d38856ee`.

Exports: `Cache`, `CacheEntry`, `Placement`, `Observer`, `CacheUnavailable`,
`InvalidEntry`, `logical_key`, `canonical_json`, `redis_client`.

`Cache(placement, clients, owner='doctor', observer=None, clock=None, ttl_ms=30000,
max_loaders=32, wait_ms=100)` implements the frozen async get/set/delete/
get_or_load/close interface. Clock returns epoch milliseconds; use real wall time
in deployment and an injectable clock for correctness. Client mapping values
provide async get/set/delete/aclose (redis.asyncio.Redis). `redis_client` creates
50ms connect/command bounds, zero transport retries, max32 pooled connections;
every operation also has a 100ms outer deadline. Cache-aside shares a100ms transport budget across lookup/population (DB time excluded) and skips population after an unavailable lookup. Cancellation propagates.
Explicit get/set/delete failures raise `CacheUnavailable`; cache-aside reads
fall back to the supplied owner loader. Postcommit `invalidate` swallows storage
failures and returns a boolean. Owner loader failures propagate unchanged.

Physical keys are `pg:cache:v1:<owner>:<epoch>:<sha256(logical_key)>`. Placement
receives canonical logical bytes, never physical epoch-prefixed keys. Changing
an epoch invalidates all lookups without an old-generation read. Outage never
changes placement or redirects reads to a second node. Values are UTF8 canonical
JSON, exact schema1 envelope, base64 payload, positive JSON-safe source revision,
absolute expiry. Redis TTL is the smaller of requested TTL and remaining entry
lifetime; expired/corrupt/oversized/schema-mismatched data is a miss. Serialized
entries max65536 bytes (base64 overhead included), default30s/max60s.

Each process admits up to32 cache loaders, with up to100ms semaphore wait; excess
requests bypass to the caller's existing **bounded** DB pool. This is neither a
singleflight promise nor a replacement DB connection budget. No detached tasks
are spawned. Loaders must return fresh, validated authoritative entries; cache
cannot establish authorization, tenancy or clinical correctness.

Observer exceptions are isolated. Metrics: pulsegrid_cache_requests_total with
hit/miss/unavailable/bypass outcomes; pulsegrid_cache_lookup_seconds;
pulsegrid_cache_load_seconds; pulsegrid_cache_invalidations_total;
pulsegrid_cache_errors_total with population/invalidation kind. Labels contain
component/owner/outcome/kind only. Hit ratio=hit/(hit+miss), null for denominator0;
unavailability and bypass are reported separately. Health describes observed
transport state without an extra ping and never changes owner readiness.

## Tests

Prerequisites: Python3.13 (verified), Redis server on PATH, PostgreSQL tools for
Doctor adapter tests. Create a worktree-local ignored virtual environment.
Install `-e 'components/key_value_cache[test]'` and `-e services/doctor`.

```sh
.venv-cache/bin/python -m pytest components/key_value_cache/tests services/doctor/tests/phase4_directory_cache --confcutdir=services/doctor/tests/phase4_directory_cache -o asyncio_mode=auto -o asyncio_default_fixture_loop_scope=function -q
```

The tests own temporary loopback Redis processes and a temporary PostgreSQL
cluster. They neither use nor reset Compose databases. Doctor's revision DDL is
test-only; coordinator migration and mounting still require verification.
See the Doctor adapter HANDOFF.md and the owned experiment README.md.
