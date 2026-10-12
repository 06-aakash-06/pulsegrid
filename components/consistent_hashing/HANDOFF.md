# Phase 4.2 Agent 2 handoff

Branch: `phase4/consistent-hashing`.
Reviewed/common base: `45273ea7fd1ea53e335942b6c38f2d81d38856ee`.
Final commit SHA is reported with `git rev-parse HEAD` after this handoff is
committed (embedding that same commit's hash would be self-referential).
Ownership: only `components/consistent_hashing/**` and
`experiments/phase4/consistent_hashing/**`; exact changed-path inventory below.
No merge, push, remote operation, sibling import or integration/configuration edit.

## Exports and semantics

`pulsegrid_consistent_hashing`: Node, RingSnapshot, HashRing, InvalidTopology,
NoNodes. Frozen locate/with_node/without_node/snapshot signatures; `epoch` property
implements Agent 3's structural placement seam without importing its package.
Synchronous `HashRing.health()` checks configured placement, not Redis health.
Runtime package version1.0.0; no dependencies, Python>=3.11; setuptools>=68
build backend. No schema changes, DDL, route mounting, secrets or connection pool.

Full framed SHA256 positions, configurable vnodes, bisect lookup, lexical collision
ties, immutable snapshots and strictly increasing positive JSON-safe epochs.
Node order independent and salted-process independent. Empty ring construction
and last-node removal raise NoNodes; other invalid topology raises InvalidTopology.
Lookup bytes are not domain models or authority grants. Health never changes
membership. One owner per key, no replication or automatic HA. Topology changes
require namespace invalidation/refill, as detailed in [INTEGRATION.md](INTEGRATION.md).

## Executed validation

- `PYTHONPATH=components/consistent_hashing python3 -m unittest discover -s
  components/consistent_hashing/tests -v`: **13 tests PASS**, including32 independent
  spec golden vectors, three child Python processes with distinct hash seeds,
  vnode bounds, forced collisions/exact successor/wrap, order and epoch stability,
  add/remove locality over10k keys, invalid/empty/single/full membership,
  concentrated hot-key workload and4 readers across29 controlled publications.
- `python3 -m compileall -q components/consistent_hashing
  experiments/phase4/consistent_hashing`: PASS.
- Python AST parse of5 owned Python files, pyproject TOML and golden JSON parse:
  PASS; dependency-free runtime metadata checked.
- `python3 experiments/phase4/consistent_hashing/verify.py`: PASS for all4 retained
  runs. Each validates raw/output SHA256 and sizes,36 timing cases with recomputed
  nearest-rank percentiles/means/throughput,96 complete distribution groups with
  recomputed imbalance,36 movement ratios and48 builds.
- `git diff --check` and final staged whitespace/ownership checks: PASS.
  An initial staged check rejected CSV CRLF endings; normalized records to LF,
  retained original CSV hashes in manifests and corrected the exporter. No
  measured numbers/raw samples changed. Rechecked staged whitespace successfully.
  All changed paths checked against Agent2 prefixes in ownership JSON; merge-base
  checked against requested base. Final clean-tree status verified after commit.

Ruff/mypy are unavailable on PATH; no lint/type tool result claimed. Wheel build
was not executed; package TOML/imports are verified. Retained hospital regressions,
Redis/DB integration, Compose, gateway/browser, metrics deployment and migration
checks were not run because these are coordinator-owned integration gates. No
runtime storage/network behavior is claimed from unit tests.

## Measured benchmark evidence

Executable [runner](../../experiments/phase4/consistent_hashing/run.py), raw-hash
[verifier](../../experiments/phase4/consistent_hashing/verify.py) and
[rerun guide](../../experiments/phase4/consistent_hashing/README.md).
Final low/medium/high outputs: `results/low-final`, `results/medium-404`,
`results/high-404`; first low run retained as `results/low-404` history.
Each level runs3 trials (seeds404/405/406),10k/100k/1m keys, Zipf1.1 access trace,
1/2/3/4 nodes,32/128/512 vnodes and1/4/16 shared-snapshot reader threads.
100k timed lookups per timing case following10k warmup calls;36 timing cases and
3.6m timed calls per level. CPU-only, no network/DB; timings include SHA256 and
lookup, throughput includes measurement/scheduling overhead. GIL tails are
reported, not interpreted as multi-process parallel scaling. High run completed
in52.584s with432,439,296-byte process peak RSS; dataset/traces drive this RSS,
which must not be presented as ring size. Retained summaries/charts are small;
large raw samples are ignored inside the owned experiment prefix.

High-level results (three seeds,1m keys,3 nodes,128 vnodes):

| Metric | Consistent ring | SHA256 modulo |
|---|---:|---:|
| 1→2 changed logical keys | 50.673–50.719% | 50.032–50.098% |
| 3→4 changed logical keys | 25.426–25.502% | 74.971–75.118% |
| 4→3 changed logical keys | 25.426–25.502% | 74.971–75.118% |
| one-reader lookups/s | 970,847–984,384 | 1,163,992–1,185,503 |
| one-reader p95 | 1,000ns | 792–833ns |
| uniform placement max/mean | 1.0374–1.0405 | 1.0007–1.0029 |
| Zipf access max/mean | 1.1952–1.4626 | 1.2038–1.4014 |

The ring reduces churn for3↔4 but is slower and less uniformly balanced than
modulo here. 1→2 movement is about half for both. Vnodes are not a guarantee:
512 vnodes had uniform max/mean1.0597–1.0627, worse than128 for these fixed node
IDs. Changing seed varies keys, not topology; report does not claim node-ID
sensitivity coverage. Hot accesses remain imbalanced. No throughput SLO or
production capacity/HA claim. Per-trial ratios/differences, all latency tails,
per-node shares, build allocation estimates and plot artifacts are in reports.

## Coordinator requirements and limits

Pin/package this independent technical library, map stable logical IDs to private
Redis clients, inject an immutable ring as Placement, and capture epoch/placement/
clients as one request-scoped generation. All replicas must use identical reviewed
configuration before cache enablement. Use a higher epoch/namespace for topology
or vnode changes; refill from PostgreSQL and let old TTL entries expire. No
migration/copy/dual reads, no fallback Redis selection on timeout. The selected
node's failure uses bounded owner DB fallback, including safe DB failure behavior.
Do not edit public hospital APIs or bypass authorization/revision checks. Review
[INTEGRATION.md](INTEGRATION.md) for rollout/draining and required real Redis cache
parity/outage/late-loader tests. This handoff completes the component assignment;
full Phase4 hospital integration/acceptance still requires coordinator evidence.

## Changed-path inventory
- `components/consistent_hashing/HANDOFF.md`
- `components/consistent_hashing/INTEGRATION.md`
- `components/consistent_hashing/README.md`
- `components/consistent_hashing/pulsegrid_consistent_hashing/__init__.py`
- `components/consistent_hashing/pyproject.toml`
- `components/consistent_hashing/tests/golden_vectors.json`
- `components/consistent_hashing/tests/test_benchmark.py`
- `components/consistent_hashing/tests/test_ring.py`
- `experiments/phase4/consistent_hashing/README.md`
- `experiments/phase4/consistent_hashing/results/high-404/build.csv`
- `experiments/phase4/consistent_hashing/results/high-404/distribution.csv`
- `experiments/phase4/consistent_hashing/results/high-404/distribution.svg`
- `experiments/phase4/consistent_hashing/results/high-404/latency.svg`
- `experiments/phase4/consistent_hashing/results/high-404/manifest.json`
- `experiments/phase4/consistent_hashing/results/high-404/movement.csv`
- `experiments/phase4/consistent_hashing/results/high-404/remapping.svg`
- `experiments/phase4/consistent_hashing/results/high-404/report.md`
- `experiments/phase4/consistent_hashing/results/high-404/summary.csv`
- `experiments/phase4/consistent_hashing/results/high-404/vnode_balance.svg`
- `experiments/phase4/consistent_hashing/results/low-404/build.csv`
- `experiments/phase4/consistent_hashing/results/low-404/distribution.csv`
- `experiments/phase4/consistent_hashing/results/low-404/distribution.svg`
- `experiments/phase4/consistent_hashing/results/low-404/latency.svg`
- `experiments/phase4/consistent_hashing/results/low-404/manifest.json`
- `experiments/phase4/consistent_hashing/results/low-404/movement.csv`
- `experiments/phase4/consistent_hashing/results/low-404/remapping.svg`
- `experiments/phase4/consistent_hashing/results/low-404/report.md`
- `experiments/phase4/consistent_hashing/results/low-404/summary.csv`
- `experiments/phase4/consistent_hashing/results/low-404/vnode_balance.svg`
- `experiments/phase4/consistent_hashing/results/low-final/build.csv`
- `experiments/phase4/consistent_hashing/results/low-final/distribution.csv`
- `experiments/phase4/consistent_hashing/results/low-final/distribution.svg`
- `experiments/phase4/consistent_hashing/results/low-final/latency.svg`
- `experiments/phase4/consistent_hashing/results/low-final/manifest.json`
- `experiments/phase4/consistent_hashing/results/low-final/movement.csv`
- `experiments/phase4/consistent_hashing/results/low-final/remapping.svg`
- `experiments/phase4/consistent_hashing/results/low-final/report.md`
- `experiments/phase4/consistent_hashing/results/low-final/summary.csv`
- `experiments/phase4/consistent_hashing/results/low-final/vnode_balance.svg`
- `experiments/phase4/consistent_hashing/results/medium-404/build.csv`
- `experiments/phase4/consistent_hashing/results/medium-404/distribution.csv`
- `experiments/phase4/consistent_hashing/results/medium-404/distribution.svg`
- `experiments/phase4/consistent_hashing/results/medium-404/latency.svg`
- `experiments/phase4/consistent_hashing/results/medium-404/manifest.json`
- `experiments/phase4/consistent_hashing/results/medium-404/movement.csv`
- `experiments/phase4/consistent_hashing/results/medium-404/remapping.svg`
- `experiments/phase4/consistent_hashing/results/medium-404/report.md`
- `experiments/phase4/consistent_hashing/results/medium-404/summary.csv`
- `experiments/phase4/consistent_hashing/results/medium-404/vnode_balance.svg`
- `experiments/phase4/consistent_hashing/run.py`
- `experiments/phase4/consistent_hashing/verify.py`
