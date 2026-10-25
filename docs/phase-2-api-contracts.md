# Phase 2 API contract freeze

Status: frozen preparation contract, not implemented behavior. Phase 2.0 changes documentation only. The implementation baseline is Phase 1 commit `b88913f`. This document and [the parallel plan](phase-2-parallel-plan.md) define the user-requested Phase 2 scope. They supersede older **proposed** phase assignments and abbreviated domain schemas in [API contracts](api-contracts.md), [database design](database-design.md) and [roadmap](development-roadmap.md) only for the workflows specified here. Existing implemented Phase 1 APIs remain authoritative and compatible. Security and service ownership remain binding. No runtime results are claimed.

## Scope and compatibility decisions

Phase 2 includes profiles/management, specialties and schedules, accepted availability, booking/cancellation/rescheduling, consultation documents and prescriptions, inventory/fulfillment, invoices/simulated payments, authenticated emergency tracking and existing-page integration. Automatic waitlists, QR/check-in, live queues, journey automation, insurance/crawlers, cache algorithms, distributed Snowflake evaluation, anonymous emergency tokens and telemetry dashboards remain deferred. No new authentication mechanism or eighth service. Integration clarification: Records uses a service-owned PostgreSQL sequence for positive BIGINT IDs (including durable clinical-hold preparation IDs); other domains use bounded CSPRNG candidates and PK uniqueness. Neither mechanism is custom Snowflake generation. This is an internal allocator choice, with unchanged decimal-string wire IDs.

Existing public prefixes are `/api/v1/patients`, `/api/v1/doctors`, `/api/v1/appointments`, `/api/v1/records`, `/api/v1/pharmacy`, `/api/v1/billing`, `/api/v1/emergencies`, plus `/api/v1/auth`. Singular directory names do not change these routes. All paths below are complete, without implied prefixes. Register static routes (me, users, specialties, availability, consultations, prescriptions) before overlapping ID routes; path IDs must pass ID validation.

Doctor owns immutable proposals; Appointment owns acceptance and operational slots. Records owns consultation status, without queue transitions or automatic Appointment completion. Phase 2 books remain `confirmed` until explicit cancellation; final clinical documents independently block cancellation/rescheduling through an Appointment-owned local clinical hold. No journey rows/stages are created. Previously proposed `journey_id` fields are explicitly nullable in new Phase 2 schemas; agents must add owned migrations for required legacy storage columns rather than fabricate IDs. No implemented Phase 1 response changes meaning.

## Exact common wire protocol

Typed object notation below is normative: fields are required unless suffixed `?`; `T|null` means present but nullable. Requests forbid unknown fields, omit unset PATCH fields and require at least one supplied field. Responses contain exactly the listed fields for the selected view; compatible future optional additions require coordinator review. Empty command bodies use `{}`. All responses and request bodies are JSON except existing 204 logout and reservation deletion.

| Type | Definition |
|---|---|
| ID | String matching `[1-9][0-9]{0,18}`, integer value at most 9223372036854775807; never a JavaScript number |
| Version | JSON integer 1..9007199254740991; versions/revisions increment atomically |
| Time | UTC RFC 3339 string with `Z` or `+00:00`; reject other offsets on these new APIs |
| Date | Valid `YYYY-MM-DD` |
| Name | Trimmed nonempty string, 1..200 characters |
| Text | Trimmed nonempty string, 1..4000 characters |
| Reason | Trimmed nonempty string, 1..500 characters; audit content digest, not raw text |
| Quantity | Strict JSON integer 1..1000000 |
| Minor | Strict JSON integer 0..9007199254740991; reject floats/booleans |
| Currency | Literal `INR` for Phase 2; no client currency conversion |
| Role | patient, doctor, receptionist, pharmacist, billing_staff, emergency_staff, hospital_admin, ops |
| Page<T> | `{items:[T],next_cursor:string\|null}` |

Every new route requires a valid existing Bearer user JWT; no cookies authorize domain commands. `iss=pulsegrid-patient`, `aud=pulsegrid-api`, RS256 with pinned public keys, `token_use=access`; preserve `sub`, `patient_id`, `roles`, `auth_version`, expiry and key verification. Staff roles do not imply clinical access. Current authority is checked for **all new mutations and sensitive reads**, using Patient locally or the existing private authority protocol. Select one applicable role actually held by the caller, and independently check ownership/assignment. Denial of current authority returns 403; invalid/expired user tokens return 401. GET patients/me retains its existing current-account 401 behavior. Ops receives no new business access. Resource-specific denial is concealed with 404; listing applies scope before pagination, never filters a fetched global page in the browser.

Requests use existing UUID `X-Request-ID`/`X-Correlation-ID` and W3C `traceparent`; generated IDs are returned as existing middleware headers. All new single-resource GETs/mutations return `ETag: "<version>"`. PATCH and POST targeting an existing mutable aggregate require exact quoted decimal `If-Match`; missing is 428, malformed 400, stale 412. List/availability responses have no aggregate ETag. POST child creation also checks the parent's ETag where specified below. Idempotency replay is checked after current authorization but before stale If-Match rejection.

Every new POST requires `Idempotency-Key`, 16..128 ASCII printable non-space characters. Key scope is authenticated `user:<sub>`, HTTP method, canonical route template **plus actual resource IDs** (store IDs in the fingerprint if the existing table uses route template only), key. Fingerprint includes normalized body and If-Match. Same-key different content is 409; concurrent equal requests serialize in the owner DB and return original status/body/ETag. Persist response version so replay ETag represents that response, not today's aggregate. Retain keys at least 24 h, payments seven days; durable source uniqueness survives expiration. PATCH is conditional, not automatically retried. Frontend retains a POST key/body/If-Match in memory after ambiguous failure and offers explicit retry; never retry a changed command under that key.

A local mutation, ordered append-only audit, immutable outbox row and persisted POST response commit in one owner transaction. No broker publisher or consumer is assumed in Phase 2. Events follow the existing envelope/catalog where applicable; new Phase 2-only operational actions use `<domain>.<entity>.<action>.v1` with payload `{resource_id:ID,version:Version,state?:string}` and no sensitive text. Do not change the implemented `patient.registered.v1` name. Undelivered outbox rows remain unpublished; no delivery/completion claim, no automatic deletion. Shared event schemas and eventual broker activation require later coordinator review.

