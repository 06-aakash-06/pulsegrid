# Database design

Phase 1.1 defined this schema. Phase 1.4B implements its initial storage in seven service-owned Alembic histories on one PostgreSQL instance; transactional algorithms and the explicitly deferred overlap exclusions remain later work. See [the infrastructure decisions and runbook](infrastructure.md) for exact tables, privileges and deferrals. Seven separate PostgreSQL logical databases initially share an instance. Each has its own non-superuser migration owner and restricted runtime account, with no access to other databases. A later host split changes connection configuration, not domain foreign keys. No cross-database joins, FDWs, dblink, shared domain tables, or direct reads of another service's outbox.

## Common conventions

`id` is a nonnegative signed BIGINT generated locally by the planned Snowflake algorithm and serialized as a decimal string. IDs are not authorization secrets. All times use `timestamptz`, stored/returned in UTC; Doctor preserves an IANA schedule timezone for local-day interpretation and DST validation. Time intervals are half-open `[start,end)`. Mutable aggregates have `version BIGINT`, `created_at`, `updated_at`; conditional writes require expected version. Money uses integer minor units plus ISO currency (initially INR); quantity uses bounded positive integer units, never floats. Check constraints enforce state/value ranges. Lifecycle state transitions are explicit, not arbitrary string assignments.

FKs below are exclusively inside the listed database. External references marked `ref` are IDs with application-level verification and versioned snapshots. Required refs are NOT NULL except explicitly anonymous emergency identity. Delete policies preserve history: credentials can be revoked, domain rows archived; clinical/audit/financial rows are not cascade-deleted. Local association rows can use ON DELETE RESTRICT where history exists.

Every database plans `outbox_events(event_id PK, aggregate_type, aggregate_id, aggregate_version, event_type, envelope JSONB, created_at, published_at nullable, attempt_count, next_attempt_at, claimed_by nullable, lease_expires_at nullable)`, `inbox_events(consumer_name, event_id, processed_at, PRIMARY KEY(consumer_name,event_id))`, `idempotency_requests(principal_scope, method, route_template, key, request_hash, response_code, response JSONB, expires_at, UNIQUE(principal_scope,method,route_template,key))`, `audit_heads(chain_id PK,last_sequence,last_hash)`, `audit_entries(chain_id,sequence,entry_id UNIQUE,prev_hash,entry_hash,canonical_metadata,created_at,PRIMARY KEY(chain_id,sequence))`, and `id_worker_state(worker_id PK,reserved_through_ms)`. UUIDs for request/correlation/trace identifiers are separate from domain IDs. Audit chain serialization is per service, with a locked chain head; partition by documented scope only if scalability tests justify it.

An idempotency conflict with different request content returns 409. Concurrent equal keys serialize and replay the committed response; business data, response record, outbox, and audit commit together. Retain response keys at least 24 h for normal commands, seven days for simulated payments; durable business uniqueness protects delayed duplicate events beyond this window. Never retain raw passwords, JWTs or QR/tracking tokens in idempotency responses. Token-issuing commands store only a sanitized outcome; lost first responses require explicit token reissue and cannot replay secrets (see api-contracts.md). `principal_scope` is a nonnullable typed string for authenticated user/service IDs or a hashed client-supplied random anonymous command nonce; anonymous replay does not expose private data or tokens.

## Patient database

- `users(id PK, email_normalized UNIQUE, password_hash, account_state, auth_version)`; email normalization is documented and consistent, not ad hoc lowercase rules per endpoint.
- `patient_profiles(id PK, user_id FK users UNIQUE, display_name, date_of_birth, synthetic_contact)`; profile ID is the cross-service `patient_id`.
- `role_assignments(id PK, user_id FK users, role, UNIQUE(user_id,role))`.
- `refresh_sessions(id PK, user_id FK users, family_id, token_hash UNIQUE, expires_at, family_expires_at, revoked_at, replaced_by_id FK refresh_sessions nullable)`; single-use rotation and family replay detection.
- `access_grants` are not here: Records owns patient-to-record access grants. User roles remain here.

Index normalized email; refresh family/user and expiry; patient profile lookup by user. Registration inserts user, patient profile, role, audit and registration outbox atomically. Authentication rotates/revokes sessions atomically. Role mutations increment `auth_version` and emit an account-state event; service replicas do not independently author roles.

