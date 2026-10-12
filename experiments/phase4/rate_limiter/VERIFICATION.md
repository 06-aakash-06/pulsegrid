# Phase 4.1 verification

Component source: `87bd594a397562a7217ec8dfcf815f6fae8ec1e0`; branch
`phase4/rate-limiter`; base `45273ea7fd1ea53e335942b6c38f2d81d38856ee`.
Final evidence commit is reported separately after committing. Every changed
tracked path is inside Agent 1's two exclusive prefixes. No shared integration,
main modification, merge or push.

## Correctness and package checks

Executed on macOS arm64, Apple M2 Pro, Python3.14.7, redis-py5.2.1, pinned
`redis:7-alpine@sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499`
(actual server7.4.11). Real Redis tests create loopback-only owned containers,
128 MiB/one CPU,64 MiB noeviction Redis. Commands:

```sh
RATE_LIMITER_REDIS_IMAGE=redis:7-alpine@sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499 .venv/bin/pytest -c components/rate_limiter/pyproject.toml components/rate_limiter/tests -q --disable-warnings --import-mode=importlib
.venv/bin/python -m compileall -q components/rate_limiter experiments/phase4/rate_limiter
.venv/bin/python -m build --wheel --outdir /tmp/pulsegrid-rate-limiter-wheel components/rate_limiter
git diff --check
git diff --cached --check
```

- Final correctness suite: **60 passed**,15.81 seconds.290 external pytest-asyncio
  deprecation warnings under Python3.14 (event-loop policy removal planned in3.16),
  no test skips. Tests run explicitly using component config because the root
  pytest default intentionally covers service paths only.
- Real four-replica/16-concurrent-client Lua burst:140 decisions, exactly40 accepted;
  compound denial does not debit the other buckets. These are independent limiter
  instances/pools; the benchmark additionally uses actual decision processes.
- Capacity, refill/expiry, future-clock clamp, numeric boundaries, fixed-point
  fractional carry, safe local eviction and max_replicas validation pass.
- All policy/identity/aggregate partitions, spoofed IP/actor headers, malformed
  JWT verifier-port errors, distinct principals, owner-normalized account digest,
  current staff and Emergency isolation pass. Existing Emergency submission still requires an authenticated current Patient;
  public Emergency tests cover only the isolated component policy, not a new
  unauthenticated hospital endpoint. No JWT parsing/authorization is
  implemented here; existing owner verifier/RBAC/current-role checks remain required.
- Real Redis7 NOSCRIPT, OOM, BUSY, corrupt key/type, two-second outage/restart and
  repeated recovery pass. Lost-response test executes the actual Redis script then
  drops the response; no transport re-execution, conservative local charge only.
- Redis ACL/unknown-command/CROSSSLOT/credential configuration errors return503;
  local denied identity churn does not allocate fresh entries. Saturation returns
  unavailable, never fail-open. Metrics labels and two recovery transitions pass;
  observer failure cannot prevent admission. HTTP429/503 retry/error envelopes
  pass; business-invalid admitted requests retain consumed tokens.
- Python compilation, wheel build, packaged `bucket.lua` assertion and Git whitespace
  checks pass. Heterogeneous compound policy IDs and varying per-request token
  costs pass; saturated eviction probes at most32 rotating candidates and never
  evicts buckets participating in the current compound decision. The Lua itself compiles/executes repeatedly on real Redis7.
- The initial, earlier46-test version also passed on host Redis8.8.0; this is
  secondary compatibility evidence, not a claim of a final Redis8 suite rerun.

## Benchmark evidence

Three levels are run sequentially to avoid overlapping benchmark Redis workloads.
Each level has three seeds404/405/406, alternate baseline/proposed order,5s warmup
and30s measurement per backend/trial. Each complete level is under the10-minute
bound. This is **paced component-decision throughput**, not maximum sustainable
throughput, HTTP/auth latency or whole-hospital performance. Closed-loop scheduler
lateness and fixed-arrival burst queue delays are recorded separately.

See each results directory for exact summary CSV, manifest/source/dependency/input/
raw-output SHA256, nearest-rank percentiles, per-outcome distributions, CDF/outcome
plots, quota curve and burst results. Raw traces are ignored under
`artifacts/phase4/rate_limiter/<run_id>/`; hashes allow review/reproduction without
committing identifiers or large datasets. Manifests record proposed seed budgets,
resource limits, network topology, wall UTC start/end and trial comparisons.

All required levels completed on the final algorithm source above. Aggregate
results below sum the three Redis trials; latency ranges show trial variation,
not pooled or averaged percentiles. Each completed level took about223 seconds.

| Level | Processes / clients | Decisions/s | P50 ms range | P95 ms range | Accepted | Limited | Unavailable |
|---|---:|---:|---:|---:|---:|---:|---:|
| low | 1 / 8 | 49.87 | 1.58–1.81 | 3.24–5.64 | 3605 | 883 | 0 |
| medium | 2 / 32 | 199.47 | 2.76–2.83 | 6.73–7.72 | 11248 | 6704 | 0 |
| high | 4 / 128 | 797.87 | 5.91–6.95 | 16.07–17.29 | 27317 | 44491 | 0 |

Zero fallback decisions in all measured nominal Redis trials. Targets50/200/800
requests/s have4/16/64 unmet arrivals per trial from discrete client scheduling;
actual49.87/199.47/797.87 decisions/s are reported rather than claiming targets.
The baseline has lower CPU-only latency but no distributed guarantee: burst
admissions were60/120/160 for1/2/4 replicas against shared capacity60; Redis
admitted60 at each level, with zero excess shared admissions. Rejected latency
and separate queue delay remain in raw samples and per-trial summaries.

