# PulseGrid Records Service

## Phase 3 G1 workflow leaf

The metadata-only `GET /internal/v1/appointments/{appointment_id}/workflow-snapshot`
requires Appointment service authentication, `patient_id`, and a revision-bound
cursor. It excludes clinical notes, dosage and instructions. PostgreSQL triggers
advance the local episode revision with consultation, record, prescription and
item mutations. Unknown local appointments return 404; a consumer must preserve
pending state rather than infer no prescription.

`PULSEGRID_RECORDS_WORKFLOW_GATE=true` enables a delegated pre-hold call to
Appointment's `workflow-context` leaf. Enrolled appointments must be
`in_consultation`; unenrolled legacy appointments keep the Phase 2 path. Enable
this only after Appointment's leaf, service scope and under-lock hold recheck
are integrated. Existing hold finalization/replay remains the recovery path.

Phase 2.4 implements synthetic medical histories, consultations, immutable finalized records and prescriptions in the existing independent FastAPI service. The [frozen Phase 2 contracts](../../docs/phase-2-api-contracts.md), [security rules](../../docs/security.md) and [database ownership](../../docs/database-design.md) remain authoritative. Diagnoses and consultation notes use the bounded `summary`, `assessment`, `plan` fields; no extra diagnosis fields or arbitrary clinical JSON are introduced.

## Endpoints

Public prefix: `/api/v1/records`.

| Method | Relative path | Behavior |
|---|---|---|
| GET | `/patients/{patient_id}` | Patient history summaries; cursor/limit |
| GET | `/{record_id}` | Immutable medical-record revision |
| GET / POST | `/consultations` | Scoped listing / assigned-doctor draft creation |
| GET / PATCH | `/consultations/{consultation_id}` | Consultation detail / draft text update |
| POST | `/consultations/{consultation_id}/finalize` | Atomic finalized record and optional prescription |
| POST | `/{record_id}/amendments` | Append a new record revision, preserving original text |
| GET | `/prescriptions` | Patient/author listing; patient_id/consultation_id filters |
| GET | `/prescriptions/{prescription_id}` | Prescription detail, including dosage/instructions |
| POST | `/prescriptions/{prescription_id}/revoke` | Issued to revoked; no item edits or replacements |
| POST | `/access-grants` | Patient grants doctor scoped access for at most 30 days |
| DELETE | `/access-grants/{grant_id}` | Conditional soft revocation; 204 |

Consultation listing filters are `appointment_id`, `patient_id`. Lists default to 20, maximum 100, ascending `(created_at,id)`, with cursors bound to filters, user and effective role. Unknown/duplicate query keys fail validation. Single-resource routes accept no query keys. POST commands require a printable 16..128-character `Idempotency-Key`; same-key retries retain the original response and ETag. PATCH and existing-aggregate POST/DELETE commands require quoted `If-Match`. Amendments check the latest record's ETag. Request bodies reject unknown fields; IDs are bounded decimal strings; quantities are strict positive integers; grant expiry must be a UTC RFC 3339 string. Sensitive responses and safe errors use `Cache-Control: no-store`.

Private leaves, never exposed through the gateway:

- `GET /internal/v1/prescriptions/{prescription_id}/dispensing-context`: caller Pharmacy, exact scope `prescriptions:dispensing-context`, delegated owning patient or pharmacist. Returns only references, issued/revoked state, revision/version and immutable medicine quantities. It omits clinical content, dosage and instructions.
- `GET /internal/v1/consultations/{consultation_id}/charge-context`: caller Billing, exact scope `consultations:charge-context`, delegated billing_staff. Returns references, draft/finalized state and the fixed consultation charge code/quantity; no notes.

These leaves verify both pinned service identity and delegated access JWT, check local scope/state, audit before disclosure, and make no dependency calls. The initiating service must check current delegated authority, as specified by the frozen contract. OpenAPI at `/openapi.json` describes the input/output views and listing filters; runtime authorization is enforced in the handlers/dependencies.

## Access decisions

Every public command and sensitive read checks current Patient authority without a cached fallback. Patients can read only their own records, consultations and prescriptions. Doctors can read their authored documents. History listings and amendments require a live active Appointment clinical hold or an unexpired Records-owned `records:read` grant. A finalized hold ends access to other historical documents. A `prescriptions:read` grant permits prescription detail only, not history or another doctor's consultation. Amendments also require original authorship. Grants are rechecked under local locks before disclosure/amendment; expired/revoked grants fail closed.

Only the assigned current doctor can create a consultation; only that author can edit/finalize it or revoke its prescription. Draft updates/finalization validate current Appointment assignment. Pharmacists can look up a prescription by ID but cannot bulk-list prescriptions or see consultation/history content. Admin, receptionist, emergency_staff, billing_staff and ops roles give no general clinical access. Multiple-role users select an applicable role and still pass resource scope checks. Resource denial is concealed as 404; attributable policy denials append nonclinical audit entries.

## Database and transaction decisions

