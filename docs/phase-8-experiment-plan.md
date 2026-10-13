# Phase 8 experiment plan

Status: **locked before new Phase 8 measurements**, 2026-10-13. Starting
commit: `1de2a1c` on local `main`; the working tree was clean. This plan uses the
retained synthetic development stack and does not reset or remove any Docker
volume.

## Environment and guardrails

- Host: Apple Silicon MacBook, 12 host CPUs and 16 GiB RAM. Docker Desktop runs
  Ubuntu 24.04.2 with a 4-CPU, 5.77-GiB memory limit. Docker Engine is 28.4.0.
- The existing Compose project has 22 services/containers listed by Compose,
  including seven owner APIs, two Doctor containers, Redis, PostgreSQL,
  RabbitMQ, Traefik and the Phase 7 observability stack. Existing data volumes
  remain attached. The Docker daemon reports 31 containers overall, so other
  local projects may contribute background load.
- Per-container caps relevant to the planned load are Doctor and its replica
  0.5 CPU/256 MiB each, PostgreSQL 1 CPU/512 MiB, Redis 0.25 CPU/128 MiB and
  Traefik 0.25 CPU/128 MiB. Current Doctor, replica, PostgreSQL, Redis,
  RabbitMQ, Traefik, Prometheus and Tempo containers are running. Both Doctor
  containers and the owner data services report healthy.
- All new workload HTTP requests are authenticated reads against synthetic
  Doctor data. No appointment, clinical, inventory, invoice, payment or
  emergency writes are part of the load matrix. The existing private Phase 3
  fixture supplies a synthetic patient account and Doctor ID; the separate
  private Phase 2.9 fixture supplies the existing admin account used only for
  audited Surge Mode transitions. The harness reads credentials without
  printing or persisting access tokens and logs out after each run.
- No database, Redis, RabbitMQ, Prometheus, Tempo or Grafana volume is reset.
  The Doctor scale comparison temporarily changes only the Traefik file
  provider's Doctor upstream list, then restores the original file byte for
  byte. The two existing Doctor containers stay running. A final configuration
  hash and health check verifies restoration.
- The load runner uses bounded closed-loop clients, 5 seconds of warm-up,
  30 seconds of measurement, 5-second request timeouts and no retries. A run
  stops at its fixed duration. Stop the matrix early if an owner readiness
  check fails, a container restarts, a target container exceeds 90% of its
  configured memory limit, or observed HTTP 5xx exceed 5% for 5 consecutive
  seconds. Record any early stop without rerunning it.

## Existing evidence inventory

| Area | Existing measured evidence to reuse | Remaining limit |
|---|---|---|
| Distributed rate limiter | Three 30-second component trials per level, plus authenticated Traefik evidence with 100 attempts: 63 accepted, 37 expected 429, no transport/server failures. A local-only burst admitted 120/160 against an approximately 60-request shared quota; Redis admitted 60/160. | Component timings and authenticated HTTP timings are distinct. Local fallback is approximate across replicas. |
| Consistent hashing | One-million-key runs and real cache-topology results. On 3→4 nodes, modulo moved 74.97–75.12% of keys; ring/32 moved 22.82–22.83%, and ring/128 moved 25.43–25.50%. | Ring lookup was slower than modulo in the pure algorithm run. Placement is not replication or high availability. |
| Cache-aside | Three-trial adapter results exist for 1k/10k/50k synthetic rows and cold/warm/uncached paths. The authenticated five-Doctor endpoint was slower with cache enabled. | Adapter measurements are not authenticated gateway capacity; the small live catalog showed no endpoint speedup. |
| ID generation | Three levels and multiple PostgreSQL-backed trials exist, including restart/rollback evidence. CSPRNG throughput was 2.136x, 1.806x and 2.368x Snowflake pipeline throughput at low/medium/high. | Additive distributed-ID properties are the trade-off; Snowflake was not the faster baseline. |
| Short links | Adapter and partial authenticated gateway evidence exist. The adapter baseline workflow read was faster than alias resolution. | High-concurrency authenticated results remain partial; no new alias workload is planned. |
| Insurance crawler | Three-seed loopback synthetic-provider results exist for sequential and bounded concurrent runs. | Throughput uses a fake persistence port, not Billing/PostgreSQL capacity. |
| Autocomplete | Seeded CPU-only and authenticated route results exist. The trie is not consistently faster; a 100k-entry index exceeds the production 64-MiB cap and falls back. | Large-catalog database-fallback route latency was not measured. |
| RabbitMQ and dependency failures | Phase 5/6 records include outbox retention during broker outage, resumed publication, one inbox effect, Records breaker opening/recovery, and Redis fallback/recovery. The Phase 6 broker timeline records outbox creation at 19:47:59 UTC, publication at 19:48:07, and inbox processing at 19:48:09 on 2026-10-12. | These are bounded workflow cases, not throughput or broker-HA claims. Do not repeat them against retained volumes. |
| Surge Mode | Phase 6 recorded a 20-request authenticated Doctor autocomplete burst in SURGE: 4 accepted and 16 expected 429, plus a separate successful synthetic Emergency workflow. | A same-workload NORMAL comparison is missing and is included below. |
| Observability/Tempo | Phase 7 verified eight API targets, readiness probes, request metrics, four RabbitMQ queue series and Prometheus outage isolation. Tempo restart count was 13 in that report; it recorded no OOM kill and a missing-WAL-meta warning. | The cause of Tempo restarts is unresolved. Current status and a short stability window are included below. |

