# Event contracts

This is the broader event catalog proposal. Phase 5 activates only the two
producer-to-consumer paths documented in
[Phase 5 event contracts](phase-5-event-contracts.md); other entries remain
proposals and must not be treated as active broker subscriptions. The Phase 5
document records the actual envelope, payloads, topology, and recovery behavior.
Phase 5 uses the durable topic exchange `pulsegrid.events`; each active consumer
purpose has its own durable queue, and separate subscribers do not share a queue.

## Envelope and field schemas

```json
{
  "event_id": "123456789012345",
  "event_type": "appointment.booked.v1",
  "schema_version": 1,
  "producer": "appointment",
  "occurred_at": "2026-10-10T14:30:00Z",
  "aggregate_type": "appointment",
  "aggregate_id": "123456789012346",
  "aggregate_version": 1,
  "correlation_id": "37a4a810-9b07-4b32-a51a-725e3a0d693c",
  "request_id": "688ceebc-e089-4908-a519-a3cbdcc18c4e",
  "causation_id": null,
  "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
  "payload": {
    "appointment_id": "123456789012346",
    "journey_id": "123456789012347",
    "patient_id": "123456789012348",
    "doctor_id": "123456789012349",
    "slot_id": "123456789012350",
    "starts_at": "2026-10-11T04:30:00Z",
    "ends_at": "2026-10-11T04:45:00Z",
    "schedule_revision": 1
  }
}
```

IDs are decimal strings, versions positive integers, quantities positive integers, timestamps UTC RFC 3339. All envelope fields above are required; `causation_id` is nullable and names the causing event when there is one. `traceparent` may be null if no context exists. Workers generate request/correlation IDs for scheduled work. `producer` is the singular service name. Wire payload fields below are required unless `?` is shown. No passwords, tokens, clinical notes, diagnoses, or contact addresses in events. Prescription dosage/instructions are fetched through an authorized API; the event includes only required quantity and medicine references.

Definitions:

- `AppointmentPayload`: appointment_id, journey_id, patient_id, doctor_id, slot_id, starts_at, ends_at, schedule_revision.
- `QueuePayload`: appointment_id, journey_id, doctor_id, queue_entry_id, token_number, local_date, state.
- `PrescriptionPayload`: prescription_id, consultation_id, journey_id, patient_id, revision, state, items:[{item_id,medicine_id,quantity}].
- `ReservationPayload`: reservation_id, prescription_id, journey_id, patient_id, state, items:[{item_id,medicine_id,quantity}], expires_at.
- `InvoicePayload`: invoice_id, journey_id, patient_id, currency, total_minor, paid_minor, balance_minor, state, charge_source_keys:[{source_service,source_item_id}].

## Catalog: names, producers, consumers and payloads