Migration `0003_clinical` appends to the existing `0002_explicit_worker` head. It makes legacy journey refs nullable, adds trusted consultation author and hold-recovery metadata, durable command preparations, record revision/supersession and item uniqueness, state/quantity constraints, indexes, immutable-history triggers and restrictive runtime grants. No old row is deleted or assigned a fabricated journey/author. Legacy rows without an author cannot authorize doctor workflows and require explicit coordinator-reviewed provenance before any future backfill. State/quantity checks are `NOT VALID` for legacy compatibility; they enforce new writes, and validation of any legacy data is later coordinator work. Revision/item uniqueness creation fails visibly on conflicting legacy rows instead of deleting history. Downgrade is deliberately refused.

Phase 2 IDs use a Records-local PostgreSQL BIGINT sequence seeded above existing owned IDs. Sequence allocation survives rollback/restart; gaps are expected. This does not claim Snowflake evaluation or cross-service global ID uniqueness. The existing worker-state table remains unchanged. No database access, foreign keys or imports cross service boundaries.

Clinical mutations, ordered audit append, immutable unpublished outbox and persisted POST response commit together. Finalization locks the consultation and creates exactly one immutable record plus an optional immutable prescription and items. Amendments lock the consultation, check latest revision and append a new immutable record. Revocation locks the prescription. Local grants are locked after aggregates and before the audit head. Replay uses transaction advisory locks for POST keys; consultation insertion also serializes by appointment ID. These locks are in PostgreSQL and are never held across network calls.

The `records_append_audit` SECURITY DEFINER function has fixed search_path, a fixed action/result allowlist, typed IDs/request/correlation IDs and an optional SHA-256 content digest. It accepts no raw notes, diagnoses, reasons or tokens. Runtime can read the chain but cannot insert/update/delete its tables; only the constrained function appends. Finalized consultations, records, prescription items and event envelopes have database-level immutability guards. Audit hashes use `SHA256(previous_hash || canonical_metadata::text)` with PostgreSQL JSONB text as the canonical representation. Verification needs a separately trusted chain-head anchor; export/anchoring infrastructure remains future work.

## Clinical hold recovery

Before acquiring an Appointment hold, a short local preparation transaction persists the prospective consultation ID, normalized fingerprint, identity snapshot and original Appointment precondition. It contains no clinical text/effect or successful response. Retrying the same key/body uses the same ID and remote hold key/precondition, even if the first remote response was lost. Body mismatch is rejected. An orphan hold deliberately blocks cancellation/rescheduling; it has no automatic timeout unlock. The coordinator must review Records absence before any owner-authorized release.

After local finalization commits, Records requests Appointment hold finalization with stable key `records-hold-finalize-<consultation_id>` and the stored acquired-hold version. A failure logs only `clinical_hold_finalize_pending` and request ID; the committed final clinical document is still returned. Explicitly retry the same finalize key/body/If-Match to replay the local result and retry the remote hold finalization. `hold_finalized_at` records the acknowledged remote result without changing the clinical version. No background worker, queue completion, journey or broker publication is implemented.

## Configuration and tests

From this service directory:

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/uvicorn records_service.main:app --host 127.0.0.1 --port 8000
.venv/bin/python -m pytest
.venv/bin/python tests/run_isolated.py
```

The final command requires local `initdb` and `pg_ctl`. It creates a fresh loopback-only PostgreSQL cluster with an available port under ignored `.test-resources/`, verifies that cluster's data directory, uses per-test disposable databases and migration/runtime roles, then stops/removes the cluster. It never invokes Docker or accesses shared persistent resources. Without this runner, PostgreSQL tests explicitly skip. JWT fixture keys and identities are synthetic and generated per test. Owner API replies are simulated through HTTPX transports; Records storage, migration, locking, constraints and privileges use real PostgreSQL.

Existing settings use `PULSEGRID_RECORDS_ENVIRONMENT`, `LOG_LEVEL` and `DB_*` under the same prefix. Readiness requires PostgreSQL; Redis/RabbitMQ are not application prerequisites. Production schema changes run through the migration role, never runtime schema creation. The default dependency bases are `http://patient:8000`, `http://appointment:8000`, `http://pharmacy:8000`; isolated tests can override `PULSEGRID_RECORDS_PATIENT_URL`, `APPOINTMENT_URL`, `PHARMACY_URL`. Each dependency call is bounded to one second and 256 KiB, redirects/proxies disabled, with two safe validation/read attempts, a five-failure/15-second local circuit and a five-second dependency deadline including the existing two-second authority check. Remote hold writes make one attempt per request and are retried explicitly with the same persisted key/precondition. Timeout returns 504; unavailable/schema/oversize failures return 503.

Existing auth settings under `PULSEGRID_RECORDS_AUTH_*` require public user JWKS, caller-bound service JWKS, the Records service private key and service kid for authority/owner calls. Never generate/commit production secrets here. Infrastructure integration and TLS outside isolated development belong to the coordinator. See [verification](VERIFICATION.md) for actual checks and limitations.

Remote role/catalog/assignment revocations can occur immediately after validation. Prescription revocation cannot undo already committed Pharmacy dispensing or automatically release reservations; Pharmacy must explicitly revalidate/release. No broker event is assumed delivered. This educational synthetic prototype is not a certified clinical or emergency-response system.
