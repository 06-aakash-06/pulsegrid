# Real-storage Doctor cache adapter experiments

Run from repository root with worktree-local Python3.13, installed Doctor and
cache packages, psycopg[binary]3.2.10, Redis server and PostgreSQL initdb/pg_ctl
on PATH. Exact resolved dependencies, server versions and hardware are recorded
per manifest; reproducibility pins are in requirements.lock in this directory.

```sh
.venv-cache/bin/python experiments/phase4/key_value_cache/run.py --seed 404 --level low --output experiments/phase4/key_value_cache/results/low-rerun
```

Repeat for medium/high with fresh output directories. Default per level: five
scenarios, seeds404/405/406, 5s warmup+30s measurement, roughly9min (under the
10min component-level cap). `--warmup .2 --duration 3` is a smoke run, not frozen
evidence duration. Scripts exit nonzero on missing dependency, incorrect output
or cleanup failure. They create fresh temporary loopback PostgreSQL plus two
Redis processes and tear them down in finally; never touch shared Compose.
Trust auth is restricted to this disposable loopback cluster, not deployment.

Levels: 1000/10000/50000 synthetic active rows, ten specialties, 1/8/32 clients;
one hot specialty query receives 50/80/95 percent selection probability, with
remaining selection uniformly among nine others. This models hot query share,
not the probability a query is repeated: the finite ten-key working set has
high reuse after warmup. This workload deviation is explicit; coordinator should
add realistic query/cursor cardinality and exact repeated-key trace for HTTP
acceptance. Prefix is the existing normalized 'synthetic doctor', limit20.
Fixture ordering and memberships are deterministic; seed controls access traces.

Both paths use the same snapshot SQL and minimal allowlisted projection.
Baseline runs that SQL once; cache paths retain a current owner revision SQL
query and run source SQL on misses, counting both. Pagination/field parity is
verified in adapter tests. Timing includes DB session/pool costs, read,
serialization and cache population. Cold forcibly deletes the chosen key before
each read; its setup revision read/delete are outside latency but inside wall
throughput, and excluded from application DB-query count. Concurrent repopulation
can produce cold hits. Invalidation atomically renames one row and bumps revision
every0.5s in owned PostgreSQL, counting query-path DB work separately from mutation
SQL. Failure pauses both owned Redis nodes for2s and restores in finally; all
latencies (including successful fallback) remain in total samples. Separate
unavailable p95/p99 prevent a low failure share concealing timeout costs. Outage
health recovery pings are checked before resource teardown.

One adapter process with two cache objects simulates replicas; real Redis storage
and shared PostgreSQL are used, but independent API processes are not. Placement
is a two-node SHA256 modulo harness; no sibling package import or ring claim.
There is no HTTP authentication/gateway/final wire reconstruction measurement.
The coordinator guide specifies how to complete those frozen acceptance gates.

summary.csv includes per-trial sample counts, errors, successful ratio, mean,
nearest-rank p50/p95/p99, min/max, throughput, hit/miss/unavailable/bypass counts,
hit=hits/(hits+misses), query counts and lookup/load/unavailable p95. report.md
averages the three trial summaries; raw samples are retained only under ignored
artifacts/phase4/key_value_cache/<run_id>/, with SHA256 and byte sizes in manifest.
latency.svg is a bounded reproducible comparison plot. Manifests hash exact
source files before commit to resolve source-version ambiguity.

The earlier low-smoke result is retained as superseded diagnostic evidence,
not used for final comparisons. Two exploratory full runs were interrupted for
review fixes; their raw samples remain ignored and are not successful trial rows.
The first final low cold trial overlapped approximately5s of a local test rerun;
this background workload is disclosed rather than treated as isolated hardware.

## Index fidelity and sensitivity

The full-duration run.py fixtures use primary keys only and omit the existing
Doctor query secondary indexes. Both uncached/cached paths see the same schema,
but those timings are **unindexed fixture diagnostics**, not the frozen actual
owner endpoint baseline and not evidence of production cache benefit.

run_indexed.py copies the relevant existing Doctor0001/0004 indexes into each
disposable fixture and runs all five scenarios, three trials and all three levels
with the same reader/serializer and two-node harness. It defaults to0.2s/3s
for a bounded sensitivity check; use --warmup 5 --duration 30 for a full repeat.

```sh
.venv-cache/bin/python experiments/phase4/key_value_cache/run_indexed.py --seed 404 --level low --output experiments/phase4/key_value_cache/results/low-indexed-rerun
```

Repeat for medium/high. These remain adapter measurements. Final migration
fixtures, realistic query/cursor reuse, wire reconstruction and authenticated
HTTP must be measured by the coordinator before Phase4 acceptance.