Manifests are in [low](results/redis7-low/manifest.json),
[medium](results/redis7-medium/manifest.json),
[high](results/redis7-high/manifest.json). Sanitized
[aggregate results](results/aggregate.json) and all bounded reports/plots are
committed; raw outputs remain ignored, hashed and reproducible. Prior exploratory
runs were superseded after correctness fixes; only final-source full-protocol
results are delivered. No required benchmark execution blocker remained.

Artifacts passed raw/input SHA256 verification, trial/count/outcome accounting,
SVG XML parsing and render checks. The final wheel contains the exact tested Lua.


## Integration and limitations

[Coordinator handoff](../../../components/rate_limiter/HANDOFF.md) supplies the exact
configuration keys, package/image/network/ACL wiring, trusted-peer configuration,
matched-route hooks, existing verifier/CSRF/RBAC/current-authority ordering,
Retry-After CORS exposure and retained readiness/idempotency semantics.

The standalone hooks are deliberately unmounted and enabled=false until the
coordinator freezes the full route inventory. Redis/local transitions and restarts
have approximate quotas; Lua runtime/allocation failures can conservatively charge
partial compound buckets after the first write. No hard real-time scheduling
promise: deadlines bound async backend work and reserve5ms for local fallback;
Python scheduling and a supplied observer must remain bounded/nonblocking.

Skipped by ownership/scope: modifying Compose/gateway/owner service registration,
full retained Phase2/3 regressions, hospital HTTP/gateway/browser acceptance,
clinical or emergency-dispatch certification, HA/full-system load experiments.
Those remain coordinator integration gates, not component execution blockers.

## Owned files changed

- `components/rate_limiter/HANDOFF.md`
- `components/rate_limiter/README.md`
- `components/rate_limiter/pyproject.toml`
- `components/rate_limiter/requirements-test.lock`
- `components/rate_limiter/src/pulsegrid_rate_limiter/__init__.py`
- `components/rate_limiter/src/pulsegrid_rate_limiter/adapter.py`
- `components/rate_limiter/src/pulsegrid_rate_limiter/bucket.lua`
- `components/rate_limiter/src/pulsegrid_rate_limiter/limiter.py`
- `components/rate_limiter/src/pulsegrid_rate_limiter/local.py`
- `components/rate_limiter/src/pulsegrid_rate_limiter/policies.py`
- `components/rate_limiter/src/pulsegrid_rate_limiter/types.py`
- `components/rate_limiter/tests/conftest.py`
- `components/rate_limiter/tests/test_adapter.py`
- `components/rate_limiter/tests/test_limiter.py`
- `experiments/phase4/rate_limiter/README.md`
- `experiments/phase4/rate_limiter/VERIFICATION.md`
- `experiments/phase4/rate_limiter/fixtures.py`
- `experiments/phase4/rate_limiter/resources.py`
- `experiments/phase4/rate_limiter/results/aggregate.json`
- `experiments/phase4/rate_limiter/results/redis7-high/burst.json`
- `experiments/phase4/rate_limiter/results/redis7-high/latency.svg`
- `experiments/phase4/rate_limiter/results/redis7-high/manifest.json`
- `experiments/phase4/rate_limiter/results/redis7-high/outcomes.svg`
- `experiments/phase4/rate_limiter/results/redis7-high/quota_curve.csv`
- `experiments/phase4/rate_limiter/results/redis7-high/quota_curve.svg`
- `experiments/phase4/rate_limiter/results/redis7-high/report.md`
- `experiments/phase4/rate_limiter/results/redis7-high/summary.csv`
- `experiments/phase4/rate_limiter/results/redis7-low/burst.json`
- `experiments/phase4/rate_limiter/results/redis7-low/latency.svg`
- `experiments/phase4/rate_limiter/results/redis7-low/manifest.json`
- `experiments/phase4/rate_limiter/results/redis7-low/outcomes.svg`
- `experiments/phase4/rate_limiter/results/redis7-low/quota_curve.csv`
- `experiments/phase4/rate_limiter/results/redis7-low/quota_curve.svg`
- `experiments/phase4/rate_limiter/results/redis7-low/report.md`
- `experiments/phase4/rate_limiter/results/redis7-low/summary.csv`
- `experiments/phase4/rate_limiter/results/redis7-medium/burst.json`
- `experiments/phase4/rate_limiter/results/redis7-medium/latency.svg`
- `experiments/phase4/rate_limiter/results/redis7-medium/manifest.json`
- `experiments/phase4/rate_limiter/results/redis7-medium/outcomes.svg`
- `experiments/phase4/rate_limiter/results/redis7-medium/quota_curve.csv`
- `experiments/phase4/rate_limiter/results/redis7-medium/quota_curve.svg`
- `experiments/phase4/rate_limiter/results/redis7-medium/report.md`
- `experiments/phase4/rate_limiter/results/redis7-medium/summary.csv`
- `experiments/phase4/rate_limiter/run.py`

Final staged ownership, base/main preservation, Markdown links and whitespace checks passed.
All owned disposable Redis containers were removed; ignored venv/raw evidence is retained for reproduction.

CSV export line endings were normalized to LF after Git detected CRLF as trailing whitespace; parsed values were checked unchanged. The measured runner hash remains tied to source commit87bd594; manifests separately record the exporter correction hash. Future runs emit LF directly.
