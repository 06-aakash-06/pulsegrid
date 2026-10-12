# Architecture

This architecture reflects the implemented Phase 2–6 service boundaries and
selected workflows. The [Phase 4 component contract](phase-4-component-contracts.md)
and [parallel plan](phase-4-parallel-plan.md) retain their historical preparation
scope; implementation status and evidence are in the phase verification reports.

## Scope and decisions

Appointment uses bounded authenticated owner REST snapshots and durable local
polling/reconciliation for waitlist offers, check-in, consultation queues and
journeys. Selected Phase 5 outbox/inbox event paths wake that reconciliation;
owner APIs and PostgreSQL remain authoritative. Expected charge-source
acknowledgments and fresh owner versions gate administrative discharge. Phase 6
adds shared Surge Mode admission and bounded optional snapshot resilience. The
Control Room, broad event adoption, and infrastructure HA remain out of scope.

PulseGrid serves one synthetic hospital. It includes patient and staff workflows
and emergency request tracking. Multi-hospital networking, emergency bed
management, family health profiles, predictive autoscaling, forecasting, and a
restricted distributed systems control room are excluded. Phase 4 components,
selected Phase 5 event delivery, and Phase 6 resilience controls are implemented
under separate authorizations. See the [Phase 3](phase-3-integration-verification.md),
[Phase 4](phase-4-integration-verification.md), [Phase 5](phase-5-integration-verification.md),
and Phase 6 verification records.

The stack is React/TypeScript, Python/FastAPI, PostgreSQL, Redis, RabbitMQ, Traefik, Docker Compose, Locust, Prometheus/Grafana, and OpenTelemetry. Avoid Kubernetes and additional infrastructure unless a later requirement justifies it through an architecture decision documented here.

Seven domain services are independently packaged and deployable. One prototype PostgreSQL instance hosts seven logical databases with separate credentials. Redis, RabbitMQ, routing, and telemetry are shared infrastructure, never domain ownership authorities. Stateless API replicas share only their own persistent database and explicit infrastructure. No service imports another service's ORM or queries its database. External references are IDs with validated local snapshots, never cross-database foreign keys.

```mermaid
flowchart TB
  UI[React patient and staff UI]
  CR[Restricted control room]
  GW[Traefik API gateway]
  UI --> GW
  CR --> GW
  GW --> P[Patient]
  GW --> D[Doctor]
  GW --> A[Appointment]
  GW --> R[Records]
  GW --> PH[Pharmacy]
  GW --> B[Billing]
  GW --> E[Emergency]
  P --> PDB[(Patient DB)]
  D --> DDB[(Doctor DB)]
  A --> ADB[(Appointment DB)]
  R --> RDB[(Records DB)]
  PH --> PHDB[(Pharmacy DB)]
  B --> BDB[(Billing DB)]
  E --> EDB[(Emergency DB)]
  P & D & A & R & PH & B & E --> MQ[RabbitMQ events via outboxes]
  D & PH & A & B --> C[Redis cache pools]
  GW --> RL[Redis admission middleware in services]
  RL --> C
  P & D & A & R & PH & B & E --> OT[OpenTelemetry collector]
  P & D & A & R & PH & B & E --> PM[Prometheus]
  MQ & C & GW --> PM
  PM --> G[Grafana]
  OT --> TS[Trace storage: local bounded collector file sink initially]
  G --> CR
```

Arrows to RabbitMQ represent publishers and subscriptions, expanded below. Traefik routes; admission middleware executes in each service before business logic, using the distributed rate limiter. All business routes pass admission, including internal calls with separate trusted budgets. Compose services and the displayed middleware are not an eighth domain service. Grafana/trace access is through restricted infrastructure routes, not direct public telemetry endpoints. Initial file-backed tracing is a bounded development artifact, not a production query backend; a later observability decision must select a simple trace query backend for control-room trace search (see roadmap Phase 8).

## Authorities and critical consistency boundaries

| Boundary | Authority and guarantee | Replicas and stale reads |
|---|---|---|
| Identity, credentials, roles, refresh revocation | Patient DB transactions; token claims bounded by expiry | Local JWT verification; privileged mutations check current authorization |
| Approved schedule and active bookings | Appointment DB active slot revision, row locks, unique active booking per slot | Availability caches can lag; booking revalidates locally in transaction |
| Medical records and final prescriptions | Records DB transactions, revisions and access checks | Pharmacy receives a validated prescription projection by event |
| Inventory and reservations | Pharmacy DB conditional stock updates and reservation state | Search caches never authorize reservation/dispensing |
| Invoice state and simulated payment | Billing DB locking, unique payment idempotency and source charges | Estimate projections are eventual, not final invoice authority |
| Emergency priority/claim state | Emergency DB atomic claim and version checks | Tracking projections can lag; emergency capacity is separate |
| Sensitive audit history | Per-service database ordered hash chain in the mutation transaction | Independent chains; no global total order is claimed |

