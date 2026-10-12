# Phase 4 component benchmark plan

Status: design only, 2026-10-12; **no benchmark executed, no numerical result
claimed**. Companion [contracts](phase-4-component-contracts.md) and
[agent plan](phase-4-parallel-plan.md). Agent-owned experiment prefixes are in the
[ownership manifest](phase-4-ownership.json). Phase 4 implementation must provide
component evidence and actual hospital integration. Phase 8 owns whole-system
load/scalability/HA experiments. Performance improvements are hypotheses to test,
not acceptance facts; slower valid algorithms must be reported honestly.

## Reproducible experiment contract

Each component agent creates, in its exclusive experiment prefix:
`run.py`, `README.md`, small fixture/truth generator with seed, and
`results/<run_id>/manifest.json`, `summary.csv`, `report.md`, `latency.svg` and
component-specific tables/graphs below. Raw request samples and large synthetic
datasets stay in ignored `artifacts/phase4/<component>/<run_id>/`; commit bounded,
sanitized summaries/manifests/plots only. Include SHA256 of raw inputs/outputs
and generation command so another worktree can reproduce them. If exact raw
samples must be retained for review, a bounded token-free sample can be committed
inside that owner's results path, with size reported. No secrets or identifiers
in metric labels. Frontend benchmarks/tests stay inside Agent 8's owned tests;
coordinator integration measurements use `experiments/phase4/integration/`.

Uniform later command from root: `<worktree-python> experiments/phase4/<component>/run.py
--seed 404 --level low|medium|high --output <owned-results-path>`.
Names: rate_limiter, consistent_hashing, key_value_cache, unique_id, short_links,
insurance_crawler, autocomplete. Each README supplies prerequisite versions,
explicit owned resource creation/cleanup, synthetic DB migration/fixture setup,
additional endpoint arguments (credentials via environment/secret files only),
and a single rerun command. Exit nonzero on incorrect output, failed cleanup or
required missing dependency; do not print a successful row for an unexecuted case.
No benchmark scripts are implemented in Phase 4.0.

Run fixed seed404 and repeat seeds405/406 for distribution sensitivity. Record
hardware/OS/CPU/memory, Python/Redis/PostgreSQL versions, component and baseline
commits/dependency locks, topology/process count, network location, resource
limits, pool size, dataset size/hash, policy/config, wall UTC start/end, timer
resolution and raw sample counts. Baseline/proposed use identical data and
normalization, hardware limits, connections and concurrent clients. Alternate
execution order across repeats, reset only owned disposable resources to the
same seeded state; preserve retained development DBs.

Latency uses monotonic perf_counter_ns around complete operation (include
serialization/network/DB fallback when part of integration), not just internal
algorithm time. Report p50/p95/p99 using sorted samples, nearest-rank
ceil(p*n)-1, min/max and sample count. Report algorithm CPU-only separately.
Use 5s warmup and 30s measurement x3 independent repeats for service paths;
pure algorithms use >=100000 timed operations/trial after warmup unless the
finite dataset below requires fewer, then disclose count. Crawler measures each
whole finite run x3 with no warmup result exclusion. Clock-dependent correctness
uses an injectable test clock; throughput uses real clocks.

Three levels are experimental inputs, not production capacities. Closed-loop
concurrency plus attempted and completed throughput, errors/rejections and
latency sample counts are mandatory. Also a bounded fixed-arrival burst for
rate-limiter admission, with queue delay measured separately to avoid concealing
client-side backlog. Stop after the level's duration or finite workload;
max component test run10min. Record unmet target arrival rate. Histograms include
errors/rejected latencies separately; don't silently exclude slow/error requests.
Mean efficiency/ratio=totals denominator explicitly specified, no divide-by-zero
fabrication. For improvements report baseline/proposed ratio and absolute
difference with per-trial variation, not a single best run. No target latency
SLO or superiority threshold until observed evidence is reviewed.

## 1. Distributed token bucket

Baseline: equivalent per-process token bucket (same capacity/refill/policies),
which can over-admit shared quotas across replicas. Proposed: atomic Redis script
plus conservative bounded fallback; baseline has no exact distributed guarantee.
Dataset:100 synthetic source/principal identities, one hot identity50 percent,
normal user/search and separate auth/public-emergency/authenticated-emergency/
staff-emergency partitions. No passwords/JWTs in samples.
Levels:1/2/4 API decision processes, 8/32/128 clients, attempted50/200/800
requests/s; policy seed capacities from contracts. Keep configured max_replicas4
for fallback cases. Burst at time0 capacity+100 requests against one compound
bucket; controlled fractional refill with injected clock in correctness tests.

Correctness: initial simultaneous burst admits exactly available integer tokens,
refill admitted cost never exceeds capacity+elapsed*refill within documented
precision; multi-bucket rejected request debits none; accepted business-invalid
requests still debit; spoofed headers cannot change identity; malformed JWT
not a trusted principal; overload public bucket leaves staff/authenticated
Emergency buckets unchanged. Real Redis replicas/concurrent clients are required.
Test NOSCRIPT, OOM/BUSY, timeout ambiguity, dedicated Redis outage2s and recovery
in **owned disposable Redis only**, local cardinality saturation and max-replica
validation. Recovery check: mode returns redis and no unbounded reset burst;
report conservative loss/approximation and transitions, not exact outage quotas.

