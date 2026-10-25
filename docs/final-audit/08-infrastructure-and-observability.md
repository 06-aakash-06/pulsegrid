# Infrastructure isolation, repairs and observability

## Retained environment

The retained project is `pulsegrid`; frontend/gateway are 5173/8080. Seven domains have independent logical DBs/roles on one PostgreSQL instance; Doctor has two API processes. Redis admission, two cache nodes, RabbitMQ, Traefik, three synthetic fixture hosts and optional monitoring remain the existing architecture. Unrelated `sdrecord-*` containers were untouched.

Only retained Appointment was recreated to apply validated source fixes. No migration was needed. Previous image remains tagged `pulsegrid-audit-rollback-appointment:20261025`; [old/new image IDs and exact actions](evidence/retained-repair-application.json). The existing consumer's anchored write whitelist gained only `pulsegrid.dlx`; no password, role tag, publisher grant or .env was changed. Neither change mutates retained business records for testing.

After repair: **eight readiness HTTP 200; 223 Python package hashes across seven domains match checkout; both selected broker queues have one consumer and zero backlog/DLQ messages**. [Final retained checks](evidence/final-retained-health.json). These are point-in-time results, not infrastructure HA or a soak test.

## Audit-only project

`pulsegrid-audit-20261025` used separate network and volume identities, gateway 18880, frontend 19173 and Grafana 13000. All shared binds were read-only. Network overlap was checked against existing Docker networks; final custom subnets were 10.251.100.0/24 and 10.251.101.0/24. The initial overlapping candidate was rejected before mutations. [Manifest](evidence/isolation-manifest.json).

All functional mutations, concurrency races, cache/broker/dependency outage tests, poison delivery and Surge changes used this project or disposable local PostgreSQL clusters. No retained DB/volume/audit chain was reset/deleted. The private ignored `secrets/final-audit/` contains restart configuration and synthetic fixtures and is deliberately absent from Git. Audit shutdown stops only its containers/Vite listener, preserving volumes and history; [cleanup evidence](evidence/cleanup.json) records the final state.

## Monitoring and bounded live checks

Prometheus/Grafana/Tempo health endpoints returned 200. Protected Control Room summary and Trace Explorer search/detail returned real data. A Doctor request with an explicit fresh W3C trace ID was exported and returned 13 Doctor spans via the bounded operator endpoint. [Evidence](evidence/live-observability.json). The test proves a fresh correlated trace, not a full multi-owner event trace or continuous export stability.

Doctor admission counter deltas from both replicas match HTTP results after correcting the verifier's sum across state/class labels. Live cache fallback and selected event queue state are independently recorded. Control Room was visited as admin/ops, including four-size samples; ops mutation denial passed. Metrics and traces remain observational, optional and bounded; no arbitrary PromQL/URL proxy or business authority was added.

Manual Surge activation, authorized deactivation to RECOVERY and automatic return to NORMAL were observed in isolation. Both cache nodes recovered healthy. One status GET returned 503 `admission_unavailable`; later GET confirmed NORMAL/recovery_elapsed. This is explicit incomplete stability evidence, not a silently retried PASS.

## Tempo remains an open operational item

Retained Tempo has a 512 MiB cap and restart count 4 at both the initial and final inspections; current OOMKilled=false and running/ready. The initial bounded log window included scheduler `no jobs found` warnings/errors. No additional restart was observed between these inspections, but lifecycle causation and long-term stability remain unproven. Historical memory-related incidents cannot be declared fixed from these facts. No WAL/trace data was deleted, memory setting guessed, or healthy Tempo restarted to manufacture a clean count.

Live alert firing, telemetry-component outage injection, resource-exporter installation, sustained memory correlation, restore/soak and a broad new performance campaign remain unexecuted. The Grafana infrastructure dashboard truthfully reports absent resource export; generic Emergency HTTP metrics are not dedicated triage/processing business metrics. Earlier targets and decisions are separated in [missing-feature reconciliation](10-missing-features.md).