## Doctor database

- `doctors(id PK, staff_user_id ref UNIQUE, display_name, active, profile_version)`.
- `specialties(id PK, slug UNIQUE, name)` and `doctor_specialties(doctor_id FK doctors,specialty_id FK specialties, composite PK)`.
- `schedule_versions(id PK, doctor_id FK doctors, revision, timezone, slot_minutes, effective_from, status, UNIQUE(doctor_id,revision))`.
- `schedule_intervals(id PK, schedule_version_id FK schedule_versions, starts_at, ends_at)`; bounds/length checks and no overlapping intervals per version (local GiST exclusion, implemented in Doctor revision `0002_schedule_exclusion`).
- `schedule_acknowledgements(id PK, schedule_version_id FK schedule_versions UNIQUE, accepted, operational_version, reason)`.

Only one unacknowledged proposal per doctor via a partial unique index for `status='pending'`. Version creation and proposal outbox commit together. Acknowledgement consumption and status update commit together. Index doctor active/name normalized prefix and specialty association; ordinary B-tree text prefix with appropriate collation/operator class provides autocomplete baseline before trie experiments.

## Appointment database

- `doctor_schedule_snapshots(doctor_id ref PK, accepted_revision, policy_snapshot, staff_user_id ref, last_decided_proposal_revision, version)`.
- `schedule_proposals(id PK, doctor_id ref, revision, state, UNIQUE(doctor_id,revision))` records accepted/rejected decisions for replay.
- `slots(id PK, doctor_id ref, schedule_revision, starts_at, ends_at, state, UNIQUE(doctor_id,starts_at,ends_at))`; GiST exclusion `(doctor_id WITH =, tstzrange(starts_at,ends_at,'[)') WITH &&)` for bookable/nonretired slots. Use PostgreSQL `btree_gist` in a later migration, not now.
- `appointments(id PK, patient_id ref, slot_id FK slots, doctor_id ref, starts_at, ends_at, schedule_revision, state, version)`; copied doctor/time must match locked slot, enforced by transaction and later trigger/constraint design. Partial unique `(slot_id)` WHERE state IN ('confirmed','checked_in','in_consultation'); partial GiST exclusion `(patient_id WITH =, tstzrange(starts_at,ends_at,'[)') WITH &&)` for the same active states prevents overlapping patient bookings across doctors. Historical completed/cancelled rows release capacity.
- `waitlist_entries(id PK, slot_id FK slots, patient_id ref, state, joined_at, promoted_appointment_id FK appointments nullable, skip_reason nullable)`; partial UNIQUE `(slot_id,patient_id)` WHERE state='waiting'. Order `(slot_id,state,joined_at,id)`; one waiting row per patient/slot. Active appointment and waitlist for that same patient/slot are mutually exclusive, checked under the slot lock.
- `patient_status_snapshots(patient_id ref PK, active, source_version, observed_at)`; eventual eligibility and reconciliation.
- `checkin_links(id PK, appointment_id FK appointments, token_hash UNIQUE, purpose, expires_at, consumed_at, revoked_at)`; only one active purpose-specific link by transactional revocation on reissue. Expiry is evaluated at redemption, not a time-dependent index predicate.
- `queue_counters(doctor_id ref, local_date, next_token, composite PK)` and `queue_entries(id PK, appointment_id FK appointments UNIQUE, doctor_id ref, local_date, token_number, state, UNIQUE(doctor_id,local_date,token_number))`; partial UNIQUE `(doctor_id)` WHERE state='in_consultation'. Counter allocation is atomic, gaps are acceptable.
- `journeys(id PK, appointment_id FK appointments UNIQUE, patient_id ref, state, version)` and `journey_stages(journey_id FK journeys, stage, state, source_resource_id ref nullable, source_version, source_resources JSONB, observed_at, composite PK(journey_id,stage))`; The API/event `journey_id` is obtained from `journeys.appointment_id`; there is no redundant circular appointment-to-journey FK. Create appointment and journey in the same transaction.