Lists default `limit=20`, allowed 1..100, ordered `(created_at,id)` ascending, opaque base64url JSON cursor `{created_at:Time,id:ID,filter_hash:string}`. Validate cursor and identical normalized filters/authorization scope; malformed or changed filters return 400. Cursor is a position, not a credential; authorize every request. No snapshot guarantee against intervening writes. Search `q` is trimmed caseless prefix 2..100 characters; use SQL prefix baseline, no trie. Unknown query keys return 422. Filters below are optional unless stated; multiple filters combine with AND. Only listed filters/sorts exist. Availability requires `doctor_id,from,to`, half-open interval, `from<to`, maximum 31 days and maximum 1000 returned slots; over-limit returns 422 and caller must narrow interval. Dates/intervals are never inferred from browser timezone.

All new routes use `{error:{code:string,message:string,request_id:UUID,details?:object}}`, preserving Phase 1 envelope. No field values, tokens or clinical text in errors. Stable common errors: 400 `bad_request`; 401 `unauthorized` with WWW-Authenticate; 403 `forbidden`; 404 `not_found`; 409 `conflict`; 412 `version_conflict`; 422 `validation_error`; 428 `precondition_required`; 429 `rate_limited`; 503 `dependency_unavailable`; 504 `dependency_timeout`; unexpected 500 `internal_error`. Specific 409 codes below replace `conflict`. Retry-After is 1 second for 429/503 as an initial proposal, not measured tuning. No new throttling infrastructure in this phase. Invalid transitions return 409, invalid field values 422. Foreign missing/inactive reference returns 422 `invalid_reference` only after caller scope validation; remote unavailability never becomes not-found or an empty successful page. All money computations check safe-integer overflow. Sensitive responses use `Cache-Control: no-store`.

## Phase 1 authentication retained verbatim

[Authentication integration](authentication-integration.md) and actual Patient code define the implemented behavior. These routes do not inherit new domain preconditions:

| Method/path | Request/access | Success |
|---|---|---|
| GET `/api/v1/auth/csrf` | Credentialed; allowlisted Origin or GET origin-only Referer | 200 `{csrf_token:string,header_name:"X-CSRF-Token",expires_in:3600}` and HttpOnly cookie |
| POST `/api/v1/auth/register` | Allowed Origin; `{email:string,password:string,display_name:Name,date_of_birth?:Date,synthetic_contact?:string}`; existing Idempotency-Key and 43..128 base64url X-Anonymous-Command-ID | 201 PatientProfile; no automatic login |
| POST `/api/v1/auth/login` | Allowed Origin, CSRF cookie/header; `{email:string,password:string}` | 200 TokenSet and refresh cookie |
| POST `/api/v1/auth/refresh` | Allowed Origin, CSRF cookie/header and refresh cookie; no body | 200 TokenSet and rotated refresh cookie |
| POST `/api/v1/auth/logout` | Allowed Origin, CSRF cookie/header and credentials; no body | 204 revoked family and removed cookies |
| GET `/api/v1/patients/me` | Bearer; current active account, auth_version and patient role | 200 PatientProfile with ETag |

`TokenSet={access_token:string,token_type:"Bearer",expires_in:integer}`. `PatientProfile={id:ID,user_id:ID,display_name:Name,version:Version,date_of_birth?:Date,synthetic_contact?:string}`; null optional stored fields are omitted as implemented. Email/password validation, sanitized registration replay, generic auth errors and cookie settings remain implemented rules. Keep access tokens only in memory; keep CSRF/session single-flight, Web Locks coordination and one protected-401 refresh retry. Do not automatically retry login/refresh/logout. No JWT doctor_id exists; resolve doctor identity by Doctor's trusted staff_user_id mapping.

## Patient contracts

Patient management means existing registered profiles, administration of existing accounts and roles, and safe staff fixture setup. No patient deletion, new password reset mechanism or real-person imports.

`ProfilePatch={display_name?:Name,date_of_birth?:Date|null,synthetic_contact?:string|null}`; contact max 256; birth cannot be future. `UserView={id:ID,email:string,display_name:Name,roles:[Role],state:"active"|"disabled",auth_version:Version,version:Version}`. User and profile versions are independent. Role replacement is nonempty, distinct enum values, max eight; cannot disable oneself, remove one's own admin role or remove the last active admin (409 `last_admin`).

| Method/path | Body or query | Success | Authorization / conflicts |
|---|---|---|---|
| PATCH `/api/v1/patients/me` | ProfilePatch; profile If-Match | 200 PatientProfile | Active patient self |
| GET `/api/v1/patients` | q, cursor, limit | 200 Page<PatientProfile> | Current receptionist or hospital_admin; demographics only |
| GET `/api/v1/patients/{patient_id}` | None | 200 PatientProfile | Patient self, current receptionist/admin; no automatic doctor/pharmacist access |
| PATCH `/api/v1/patients/{patient_id}` | ProfilePatch; profile If-Match | 200 PatientProfile | Current receptionist/admin |
| GET `/api/v1/patients/users` | role, state, q, cursor, limit | 200 Page<UserView> | Current hospital_admin |
| GET `/api/v1/patients/users/{user_id}` | None | 200 UserView | Current hospital_admin |
| PATCH `/api/v1/patients/users/{user_id}/roles` | `{roles:[Role]}`; user If-Match | 200 UserView | Current hospital_admin; last_admin protection |
| PATCH `/api/v1/patients/users/{user_id}/account-state` | `{state:"active"\|"disabled",reason:Reason}`; user If-Match | 200 UserView | Current hospital_admin; last_admin protection |

Account/role changes atomically increment user version and auth_version, revoke refresh sessions and append audit/outbox; role assignment rows are not separate user ETags. Serialize last-admin checks with a local administration lock. Existing users can become synthetic staff; a service-local explicit operator CLI/fixture may bootstrap the first admin only when later implementation is authorized, never through anonymous registration or startup. No default password or credentials committed. Doctor agent depends on a Patient staff-status API, not on implementing its own accounts.

