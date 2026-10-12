# Reproducible consistent-hashing CPU benchmarks

Prerequisite: Python3.11+ standard library only. No installation, servers,
credentials, ports or resource failure injection. Run from repository root:

```sh
python3 experiments/phase4/consistent_hashing/run.py --seed 404 --level low --output experiments/phase4/consistent_hashing/results/low-rerun
python3 experiments/phase4/consistent_hashing/run.py --seed 404 --level medium --output experiments/phase4/consistent_hashing/results/medium-rerun
python3 experiments/phase4/consistent_hashing/run.py --seed 404 --level high --output experiments/phase4/consistent_hashing/results/high-rerun
```

Choose a new output name; existing history is never overwritten. All writes,
including ignored raw data in `artifacts/<run_id>`, remain under this exclusive
experiment prefix. Do not run measurement scripts concurrently: CPU contention
would invalidate baseline comparisons. No disposable external resources require
cleanup; retained raw files are local ignored evidence and summaries are bounded.

Levels generate 10k/100k/1m unique seeded logical keys. Every level runs seeds
404/405/406 (three independently generated datasets). The equivalent SHA256
modulo baseline uses sorted identical node IDs and identical full key framing.
Ring variants use32/128/512 vnodes. Topologies1/2/3/4 provide1→2,3→4,4→3 movement.
Uniform placement counts differ from Zipf exponent1.1 access counts; each access
trace has the same finite length as its logical dataset. Key/trace hashes and raw
latency hashes/sizes are in each manifest. CPU-only ring latency uses100k timed
lookups per trial/variant/readers1/4/16 after10k untimed warmup calls; baseline/
proposed ordering alternates between trials. No timing sample is dropped.
Per-call nearest-rank p50/p95/p99, average/min/max, attempted/completed/errors,
throughput, build duration, retained allocation estimate and process peak RSS
are recorded. Single process with threads, so GIL/contention affects tails;
thread count is not a multi-process parallel scaling claim. Throughput includes
measurement overhead and thread-pool construction. Distribution and movement
use the complete finite dataset. Timings are machine-dependent and CPU-only.

Outputs: manifest.json, summary.csv, report.md, latency.svg, distribution.csv,
movement.csv, build.csv, distribution.svg, remapping.svg and vnode_balance.svg.
The report includes same-seed baseline/proposed ratios and absolute differences.
Script exits nonzero for wrong locality/placement or invalid/missing output;
maximum finite workload is high with a10-minute guard checked each trial.
Reproducibility means matching keys, trace counts and placement; exact nanosecond
sample hashes change on rerun. The initial low-404 run precedes an output-hash
coverage correction; low-final includes report.md in its manifest hashes. All runs precede a CSV
CRLF-to-LF export-only correction; manifests retain original CSV hashes and
record normalization. Current runner writes LF directly; measured values and
raw samples remain unchanged. Historical low-404 evidence is retained.

Validate all measured evidence using the owned verifier:

```sh
python3 experiments/phase4/consistent_hashing/verify.py
```

No automatic replication, HA, Redis performance, cache hit improvement, database
load reduction or public API integration is demonstrated by these experiments.
