# Phase 8.2 — Final Doctor Service Scalability Evaluation

**Evaluation date:** 2026-10-13

**Branch:** local `main`

**Successful run:** `phase8-2-20261013-run3`

**Verdict:** **PASS for the scoped Phase 8.2 matrix**

## 1. Purpose and relationship to prior evidence

Phase 8.2 completed the six authenticated Doctor HTTP conditions left open by
Phases 8 and 8.1: one and two Doctor replicas at 4, 16, and 64 concurrent
clients. Each condition completed one 30-second measurement. Distributed
tracing was disabled in the same way across both topologies. These are local
synthetic-prototype measurements, not production capacity estimates.

The original Phase 8 trial was dominated by admission rejections: it recorded
508.13 attempted requests/s, 4.17 successful requests/s, and 99.18% HTTP 429.
Phase 8.1 corrected the benchmark admission setup and measured 110.70 successful
requests/s for one replica at four clients. Its matched two-replica sample
stopped after 14.635 seconds at 148.55 requests/s on the Tempo guardrail, so
that ratio remained provisional. The Phase 8.2 tracing-disabled matrix is a
separate configuration and does not replace or revise either historical
measurement.

Two Phase 8.2 setup attempts stopped before the admission preflight or any
measured trial. The first exposed an edge-network address collision during
parallel service recreation; the second observed Prometheus targets before
their scrape state had recovered after recreation. Both attempts and their
restoration evidence are retained as `run1` and `run2`. The runner was corrected
to start the gateway before dynamically addressed APIs and to wait for the
Prometheus scrape recovery. The successful six-trial run is `run3`.

## 2. Tracing-free environment

The benchmark overlay disabled SDK span creation and OTLP trace export in all
eight application containers: Patient, Doctor, the Doctor replica, Appointment,
Records, Pharmacy, Billing, and Emergency. Traefik used a benchmark-only static
configuration without its tracing exporter. The OpenTelemetry Collector and
Tempo containers were stopped for the matrix. No tracing volume or historical
trace data was deleted or reset.

Prometheus, Traefik metrics, Doctor HTTP metrics, authentication, PostgreSQL,
Redis, RabbitMQ, cache behavior, and distributed admission remained active.
Grafana also remained running. Its cap was temporarily raised from 256 MiB to
384 MiB because its pre-run use was 87.44% of the original cap; the cap was
restored afterward. All six trials recorded the same tracing-free
configuration. The results must not be described as fully instrumented
deployment performance.

## 3. Authentication, admission, and routing

The runner used the existing synthetic patient fixture and real JWT
authentication. Traffic consisted only of authenticated GET requests. The
Phase 8.1 Doctor benchmark policy remained enabled through Redis with a finite,
isolated benchmark namespace. Its source and principal capacities were 10,000
tokens, and aggregate capacities were 20,000 tokens; each used a finite rate of
2,000 tokens per second. The policy was bound to the synthetic JWT subject.
Normal admission keys and policies were not changed, no staff or Emergency
priority was assigned, and the Doctor admission middleware stayed active.

Inspection confirmed that live Traefik mounted
`infra/phase4/routes.yaml`. The one-replica host routed to the primary Doctor
upstream; the two-replica host routed to the primary and replica. Each topology
probe completed 12 of 12 requests with HTTP 200. The profile counters showed
only the primary for the one-replica route, and six requests on each Doctor
process for the two-replica route. Prometheus and Redis-backed admission
counters confirmed that benchmark traffic used the intended policy.

The five-second admission preflight completed 610 of 610 authenticated
responses successfully: 122 attempted, admitted, and successful requests/s,
with zero 429, other 4xx, 5xx, timeout, or connection-failure outcomes.
Prometheus observed the Redis backend. The normal Doctor quota counter did not
change during the benchmark preflight or matrix.

## 4. Environment and guardrails

| Resource | Recorded configuration |
|---|---|
| Host | Apple Silicon arm64, macOS 26.6.2, 12 CPUs, 16 GiB RAM |
| Docker VM | Ubuntu 24.04.2 LTS, 4 CPUs, 6.20 GB (5.77 GiB) memory |
| Docker | Engine 28.4.0, Compose 5.0.1 |
| Runtime | Python 3.12.11; PostgreSQL 16.15; Redis 7.4.11; RabbitMQ 4.3.6 |
| Doctor and replica | 0.5 CPU, 256 MiB each |
| PostgreSQL | 1 CPU, 512 MiB |
| Redis | 0.25 CPU, 128 MiB |
| Traefik | 0.25 CPU, 128 MiB |
| Prometheus | 0.25 CPU, 256 MiB |
| Grafana during matrix | 0.25 CPU, 384 MiB (normal cap restored to 256 MiB) |
| RabbitMQ | 0.5 CPU, 512 MiB |

The runner retained the existing 90% per-container and Docker VM memory
thresholds, a 90% Docker CPU threshold for three consecutive samples, a 10%
macOS free-memory floor, a 90% host-load threshold for three samples, service
health/restart checks, Docker sampling checks, and the sustained-5xx stop
condition. Docker resources were sampled about every two seconds, including
timestamps, through each warm-up and measurement window.