Outputs: level/processes/clients/attempted/completed/accepted/limited/unavailable/
rejection_percent/fallback_percent/throughput/admission_p50/p95/p99; quota-debit
vs theoretical refill curve; stacked outcome bars and latency CDF. Rate rejection
percent=limited/(accepted+limited); availability failures separate. Baseline's
excess admissions reported as correctness difference, not speed success.

## 2. Consistent hashing

Baseline: SHA256 modulo sorted node list. Proposed: frozen SHA256 ring,
vnodes32/128/512. Generated logical keys10k/100k/1m, uniform then Zipf hot-access
trace (key placement counts and access loads measured separately), seed recorded.
Initial3 nodes; fixed transitions1->2,3->4,4->3; concurrency1/4/16 readers sharing
immutable snapshot. Both algorithms same keys/hash/node IDs.

Correctness: golden placement vectors across processes/Python runs, order-
independent input nodes, duplicates/empty topology rejected, all keys assigned
exactly once. Addition moves keys only to new node; removal moves only keys whose
old owner was removed (apart from explicitly identical-position tie fixtures).
Epoch change by itself does not move logical node placement. Snapshot reads
cannot see partial updates. No Redis replication/availability inference.

Outputs: per-node counts and load shares; max/mean and coefficient of variation;
changed_keys/total percent for each transition; ring memory/build and lookup
p50/p95/p99; distribution bars, modulo-vs-ring remap bars and vnode balance curve.
Hot-key access may remain imbalanced even when placement is uniform: report both.

## 3. Key-value cache

Baseline: actual authenticated Doctor directory projection queried from owner
PostgreSQL with existing bounded pagination. Proposed: same projection using
cache-aside with current DB revision read and2 independently sharded Redis nodes.
Compare1-node fake placement harness to coordinator-wired real ring separately,
not claim ring integration from fake tests. Synthetic active directory1k/10k/50k
rows,10 specialties,50/80/95 percent repeated query keys; limits20, realistic
normalized q/specialty/cursor keys. Clients1/8/32; cold-cache and warm-cache cases
at each level. Do not include staff/patient/clinical data.

Correctness: baseline equality of returned allowed data and pagination;
get/set/delete/TTL at expiry boundaries; corrupt/schema-mismatch treated as miss;
committed rename/deactivation/specialty mutation revision prevents late-loader
stale resurrection on two replicas; node add/remove epoch invalidation; cache
node outage2s, no stale-on-error, owner DB failure503. Perform all resource
failure injection on disposable stack with restoration in finally. Concurrent
same-key misses exercise bounded loaders and DB pool rather than unlimited spawn.

Outputs: successful lookups/hits/misses/cache failures/bypasses/DB queries,
hit=hits/(hits+misses), miss=misses/(hits+misses), successful response ratio,
lookup/end-to-end/load p50/p95/p99, completed throughput and DB load. Efficiency
reported as DB query reduction and end-to-end latency difference (revision reads
count as DB queries). Cold/warm latency charts and hit ratio vs reuse; no cache
benefit assertion based on get latency alone.

## 4. Unique IDs

Baseline: current positive signed BIGINT CSPRNG with local DB PK, plus Records
sequence as a separately labeled owner baseline. Proposed: generator and durable
owner high-watermarks/dedicated session lock. Never migrate existing tables in
benchmark. New disposable entity tables. Levels1/4/16 distinct workers,
clients1/8/32 total, 100k/400k/1m IDs finite generation. Track Python synchronization
and owner DB ownership-check cost. Baseline/pipeline timer includes required
collision-check/insert consistently; report generation-only separately.

Correctness: decode layout bounds, IDs strict increasing within each worker,
all proposed IDs distinct across workers; duplicate worker assignment fails;
>4096 same-ms requests overflow waits, not wraps; clock rollback poisons;
clock-before-epoch and 41-bit overflow fail; crash/restart after committed range,
after issued ID and after rolled-back business insert cannot reuse ID; session
loss/DB uncertainty blocks output and range reclaim. Test with real PostgreSQL
and injected wall clock. Forced legacy PK collision retries whole new command
bounded3; no retry on unrelated violation. Record0 observed collisions only if
actually observed, never proof of infinite uniqueness. Different workers have
no global monotonic promise.

Outputs: workers/count/generated/persisted/collisions/rejected/overflow_waits/
restart_wait_ms/generation_p50/p95/p99/IDs_per_second/reservation_transactions;
throughput-vs-workers, latency CDF and rollback/restart event timeline.

## 5. Short links

