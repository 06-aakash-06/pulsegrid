# Rate limiter component benchmark

Requires Python >=3.11 and Redis 7 (pinned deployment image tested). Use this
worktree's ignored `.venv`, never install into a shared venv:

```sh
python3 -m venv .venv
.venv/bin/pip install -r components/rate_limiter/requirements-test.lock
.venv/bin/pip install -e components/rate_limiter
export RATE_LIMITER_REDIS_IMAGE=redis:7-alpine@sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499
.venv/bin/pytest -c components/rate_limiter/pyproject.toml components/rate_limiter/tests -q --disable-warnings
.venv/bin/python experiments/phase4/rate_limiter/run.py --seed 404 --level low --output experiments/phase4/rate_limiter/results/low-run
```

Repeat `--level medium|high` with new owned output directories. The runner repeats
seeds404/405/406 automatically; each baseline/proposed path has 5s warmup and 30s
measurement. Order alternates across trials. Low/medium/high use 1/2/4 real API
decision processes and 8/32/128 paced closed-loop clients at 50/200/800 requests/s.
This measures component decisions including Redis network time, **not** HTTP/auth
or hospital throughput/max sustainable load. Pool limits and VM resource limits
are recorded. No PostgreSQL is required for this authority-free component.

Each run creates its own random-name loopback-only disposable Redis with 64 MiB
noeviction, Docker memory128 MiB/CPU1. It stops/removes **only that container** in
finally, including worker errors. It never flushes any shared Redis/DB. Without
`RATE_LIMITER_REDIS_IMAGE`, `RATE_LIMITER_REDIS_SERVER` selects a local executable;
default redis-server is allowed but exact version is recorded (host Redis8 is
secondary compatibility evidence). Tests also create and clean owned resources;
OOM/BUSY/flush/restart injection never touches a supplied shared endpoint.
No credentials are generated or copied. Docker daemon must already be running.

Seeded fixtures contain 100 synthetic identity indexes, identity0 gets50% workload,
and five separate directory/auth/public-emergency/authenticated-emergency/staff-
emergency partitions. `fixtures.py` is the truth generator; raw traces and outputs
are ignored under `artifacts/phase4/rate_limiter/<run_id>/` and SHA256-recorded in
manifest. Each client trace is generated using `seed+client_id*100003`. Baseline
and proposed use the same scheduled traces, policies and time budget. Pending
clients are never hidden: scheduler delay is reported separately; failed decisions
and rejection latency stay in samples, unmet target arrivals are recorded.

Outputs include manifest, per-trial summary, outcome bars, latency CDF, shared
quota-debit curve (CSV/SVG) and fixed-arrival capacity+100 burst at one compound
bucket. Burst uses concurrent independent limiter instances and separately
records queued arrival delay; normal trials use real processes. Baseline uses
identical unpartitioned local policy buckets and can exceed shared quota with
multiple replicas; this is a correctness defect, not a performance benefit.
No fabricated latency target or superiority threshold. Mean/percentile comparison
is per trial, nearest-rank ceil(p*n)-1; unavailable stays separate from rejection
limited/(accepted+limited), throughput completed/measurement duration.

The full per-level run is bounded below ten minutes. Reduced `--warmup`/`--duration`
values are for harness smoke checks only and manifest flags them `full_protocol=false`.
A missing dependency, child failure, quota violation or failed cleanup exits
nonzero; no successful final manifest is emitted before cleanup. Output must be
inside this owned experiment's results directory and cannot overwrite prior runs.
Existing hospital mounting/gateway/browser integration remains coordinator work.
