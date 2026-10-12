# Reproduce the bounded benchmark

Python >=3.11, psycopg[binary] 3.2.10, PostgreSQL available. Tested locally with
Python 3.14.7 and PostgreSQL 14; deployment PostgreSQL 16 is a pending gate.
Use a new private temporary cluster/port, never a development owner database.
Initialize UTF8 with initdb; start loopback only. Create test-only DDL:

```sql
CREATE TABLE id_worker_state (
 worker_id integer PRIMARY KEY CHECK(worker_id BETWEEN 0 AND 1023),
 reserved_through_ms bigint NOT NULL CHECK(reserved_through_ms >= 0));
```

Provide connection credentials through ID_BENCHMARK_DSN, then run sequentially:

```sh
for level in low medium high; do
 python experiments/phase4/unique_id/run.py --seed 404 --level "$level" --output "experiments/phase4/unique_id/results/$level" || exit 1
done
```

Each level has three alternating-order trials per mode, seeds 404/405/406, real
clock, 5s warmup. Fixed counts 100k/400k/1m; workers 1/4/16; clients 1/8/32.
One process/event loop; all three modes get the same concurrent insert clients.
Each client owns a temporary entity PK table; global uniqueness checked by a
whole-trial set. Temporary tables drop on close. Generator sessions are closed
in finally. Sequence and high-watermark tables persist in this disposable
cluster across trials; stop pg_ctl in finally at orchestration level. No
hospital tables, migrations or shared resources are touched. Run deadline is
bounded to 10 minutes per level; failure exits nonzero and has no success report.
Raw samples are ignored artifacts/phase4/unique_id; manifest hashes them.
System CSPRNG/UTC make exact IDs non-reproducible; seeds label repeats rather
than seed cryptographic randomness. Correctness uses deterministic clocks.

Pipeline timer includes allocation plus INSERT. Allocation-only timer is also
reported. Snowflake cost includes SELECT ownership and committed reservations;
CSPRNG is current positive BIGINT sampling; sequence is owner nextval technical
baseline, not an executed Records API path. This is component evidence only.

For high, run `--trial 1`, `--trial 2`, `--trial 3` sequentially in separate
output folders. Each invocation is bounded to 600 seconds; all three retain the
full 1m IDs per mode/trial workload. This splits orchestration only, not samples.
Raw samples are kept under this owned experiment's ignored `artifacts/` rather
than root artifacts/phase4: the task's exclusive-path restriction takes
precedence over the plan's suggested raw location. Measured low/medium and three
high folders are the authoritative runs; the earlier low folder is preliminary.

After all measured runs, `python experiments/phase4/unique_id/summarize.py`
checks every raw hash and all 27 successful measurement rows, then emits the
combined comparison/throughput plot. `timeline.py` emits the measured synthetic
rollback/restart timeline (ID_TEST_DSN, dedicated correctness DB). Unit tests also
verify 5000 same-ms calls and actual four-process uniqueness. Peak raw sample
memory and operating-system scheduling contribute to latency; no SLO is claimed.

Authoritative folders are `verified-low`, `verified-medium`, and
`measured-high-1/2/3`; `results/combined/report.md` aggregates exactly27 rows.
All other complete run folders are explicitly preliminary. Render with
`python plot.py` from this experiment directory, or its full root-relative path;
install the optional isolated plotting dependency in requirements-plot.txt.
The runtime library does not depend on matplotlib. plot.py overwrites only
figures from already retained measurements; it does not generate new timings.