Baseline: Phase 3 full appointment/check-in landing navigation and existing
authenticated appointment/workflow lookup; **no unauthenticated baseline or raw
QR secret in logs**. Proposed: alias creation plus303 fixed landing navigation
and authenticated JSON resolution, with existing explicit QR POST separate.
Dataset1k/10k/50k synthetic future appointments/aliases; clients1/8/32; read/create
mix90/10. Secrets held only in process memory, not samples or plots.

Correctness: concurrent reissue yields one unrevoked appointment/purpose alias;
forced collisions retry bounded3; digest-only DB/idempotency audit persistence;
expiry/revocation/cancel/reschedule/no-show/complete safely hide alias; owner and
receptionist valid, wrong user/unauthenticated resolution rejected; navigation
303 never resolves data or changes workflow. Original QR concurrent consumption,
window, stale ETag and same-key replay still pass. A link can navigate repeatedly
but cannot check in without existing validated credential/staff fallback.

Outputs: creation throughput/latency, navigation303 latency, authenticated
resolution throughput/latency, collisions/expired/revoked/unauthorized totals,
baseline full-link vs alias path lengths (opaque alias only, no clinical content),
latency bars/CDF. Browser validation confirms fragment clearing and login loss
handling. Do not compare protected API latency to an unprotected redirect.

## 6. Insurance crawler

Baseline: sequential1-inflight crawler with identical parser/rules/allowlist/
retry policy; proposed controlled async concurrency1/4/8 (8 only experiment
configuration, deployment default4) and per-host2 cap. Three synthetic provider
sites,10/100/300 total finite pages across three levels, partition into runs
<=100 pages/provider; truth manifests include10 percent duplicate pages,
5 percent transient5xx,5 percent invalid/timeout pages and same-revision conflicting
content. Fixture network delay20ms fixed; separate delay100ms sensitivity run.
Never external internet providers or patient information.

Correctness: exact field extraction/validation against truth, deterministic
provider/policy source dedup, different-content revision quarantine, bounded
redirect/DNS/IP/size/decompression/concurrency/page/time limits; retries don't
create duplicate accepted rules; worker crash/lease reclaim stale finalizer
cannot commit; immutable rule provenance maintained. Integer estimate oracle
covers deductibles/caps/uncovered codes/paid balance/currency/overflow/effective
expiry/stale sources/invoice changes. Confirm invoice balance/payment history
byte-equivalent before/after estimates and source outages.

Outputs: retrieved/processed/valid/invalid/duplicate/failed/retried pages,
wall completion time, pages per second (processed/wall), duplicate percent
(duplicate/processed), failure percent(failed attempted unique pages/attempted
unique pages), field accuracy(correct fields/expected truth fields), rule
precision/recall and estimate correctness counts. Invalid fixtures counted
separately, not lower accuracy when correctly rejected. Failure accounting
includes exhausted retries; page-attempt counts and unique-page counts separate.
Graphs: sequential-vs-async completion bars, throughput-vs-concurrency and
extraction confusion table; slower/rejected fixtures remain in run denominator.

## 7. Autocomplete

Baseline: owner PostgreSQL/string prefix search using frozen NFKC/casefold/
whitespace normalization, escaped wildcards and same active visibility, stable
order/limit. If indexed SQL needs a new normalized-column/index migration,
coordinator reviews it; compare existing DB plan and disclose any unindexed scan.
No silent indexing advantage. Proposed trie snapshot plus required DB revision/
selected-ID validation. CPU-only Python string scan secondary baseline.
Synthetic1k/10k/100k entries split doctor/specialty/medicine in independent owner
fixtures, query prefix lengths1/3/8, hot and missing queries, Unicode/case/ties/
rename/removal fixtures. Clients1/8/32, result limit10 and20 sensitivity.

Correctness: exact ordered topK equality with truth for every prefix, not merely
matching count; no unauthorized/inactive entries; rename/remove/update snapshot
atomic; two replicas observe DB revision mismatch and fallback; rebuilt snapshot
rejects revision race; degraded/oversized index uses DB rather than partial trie;
DB outage503. Existing owner search schemas and stock correctness unchanged.

Outputs: query_count/empty/fallback/error/exact_accuracy, p50/p95/p99 algorithm
and endpoint latency, entries/nodes/estimated_bytes/peak_RSS/rebuild_seconds,
DB query counts; endpoint P95 vs entries/concurrency, trie memory vs entries,
accuracy and fallback tables. Approximate trie allocated-size estimate and
process RSS are separately labeled, not conflated. Component endpoint results
must include DB validity overhead to substantiate efficiency.

## Evidence gates

An agent is ready to hand off when correctness tests pass on real required
storage, every level has three measured trials or a concrete resource-limit
failure report, manifests/tables/graphs reproduce, and exact unavailable checks
are explicit. Missing required evidence blocks final Phase 4 acceptance but
never invites fabricated numbers. Coordinator reruns the connected component
cases on an isolated integrated topology (not all-hospital Locust scale testing),
compares API parity and retains baseline source/workload hashes. Only then can
Phase 4 be described as implemented and benchmarked.
