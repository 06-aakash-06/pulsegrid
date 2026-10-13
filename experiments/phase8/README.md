# Phase 8 performance evaluation

This directory contains the bounded, authenticated read workload and measured
Phase 8 artifacts. It does not install packages, reset data volumes, or invoke
business write endpoints.

See the [Phase 8 performance evaluation](../../docs/phase-8-performance-evaluation.md)
for results, analysis, and explicit acceptance gaps.

## Prerequisites

- The existing local PulseGrid Compose project must be running with the
  authentication, Phase 4 and observability overlays used by the current
  deployment.
- Use the repository `.venv`, which already contains `httpx` for the existing
  HTTP verification scripts. No dependency installation is required.
- The mode-0600 Phase 3 fixture must contain the existing synthetic `patient`
  actor and Doctor ID. The default is
  `/tmp/pulsegrid-phase3-live-fixture.json`. The separate mode-0600 Phase 2.9
  fixture supplies the existing synthetic `admin` actor; its default is
  `/tmp/pulsegrid-phase29-live-fixture.json`. The harness logs in over the
  normal auth APIs, keeps bearer tokens in memory, and logs both actors out.
- Traefik, the seven owner APIs, both Doctor containers, PostgreSQL, Redis and
  RabbitMQ must be healthy before the run. The Phase 7 Prometheus/Grafana
  containers must be available for metric snapshots.

## Checks

Run the local harness tests without contacting the stack:

```sh
./.venv/bin/python -m unittest discover -s experiments/phase8 -p 'test_*.py' -v
./.venv/bin/python experiments/phase8/benchmark.py --self-test
```

## Fixed live matrix

Run once from the repository root:

```sh
./.venv/bin/python experiments/phase8/run_matrix.py
```

The default run ID is `phase8-1-20261013-run1`; results go under
`experiments/phase8/results/<run-id>/`. Use `--fixture`, `--base-url`, or
`--run-id` only when the equivalent synthetic actor fixture or local gateway
address differs.

The Phase 8.1 runner performs one two-second-warm-up, five-second admission
preflight, then exactly 18 measured trials: three trials for each of 4, 16 and
64 closed-loop clients at one and two active Doctor Traefik upstreams. Each
trial has a five-second warm-up and a 30-second window, with the same
deterministic 50/30/20 authenticated Doctor directory, autocomplete and profile
GET mix. Three trials per cell are declared in the manifest before load begins.
No Surge transition or Phase 6 fault scenario is invoked.

Run the bounded Tempo observation once before the matrix:

    ./.venv/bin/python experiments/phase8/observe_tempo.py --duration-seconds 600 --interval-seconds 10 --workload-interval-seconds 20 --output-dir experiments/phase8/results/phase8-1-20261013-run1/tempo

Then run the fixed matrix:

    ./.venv/bin/python experiments/phase8/run_matrix.py --run-id phase8-1-20261013-run1

The benchmark overlay enables a server-side policy only for the exact
`phase8-one.localhost` and `phase8-two.localhost` Doctor read routes. The runner supplies the
synthetic fixture principal from the signed-in JWT subject; the Doctor
middleware checks that ID against the already-verified principal. Admission
continues through Redis under a separate finite Phase 8 policy key namespace:
capacity 10,000 with refill 2,000 requests/second per principal and capacity
20,000 with refill 2,000 requests/second aggregate. A similarly finite
pre-auth source/aggregate gate remains active. Normal Phase 4 budgets and the
shared Redis topology are unchanged.

The runner temporarily applies compose.phase8-benchmark.yaml to the two Doctor
containers, adds a temporary benchmark-only Traefik route with one or two
upstreams, and verifies actual routing from per-replica Prometheus counters.
Both Doctor containers remain running in both conditions; the one-upstream
condition sends no benchmark requests to doctor_replica. The test policy and
host route are removed after the run. It waits beyond the maximum 11-second
benchmark bucket TTL instead of deleting Redis keys, restores the normal
Compose configuration, and verifies the route file hash, normal Redis
admission, Surge Mode NORMAL, authenticated Doctor access, Emergency
authentication, service readiness and Tempo readiness.

The runner stops the active trial if any sampled container or aggregate Docker
VM memory reaches 90% of its configured limit, Tempo stops or restarts, Docker
resource sampling fails, or a five-second run of one-second buckets exceeds
5% HTTP 5xx. It stores raw request and resource samples before evaluating a
post-trial guardrail. A guardrail or interrupted trial cannot be resumed or
repeated under that run ID.

### Captured Phase 8.1 run

