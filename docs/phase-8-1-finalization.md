# Phase 8.1 — Performance and Observability Stability Finalization

| Field | Value |
|---|---|
| Date | 2026-10-13 |
| Branch | local main |
| Starting commit | d5d677c8e17fa3a1c71c39a6099ff66f4be2b696 |
| Checkpoint status | Tempo passed; authenticated HTTP matrix pending |
**Final verdict:** pending the fixed matrix and restoration checks

## 1. Original Phase 8 blockers

The original Phase 8 result remains PARTIAL. Its only HTTP condition attempted 15,244 requests at four clients and two Doctor upstreams; 15,119 (99.18%) were HTTP 429. It measured admission rejection throughput, not Doctor processing capacity. Tempo reached 99.08% of its 256 MiB limit during that trial, and the later idle observation recorded a restart. See the historical [Phase 8 evaluation](phase-8-performance-evaluation.md) and its retained [run artifacts](../experiments/phase8/results/phase8-20261013-run1/).

## 2. Scope

Phase 8.1 addresses only Tempo stability and authenticated Doctor HTTP scalability. It preserves the existing PostgreSQL, Redis, RabbitMQ, and Tempo volumes. It does not repeat Phase 4 component benchmarks or Phase 6 fault scenarios.

## 3. Tempo diagnostic evidence

At 2026-10-13 08:11 UTC, Docker inspected pulsegrid-tempo-1 in restarting state with restart count 66, exit code 137, OOMKilled=true, a 256 MiB memory cap, and a 0.25 CPU cap. The latest reported failure finished at 08:10:41.629Z; the next process began at 08:10:33.593Z. This is direct evidence of an OOM termination followed by restart-policy recovery. The prior process had reached 99.08% of its configured memory during the earlier Phase 8 workload.

The direct Docker event query returned no retained lifecycle events, so a complete timestamp history for the 66 restarts was unavailable. The inspected process attempt began at 08:10:33.593Z and exited at 08:10:41.629Z. The exit/OOM state distinguishes a process OOM from an intentional Compose recreation or health-check restart. Tempo has no Compose health check; the observation used its /ready endpoint directly.

The host snapshot recorded a four-CPU Docker VM with 6,198,358,016 bytes (about 5.77 GiB) available to the daemon. Running containers reported about 1.478 GiB in aggregate while Tempo was restarting. macOS reported 44% free system memory. The snapshot does not indicate broad Docker-VM memory exhaustion, though Grafana was using about 87% of its own 256 MiB cap.

The captured pre-fix diagnostics, VM memory snapshot, and redacted relevant logs are retained in the Phase 8.1 tempo evidence directory: [tempo/](../experiments/phase8/results/phase8-1-20261013-run1/tempo/).

## 4. Tempo root-cause assessment