Strong consistency is local to each row/aggregate and its service database. Eventual consistency applies to discovery caches, schedule acknowledgement views, journey timeline, prescription delivery, insurance estimates, invoice generation, metrics, and notifications. No request claims completion for another service before that service has committed it.

## Synchronous communication

Browser -> Traefik -> owning service is the default. Services validate JWT audience/issuer, RBAC, resource ownership, and admission budgets themselves; gateway checks are insufficient.

- Doctor profile and policy discovery: Doctor API; operational availability: Appointment API.
- Records checks Appointment consultation assignment before a clinician finalizes a consultation/prescription. Pharmacy checks Records' current prescription revision and revocation before dispensing. Fail closed if unavailable; a prior cached result cannot authorize these writes.
- Privileged writes use Patient's internal authorization check for current account/role status. Patient is consequently a dependency for sensitive operations. Nonprivileged patient reads use short-lived claims and resource ownership checks.
- Cross-service reference validation occurs before opening local transactions. Versioned response snapshots and conditional writes prevent local stale updates. Remote validation cannot create a global transaction; revocation races require compensation/review as described in security.
- Aggregated journey reads come from Appointment's event projection with `observed_at` and per-stage pending state. UI may separately retrieve Records, Pharmacy, and Billing resources with their own permissions.

Initial configurable targets: external request deadline 3 s; downstream call timeout 1 s; maximum two attempts including the first, within the parent deadline, with exponential backoff and jitter. Retry safe reads and writes only with a persisted idempotency key. Never retry validation errors or blindly retry POST. Circuit opens after five consecutive connection/time-out failures, waits 15 s, then admits a bounded half-open probe. These are experiment starting points, not measured tuning results. Pass remaining deadlines to downstream calls; no network calls inside database lock scopes.

## Asynchronous communication and schedule handoff

RabbitMQ durable topic exchange `pulsegrid.events` routes event names to one durable queue per logical consumer, with multiple competing worker replicas. Publishers use transactional outboxes and publisher confirms. Consumers use inbox deduplication and local transactions. Delivery is at least once; business effects must be effectively once. There is no globally ordered delivery.

Doctor owns schedule intentions, timezone, specialty, appointment length, and profile. Appointment owns accepted bookable slot revisions and local copies of scheduling rules needed for correctness. Doctor submits a new immutable schedule version in `doctor.schedule.proposed.v1`. Appointment serializes processing per doctor, reconciles affected slots and active bookings, and publishes `appointment.schedule.accepted.v1` or `appointment.schedule.rejected.v1`. Doctor activates its display version on acknowledgement. Proposal is pending until then. Appointment processes proposal revisions in order, including rejected revisions; `previous_revision` names the previous proposal, not the last accepted schedule. Gaps trigger replay/reconciliation. Doctor tracks both last decided proposal revision and last accepted operational revision. Changes overlapping active bookings are rejected with conflict IDs; an authorized explicit reschedule/cancellation must resolve conflicts first. Appointment's committed accepted version controls availability even if acknowledgement delivery is delayed. New bookings never depend on querying Doctor during their transaction.

```mermaid
sequenceDiagram
  participant C as Client
  participant A as Appointment
  participant DB as Appointment DB
  participant Q as RabbitMQ
  participant R as Records
  participant PH as Pharmacy
  participant B as Billing
  C->>A: Book slot + Idempotency-Key
  A->>DB: Lock slot, validate revision, insert booking + outbox
  DB-->>A: Commit
  A-->>C: 201 confirmed appointment
  A->>Q: appointment.booked.v1 (confirmed publish)
  C->>A: QR token check-in
  A->>DB: Consume token, check in, create unique queue token + outbox
  A->>Q: appointment.checked_in.v1
  R->>A: Validate current consultation assignment
  R->>R: Finalize consultation/prescription + outbox
  R->>Q: records.consultation.completed.v1 / records.prescription.issued.v1
  Q->>PH: Prescription projection
  Q->>B: Consultation charge source
  C->>PH: Reserve and dispense through authorized staff
  PH->>R: Validate prescription current revision before dispensing
  PH->>PH: Stock and dispensing transaction + outbox
  PH->>Q: pharmacy.dispensed.v1
  Q->>B: Unique medicine charge sources
  B->>B: Create/update invoice transaction
  B->>Q: billing.invoice.updated.v1 / billing.payment.succeeded.v1
  Q->>A: Deduplicated journey projection
```