The captured run is `phase8-1-20261013-run3`. It stopped safely during the
first two-replica, C=4 trial when Tempo reached 90.99% of its 512 MiB limit.
The complete one-replica C=4 trial recorded 3,321 successful responses in 30s
(110.7 responses/s, 36.21 ms mean and 90.56 ms P95). The two-replica trial
recorded 2,174 successful responses in 14.64s (148.55 responses/s, 26.92 ms
mean and 84.17 ms P95) before the guardrail stopped it. Neither captured trial
had HTTP 429 or 5xx responses. This is partial evidence; the remaining matrix
cells were not started and the provisional ratio is not accepted as a matched
scaling result.

The final read-only recheck found all seven API readiness routes and all
Prometheus API/readiness targets up, the benchmark policy absent from both
Doctor containers, normal Redis admission restored, Emergency returning 401
without credentials, and Surge Mode NORMAL. The original Phase 8 429-dominated
trial and the invalid first setup attempt are retained in their original
result directories and excluded from the accepted capacity observation.

## Evidence files

- `requests/*.csv`: one row per attempted HTTP request; status, latency,
  endpoint alias and outcome only. No response body, patient/doctor ID,
  credential or bearer token is saved.
- `resources/*.csv`: 2-second `docker stats` samples for Doctor, PostgreSQL,
  Redis, Traefik, RabbitMQ and observability containers. These are distinct
  from Prometheus metrics because this stack has no container exporter.
- `summaries/topology_{1,2}_replica_probe.json`: bounded Prometheus snapshots
  around the one- and two-upstream routing probes. The stopped trial has no complete per-trial
  Prometheus counter delta; its request samples come from the client and its
  resource samples come from Docker stats. The Prometheus scrape interval is
  15 seconds.
- `summaries/*.json`: status classification, attempted/admitted/successful
  rates, nearest-rank latency percentiles, resource aggregates, scaling
  counter checks and Surge Mode state transitions.
- `manifest.json` and `progress.json`: workload seed, hardware/software,
  Compose/container limits, fixture hash prefix, configuration hashes and
  resumable case state. Secrets and fixture contents are not copied.
- `setup_attempts/`: preserved invalid setup runs and the first 429-dominated
  trial, clearly excluded from the corrected matrix.
- `tempo/pre_fix_diagnostics.json`, `tempo/pre_fix_vm_stat.txt` and
  `tempo/pre_fix_relevant_logs.txt`: pre-fix OOM/container/host diagnostics
  and selected redacted logs.
- `tempo/stability_samples.csv`, `tempo/stability_workload.csv`,
  `tempo/stability_summary.json` and `tempo/stability_relevant_logs.txt`:
  bounded Tempo stability data, controlled trace traffic, restart/memory/
  readiness samples and warning/error lines.
- `tempo/finalization_snapshot.json` and `tempo/post_t1_*.json` plus
  `tempo/post_t1_relevant_logs.txt`: a later read-only finalization snapshot
  and selected, redacted log lines. These are outside the bounded T1 counts.
- `summaries/historical_phase6.json`: clearly labeled summary values
  transcribed from the Phase 6 verification report because its request-level
  samples are not retained; it is not raw Phase 6 telemetry.
- `graphs/*.svg` and `graphs/plot_manifest.json`: generated charts and a list
  of supported versus unavailable requested plots.

Latency summaries separate all attempts, all HTTP responses, admitted HTTP
responses (excluding 429), and successful 2xx responses. HTTP 429, other
4xx, HTTP 5xx, timeouts and connection failures have separate counts. No
request is retried. A 5xx response counts as admitted by the limiter; 429 is
excluded from admitted throughput. Every request row contains only a bounded
endpoint alias and response classification, with no IDs, credentials or
response body.

Phase 4 component baselines remain in their original directories. See
[`docs/phase-4-integration-verification.md`](../../docs/phase-4-integration-verification.md)
for the audited summaries and
[`docs/phase-4-benchmark-plan.md`](../../docs/phase-4-benchmark-plan.md) for
their original experimental conditions.

## Tempo observation and plots

Regenerate the captured Phase 8.1 SVG and PNG graphs from retained CSV/JSON
evidence with:

    python3 experiments/phase8/plot_results.py --run-id phase8-1-20261013-run3 --phase8-1-finalization

The plotting runtime uses the already available system Matplotlib; it does
not install dependencies. The Phase 8.1 graph manifest labels all four new
graphs as partial and records the incomplete matrix; the original Phase 8 and
Phase 4 plots remain historical evidence.