| Suspected cause | Evidence and counter-evidence | Confidence and decision |
|---|---|---|
| Tempo memory budget | Docker directly reported OOMKilled=true and exit 137 at the 256 MiB cap; the earlier workload reached 99.08%. Host-wide memory was not near its configured ceiling. | High confidence that the per-container cap caused the observed termination. Raise only this bounded cap. |
| Excessive tracing volume or sampling | The stack samples controlled synthetic traces at 100%. The earlier HTTP run generated significant request activity, but no trace-volume-to-memory time series was retained. During the new low-rate observation, 30 of 31 authenticated reads succeeded and memory peaked at 41.97%. | Possible contributor, not established as root cause. Keep the documented sample rate; do not reduce it without evidence. |
| Collector queues and batching | The Collector memory limiter is 96 MiB; batch size is 256 with a 512 maximum; the exporter queue is bounded at 256 and retry is bounded. No queue-saturation evidence was retained. | Low confidence as a cause. Keep the asynchronous, bounded export settings. |
| WAL recovery | Pre-fix retained logs include incomplete block/missing meta.json replay warnings. The ten-minute observation had zero such warnings. These may indicate stale or incomplete prior blocks but do not explain Docker's direct OOM flag. | Not established as the restart cause. Preserve the volume and investigate only if the warnings recur. |
| Monolithic mode and local storage | Tempo 3.1.0 runs as a single binary with local WAL and block paths and 24-hour retention. Grafana documents that monolithic components share a resource pool and can encounter memory pressure; local storage is supported for evaluation. | Plausible pressure multiplier, not an independent defect. Keep this bounded educational deployment. |
| Idle scheduler messages | The observation recorded 15 error-level no jobs found messages and zero other error-level lines. Tempo issue [#7403](https://github.com/grafana/tempo/issues/7403) describes an empty scheduler queue returning NotFound during idle/low-ingest monolithic operation. | Matches known idle behavior; not evidence of a restart cause. |
| Single-binary worker address warnings | The pre-fix logs include address auto-configuration warnings. The version-pinned Tempo 3.1.0 source [configures the worker address when unset](https://github.com/grafana/tempo/blob/v3.1.0/cmd/tempo/app/modules.go). | Expected single-binary setup, not a configuration failure. |
| CPU contention or unsupported configuration | The pre-fix Docker VM snapshot had aggregate use well below its memory capacity. The pinned Tempo binary accepted the configuration verification command. | Low confidence. No CPU or config error justified changes. |

Grafana's [deployment-mode guidance](https://grafana.com/docs/tempo/latest/reference-tempo-architecture/deployment-modes/) notes that monolithic components share memory and CPU; its [local deployment guide](https://grafana.com/docs/tempo/latest/set-up-for-tracing/setup-tempo/deploy/locally/linux/) supports local storage for evaluation and cautions that co-location raises memory pressure. These facts support the bounded cap correction without claiming production stability.

## 5. Tempo configuration change

compose.observability.yaml raises only Tempo's mem_limit from 256 MiB to 512 MiB. Its CPU cap remains 0.25. This is a reversible, finite increase selected after the direct OOM evidence and host-capacity check. No WAL, block, retention, sampling, Collector queue, or export settings changed, and no Tempo volume was removed.

The original observability overlay ceiling was 928 MiB; the current configured ceiling is 1184 MiB, with the same 0.95 aggregate CPU cap. Both are configuration budgets rather than measured host use. The pinned Tempo 3.1.0 -config.verify=true validation and Compose configuration validation passed.

## 6. Bounded Tempo stability observation

One 600-second observation ran with the normal monitoring stack and an authenticated Doctor directory GET every 20 seconds carrying a unique W3C trace context.

| Measure | Observed |
|---|---:|
| Duration | 600.007 seconds |
| Samples / median interval | 61 / 9.999 seconds |
| Restart-count delta | 0 |
| Readiness | 61 successes, 0 failures |
| Memory | 91,687,485–225,338,982 bytes; 41.97% peak of 512 MiB |
| CPU | 0.707% mean; 1.64% peak |
| Controlled trace requests | 30 HTTP 200, 1 HTTP 401 at access-token expiry |
| New trace query | HTTP 200, 13 spans |
| WAL replay/missing-meta warnings | 0 |
| Scheduler no jobs found messages | 15 |
| Other error-level log lines | 0 |

The 401 occurred at the final request as the ten-minute access token expired; all seven API readiness routes remained 200 at both endpoints of the observation. The observer refreshes tokens for the subsequent longer matrix. This is a bounded local stability result, not a production guarantee.

Raw samples, workload records, summary, and retained logs are in the [Phase 8.1 Tempo evidence directory](../experiments/phase8/results/phase8-1-20261013-run1/tempo/).

## 7. Admission policy and HTTP matrix

Pending the checkpoint 2 preflight and fixed 18-trial matrix. Planned conditions are 4, 16, and 64 concurrent clients at one and two configured Doctor upstreams, three 30-second trials per cell, and a 50/30/20 authenticated GET mix of directory, autocomplete, and profile reads. The benchmark policy uses the existing Redis limiter with a separate policy key namespace, finite budgets, and the verified synthetic fixture principal. Normal budgets remain unchanged.

## 8. Throughput and latency

Pending measured HTTP evidence.

## 9. Response classification and admission preflight

Pending the short authenticated preflight and measured HTTP evidence.

## 10. Resource utilization

Pending per-trial Docker stats and Docker-VM aggregate measurements.

## 11. Horizontal scaling

Pending matched one-versus-two-upstream measurements at each concurrency.

## 12. Graphs

Pending reproducible Graphs 1–4 from retained Phase 8.1 CSV/JSON files.

## 13. Tempo and load-test interaction

The stability observation confirms the 512 MiB cap was sufficient for its low-rate workload. Whether it remains sufficient during the fixed HTTP matrix will be determined from per-trial Docker stats and the 90% guardrail. No sampling or observability setting will be changed between replica conditions.

## 14. Restoration and safety

Pending the matrix cleanup. The runner will restore the original Traefik route bytes and normal Doctor Compose configuration, wait past the bounded benchmark Redis-key TTL, verify normal Redis-backed admission, check Surge Mode remains NORMAL, and confirm Emergency access still requires authentication. No application data volumes are reset.

## 15. Remaining limitations

The prior restart history is represented by the inspected count and retained logs, but the Docker daemon did not return lifecycle events for those earlier restarts. A ten-minute stable observation cannot establish indefinite stability. The performance conclusions remain pending until the preflight and full matrix complete.

## 16. Final verdict

Pending all four checkpoints. Phase 8.1 will be PASS only if the complete matrix is valid, Tempo passes its bounded checks, deployment restoration succeeds, the requested graphs are reproducible, and all changes are committed locally on main. Otherwise the final report will state PARTIAL with the precise stopping evidence.