## Doctor contracts and schedule workflow

`Specialty={id:ID,slug:string,name:Name,version:Version}`; slug `[a-z0-9]+(?:-[a-z0-9]+)*`, 1..128. `DoctorProfile={id:ID,display_name:Name,specialties:[{id:ID,name:Name}],active:boolean,version:Version}`. `DoctorSelf={doctor:DoctorProfile,staff_user_id:ID}` is private to that doctor/admin. Public profiles omit staff_user_id.

`ScheduleInput={timezone:string,slot_minutes:integer,intervals:[{starts_at:Time,ends_at:Time}],expected_revision:integer}`. Timezone is valid IANA name (max 128); slot_minutes 5..120; expected_revision >=0, exactly latest proposal revision (0 initially). Intervals 0..64, ordered/nonoverlapping, future, within next 366 days; each length a multiple of slot_minutes, maximum 31-day span and 1000 generated slots. Empty intervals propose closure. UTC input resolves DST ambiguity before submission. `ScheduleProposal={id:ID,doctor_id:ID,revision:Version,status:"pending"|"accepted"|"rejected",timezone:string,slot_minutes:integer,intervals:[{starts_at:Time,ends_at:Time}],conflicts:[ID],version:Version}`. Conflicts is empty until an acknowledged rejection.

| Method/path | Body or query | Success | Authorization / conflicts |
|---|---|---|---|
| GET `/api/v1/doctors/specialties` | cursor, limit | 200 Page<Specialty> | Authenticated |
| POST `/api/v1/doctors/specialties` | `{slug:string,name:Name}` | 201 Specialty | Current hospital_admin; 409 duplicate slug |
| GET `/api/v1/doctors/me` | None | 200 DoctorSelf | Current doctor mapped by sub; 404 missing mapping |
| GET `/api/v1/doctors` | specialty_id, active, q, cursor, limit | 200 Page<DoctorProfile> | Authenticated; active defaults true |
| GET `/api/v1/doctors/{doctor_id}` | None | 200 DoctorProfile | Authenticated |
| POST `/api/v1/doctors` | `{staff_user_id:ID,display_name:Name,specialty_ids:[ID]}` | 201 DoctorProfile | Current admin; active Doctor-role account required; 409 duplicate mapping |
| PATCH `/api/v1/doctors/{doctor_id}` | `{display_name?:Name,specialty_ids?:[ID],active?:boolean}`; If-Match | 200 DoctorProfile | Own current doctor edits name only; admin all fields |
| POST `/api/v1/doctors/{doctor_id}/schedules` | ScheduleInput; doctor If-Match | 202 ScheduleProposal | Own current doctor/admin; 409 proposal_pending/revision_conflict |
| GET `/api/v1/doctors/{doctor_id}/schedules` | cursor, limit | 200 Page<ScheduleProposal> | Own current doctor/receptionist/admin |
| GET `/api/v1/doctors/{doctor_id}/schedules/{proposal_id}` | None | 200 ScheduleProposal | Same as schedule list |
| POST `/api/v1/doctors/{doctor_id}/schedules/{proposal_id}/reconcile` | `{}`; proposal If-Match | 200 ScheduleProposal | Own current doctor/admin; 409 decision_pending |

Specialty IDs are distinct, 1..20 per doctor, validated locally. Proposal creation increments doctor version and creates immutable proposal revision. Only one pending proposal per doctor, preserving the existing constraint. Frontend explicitly submits proposal, asks Appointment to decide it using the route below, then calls Doctor reconcile. Reconcile reads an Appointment-owned decision before its local transaction; it never alters Appointment state. Repeating an identical decision is safe; mismatched decision is 409. Lost responses recover by GET decision and replay/reconcile. Accepted availability never comes from Doctor alone.

Deactivation hides discovery and forbids new proposals, but does not revoke existing Appointment slots by itself. UI must first submit/accept an empty closure and reconcile it, then PATCH active=false. Doctor deactivation validates Appointment's leaf operational-status API; any live bookable slot or confirmed booking returns 409 `schedule_not_closed`. Re-enabling requires a current staff Doctor role; availability appears only after a newly accepted proposal. Remote races are bounded validation, not global atomic deactivation.

## Appointment contracts and concurrency

`Slot={id:ID,doctor_id:ID,starts_at:Time,ends_at:Time,state:"bookable"|"retired",revision:Version}`; revision is accepted schedule revision. Availability returns only unoccupied bookable slots. `Availability={slots:[Slot],accepted_revision:integer,observed_at:Time}`; revision 0 means no accepted proposal. `Appointment={id:ID,journey_id:null,patient_id:ID,doctor_id:ID,slot_id:ID,starts_at:Time,ends_at:Time,state:"confirmed"|"cancelled",version:Version}`. `ScheduleDecision={proposal_id:ID,doctor_id:ID,revision:Version,state:"accepted"|"rejected",reason_code:string|null,conflicting_appointment_ids:[ID],version:Version}`.

| Method/path | Body or query | Success | Authorization / conflicts |
|---|---|---|---|
| POST `/api/v1/appointments/schedule-decisions` | `{doctor_id:ID,proposal_id:ID,expected_accepted_revision:integer}` | 201 ScheduleDecision | Own current doctor/admin; rejected proposal is a persisted decision, not a transport error |
| GET `/api/v1/appointments/schedule-decisions/{proposal_id}` | None | 200 ScheduleDecision | Own current doctor/receptionist/admin |
| GET `/api/v1/appointments/availability` | Required doctor_id, from, to | 200 Availability | Authenticated; hint only |
| POST `/api/v1/appointments` | `{patient_id:ID,slot_id:ID,expected_schedule_revision:Version}` | 201 Appointment | Current patient self/receptionist; 409 slot_occupied/patient_overlap/schedule_changed |
| GET `/api/v1/appointments` | patient_id, doctor_id, state, cursor, limit | 200 Page<Appointment> | Patient self; own mapped doctor; current receptionist; scope intersects filters |
| GET `/api/v1/appointments/{appointment_id}` | None | 200 Appointment | Same resource scope as list |
| POST `/api/v1/appointments/{appointment_id}/cancel` | `{reason:Reason}`; appointment If-Match | 200 Appointment | Current patient self/receptionist; 409 clinical_hold |
| POST `/api/v1/appointments/{appointment_id}/reschedule` | `{target_slot_id:ID,expected_schedule_revision:Version}`; appointment If-Match | 200 Appointment | Current patient self/receptionist; 409 clinical_hold/cancelled/slot_occupied/patient_overlap/schedule_changed |

