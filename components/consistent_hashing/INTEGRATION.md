# Coordinator integration guide

This component is ready for composition but has no deployed Redis or hospital
API integration. No Agent 3 source, service integration, shared configuration,
Dockerfile or Compose file has been edited.

1. Independently build/pin `pulsegrid-consistent-hashing==1.0.0` into the cache
   consumer image using an allowlisted package/wheel. Runtime dependencies: none.
   Build backend: setuptools>=68; no lock needed for dependency-free runtime.
   Root build contexts/image copying and version pinning are coordinator-owned.
2. Validate one reviewed `RingSnapshot(epoch, virtual_nodes, node_ids)` across
   every replica. Exact IDs, framing/version, vnode count and epoch must match.
   Resolve IDs to private Redis clients outside this package; map each logical
   ID exactly once and reject missing/extra mappings at composition time. Do not
   use IPs or credential-bearing URLs as IDs. Keep features disabled until this
   validation and integrated tests succeed.
3. Inject the immutable ring directly as Agent 3's structural placement port:
   it supplies `locate(key: bytes) -> str` and read-only `epoch -> int`. There is
   no sibling import or dependency in either agent's module. The coordinator
   constructs Agent 3's cache with this placement, the matching client mapping,
   observer and clock using that package's reviewed constructor. Public hospital
   APIs and their authorization/response schemas stay unchanged.
4. Capture placement and client mapping as one request-scoped configuration.
   Keep that immutable placement throughout get/load/set/delete so epoch/key
   placement cannot drift midway. Publish a complete replacement configuration
   under coordinator synchronization, allowing in-flight requests to finish on
   their captured generation. Do not provide a mutable facade whose `epoch`
   and `locate` can observe different generations. Drain/recreate cache instances
   on rollout if Agent 3 retains placement in its constructor; do not mutate its
   internals. Connection closure must wait for in-flight requests.
5. On add/remove **or vnode-count/framing changes**, advance the epoch and switch
   the physical namespace `pg:cache:v1:<owner>:<epoch>:<digest>`. Do not reuse
   an epoch for a different topology, and do not roll back to an old epoch:
   restoration is another higher-epoch rollout. Same nodes/vnodes with a different
   epoch keep logical placement but invalidate all physical cached entries.
   Rollout all replicas before cache enablement (temporarily bypass cache if
   necessary). The cache contract uses namespace invalidation and refill from
   owner PostgreSQL, not Redis value migration, dual reads or copying stale keys.
   Old namespace entries expire under bounded TTL (default30s/max60s). Epoch
   shifts invalidate even unchanged-owner keys; warmup/DB connection budgets must
   account for the full cold cache. Late old-generation fills remain isolated.
6. On a selected node timeout/outage keep the ring unchanged and invoke bounded
   owner DB fallback. Never pick a second Redis node automatically, treat cache
   entries as replicas, or return stale data on DB failure. Only explicit reviewed
   topology changes alter membership. Redis nodes are independent cache shards;
   placement does not establish replication, automatic HA or dispatch reliability.
7. Coordinator acceptance: test real node mapping, namespace switch on all
   replicas, late loader race, expiry, bounded node outage/recovery and DB fallback
   against isolated Redis/owner PostgreSQL; verify directory parity and public
   API/auth regressions. Cache revision reads, authorization and business DB
   correctness remain Agent 3/owner requirements, never ring authority.

No schema manifest, migration, route, secret, health probe or DB connection is
required by the ring. Configuration may be translated by the coordinator from
its existing feature settings; this package does not read environment variables.
