# Phase 8 performance evaluation

This directory contains the bounded, authenticated read workload and measured
Phase 8 artifacts. It does not install packages, reset data volumes, or invoke
business write endpoints.

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

The default run ID is `phase8-20261013-run1`; results go under
`experiments/phase8/results/<run-id>/`. Use `--fixture`, `--base-url`, or
`--run-id` only when the equivalent synthetic actor fixture or local gateway
address differs.

The runner executes three 30-second, five-second-warm-up trials at 4, 16 and 64
closed-loop clients for a deterministic 50/30/20 mix of authenticated Doctor
directory, autocomplete and profile GETs. It then compares a Class B Doctor
profile GET at 16 clients against one and two Traefik upstreams, three trials
each. A fixed 20-request autocomplete burst compares NORMAL and SURGE. The
existing Phase 6 authenticated Emergency scenario supplies the critical Class
A workflow evidence.

The checked-in Traefik route currently names only `doctor:8000`. For the
two-upstream cases, the runner temporarily adds the already-running
`doctor_replica:8000`, waits for Prometheus to confirm both receive requests,
and restores the original route file in a `finally` block. It retains a local
backup in the system temporary directory until the byte hash is verified. If a
case starts and is interrupted, its progress marker prevents that case from
running again; inspect the partial files and record the gap instead.

## Evidence files

- `requests/*.csv`: one row per attempted HTTP request; status, latency,
  endpoint alias and outcome only. No response body, patient/doctor ID,
  credential or bearer token is saved.
- `resources/*.csv`: 2-second `docker stats` samples for Doctor, PostgreSQL,
  Redis, Traefik, RabbitMQ and observability containers. These are distinct
  from Prometheus metrics because this stack has no container exporter.
- `metrics/*.json`: Prometheus API-target, HTTP, admission, cache,
  autocomplete and RabbitMQ snapshots. The Prometheus scrape interval is 15
  seconds; these snapshots corroborate per-process telemetry and do not replace
  per-request client samples.
- `summaries/*.json`: status classification, attempted/admitted/successful
  rates, nearest-rank latency percentiles, resource aggregates, scaling
  counter checks and Surge Mode state transitions.
- `manifest.json` and `progress.json`: workload seed, hardware/software,
  Compose/container limits, fixture hash prefix, configuration hashes and
  resumable case state. Secrets and fixture contents are not copied.

Latency includes successful and rejected HTTP responses. HTTP 429,
HTTP 409/404, HTTP 5xx, timeouts and connection failures are separate
categories. No request is retried. A request that receives 5xx counts as an
HTTP response admitted by the limiter, while 429 is excluded from admitted
throughput.

Phase 4 component baselines remain in their original directories. See
[`docs/phase-4-integration-verification.md`](../../docs/phase-4-integration-verification.md)
for the audited summaries and
[`docs/phase-4-benchmark-plan.md`](../../docs/phase-4-benchmark-plan.md) for
their original experimental conditions.