Schedule decisions pull the immutable Doctor proposal and staff mapping, validate caller, active doctor and current role before opening a transaction. expected_accepted_revision >=0 must equal local revision or 409 schedule_changed. The proposal revision must be next after last decided revision; gaps are 409 revision_gap. Persist exactly one decision per proposal and doctor/revision. Reject proposed replacement if it removes or shifts any confirmed booked interval; conflicts are visible only to schedule-authorized staff. Keep old accepted slots unchanged on rejection. Acceptance retires unbooked replaced slots, updates preserved slots to accepted revision, creates/upserts exact new intervals and records decision in one transaction. Existing bookings retain the revision accepted at booking. Closure cannot remove a confirmed booking. Expired slots are not bookable even if their stored state remains bookable.

PostgreSQL correctness requirements are mandatory, not optional optimizations:

1. Add owned Alembic migrations for `btree_gist`, nonretired doctor-slot half-open interval exclusion, and active patient-appointment overlap exclusion for `confirmed`, `checked_in`, `in_consultation` (retain legacy states for future compatibility). Preserve existing unique active slot index. Enforce appointment doctor/time/revision copies against locked slot; no caller times accepted.
2. Acquire a per-command idempotency lock first, then doctor snapshot rows sorted by doctor ID, slot rows sorted by slot ID, appointment rows sorted by appointment ID, any clinical-hold row, then audit head. Initialize absent doctor snapshot under a per-doctor PostgreSQL transaction advisory lock before row locking. All commands use the same order. Preliminary reads are revalidated after locks; if rescheduling changed the discovered slot/doctor, restart the bounded transaction rather than locking in reverse order.
3. Booking validates current patient and accepted active doctor context remotely before locks, then revalidates local revision, future times and slot state while locked. Insert plus audit/outbox/idempotency commits once. Constraint conflicts map to 409; Redis and process mutexes do not enforce correctness.
4. Reschedule updates the same appointment ID atomically, acquiring both doctors/slots in sorted order. Failure retains original slot/state/version. Cancellation releases capacity without promotion; already-cancelled with current ETag is a 200 no-op, with no extra business event. Overlap is `[start,end)`, so adjacent appointments are allowed.
5. Records explicitly acquires a local Appointment clinical hold before document creation (private contract below). Holds prevent cancellation/rescheduling once clinical work starts. No queue/check-in/start transition is added. READ COMMITTED with locks/exclusions is sufficient; maximum two retries for deadlock/serialization failure under the same key, then 503. Never hold DB locks across HTTP. No cross-service atomicity claim.

## Records contracts

`ClinicalContent={summary:Text,assessment:Text,plan:Text}` is the exact bounded synthetic content schema, not arbitrary executable JSON. `Consultation={id:ID,appointment_id:ID,patient_id:ID,doctor_id:ID,status:"draft"|"finalized",clinical_content:ClinicalContent,revision:Version,version:Version}`. `RecordSummary={id:ID,consultation_id:ID,patient_id:ID,revision:Version,created_at:Time,version:Version}`. `MedicalRecord={id:ID,consultation_id:ID,patient_id:ID,content:ClinicalContent,revision:Version,supersedes_id:ID|null,version:Version}`.

`PrescriptionItemInput={medicine_id:ID,quantity:Quantity,dosage:Text,instructions:Text}`. `Prescription={id:ID,consultation_id:ID,patient_id:ID,journey_id:null,revision:Version,state:"issued"|"revoked",items:[{id:ID,medicine_id:ID,quantity:Quantity,dosage:Text,instructions:Text}],version:Version}`. `FinalizeResult={consultation:Consultation,record:MedicalRecord,prescription:Prescription|null}`. `AccessGrant={id:ID,patient_id:ID,grantee_user_id:ID,scope:"records:read"|"prescriptions:read",expires_at:Time,version:Version}`.

| Method/path | Body or query | Success | Authorization / conflicts |
|---|---|---|---|
| GET `/api/v1/records/patients/{patient_id}` | cursor, limit | 200 Page<RecordSummary> | Current patient self; current doctor with active appointment clinical hold or unexpired records:read grant |
| GET `/api/v1/records/{record_id}` | None | 200 MedicalRecord | Same patient-scoped policy; sensitive read audited |
| GET `/api/v1/records/consultations` | appointment_id, patient_id, cursor, limit | 200 Page<Consultation> | Self patient; own author doctor; no global clinical listing |
| GET `/api/v1/records/consultations/{consultation_id}` | None | 200 Consultation | Self patient or own author doctor |
| POST `/api/v1/records/consultations` | `{appointment_id:ID,clinical_content:ClinicalContent}` | 201 Consultation | Current assigned doctor; 409 consultation_exists/appointment_unavailable |
| PATCH `/api/v1/records/consultations/{consultation_id}` | `{clinical_content:ClinicalContent}`; If-Match | 200 Consultation | Current author doctor, draft only; 409 finalized |
| POST `/api/v1/records/consultations/{consultation_id}/finalize` | `{prescription_items:[PrescriptionItemInput]}`; If-Match | 200 FinalizeResult | Current assigned author doctor; 409 finalized |
| GET `/api/v1/records/prescriptions` | patient_id, consultation_id, cursor, limit | 200 Page<Prescription> | Self patient or own author doctor; pharmacists use ID lookup, no bulk clinical listing |
| GET `/api/v1/records/prescriptions/{prescription_id}` | None | 200 Prescription | Self/current author doctor or current doctor with unexpired prescriptions:read grant; current pharmacist gets prescription only, never clinical content |
| POST `/api/v1/records/{record_id}/amendments` | `{content:ClinicalContent,reason:Reason}`; If-Match latest record | 201 MedicalRecord | Current author doctor with unexpired records:read grant or active hold; 409 superseded |
| POST `/api/v1/records/prescriptions/{prescription_id}/revoke` | `{reason:Reason}`; If-Match | 200 Prescription | Current author doctor; issued -> revoked, repeated current-state no-op |
| POST `/api/v1/records/access-grants` | `{patient_id:ID,grantee_user_id:ID,scope:"records:read"\|"prescriptions:read",expires_at:Time}` | 201 AccessGrant | Current patient self; active doctor grantee; future expiry <=30 days |
| DELETE `/api/v1/records/access-grants/{grant_id}` | If-Match | 204 | Current patient grant owner; revoke, never erase audit |