## 5. Workload and fixed matrix

Each trial used the same synthetic dataset, seed `20261013`, JWT authentication,
cache and database configuration, Redis topology, quota, monitoring, and
five-second warm-up. The deterministic request mix was 50% directory search,
30% autocomplete, and 20% Doctor profile reads. No request retries were used.
Successful-request latency includes only HTTP 2xx responses. One trial was run
per matrix condition; the six measurements sum to the planned 180 seconds.

| Order | Doctor replicas | Concurrent clients | Requested duration | Actual duration |
|---:|---:|---:|---:|---:|
| 1 | 1 | 4 | 30 s | 30.000 s |
| 2 | 2 | 4 | 30 s | 30.000 s |
| 3 | 1 | 16 | 30 s | 30.000 s |
| 4 | 2 | 16 | 30 s | 30.000 s |
| 5 | 1 | 64 | 30 s | 30.000 s |
| 6 | 2 | 64 | 30 s | 30.000 s |

## 6. HTTP results

All values below come from the retained per-request CSV files and trial
summaries. Attempted, admitted, and successful counts match because every
measured response was HTTP 200.

| Replicas | Clients | Attempted | Admitted | Successful | Attempted RPS | Admitted RPS | Successful RPS |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 4 | 3,940 | 3,940 | 3,940 | 131.33 | 131.33 | 131.33 |
| 2 | 4 | 6,544 | 6,544 | 6,544 | 218.13 | 218.13 | 218.13 |
| 1 | 16 | 3,790 | 3,790 | 3,790 | 126.33 | 126.33 | 126.33 |
| 2 | 16 | 7,360 | 7,360 | 7,360 | 245.33 | 245.33 | 245.33 |
| 1 | 64 | 3,224 | 3,224 | 3,224 | 107.47 | 107.47 | 107.47 |
| 2 | 64 | 5,110 | 5,110 | 5,110 | 170.33 | 170.33 | 170.33 |

| Replicas | Clients | Mean latency | Median latency | P95 latency | P99 latency |
|---:|---:|---:|---:|---:|---:|
| 1 | 4 | 30.46 ms | 16.29 ms | 77.77 ms | 96.10 ms |
| 2 | 4 | 18.37 ms | 10.78 ms | 58.78 ms | 90.49 ms |
| 1 | 16 | 126.76 ms | 109.95 ms | 229.08 ms | 341.63 ms |
| 2 | 16 | 65.24 ms | 56.22 ms | 158.10 ms | 238.42 ms |
| 1 | 64 | 599.09 ms | 517.90 ms | 1,311.74 ms | 2,173.11 ms |
| 2 | 64 | 376.47 ms | 289.96 ms | 1,120.76 ms | 1,969.88 ms |

| Replicas | Clients | HTTP 429 | Other HTTP 4xx | HTTP 5xx | Timeouts | Connection failures |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 4 | 0 | 0 | 0 | 0 | 0 |
| 2 | 4 | 0 | 0 | 0 | 0 | 0 |
| 1 | 16 | 0 | 0 | 0 | 0 | 0 |
| 2 | 16 | 0 | 0 | 0 | 0 | 0 |
| 1 | 64 | 0 | 0 | 0 | 0 | 0 |
| 2 | 64 | 0 | 0 | 0 | 0 | 0 |

The raw classifier reconciles the attempt total for every trial, and each
successful RPS value equals successful responses divided by the actual
measurement duration. The single-trial estimates do not support confidence
intervals or a population-performance claim.

## 7. Replica scaling

For each concurrency level, the throughput ratio is `T2 / T1` and scaling
efficiency is `T2 / (2 × T1)`. Both replicas increased measured successful
throughput and reduced mean and P95 latency in these observations.

| Clients | One-replica RPS | Two-replica RPS | Throughput ratio | Scaling efficiency | Mean latency, 1 → 2 replicas | P95 latency, 1 → 2 replicas |
|---:|---:|---:|---:|---:|---:|---:|
| 4 | 131.33 | 218.13 | 1.66× | 83.05% | 30.46 → 18.37 ms | 77.77 → 58.78 ms |
| 16 | 126.33 | 245.33 | 1.94× | 97.10% | 126.76 → 65.24 ms | 229.08 → 158.10 ms |
| 64 | 107.47 | 170.33 | 1.58× | 79.25% | 599.09 → 376.47 ms | 1,311.74 → 1,120.76 ms |

Successful throughput declined between the lower and higher concurrency
observations for both replica counts, while latency rose sharply at 64
clients. The measurements do not isolate a specific cause, and no application
optimization or database tuning was performed.

## 8. Resource observations

The table reports the highest observed CPU and memory values across the six
measurement windows. Docker CPU percentages are the values returned by Docker
stats; the Docker VM CPU figure is normalized to its four allocated CPUs.