| Event name | Producer | Consumers / effect | Payload |
|---|---|---|---|
| `patient.registered.v1` | Patient | Appointment: minimal active patient snapshot | patient_id, user_id, active, patient_version |
| `patient.profile.updated.v1` | Patient | Appointment: invalidate permitted profile hints (no clinical data) | patient_id, patient_version, changed_fields:[string] |
| `patient.account.changed.v1` | Patient | Appointment: patient eligibility; all domain services: invalidate account/role hints | user_id, patient_id?, active, auth_version, patient_version? |
| `doctor.profile.updated.v1` | Doctor | Appointment: nonauthoritative display hints | doctor_id, staff_user_id, profile_version, active |
| `doctor.schedule.proposed.v1` | Doctor | Appointment: serialize proposal, accept or reject local slot changes | proposal_id, doctor_id, revision, previous_revision, timezone, slot_minutes, intervals:[{starts_at,ends_at}] |
| `appointment.schedule.accepted.v1` | Appointment | Doctor: acknowledge displayed activation | proposal_id, doctor_id, revision, accepted_at |
| `appointment.schedule.rejected.v1` | Appointment | Doctor: show actionable conflict | proposal_id, doctor_id, revision, reason_code, conflicting_appointment_ids:[ID] |
| `appointment.booked.v1` | Appointment | Appointment journey consumer: project booked stage; optional frontend notification read model remains local | AppointmentPayload |
| `appointment.cancelled.v1` | Appointment | Appointment journey consumer: cancel episode; Records: invalidate drafts/context; Billing: reconcile any charges by policy | AppointmentPayload + reason_code |
| `appointment.rescheduled.v1` | Appointment | Appointment journey: change schedule; Records: invalidate stale draft assignment | AppointmentPayload + previous_slot_id, previous_starts_at, previous_ends_at |
| `appointment.waitlist.promoted.v1` | Appointment | Appointment journey: promotion visibility | AppointmentPayload + waitlist_entry_id |
| `appointment.checked_in.v1` | Appointment | Appointment journey: check-in stage | QueuePayload |
| `appointment.consultation.started.v1` | Appointment | Appointment journey; Records: assignment hint, never write authorization | QueuePayload + patient_id, doctor_user_id |
| `appointment.no_show.v1` | Appointment | Appointment journey: incomplete episode state | AppointmentPayload |
| `records.consultation.completed.v1` | Records | Appointment: finish queue and consultation stage; Billing: add consultation charge | consultation_id, appointment_id, journey_id, patient_id, doctor_id, prescription_id? (nullable), charge_code |
| `records.record.amended.v1` | Records | Appointment: update relevant completion version, flag review if workflow affected | record_id, consultation_id, appointment_id, journey_id, revision, workflow_review_required:boolean |
| `records.prescription.issued.v1` | Records | Pharmacy: minimal prescription allowance projection; Appointment: prescription stage | PrescriptionPayload |
| `records.prescription.revoked.v1` | Records | Pharmacy: release remaining reservations, flag dispensed items for review; Appointment: reopen stage | prescription_id, consultation_id, journey_id, patient_id, revision, reason_code |
| `pharmacy.reservation.created.v1` | Pharmacy | Appointment: pharmacy pending state | ReservationPayload |
| `pharmacy.reservation.released.v1` | Pharmacy | Appointment: update pharmacy state; Billing: no charge before dispensing | ReservationPayload + reason_code (`expired`, `cancelled`, `prescription_revoked`) |
| `pharmacy.reservation.dispensed.v1` | Pharmacy | Appointment: request fresh journey reconciliation | resource_id, version, state, appointment_id? |
| `billing.invoice.updated.v1` | Billing | Appointment: billing state and discharge eligibility projection | InvoicePayload |
| `billing.payment.succeeded.v1` | Billing | Appointment: request fresh journey reconciliation | appointment_id (new messages); historical unpublished rows may have the earlier proposal payload |
| `billing.payment.reversed.v1` | Billing | Appointment: reopen payment/billing stage | InvoicePayload + payment_id, amount_minor, reason_code |
| `billing.insurance.rules.updated.v1` | Billing | Billing estimate worker: recalculate informational estimates | provider_id, rules_id, revision, fetched_at, source_hash |
| `emergency.request.submitted.v1` | Emergency | Emergency processing worker: eligible work hint | request_id, patient_id? (nullable), state, reported_urgency |
| `emergency.request.status.changed.v1` | Emergency | Emergency status projection / operational metrics | request_id, state, assigned_priority? (nullable until triage), claimed_by_user_id? (nullable), version |
| `appointment.journey.discharged.v1` | Appointment | Appointment journey history / operational metrics | journey_id, appointment_id, patient_id, discharged_at |
| `<service>.cache.invalidated.v1` (Doctor, Pharmacy, Appointment, Billing only) | Owning service | Owning cache invalidation workers/replicas | namespace, entity_id, entity_version, cache_tags:[string] |

Owning transactions update their local journey/status projections directly. The catalog's self-consumer entries describe these local effects; there is no RabbitMQ self-subscription for them. Only cross-service projection effects use inbox consumers. Emergency processing workers may use their submitted-event queue as a wake-up hint, but always claim authoritative DB state. No double application. Metrics typically observe local instrumentation rather than becoming correctness-critical broker consumers. No generic cross-domain notification service is implied.

Cache invalidation queues cannot use competing consumers when every in-memory replica must refresh: use a per-replica ephemeral subscription for hints, plus version polling/rebuild for replicas missing hints. Durable Redis invalidation is performed once by a competing owning worker. A short TTL bounds staleness even after lost hints. Ring version is part of the cache namespace.

## Transactional outbox and delivery