Create consultation verifies Patient eligibility and Appointment assignment, then acquires its durable clinical hold through a retryable private POST **before** committing locally. Hold owner is the prospective consultation ID, fixed for the same POST key in a durable Records-local command-preparation row before the remote call; that short preparation transaction stores the fingerprint and rejects key/body mismatch, with no clinical effect or success response. A crash can leave an orphan hold; retry completes the same consultation, and authorized coordinator review can release it only after Records confirms absence (no automatic timeout unlock). Finalize validates 0..50 distinct active Pharmacy medicines before local locks, atomically finalizes consultation, writes immutable record revision 1 and optional issued prescription, audit, outbox and response. No network calls inside that transaction. Draft updates increment version; finalization freezes text. Amendments append revisions and preserve old text. No replacement prescription or item edits. New commands do not complete Appointment or create a journey.

After finalization, Records calls the private hold-finalize command after commit; failures leave a safe active hold and show retry/reconciliation required in service-local logs/README, with no clinical payload. Active-hold access to *other* historical records ends when hold is finalized; subsequent historical access requires a patient grant. Own authored document reads remain allowed. Revocation stops new validated fulfillment but cannot atomically undo committed dispensing. Frontend warns that existing reservations require Pharmacy revalidation/release, rather than claiming an event was delivered.

## Pharmacy contracts

`Medicine={id:ID,sku:string,name:Name,active:boolean,availability:"available"|"unavailable"|"unknown",catalog_version:Version,version:Version}`; sku trimmed 1..128, unique. Availability is a stock hint. `Batch={id:ID,medicine_id:ID,batch_code:string,expires_on:Date,on_hand:integer,reserved:integer,available:integer,version:Version}`. Nonnegative quantities <=1000000, available=on_hand-reserved; expired stock has available=0 for fulfillment views. `StockResult={movement_id:ID,batch:Batch}`.

`Reservation={id:ID,patient_id:ID,prescription_id:ID,state:"reserved"|"expired"|"released"|"dispensed",items:[{prescription_item_id:ID,medicine_id:ID,quantity:Quantity}],expires_at:Time,version:Version}`. `Dispensing={id:ID,reservation_id:ID,prescription_id:ID,patient_id:ID,appointment_id:ID,items:[{id:ID,prescription_item_id:ID,medicine_id:ID,quantity:Quantity}],completed_at:Time,version:Version}`.

| Method/path | Body or query | Success | Authorization / conflicts |
|---|---|---|---|
| GET `/api/v1/pharmacy/medicines` | q, active, cursor, limit | 200 Page<Medicine> | Authenticated; active defaults true |
| GET `/api/v1/pharmacy/medicines/{medicine_id}` | None | 200 Medicine | Authenticated |
| POST `/api/v1/pharmacy/medicines` | `{sku:string,name:Name}` | 201 Medicine | Current pharmacist/admin; 409 duplicate sku |
| PATCH `/api/v1/pharmacy/medicines/{medicine_id}` | `{name?:Name,active?:boolean}`; If-Match | 200 Medicine | Current pharmacist/admin; increment catalog_version and version |
| GET `/api/v1/pharmacy/inventory` | medicine_id, cursor, limit | 200 Page<Batch> | Current pharmacist |
| POST `/api/v1/pharmacy/inventory-adjustments` | `{medicine_id:ID,batch_code:string,expires_on:Date,delta:integer,reason:Reason,expected_batch_version:integer}` | 201 StockResult | Current pharmacist; expected 0 for new batch, positive for existing; 412 stale, 409 stock_reserved |
| POST `/api/v1/pharmacy/reservations` | `{prescription_id:ID,items:[{prescription_item_id:ID,quantity:Quantity}]}` | 201 Reservation | Current patient self/pharmacist; 409 insufficient_stock/prescription_revoked/allowance_exceeded |
| GET `/api/v1/pharmacy/reservations` | patient_id, prescription_id, state, cursor, limit | 200 Page<Reservation> | Patient self/current pharmacist |
| GET `/api/v1/pharmacy/reservations/{reservation_id}` | None | 200 Reservation | Same resource policy |
| DELETE `/api/v1/pharmacy/reservations/{reservation_id}` | If-Match | 204 | Current patient self/pharmacist; 409 dispensed |
| POST `/api/v1/pharmacy/reservations/{reservation_id}/dispense` | `{}`; If-Match | 201 Dispensing | Current pharmacist; 409 expired/released/prescription_revoked |
| GET `/api/v1/pharmacy/dispensings` | patient_id, prescription_id, appointment_id, cursor, limit | 200 Page<Dispensing> | Patient self/current pharmacist |
| GET `/api/v1/pharmacy/dispensings/{dispensing_id}` | None | 200 Dispensing | Same resource policy |
| POST `/api/v1/pharmacy/reservations/{reservation_id}/revalidate` | `{}`; If-Match | 200 Reservation | Current pharmacist; release if revoked, otherwise same state |

