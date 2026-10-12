# Phase 4.3 component verification

Base `45273ea7fd1ea53e335942b6c38f2d81d38856ee`; branch
`phase4/key-value-cache`. Final commit and clean-tree status are reported after
commit; no merge or push is performed.

## Executed checks

- PASS: `.venv-cache/bin/python -m pytest components/key_value_cache/tests services/doctor/tests/phase4_directory_cache --confcutdir=services/doctor/tests/phase4_directory_cache -o asyncio_mode=auto -o asyncio_default_fixture_loop_scope=function -q`: **43 passed**, no skips, final run5.98s.
- PASS: real Redis get/set/delete/cache-aside, binary serialization, corrupt/schema/oversized/expired miss, application expiry boundary and Redis TTL, namespaced owner/tenant/role/revision/epoch isolation, loader concurrency/saturation/cancellation, bounded timeouts/shared attempt budget, failed observer, unavailable/missing-node fallback and structural ring-adapter compatibility.
- PASS: disposable owner PostgreSQL repository minimal-projection and opaque pagination parity, including tied timestamps; late-loader revision isolation across cache replicas; rename/deactivation/specialty association/name changes; invalid/sensitive projection rejection; actual PostgreSQL stop with Redis still warm prevents a read and propagates owner storage failure; restart/read recovery.
- PASS: full diagnostics run.py for low/medium/high, seeds404/405/406, five scenarios, 5s warmup/30s measurement,45 trials. Test-only schema has primary keys but omits owner secondary indexes.
- PASS: run_indexed.py low/medium/high, seeds404/405/406, five scenarios,0.2s warmup/3s measurement,45 short sensitivity trials with existing Doctor query indexes. No frozen-duration indexed endpoint claim.
- PASS: summarize.py verified6 final/sensitivity manifests, all6 retained raw-output SHA256/counts, runtime source hashes and6 latency SVG XML files; generated per-trial ratio/delta comparisons. **1,702,317 successful measured reads, zero read errors** across90 trials. Two-second owned Redis pauses restored in finally; owned temporary storage cleanup passed.
- PASS: compileall for cache package, Doctor adapter and owned experiment scripts; git diff --check; changed-file ownership checked against Agent3 manifest prefixes.

## Limits and skipped checks

No authenticated HTTP/gateway/browser benchmark, Agent2 real-ring integration,
final Doctor revision Alembic migration/triggers, stock/Pharmacy cache, wire-field
reconstruction, Compose/ACL deployment or full hospital regression was executed.
These shared wiring/deployment paths are coordinator-only. Phase4 integrated
acceptance remains incomplete. SVG syntax/data were checked; visual raster render
was not performed. See owned experiment RESULTS.md for every measured scenario
and trial-level comparisons/raw manifests; see adapter HANDOFF.md for mounting.

Cold preparation/query reuse/one-process topology and index-fidelity limitations
are explicit in benchmark reports. The initial low final cold trial overlapped
roughly5s of local tests. Earlier interrupted exploratory runs are not counted;
superseded smoke evidence is retained separately. No measured owner-service speedup,
HA, whole-system scalability, clinical or broker-delivery claim is made.