Book transaction locks doctor snapshot then slot, validates active revision/state and patient conflicts, checks waitlist fairness, inserts appointment/journey and outbox. A uniqueness/exclusion violation returns 409, not a 500. Lock schedule snapshot before slot edits; all booking/schedule operations use that same doctor lock order. Cancellation locks doctor snapshot and slot, changes state, promotes oldest eligible waitlist, emits events. Waitlist promotions must also respect patient overlap exclusion: use savepoints to mark ineligible/conflicting entries skipped and try the next candidate, not roll back the cancellation. Candidates retain a reason and can rejoin explicitly.

Rescheduling locks involved doctor snapshots and then slots in sorted IDs, moves appointment (same journey), records change and promotes old slot. All Appointment commands acquire locks in this order where applicable: doctor snapshots sorted by doctor ID, slots sorted by slot ID, appointments sorted by ID, waitlist entries in FIFO order, queue counters/entries, journeys, then audit head. Check-in locks the doctor snapshot, slot, appointment and queue counter in this order; it consumes token and inserts queue entry once. Schedule proposal application locks doctor snapshot and affected slots, rejects conflicts, updates availability atomically, and emits acknowledgement. Local transactions use READ COMMITTED plus explicit row locks and constraints; retry bounded deadlocks/serialization failures only with safe idempotency. Keep this lock ordering consistent in migrations and implementation; do not use distributed locks for these invariants.

Indexes: doctor/time/state availability; patient/time appointment history; waiting priority; queue doctor/day/state; journey patient/updated_at; token hash. Availability cache is a hint only.

## Records database

- `consultations(id PK, appointment_id ref UNIQUE, journey_id ref, patient_id ref, doctor_id ref, status, revision, clinical_content JSONB)`.
- `medical_records(id PK, consultation_id FK consultations, patient_id ref, author_user_id ref, version, revision, content JSONB, supersedes_id FK medical_records nullable)`; immutable finalized revisions.
- `prescriptions(id PK, consultation_id FK consultations, patient_id ref, journey_id ref, revision, state, UNIQUE(consultation_id,revision))`.
- `prescription_items(id PK, prescription_id FK prescriptions, medicine_id ref, medicine_snapshot, dosage, instructions, quantity)`; item IDs are stable source references for dispensing limits.
- `record_access_grants(id PK, patient_id ref, grantee_user_id ref, scope, expires_at, revoked_at)`; explicit minimum scopes.

Record/prescription finalization, audit and outbox are atomic. Initial prescriptions have immutable item IDs and quantities; revocation changes state/version without modifying item content. This phase plan supports record amendments and whole-prescription revocation, not in-place prescription item edits. A replacement prescription requires an explicit future reviewed contract for supersession and remaining quantity reconciliation before implementation. Clinical amendments create new immutable revisions and supersession/revocation events, never overwrite historical text. Index patient/time, consultation/appointment, active grant `(patient_id,grantee_user_id)` and prescription lookup. Medicine existence/revision validation calls Pharmacy before the local transaction; retain snapshot and source version.

## Pharmacy database

- `medicines(id PK, sku UNIQUE, name, normalized_name, active, catalog_version)`.
- `inventory_batches(id PK, medicine_id FK medicines, batch_code, expires_on, on_hand, reserved, UNIQUE(medicine_id,batch_code))`; CHECK `0 <= reserved <= on_hand`.
- `prescription_snapshots(prescription_id ref PK, patient_id ref, journey_id ref, revision, state, source_version)` and `prescription_item_snapshots(item_id ref PK, prescription_id FK prescription_snapshots, medicine_id FK medicines, prescribed_quantity, reserved_quantity, dispensed_quantity)`; quantities >=0 and reserved + dispensed <= prescribed. Unavailable local catalog item quarantines event for resolution.
- `reservations(id PK, prescription_id FK prescription_snapshots, patient_id ref, state, expires_at)`; items `reservation_items(id PK, reservation_id FK reservations, item_id FK prescription_item_snapshots, batch_id FK inventory_batches, quantity)`.
- `dispensings(id PK, reservation_id FK reservations UNIQUE, staff_user_id ref, completed_at)` and `dispensing_items(id PK, dispensing_id FK dispensings, reservation_item_id FK reservation_items UNIQUE, quantity)`.
- `stock_movements(id PK, batch_id FK inventory_batches, delta, reason, source_id, UNIQUE(batch_id,reason,source_id))`; mutations use audited deltas.