Batch code max 128; delta is strict nonzero integer -1000000..1000000. Existing expiry is immutable; conflicting expiry is 409. New batch expiry must be today or later; fulfillment uses only dates after current UTC date. Stock never falls below reserved; adjustments do not prescribe or bill. Reservation items 1..50 distinct IDs, validated through live Records dispensing-context. Fetch immutable prescription items into local snapshots without events; do not reset cumulative reserved/dispensed counters on refresh. Lock prescription aggregate, item allowances sorted ID, reservation rows sorted ID and batches sorted ID, then audit head. Batch selection uses FEFO `(expires_on,id)` but lock acquisition is ID-sorted. New reservations expire 30 minutes after creation; release expired reservations under the same lock order on relevant reservation/stock commands and explicit revalidation. No separate full stack/worker is required.

Dispense checks current prescription before locks and then allowance/local expiry/state under locks; one transaction decrements on_hand/reserved, increments dispensed quantities, records immutable dispensing/movements/outbox/audit/response. Repeating a dispense after key retention returns the same existing dispensing rather than deducting again. Constraints prevent negative stock and prescribed-quantity overrun across partial reservations. Revalidation releases unfilled revoked/expired stock once; already dispensed quantities remain historical. Cross-service revocation after validation remains a race requiring staff review, not an exactly-once global guarantee.

## Billing contracts

`Tariff={id:ID,charge_code:string,revision:Version,unit_amount_minor:Minor,currency:Currency,version:Version}`. Codes are `consultation` or `medicine:<medicine_id>`; max 128. Tariff revisions immutable, selected explicitly by Billing at charge import, never client prices. `Invoice={id:ID,journey_id:null,appointment_id:ID,patient_id:ID,status:"open"|"paid",items:[{id:ID,charge_code:string,source_service:"records"|"pharmacy",source_item_id:ID,quantity:Quantity,unit_amount_minor:Minor,tariff_revision:Version}],total_minor:Minor,paid_minor:Minor,balance_minor:Minor,currency:Currency,version:Version}`. Balance=total-paid; zero-charge invoices remain open, paid requires total>0 and balance=0. `Payment={id:ID,invoice_id:ID,amount_minor:Minor,currency:Currency,status:"success"|"declined",version:Version}`.

| Method/path | Body or query | Success | Authorization / conflicts |
|---|---|---|---|
| GET `/api/v1/billing/tariffs` | charge_code, cursor, limit | 200 Page<Tariff> | Current billing_staff |
| POST `/api/v1/billing/tariffs` | `{charge_code:string,unit_amount_minor:Minor,currency:Currency}` | 201 Tariff | Current billing_staff; new monotonic revision |
| POST `/api/v1/billing/invoices` | `{appointment_id:ID,currency:Currency}` | 201 Invoice | Current billing_staff; validate Appointment context; 409 invoice_exists |
| GET `/api/v1/billing/invoices` | patient_id, status, cursor, limit | 200 Page<Invoice> | Patient self/current billing_staff |
| GET `/api/v1/billing/invoices/{invoice_id}` | None | 200 Invoice | Same resource policy |
| POST `/api/v1/billing/invoices/{invoice_id}/charges` | `{consultation_id?:ID,dispensing_ids:[ID]}`; invoice If-Match | 200 Invoice | Current billing_staff; 409 source_not_finalized/source_mismatch/unpriced_source |
| GET `/api/v1/billing/invoices/{invoice_id}/payments` | cursor, limit | 200 Page<Payment> | Patient self/current billing_staff |
| POST `/api/v1/billing/invoices/{invoice_id}/payments` | `{amount_minor:Minor,currency:Currency,simulated_outcome:"success"\|"decline"}`; invoice If-Match | 201 Payment | Current patient self/billing_staff; amount>0; 409 overpayment/currency_mismatch |

Each invoice has unique appointment_id and nullable legacy journey_id. Charge POST supplies 0..50 distinct dispensing IDs and optional consultation ID; at least one source required. Billing fetches finalized Records consultation and completed Pharmacy dispensing snapshots before locks, validates same appointment/patient and currency/tariff mappings, then imports all requested charges atomically. Unknown tariff fails the whole command; no zero-price fallback. Stable source key `(records,consultation_id)` or `(pharmacy,dispensing_item_id)` is lifetime unique. Reimport under a new key skips identical already-posted source items; conflicting source values return 409. Snapshot price/revision are immutable. No trusted frontend totals, no foreign DB reads, no fake source_event_id: migrate that legacy column nullable for explicit REST imports.

Payments lock invoice, prevent overpayment, commit ledger and counters once; decline commits a ledger entry without balance change. Each payment attempt increments invoice version, including decline. Concurrent success attempts cannot exceed balance. Importing legitimate later charges reopens a paid invoice to open; paid means current imported balance cleared, not all future services reconciled. UI labels charge import as manual and shows that missing source imports are not automatically detected. Staff explicitly discovers consultation/dispensing IDs from owner pages; no discharge/coverage guarantee, refunds, reversals, insurance or charge deletion in Phase 2.

## Emergency contracts

Phase 2 requires authentication for request creation/tracking. Anonymous token issuance and clinical triage algorithms remain future work. `reported_urgency` is exactly `unspecified` or `urgent`, advisory only.

`EmergencyRequest={id:ID,state:"submitted"|"triaged"|"claimed"|"processing"|"resolved"|"cancelled",reported_urgency:"unspecified"|"urgent",assigned_priority:integer|null,created_at:Time,updated_at:Time,version:Version}` is the patient's minimal tracking view. `EmergencyStaffRequest` adds `{patient_id:ID,description:Text,synthetic_contact:string|null,claimed_by_user_id:ID|null,claim_expires_at:Time|null}`. Patient descriptions/contact are supplied at creation but absent from tracking. Response view selection depends on effective role/resource scope, never client query flags.