Raw historical CSV/JSON, manifests and reports remain under
[`experiments/phase4/`](../experiments/phase4/). Phase 4's integrated verdict
was PARTIAL; this plan preserves that status and does not treat every component
comparison as an end-to-end service result.

## Locked Phase 8 matrix

| ID | Question and workload | Conditions and repetitions | Measurements and stop condition |
|---|---|---|---|
| L1 | How do authenticated Doctor read throughput, latency and admission outcomes change with offered concurrency? Deterministic mix: 50% directory search (`q=Synthetic`), 30% Doctor autocomplete (`prefix=synthetic`) and 20% synthetic Doctor-profile reads. | Two Doctor upstreams, enabled by a temporary Traefik file-provider edit; concurrency 4, 16 and 64; 5-s warm-up + 30-s measurement; 3 independent trials per level; workload seed 20261013; rotate level order across trials. Cache is warmed by the measured warm-up and is not flushed. Restore the route file after L1, then verify its original hash. | Raw request samples and status classes; attempted/admitted/completed RPS; mean/median/P95/P99 latency; 4xx/429/5xx/timeouts/connection failures; per-process admission/cache/HTTP counter deltas from Prometheus; 2-s Docker CPU/memory samples for Doctor, PostgreSQL, Redis, Traefik and observability containers. Stop using the common guardrails above. |
| S1 | Does a second Doctor API upstream change throughput or latency for the same authenticated read? | `GET /api/v1/doctors/{synthetic_doctor_id}`, 16 closed-loop clients, 5-s warm-up + 30-s measurement, 3 trials with one upstream and 3 with two. The one-upstream condition is the checked-in Traefik route. The two-upstream condition adds the already-running `doctor_replica` to the temporary file-provider list. Same fixture, token role, query, cache topology, limits and host. | 2xx throughput, mean/median/P95/P99 latency, all response/error classes, per-replica request counters and CPU/memory. Scaling efficiency = two-upstream successful RPS / (2 × one-upstream successful RPS), with trial values shown. Verify both upstreams receive requests, then restore and hash-check the original route file. |
| S2 | Does Surge Mode reduce Class C admission while preserving the bounded critical workflow evidence? | One 20-request authenticated Doctor autocomplete burst in NORMAL and one identical 20-request burst in SURGE; 20 simultaneous clients; current synthetic patient actor. Use the existing synthetic admin account for audited activation/deactivation. Wait the documented minimum SURGE duration before deactivation and the two-minute RECOVERY window before final NORMAL verification. | Per-request 2xx/429 and latency, `Retry-After`, Prometheus Class C decision deltas, audited mode versions/timestamps and final state. Reuse Phase 6's admitted Emergency workflow as the Class A correctness evidence; no new emergency record is created. Abort and restore NORMAL if transition confirmation is uncertain. |
| T1 | What is Tempo's current status and does it remain stable during a short idle observation? | Read-only 120-second window after load runs; readiness sampled every 2 seconds through the existing Grafana container; Docker restart count, memory and process state sampled at start/end; capture Docker lifecycle events and bounded Tempo log excerpts. | Readiness successes/failures, restart-count delta, OOM state, memory range, new WAL/scheduler errors and whether the previously stored trace remains queryable through the existing Control Room evidence. No volume changes. Do not change Tempo configuration unless a specific, version-supported cause is established. |

No unrelated benchmark will run concurrently. L1 and S1 use GET-only routes; no
database cleanup is required. S2 adds only the audited operational-mode
transition rows required by the existing design, and returns the shared state
to NORMAL before completion.

## Explicit evidence gaps

- No new appointment booking, journey mutation, clinical write, dispense,
  invoice, payment or emergency-create load is planned. The retained stack has
  no disposable owner databases and those workflows have durable effects with
  no safe per-run cleanup contract. Existing synthetic workflow and
  concurrency-correctness evidence will be linked instead.
- The Doctor read campaign is a controlled gateway-to-Doctor/PostgreSQL/Redis
  workload, not a full seven-service or cloud benchmark. Other domain services
  receive no new sustained load.
- The existing event evidence demonstrates recovery and one processed effect,
  but not publication/consumer throughput under a generated event dataset. Do
  not fabricate queue-throughput or pending-age results.
- Prometheus has no PostgreSQL, Redis or container exporter. CPU/memory values
  for this campaign come from bounded `docker stats` samples; application
  request, cache, admission and RabbitMQ observations come from Prometheus.
- Phase 4's raw evidence remains separately labeled and is not combined with
  new HTTP measurements when the workload or timing boundary differs.

## Planned artifacts

- `experiments/phase8/benchmark.py`: authenticated bounded HTTP load runner and
  self-testable status/latency/statistics helpers.
- `experiments/phase8/run_matrix.py`: fixed matrix runner, temporary
  two-upstream route change with unconditional restoration, resource sampling,
  Surge Mode transition and final-health checks.
- `experiments/phase8/plot_results.py`: reproducible plots generated only from
  retained Phase 4 CSV/JSON and measured Phase 8 CSV/JSON.
- `experiments/phase8/results/`: request samples, summaries, manifests,
  Prometheus snapshots, Docker resource samples, Tempo observation and graphs.
- `docs/phase-8-performance-evaluation.md`: report with quantitative claims
  linked to the exact raw evidence, reused Phase 4 findings and explicit limits.

The matrix ends after the listed runs and the 120-second Tempo observation.
Any early stop or unavailable case is recorded as partial; no load level is
repeated solely to improve a result.