The consultation is not blocked by billing or insurance estimates. Appointment receives consultation completion to advance its queue and journey. The event catalog defines each subscription, including asynchronous projection events omitted from the diagram.

## Booking, waitlists, queues, and journey

A slot represents one doctor and one fixed non-overlapping interval, with capacity one in the initial model. Appointment materializes slots from accepted schedule versions. Unique active booking and interval overlap constraints backstop row locks. Cancelled or completed historical slots cannot be booked after their booking cutoff; completion does not make a past interval discoverable again. Cancellation and promotion occur in one transaction under the slot lock: release booking, choose oldest eligible waiting entry by `(joined_at, id)`, create confirmed booking, update waitlist, append outbox events. Once waiting entries exist, new arrivals join behind them; they cannot take a released slot between cancellation and promotion. Promotion creates a confirmed appointment, visible to the patient without relying on notifications. Eligibility uses validated local patient-active snapshots; stale deactivation is reconciled and can cancel an ineligible promotion. This is not a globally instantaneous account check.

Rescheduling locks source and target slots in sorted ID order, validates the target and waitlist fairness, moves the booking, and promotes the source waitlist atomically. On conflict everything rolls back; the source appointment survives. One patient cannot hold overlapping active appointment intervals. Check-in consumes a one-use short-link token and verifies patient, appointment, state, and configurable check-in window atomically. Queue tokens have unique doctor/day sequence numbers; display positions are recomputed from state and are not permanent numbers. Consultation start is an Appointment command; a clinician may hold only one in-progress consultation at a time.

Appointment's journey projection follows registration -> appointment -> check-in -> consultation -> prescription -> pharmacy -> billing -> discharge. Registration starts the profile; the episode/journey starts with booking. Each booking has its own `journey_id`, retained on rescheduling. Pharmacy is optional when there is no prescription. Discharge is a local Appointment command gated on committed completion projections for required stages and zero invoice balance, with the invoice projection acknowledging every expected consultation/dispensing charge source ID. A paid invoice missing a delayed pharmacy charge is not discharge-ready. Missing/out-of-order events leave pending stages; version gaps are reconciled. A later prescription revocation, clinical amendment, invoice adjustment, or payment reversal can reopen the relevant stage and require a new discharge decision. Never infer medical discharge suitability: this is a simulated workflow completion.

## Integrated system-design components

| Component | Workflow and planned owner | Correctness/failure behavior | Evaluation |
|---|---|---|---|
| Token bucket | Common service admission middleware; Redis atomic script; Emergency separate capacity | Atomic tokens across replicas; Redis outage uses conservative local budgets, never unbounded fail-open | Allowed/denied totals, fairness, latency, surge vs baseline |
| Consistent hashing + virtual nodes | Doctor/Pharmacy cache clients place search/profile keys across optional Redis cache nodes | Separate cache pool from dedicated rate-limit Redis; versioned ring changes use cache miss/refill or dual read during bounded transition | Remapping fraction, balance, hit rate for add/remove |
| Key-value store | Redis cache-aside in Doctor/Pharmacy, optional availability and estimate caches | DB authoritative; outbox invalidation + TTL + monotonic versions; stale misses rehydrate | Hit/miss p50/p95 and DB load vs no cache |
| Snowflake IDs | Independently owned service modules with identical reviewed algorithm contract | 41-bit time + 10-bit worker + 12-bit sequence, 63-bit nonnegative; explicit worker allocation and rollback refusal | Collisions, rollover, restarts, rollback and IDs/s |
| URL shortener | Appointment `/s/{token}` resolves opaque appointment/check-in links | Random 128-bit token encoded Base62, hashed at rest, expiring, revocable; authenticated redemption | Collisions, expiry, replay rejection, resolution latency |
| Web crawler | Billing-owned worker extracts insurance fixtures via isolated synthetic provider HTTP sites | Allowlisted hosts, bounded extraction; versioned provenance; estimates can be stale | Accuracy against fixture truth, timeout and freshness |
| Trie/radix trie autocomplete | Doctor doctor/specialty lookup; Pharmacy medicine lookup; per-replica read snapshots | Updated from owning DB versions; periodically reconcile; errors fall back to indexed prefix query | Memory, build time and prefix p95 vs PostgreSQL baseline |