| Method/path | Body or query | Success | Authorization / conflicts |
|---|---|---|---|
| POST `/api/v1/emergencies` | `{patient_id:ID,description:Text,reported_urgency:"unspecified"\|"urgent",synthetic_contact?:string}` | 201 EmergencyRequest | Current patient self; contact max 256; initial submitted, priority null |
| GET `/api/v1/emergencies` | patient_id, state, cursor, limit | 200 Page<EmergencyRequest or EmergencyStaffRequest> | Patient self/current emergency_staff; common cursor order |
| GET `/api/v1/emergencies/{request_id}` | None | 200 role-appropriate view | Patient self/current emergency_staff |
| PATCH `/api/v1/emergencies/{request_id}/priority` | `{assigned_priority:integer,reason:Reason}`; If-Match | 200 EmergencyStaffRequest | Current emergency_staff; 1..5, 1 highest; submitted -> triaged; terminal requests conflict |
| POST `/api/v1/emergencies/{request_id}/claim` | `{}`; If-Match | 200 EmergencyStaffRequest | Current emergency_staff; triaged -> claimed by caller; 409 already_claimed |
| POST `/api/v1/emergencies/{request_id}/release` | `{reason:Reason}`; If-Match | 200 EmergencyStaffRequest | Current claiming staff only; claimed -> triaged, clears claim |
| POST `/api/v1/emergencies/{request_id}/transitions` | `{state:"processing"\|"resolved"\|"cancelled",reason:Reason}`; If-Match | 200 role-appropriate view | processing/resolved: current claiming staff; cancellation: patient own submitted/triaged, or current staff submitted/triaged/claimed |

Claim is atomic conditional update/row lock with 15-minute lease. GETs are side-effect free. On claim or transition commands, expired claimed state is normalized to triaged with history and cleared claim; return 409 `claim_expired` for attempts to process expired claims, with normalization, history, audit, outbox and the persisted 409 POST outcome committed atomically; replay returns that same conflict outcome. Never expire processing claims automatically; processing ends only via assigned staff resolve. Apply current-authority and If-Match checks before any expired-claim normalization. No staff can resolve another's processing request, no reassignment during processing, no dispatch/bed management. Every transition appends immutable history. Priority edits on claimed/processing preserve assignment/state. Resolved/cancelled terminal; invalid edge 409. Staff assignment means current caller claims, not arbitrary user ID supplied by a patient.

## Exact private cross-service contracts

Use private DNS `http://<singular_service>:8000`, never gateway-exposed internal routes. Reuse existing `service_token(config,scope,target)` and verifier with caller-key binding, issuer `pulsegrid-service:<caller>`, audience `pulsegrid-internal:<owner>`, sub caller, token_use service, exactly `[scope]`, 60-second issued lifetime (verifier bound 120). Every domain workflow below also requires existing `X-Delegated-Authorization: Bearer <user access token>`; owner verifies delegated JWT and resource/role constraints. No trusted raw actor headers. Service tokens alone cannot read clinical data. Caller allowlists and scopes below are additional to signature validation. A private leaf route performs only its own database checks and local audit, never calls another service; this prevents recursive dependency cycles.

All responses are 200 unless stated, bounded JSON <=256 KiB; ETag for versioned resources. Common errors/preconditions apply. Private POST commands persist keys scoped `service:<caller>:user:<sub>`; read-only validation/authority POSTs do not require Idempotency-Key. Target current-authority validation is performed by the initiating public command before private leaf calls; leaf checks delegated claims, owner-local scope and current owner state. This bounded validation cannot eliminate authority changes immediately after checking. Sensitive leaf reads append local audit before releasing data.

| Owner method/path | Allowed caller; exact scope | Request -> exact response | Leaf authorization |
|---|---|---|---|
| Patient POST `/internal/v1/authorization/check` (existing) | Other domains; `authorization:check` | `{subject_user_id:ID,required_role:Role,auth_version:Version}` -> `{active:boolean,allowed:boolean,current_auth_version:integer}` | Existing sub/version/role equality and current Patient DB check; version may be 0 for missing user |
| Patient GET `/internal/v1/auth/jwks` (existing) | Existing allowed services; `jwks:read` | No body -> existing standard public-key JWKS | Existing service-only auth; delegation not required for this existing key route |
| Patient GET `/internal/v1/patients/{patient_id}/status` | appointment, records, emergency; `patients:status` | No body -> `{patient_id:ID,active:boolean,version:Version}` | Self patient or delegated receptionist/doctor/emergency_staff for reference validation; no demographics |
| Patient GET `/internal/v1/users/{user_id}/staff-status` | doctor, records; `users:staff-status` | No body -> `{user_id:ID,active:boolean,roles:[Role],version:Version}` | Admin for Doctor mapping; delegated current self patient for Records grant validation. The target is the active doctor grantee, not necessarily the granting patient; other staff targets are denied. Existing self-status remains supported. |
| Doctor GET `/internal/v1/doctors/{doctor_id}/schedule-proposals/{proposal_id}` | appointment; `schedules:read` | No body -> `{proposal:ScheduleProposal,staff_user_id:ID,active:boolean,doctor_version:Version}` | Own mapped doctor or admin |
| Doctor GET `/internal/v1/doctors/{doctor_id}/identity` | appointment; `doctors:identity` | No body -> `{doctor_id:ID,staff_user_id:ID,active:boolean,version:Version}` | Patient/receptionist booking, own doctor assignment, or admin; no clinical data |
| Appointment GET `/internal/v1/schedule-decisions/{proposal_id}` | doctor; `schedule-decisions:read` | No body -> ScheduleDecision | Own doctor/admin validated against stored staff mapping |
| Appointment GET `/internal/v1/doctors/{doctor_id}/operational-status` | doctor; `schedules:status` | No body -> `{doctor_id:ID,bookable_slot_count:integer,confirmed_booking_count:integer,version:Version}` | Own doctor/admin; no patient IDs; no snapshot means counts 0/version 1 |
| Appointment GET `/internal/v1/appointments/{appointment_id}/consultation-context` | records; `appointments:consultation-context` | No body -> `{appointment_id:ID,patient_id:ID,doctor_id:ID,doctor_user_id:ID,journey_id:null,state:"confirmed"\|"cancelled",clinical_hold:"none"\|"active"\|"finalized",version:Version}` | Delegated doctor matches stored accepted staff_user_id; self patient only for Records read/grant checks; never prescribing as patient |
| Appointment POST `/internal/v1/appointments/{appointment_id}/clinical-hold` | records; `appointments:clinical-hold` | `{consultation_id:ID}`; appointment If-Match, key -> context above, updated version | Assigned doctor, confirmed; same consultation hold replay-safe, different consultation 409 |
| Appointment POST `/internal/v1/appointments/{appointment_id}/clinical-hold/finalize` | records; `appointments:clinical-hold` | `{consultation_id:ID}`; appointment If-Match, key -> context above, updated version | Assigned doctor; only matching hold active -> finalized; repeated finalized no-op |
| Appointment GET `/internal/v1/appointments/{appointment_id}/billing-context` | billing; `appointments:billing-context` | No body -> `{appointment_id:ID,patient_id:ID,state:"confirmed"\|"cancelled",version:Version}` | Delegated billing_staff; no clinical content |
| Records GET `/internal/v1/prescriptions/{prescription_id}/dispensing-context` | pharmacy; `prescriptions:dispensing-context` | No body -> `{prescription_id:ID,consultation_id:ID,appointment_id:ID,patient_id:ID,journey_id:null,revision:Version,state:"issued"\|"revoked",items:[{id:ID,medicine_id:ID,quantity:Quantity}],version:Version}` | Patient owner or pharmacist; no record text/dosage needed for quantity validation |
| Pharmacy POST `/internal/v1/medicines/validate` | records; `medicines:validate` | `{medicine_ids:[ID]}` (1..50 distinct) -> `{items:[{id:ID,active:boolean,catalog_version:Version,name:Name}]}` | Delegated doctor; missing item 422 invalid_reference, inactive returned false |
| Records GET `/internal/v1/consultations/{consultation_id}/charge-context` | billing; `consultations:charge-context` | No body -> `{consultation_id:ID,appointment_id:ID,patient_id:ID,status:"draft"\|"finalized",charge_code:"consultation",quantity:1,version:Version}` | Delegated billing_staff; no notes |
| Pharmacy GET `/internal/v1/dispensings/{dispensing_id}/charge-context` | billing; `dispensings:charge-context` | No body -> `{dispensing_id:ID,appointment_id:ID,patient_id:ID,items:[{source_item_id:ID,medicine_id:ID,charge_code:string,quantity:Quantity}],version:Version}` | Delegated billing_staff; code medicine:<ID>; immutable completed source |