1. In the owning database transaction, validate command, mutate aggregate, append required audit entry, persist idempotency response, and insert immutable outbox envelope. Rollback removes all these effects.
2. Publisher workers claim bounded batches using row locks / leases and `SKIP LOCKED`. Preserve order per aggregate by publishing the lowest unpublished `(aggregate_version, created_at, event_id)` first (multiple events may share one aggregate version); parallelize different aggregates. Do not hold long database transactions across broker waits. Claims have lease expiry so killed publishers recover.
3. Publish persistent messages with publisher confirms and mandatory routing. A nack, timeout, or unroutable message is a failure; do not mark published. Reconcile topology before retrying an unroutable schema/route.
4. Mark published only after confirm. Crash after confirm before marking can produce duplicate delivery and is expected. DB transaction and broker publish are not atomic.
5. Monitor pending count/oldest age, failed publish attempts and storage thresholds. Keep locally accepted commands durable while broker is down; reject new writes with 503 at documented backlog limits, never erase pending messages to recover space.

Outbox lease metadata (`claimed_by`, `lease_expires_at`) is defined in the database proposal; these are local publisher mechanics. Broker consumers use manual acknowledgement only after their local transaction commits. Keep worker prefetch bounded so slow consumers do not monopolize emergency capacity.

## Idempotency, ordering and reconciliation

A consumer transaction inserts `(consumer_name,event_id)` into its inbox, performs side effects, inserts any new outbox event and audit entry, then commits before ack. A duplicate inbox key returns successful ack with no new effect. Business constraints also deduplicate stable charge source IDs, prescription item quantities, reservations and schedule proposal revisions. Never deduplicate solely by correlation ID: many valid events share one journey.

Track last applied version per source aggregate. Older versions are ignored for snapshots; version gaps buffer boundedly and request an owner snapshot/replay. Some versions have no event relevant to that subscription, so gaps are not proof of loss: reconciliation must understand owner snapshot versions. Delta events such as stock/charges are not discarded because a different event of that aggregate arrived first; ledger effects deduplicate by stable source identity, then recompute the projection from authoritative snapshots. Cross-aggregate arrival order is arbitrary. A payment can precede an invoice update; Appointment defers completion until a consistent invoice snapshot arrives. Consultation completion with no prescription explicitly skips prescription/pharmacy stages. With prescription items, all prescribed quantities must be dispensed or an authorized clinician explicitly revokes the unfilled remainder before pharmacy stage completes.

Durable projection state stores source aggregate/version and a per-stage resource map (multiple prescriptions/reservations/payments are possible). The database sketch stores this map as `journey_stages.source_resources` JSONB; one stage summary does not imply one source event per stage. No discharge based solely on a single pharmacy event. Discharge also requires `InvoicePayload.charge_source_keys` to cover all expected consultation and dispensing source identities already collected by the journey; a zero balance without charge coverage is pending. Unpriced charge codes leave invoice generation pending/quarantined, not implicitly free. Version gaps or unknown required stages show pending, never completed. Reconciliation uses the scoped internal APIs; consistency assumptions must be tested with delayed/out-of-order events.

## Retries, poison messages and versioning

Consumer transient failures: initial attempt plus up to five retries with jittered delays approximately 1 s, 5 s, 30 s, 2 min and 10 min; then DLQ and alert. Non-retryable malformed/unsupported contracts and permanent unknown catalog mappings go directly to quarantine/DLQ with safe reason codes. A dependency outage can resume through an operator-managed replay after repair; DLQ never silently drops work. Use broker headers for attempts and guard against retry cycles. No medical payloads in failure logs.

A replay command preserves original event_id and attaches operator/reason metadata to the confirmed replay. It is safe whether the original effect committed or not. Do not change event IDs merely to bypass inbox deduplication. Retention defaults match database-design.md: published outbox >=7 days, inbox >=30 days, business identity uniqueness for aggregate lifetime. Backfills beyond retained messages reconcile against owner state; do not imply arbitrary historical replay availability.

Payload evolution: optional additive fields keep v1, consumers ignore unknown optional fields. Breaking schema/meaning changes create `.v2` routing keys and separate reviewed schemas, with dual-publish or bridging during a documented migration window. Deduplication uses a stable business effect ID across v1/v2 so dual-publish does not double-charge. Preserve producer and consumer contract tests and sanitized examples for both supported versions. RabbitMQ payloads are sensitive even without clinical text; service queue permissions and retention apply.
