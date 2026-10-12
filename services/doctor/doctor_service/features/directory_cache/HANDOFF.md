# Phase 4.3 coordinator integration guide

Branch `phase4/key-value-cache`; common base
`45273ea7fd1ea53e335942b6c38f2d81d38856ee`. All implementation changes are confined
to Agent3's four manifest prefixes. Final commit SHA is supplied in the delivery
report (not embedded recursively in its own commit).

## Ports and mounting

`DirectoryFilters(tenant, role, query=None, specialty_id=None, cursor=None, limit=20)`
accepts the **existing Doctor** normalized search and decoded UTC cursor. Preserve
lower/strip normalization; do not silently introduce autocomplete's different
NFKC/casefold semantics into existing directory reads. Authenticated role and
trusted configured hospital partition are supplied by the owner, never headers.
All current Doctor authenticated roles are accepted. No patient-specific data
enters this projection; future scoped reads need a separate reviewed visibility
schema, not reuse of this broad directory cache.

Exports: `read_revision(session)`, `load_projection(session, filters) ->
(revision, payload_bytes)`, `cache_projection(cache, revision, filters, loader) ->
projection_dict`, `validate_projection`, `invalidate_projection`. The projection
is exact schema1 `{schema_version, items, next_cursor}`; item fields only
`id`, `display_name`, `specialties` (id/name). It excludes staff IDs, active/version
wire fields, schedules, stock and prices. Source and revision are read by a
**single PostgreSQL statement**, including empty pages; no locks across Redis.
Pagination uses the existing owner encode_cursor/filter_digest convention and
limit+1 selection. This statement uses only Doctor-owned tables.

Coordinator order for a cacheable active authenticated directory request:

1. Preserve JWT/RBAC, specialty existence, query-key validation, normalization,
   decimal IDs, cursor validation and existing audit behavior.
2. Obtain current directory revision from owner PostgreSQL in a fresh transaction
   (avoid a long-lived repeatable-read snapshot carrying obsolete revisions).
   Commit/end this read transaction before any Redis call.
3. Supply a loader that acquires an owner session from its finite pool, calls
   load_projection and closes its transaction/session **before returning**.
4. Call cache_projection. A valid mismatched-revision hit or corrupt projection
   is discarded; a raced authoritative snapshot is returned without population
   of the originally requested key. A late old snapshot can populate only its
   old revision namespace. Requests already in flight retain snapshot semantics;
   there is no linearizable cross-storage response guarantee.
5. Reconstruct existing `DoctorProfile` wire fields (`active`, current `version`)
   from fresh owner data; preserve exact response fields, ordering, cursor and
   status. Cache projection alone is NOT an existing endpoint response. Test
   full-wire equality before activating this integration. Reconstruction adds
   DB work not present in the adapter benchmark. Read the revision again in the
   same snapshot as wire-field reconstruction; if it changed, discard the cached
   projection and run the full existing owner query. Do not combine a cached old
   active page with newly deactivated/version-changed wire fields. Bypass cache for inactive/admin,
   personal, clinical, appointment, authorization and mutation reads.
6. Owner DB failures use existing503 handling; never stale-on-error/empty success.
   Cache degradation does not fail PostgreSQL readiness.

Do not wire while business locks are held. Keep existing session/pool deadlines,
max_overflow0 or equivalent bounded capacity; a saturated cache bypass still
needs the owner's pool/HTTP admission limits. Close caches at lifespan shutdown.
Feature disabled by default until coordinator validation.

## Durable invalidation and migration requirements

Coordinator-only forward migration `0005_phase4_directory_revision` creates a
Doctor-owned singleton with positive safe revision. Adapter expects
`directory_revision(singleton boolean, revision bigint)` and singleton=true.
Every doctors/specialties/doctor_specialties insert/update/delete increments it
in the **same transaction**, including deactivation and association changes;
rollback must roll revision back too. Retain existing schema/migration head,
grants, outbox/audit/idempotency and old rows. Revisions must not reset or wrap;
stop mutations safely if approaching 9007199254740991. Restrict direct runtime
revision writes. Reviewed triggers can ensure all mutation paths participate.

`invalidate_projection(cache, old_revision, filters)` is optional postcommit
cleanup of a known old key. It returns false during outage and cannot undo the
commit. It is not enough by itself: correctness depends on durable revision,
application validation and TTL, across all replicas. No Pub/Sub/broker dependency.
Test-only disposable DDL lives in the owned benchmark fixtures; no shared
migration/handler was changed or deployed.

## Placement and Redis topology

Coordinator wraps Agent2's immutable HashRing without adding imports to this
package:

```python
class RingPlacement:
    def __init__(self, ring):
        self.ring = ring
    @property
    def epoch(self):
        return self.ring.snapshot().epoch
    def locate(self, key: bytes):
        return self.ring.locate(key)
```

Roll out the same ring node IDs and increasing epoch to every replica before
cache enablement. Configure two independent private Redis cache nodes, map their
stable IDs to redis_client instances and keep admission Redis separate. No Redis
Cluster/Sentinel/replication or automatic failover. Add/remove nodes only via
reviewed immutable placement replacement plus new epoch; old entries expire.
No dual reads from old namespace, no topology change on node timeout.

Coordinator owns image build allowlists/package wheel pins, Compose network and
connection budgets, ACL secrets and `PULSEGRID_DOCTOR_PHASE4_*` enabled/config.
Use private cache network without host ports, allkeys-lru, bounded memory and
ACLs restricted to Doctor namespace GET/SET/DEL; credentials from secret files.
Redis TIME/FLUSH/config/admin are not needed by production adapter. Fixture
FLUSHDB/SIGSTOP appear only in disposable benchmark code. Existing admission
Redis retains its frozen isolation/noeviction policy.

## Pharmacy boundary

Agent3 owns no Pharmacy adapter paths and frozen contracts cache only active
Doctor directory projections. Do not reuse this payload/schema for medicine
stock, availability, prices, prescription/dispense authority or staff/patients.
Pharmacy autocomplete's revision-aware owner port belongs to Agent7; its live
availability stays owner-authoritative. Any later minimal medicine-label cache
requires coordinator-approved schema/ownership review and Pharmacy revision
mutation hooks before wiring. Generic get/set ports alone are not that approval.

## Verification and limitations

Real Redis tests cover cache-aside, TTL, corrupt data, bounded deadlines,
isolation, concurrent loads and outage. Real PostgreSQL adapter tests cover
existing repository projection/pagination parity, revision race, two cache
replicas, invalid payloads and owner failure propagation. Tests use explicit
owner fixture revisions rather than final trigger/migration integration.

Benchmarks include revision DB reads, query load and Redis serialization, compare
uncached/cold/warm/invalidation/two-second-failure scenarios, and report per-trial
counts/mean/p50/p95/p99/throughput/hit ratio/DB queries plus raw hashes. They use a
clearly labeled SHA256 modulo two-node placement harness, not Agent2's ring.
They do not measure authenticated HTTP, final wire reconstruction, final Alembic
migration, gateway/Compose networking or seven-service regressions. Those are
coordinator acceptance gates. No performance/HA/clinical guarantee follows from
component evidence.

The full-duration fixture runs omit existing Doctor secondary read indexes and
are labeled unindexed diagnostics. Separate indexed-fixture sensitivity runs
copy existing query indexes; their shorter duration is explicit. Neither is the
frozen authenticated endpoint baseline. Do not quote unindexed speedup as owner
service improvement; repeat with real migrations/indexes, realistic key reuse
and wire reconstruction at the integration gate.