Doctor's proposal and identity APIs are leaves with no Appointment lookup. Appointment context/decision/status leaves use stored staff mapping, never a Doctor callback. Records dispensing/charge contexts use its own committed documents, never Pharmacy/Appointment callbacks. Pharmacy medicine/charge leaves use its own catalog/dispensing, never Records callbacks. Patient is a sink with no domain calls. Thus bidirectional **service names** in the table do not form circular synchronous **request chains**.

## Communication, failures and consistency per interaction

Initial domain dependency budget: total request 5 seconds; each dependency call <=1 second, at most two safe GET/validation attempts including first with 50..150 ms jitter, sequential work bounded by remaining deadline. Existing Phase 1 authority helper timeout remains 2 seconds and its fail-closed timeout response remains 503 and is not changed by this preparation. New domain client uses a local circuit opening after five consecutive transport/5xx failures, probe after 15 seconds. These are proposed safety bounds, not performance results. Never retry 4xx or follow redirects; schema/oversized-response failure is 503. Propagate correlation/trace context; disable environment proxy trust. Network timeout is 504, other unavailable dependency 503. No local business mutation if prerequisite validation failed. Retry write only with same key/body/precondition; reconcile ambiguous results by owner GET. No locks across calls.

| Interaction; initiator and owner | Phase 2 workflow / consistency | Failure and recovery |
|---|---|---|
| All domains -> Patient | Current-role POST before mutations/sensitive reads; Patient-local authority strongly consistent at check | Denied fails closed; outage 503/timeout 504; no cached authority fallback; no other-domain DB access |
| Appointment -> Patient/Doctor | Patient status and Doctor identity before booking; Doctor proposal before explicit schedule decision; accepted slots/booking strongly consistent locally | Failure prevents decision/booking; proposal remains pending; repeat same key after recovery |
| Doctor -> Appointment | Explicit reconcile reads decision; deactivation reads operational-status; Doctor status is an eventual display of Appointment authority | Lost acknowledgement leaves pending and blocks next proposal; replay reconcile; no recursive callback |
| Records -> Patient/Appointment | Validate patient/assignment, acquire durable clinical hold, then author locally; finalize hold separately after local finalize | Orphan hold is safe but blocks booking changes; same-key retry or coordinator absence review; finalize-hold retry cannot roll back clinical history |
| Records -> Pharmacy | Validate medicine IDs on finalize; store name/catalog version snapshot | Catalog outage prevents finalize but draft survives; no stock reservation during prescribing |
| Pharmacy -> Records | Live prescription snapshot before reservation/dispense/revalidation; local allowance/stock strongly consistent | Outage prevents new reservation/dispense; staff release may proceed locally; stale revocation race documented, explicit revalidation/review |
| Billing -> Appointment/Records/Pharmacy | Explicit invoice creation and charge import via minimal contexts; owner source snapshots plus local unique ledger/price snapshots | Failed import commits no charges; staff retries same key; pricing missing is conflict, no free fallback; no automatic invoice generation |
| Emergency -> Patient | Validate self patient on submission and staff authority on commands; local claim/history strongly consistent | Dependency failure prevents command; submitted requests retained; no reliable dispatch implication |
| Frontend -> each public owner | Parallel scoped reads; explicit schedule submit/decision/reconcile and invoice source import; visible loading/empty/error/pending | Partial failure keeps other views usable; forms preserve safe retry key in memory; success only for actual committed owner response |

No Phase 2 handler publishes to RabbitMQ, polls another database or relies on a delivered event. Outbox rows only prepare future delivery. Phase 5 coordinator will introduce reviewed publishers/inbox consumers, replay/version-gap reconciliation and stable effect deduplication before enabling existing schedule/prescription/charge event workflows. Pending old outbox rows must be reviewed/backfilled against owner snapshots; do not blindly activate all historical events. Interim REST source identities, explicit holds and manual charge import must migrate without duplicate bookings, prescriptions or charges. No global transaction, instantaneous remote revocation or broker exactly-once delivery is claimed.