Snowflake epoch is planned as `2026-01-01T00:00:00Z`. Assign worker ID `(service_code << 7) | replica_code`, service codes Patient=0, Doctor=1, Appointment=2, Records=3, Pharmacy=4, Billing=5, Emergency=6; replicas 0..127. Infra assigns unique active replica codes. Persist a per-worker high-watermark in the owning DB and acquire an exclusive DB advisory lock for worker lifetime on a dedicated connection. Stop generating on lock loss, clock rollback, or DB uncertainty; reserve timestamp ranges durably before emitting IDs so restart cannot repeat issued ranges. Sequence exhaustion waits for the next eligible millisecond. Formalize and test range reservation in the ID phase before use. IDs are JSON strings to avoid JavaScript precision loss, never authorization secrets. A shared standards contract is permitted; a shared runtime service or ORM is not required.

## Surge mode, fault isolation, and observability

All seven owner APIs use the existing Redis-backed admission component when its
Phase 4 flag is enabled. Server-owned route templates assign Class A critical,
Class B important, or Class C deferrable policy. No caller field, token claim,
or header selects a class. NORMAL keeps existing route quotas. In SURGE and
RECOVERY, per-class Redis bucket namespaces preserve a finite Class A budget
while reducing B/C capacity and refill. Emergency retains isolated source,
authenticated-principal, and current-staff policy partitions. Redis failure uses bounded local buckets;
B/C select the SURGE profile and A remains finite. These quotas are safeguards,
not clinical capacity guarantees.

Appointment exposes the narrow `hospital_admin` Surge Mode API. State is a
versioned Redis record shared by replicas and manual transitions append to the
existing Appointment audit chain. SURGE expires after 30 minutes into a
two-minute RECOVERY window; operator transitions have cooldowns and an audited
incident override. Automatic activation is disabled because the available
metrics are process-local and cannot distinguish aggregate system pressure from
one abusive client. There is no added dashboard or collector.

Appointment's optional Records, Pharmacy, and Billing journey snapshot GETs use
one process-local breaker and two-request bulkhead per owner. The breaker opens
after three counted failures in a 10-second window, permits one half-open probe
after five seconds, and closes on a valid response. Only these idempotent reads
retry once within a one-second deadline. A 404, business 4xx, or 429 does not
count as dependency failure. An unavailable source remains pending and cannot
authorize discharge. Doctor's existing optional owner reads retain their own
bounded retry/breaker behavior; critical writes and local PostgreSQL mutations
are outside these breakers.

Existing `/metrics` endpoints expose bounded process-local counters and gauges;
they are not a cross-replica aggregation service. No patient IDs, tokens, or
clinical data are metric labels. Health remains based on the local database and
required synchronous dependencies. Redis or broker outage does not remove the
outbox, audit, idempotency, or domain database as business authority. Circuit
breaker and bulkhead failures leave optional work pending rather than inventing
success.

Chaos experiments run only against synthetic isolated deployments with an
explicit target, stop condition, baseline, expected degraded behavior, and
recovery verification. Do not confuse an injected fault or synthetic request
volume with clinical resiliency proof.

## Distributed transaction trade-offs and deployment limitations

No two-phase commit. Every domain mutation plus its outbox/audit entry is one local transaction. Downstream actions are pending until applied, may retry, and may require compensating business commands. Examples: revoked prescription releases unfilled reservations; already-dispensed items trigger staff review; cancelled consultation charges create an explicit invoice adjustment rather than deleting history. Services retain authoritative state and provide internal reconciliation APIs for events missed past retention.

Potential prototype single points of failure: PostgreSQL instance (all seven databases), RabbitMQ instance, dedicated Redis admission node, gateway instance, Compose host/network/disk, and telemetry storage. Cache nodes can disappear without losing domain correctness; rate limits degrade. PostgreSQL outage blocks authoritative writes; RabbitMQ outage delays projections until outboxes replay. Shared instance CPU/I/O and connection limits cause correlated failures despite logical ownership. Configure per-service connection budgets and resource limits. Multiple API replicas alone do not provide infrastructure high availability. Backups/restore, broker replication and separate database hosts are later experiments; the prototype makes no HA claim for them.

Compared with a monolith this design adds network latency, duplicate snapshots, seven migration streams, schema/event compatibility management, outbox/inbox storage, authorization hops, tracing and more operational failure modes. These costs are intentional educational scope. Keep the frontend a single application and use simple local transactions; split only the seven required domains. Infrastructure shared libraries must be narrow and versioned; avoid coupling domain releases through a universal shared model.