| Resource | Peak CPU | Peak memory |
|---|---:|---:|
| Doctor primary | 53.94% | 39.01% of 256 MiB |
| Doctor replica | 53.18% | 37.94% of 256 MiB |
| PostgreSQL | 29.04% | 41.71% of 512 MiB |
| Redis | 7.40% | 7.76% of 128 MiB |
| Traefik | 11.31% | 46.08% of 128 MiB |
| Prometheus | 18.06% | 31.83% of 256 MiB |
| Grafana | 3.00% | 57.66% of its temporary 384 MiB cap |
| RabbitMQ | 49.90% | 29.07% of 512 MiB |
| Docker VM | 69.86% of four allocated CPUs | 25.31% of 6.20 GB |
| macOS host | 1-minute load peak 3.60 of 12 CPUs | At least 42% free memory |

No resource, health, restart, or error guardrail stopped a trial. The stopped
Tempo and Collector were not included in per-trial resource samples. Prometheus
and Grafana remained active.

## 9. Graphs and reproducibility

All four graphs were regenerated from the retained Phase 8.2 request, resource,
summary, manifest, and progress evidence. The graph manifest validates four
PNG/SVG pairs and 21 input files by SHA-256. `validation.json` also records the
request-classification and throughput reconciliation. The captured `progress.json`
contains duplicate completion entries from a runner bookkeeping bug; its audit
confirms six unique started and completed case IDs, one trial summary per case,
and no repeated workload. The runner was fixed and the focused test suite passed.

- [Graph 1 — successful throughput (PNG)](../experiments/phase8/results/phase8-2-20261013-run3/graphs/01_phase8_2_successful_throughput.png) · [SVG](../experiments/phase8/results/phase8-2-20261013-run3/graphs/01_phase8_2_successful_throughput.svg)
- [Graph 2 — successful-request latency (PNG)](../experiments/phase8/results/phase8-2-20261013-run3/graphs/02_phase8_2_success_latency.png) · [SVG](../experiments/phase8/results/phase8-2-20261013-run3/graphs/02_phase8_2_success_latency.svg)
- [Graph 3 — rejection and failure rates (PNG)](../experiments/phase8/results/phase8-2-20261013-run3/graphs/03_phase8_2_rejection_and_failure_rates.png) · [SVG](../experiments/phase8/results/phase8-2-20261013-run3/graphs/03_phase8_2_rejection_and_failure_rates.svg)
- [Graph 4 — replica throughput and efficiency (PNG)](../experiments/phase8/results/phase8-2-20261013-run3/graphs/04_phase8_2_replica_scaling.png) · [SVG](../experiments/phase8/results/phase8-2-20261013-run3/graphs/04_phase8_2_replica_scaling.svg)
- [Graph hash and input manifest](../experiments/phase8/results/phase8-2-20261013-run3/graphs/plot_manifest.json)
- [Raw request and resource data, summaries, and restoration evidence](../experiments/phase8/results/phase8-2-20261013-run3/)

Regenerate the Phase 8.2 figures without running live services:

```sh
python3 experiments/phase8/plot_results.py \
  --run-id phase8-2-20261013-run3 \
  --phase8-2-scalability
```

## 10. Deployment restoration

The runner verified restoration after the matrix:

- The mounted Traefik source returned to `infra/phase4/routes.yaml`; the before,
  after, and mounted SHA-256 values matched
  `15e25694927bfc59643d158e49857e2e2a643af65e222a4635c989ac81eae99e`.
- No benchmark-only routes remained. Both Doctor containers had the temporary
  benchmark policy disabled and no benchmark principal configured.
- The normal Redis-backed Doctor admission path accepted an authenticated
  directory read and incremented its normal Redis counter.
- Both Doctor replicas and all seven API readiness routes were healthy; all 20
  Prometheus targets were up, and Doctor HTTP metrics remained available.
- The tracing-enabled application settings, normal Traefik configuration,
  OpenTelemetry Collector, Tempo, and Grafana's original 256 MiB cap were
  restored. Tempo's readiness endpoint returned `ready`.
- An unauthenticated Emergency read returned 401. Surge Mode returned NORMAL,
  version 4. No uncommitted deployment-configuration changes remained.
- PostgreSQL, Redis, RabbitMQ, and tracing volumes were not reset or deleted.

## 11. Remaining Tempo limitation and final verdict

Tempo's operational issue remains unresolved. Phase 8.1 recorded an OOM at the
original 256 MiB cap; the later 512 MiB setup passed one ten-minute observation,
but Tempo again approached its guardrail during a partial HTTP trial and a
subsequent restart trigger remained unknown. In Phase 8.2, Tempo and the
Collector were stopped only to isolate the requested hospital-throughput
measurement. Their configuration and data were restored. This experiment did
not investigate or resolve Tempo stability and did not measure tracing-enabled
performance.

**PASS for Phase 8.2:** all six authenticated conditions completed, admission
remained Redis-backed with zero measured rejections, routing was verified for
both topologies, errors and resources were recorded, scaling ratios and four
reproducible graphs were produced, and normal deployment restoration passed.
Each condition has one local observation, so repeatability evidence is
limited. The broader Phase 8 evaluation retains separate gaps documented in
the [performance evaluation](phase-8-performance-evaluation.md). Phase 9 was
not started.