Lock prescription item allowances and batches in sorted IDs. Reservation atomically increments reserved counters only if available stock and prescription allowance suffice; no negative stock or duplicate prescription fulfillment. Dispensing validates current Records revision before the transaction, then atomically reduces on_hand/reserved, increases dispensed allowance, records movement and outbox. Expiration/revocation releases reserved quantities once under the same locks; dispensed items are historical and require staff review, not automatic return. Index catalog prefix, batch medicine/expiry (FEFO), reservation expiry/state and prescription/patient. No billing computation in stock transactions.

## Billing database

- `tariffs(id PK, charge_code, revision, unit_amount_minor, currency, UNIQUE(charge_code,revision))`.
- `invoices(id PK, journey_id ref UNIQUE, patient_id ref, currency, status, total_minor, paid_minor, version)`.
- `invoice_items(id PK, invoice_id FK invoices, source_service, source_event_id, source_item_id, tariff_id FK tariffs, quantity, unit_amount_minor, UNIQUE(source_service,source_item_id))`; consultation ID or dispensing item ID is the stable charge source.
- `invoice_adjustments(id PK, invoice_id FK invoices, amount_minor, reason, source_adjustment_id UNIQUE)`; never delete posted charges.
- `payments(id PK, invoice_id FK invoices, idempotency_key, amount_minor, currency, status, UNIQUE(invoice_id,idempotency_key))`; payment ledger + invoice counters update in one locked transaction, prevent overpayment unless explicitly designing credits later.
- `insurance_providers(id PK, synthetic_slug UNIQUE, allowlisted_url)`, `crawler_runs(id PK, provider_id FK insurance_providers, fetched_at, state, content_hash, error_code)` and `insurance_rules(id PK, provider_id FK insurance_providers, source_run_id FK crawler_runs, revision, effective_from, rule_data, UNIQUE(provider_id,revision))`.
- `insurance_estimates(id PK, invoice_id FK invoices, rules_id FK insurance_rules, estimate_minor, calculated_at, freshness_state)`.

Charge consumption/invoice recomputation/outbox commit together. Payments lock invoice, validate balance and synthetic outcome, append event and audit. Estimate failure never mutates paid balance or blocks payment. Index patient/status/time, charge source, provider/revision, crawler history. Currency cannot differ between invoice and its monetary items/payments; enforce within transactional code and constraints where expressible.

## Emergency database

- `emergency_requests(id PK, patient_id ref nullable, synthetic_contact, description, reported_urgency, assigned_priority nullable, state, version, claimed_by_user_id ref nullable, claim_expires_at nullable, tracking_token_hash UNIQUE nullable, tracking_expires_at nullable)`.
- `emergency_status_history(id PK, request_id FK emergency_requests, previous_state, new_state, priority, actor_user_id ref nullable, reason, occurred_at)`.

Request acceptance/history/outbox is atomic. Staff claim uses a conditional state/version update, or `FOR UPDATE SKIP LOCKED` for the next eligible request; leases permit recovery from a failed worker. Changes append history and audit. Priority queues derive effective priority from assigned severity and age; materialized priority must be refreshed rather than indexed using volatile current time. Index `(state,assigned_priority,created_at,id)` and claim expiry. Anonymous status reads require a hashed opaque tracking token owned here, with expiry, rate limits and minimal fields.

## Consistency, retention, and operations

No cross-service transaction rollback is promised. Inbox/outbox effects, source versions, durable uniqueness and compensating commands handle duplicates and delay. Retain outbox payloads for at least seven days after confirmed publish; active retries never expire silently. Inbox deduplication minimum 30 days; business source keys survive for aggregate lifetime. Older replay requires explicit reconciliation and cannot rely on inbox retention alone. Values are prototype defaults and must be configurable.

Use bounded connection pools per replica, query deadlines and migration ownership per service. Add indexes based on measured query plans; avoid indexing full sensitive text. Paginate histories using stable cursors. Do not partition or shard domain tables before evidence justifies it. Backups and restore exercises must use synthetic data; one shared instance still has correlated failure and restore risks. Phase 1.4B checks connectivity, privileges, schema and controlled PostgreSQL outage/recovery; it does not measure performance, collisions, booking concurrency or backup recovery.
