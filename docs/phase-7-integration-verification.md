# Phase 7 integration verification

Status: **PASS** for the requested synthetic, local Compose scenarios. Verified
on 2026-10-13. This is an educational single-hospital prototype result, not a
production readiness, clinical safety, or performance claim.

## Live stack

Prometheus scraped all eight configured API instances (the seven domains plus
`doctor_replica`) and all eight corresponding readiness probes. The live target
counts were: `pulsegrid_api` 8/8 up, `pulsegrid_readiness` 8/8 up, and one up
target each for Prometheus, RabbitMQ, and Traefik. Control Room reported seven
healthy domain services, four Appointment/RabbitMQ queues, no firing alerts,
and Surge Mode `NORMAL`.

Prometheus uses a 15-second scrape and evaluation interval, seven-day/1 GiB TSDB
retention, and its own named volume. The two Doctor processes reported hashing
epoch 3 and two configured nodes each through
`pulsegrid_consistent_hashing_topology_epoch` and
`pulsegrid_consistent_hashing_configured_nodes`. These gauges describe the
configured ring; they do not claim that either cache node is healthy.

Grafana loaded four provisioned dashboards (PulseGrid Overview, Distributed
Systems, Event-Driven Workflows, and Infrastructure), 32 panels, and two data
sources (Prometheus and Tempo). All 30 PromQL expressions in the dashboard
files returned Prometheus `success`. `promtool check rules` found 14 rules.
There were zero firing alerts during the check; no alert was deliberately
triggered and resolved.

## Synthetic scenarios

| Scenario | Result |
|---|---|
| Doctor directory search and cache | Authenticated `GET /api/v1/doctors?q=Synthetic` returned nine synthetic profiles. Prometheus showed Doctor cache `miss` and `hit` observations and a 2xx HTTP request series. The safe trace detail API returned a 123-span search/booking trace containing Doctor and Appointment spans. |
| Real booking | A fresh synthetic Doctor schedule was accepted and reconciled through the Doctor and Appointment owner APIs. A patient booking returned 201; the Appointment HTTP metric recorded the successful request and the trace continued through Doctor, Patient, and Appointment. |
| Pharmacy event delivery | A synthetic appointment was checked in, a synthetic prescription was authored, and Pharmacy dispensed it through its API. The Appointment journey's Pharmacy stage reached `complete`. The current-process counters showed three confirmed Pharmacy outbox publishes and one Appointment consumer processing with outcome `pharmacy`. The safe trace detail returned 50 spans, including one `rabbitmq publish` and one `rabbitmq process` span across Pharmacy and Appointment. |
| Surge Mode | The admin activated `SURGE` with `capacity_pressure`. Four authenticated deferrable Doctor searches all returned 200. Prometheus recorded two Class C decisions on each Doctor process. Admin recovery moved the state through `RECOVERY` to `NORMAL`; after two minutes the state was `NORMAL` with reason `recovery_elapsed`. |
| Monitoring outage | Prometheus was stopped. Patient readiness, Doctor search, Appointment availability, and a synthetic booking still returned 200/201; the Control Room returned its safe 503 monitoring-unavailable response. Prometheus was restarted, and the Control Room returned to `available` with seven services and four queues. The `pulsegrid_prometheus_data` volume and application data volumes were preserved. |

The Control Room rejected unauthenticated access with 401 and a patient role
with 403; an authorized hospital administrator could read the live summary and
safe trace details. Trace detail includes only service, safe operation, start
time, and duration, capped at 500 spans. The browser cannot supply PromQL,
Tempo URLs, queue names, or arbitrary trace filters.

Earlier proposals to replace a used synthetic Doctor schedule were correctly
rejected because they would remove four confirmed five-minute slots. The final
booking and Pharmacy scenarios used a separate synthetic Doctor schedule and
preserved all existing appointments. The rejected proposals and resulting
verification history remain in the local synthetic environment.

## Checks run

- `./.venv/bin/python tests/run_phase2_regressions.py`: 616 passed, 52 skipped;
  Records' isolated PostgreSQL suite: 77 passed.
- Focused Phase 7 backend tests for Doctor hashing metrics and the Appointment
  Control Room: 8 passed.
- Frontend `npm run typecheck`: passed; `npm test -- --run`: 9 files and 131
  tests passed; `npm run build`: passed.
- `docker compose -f compose.yaml -f compose.phase4.yaml -f compose.observability.yaml config --quiet`: passed.
- Prometheus `promtool check config`: valid; `promtool check rules`: 14 rules
  found.
- Live Prometheus target, hashing, cache, booking, outbox, and consumer queries
  passed. All 30 dashboard PromQL expressions executed successfully.
- Compose reported all seven domain services healthy, including both Doctor
  instances. No PostgreSQL, Redis, or RabbitMQ volume was reset; nothing was
  pushed to a remote.

## Limits observed

These are local resource caps: Prometheus 256 MiB/0.25 CPU, Tempo 256 MiB/0.25,
Grafana 256 MiB/0.25, OpenTelemetry Collector 128 MiB/0.10, and Blackbox 32
MiB/0.10. One `docker stats` sample during verification reported Prometheus
53 MiB, Tempo 154 MiB, Grafana 213 MiB, and Collector 62 MiB; these are
instantaneous observations, not steady-state sizing results. None of those
containers was marked OOM-killed. Tempo's Docker restart count reached 13
(`OOMKilled=false`). Its logs repeated a scheduler `no jobs found` message and
reported dropping an incomplete WAL block whose `meta.json` was missing. After
that restart, `/ready` returned 200 and the 50-span Pharmacy trace was still
queryable. The restart cause and WAL warning were not root-caused and should be
revisited before any non-local deployment.

PostgreSQL, Redis, and container CPU/memory have no exporter in this stack, so
their dashboard panels remain no-data. The alert rules were syntax-checked but
were not tested by inducing a firing condition. The dashboard queries were
executed against Prometheus; no browser screenshot or visual layout check was
performed. No load/chaos benchmark or real clinical validation was run.
Tempo uses local storage with 24-hour block retention; telemetry is sampled at
100% in this controlled local Compose setup and should be configured for a
deployment's needs.

## Local checkpoint commits

1. `94ad8de` — Document Phase 7 observability design.
2. `1012a7b` — Implement Phase 7 Prometheus metrics collection.
3. `586f8fa` — Implement Phase 7 tracing and Control Room API.
4. `0cd91be` — Provision Grafana dashboards and Prometheus alerts.
5. `9db3588` — Add the live operations Control Room.
6. This integration report completes the documentation and verification
   checkpoint. All commits are local on `main`; no remote push was performed.
