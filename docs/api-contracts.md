# API contracts

Authentication endpoints listed in the Phase 1.4C-C integration runbook are implemented; other domain contracts below remain proposed. Each service will publish its own OpenAPI specification in `contracts/api/<service>/`. Root routing is Traefik; each service performs its own authorization. REST JSON uses `snake_case`. IDs are decimal strings, UTC timestamps RFC 3339, dates `YYYY-MM-DD`, and enums lowercase. Monetary schemas use `{amount_minor: integer, currency: "INR"}`. Examples are synthetic, and abbreviated typed schemas below define required fields unless marked `?`. API changes follow the compatibility policy in AGENTS.md.

## Common protocol

Routes are `/api/v1/<domain>/...`, internal routes `/internal/v1/...`. `/s/{token}` is the Appointment public link landing resolver routed by Traefik; it never performs check-in as a GET. `/health/live`, `/health/ready`, `/metrics` are service-local infrastructure routes, with metrics protected from public access. Phase 1.4B also exposes additive `<domain-prefix>/health/live` and `<domain-prefix>/health/ready` gateway aliases; PostgreSQL connectivity is required for readiness. Other routes below remain proposed.

Requests carry `Authorization: Bearer <access_token>` when required, `X-Request-ID` (validated UUID or generated), `X-Correlation-ID` (validated UUID or generated), W3C `traceparent`, and `Idempotency-Key` for retryable POST commands. Write updates of existing aggregates require `If-Match: "<version>"`; successful reads/writes return `ETag`. Missing precondition returns 428; stale version 412. DELETE commands that release reservations/waitlists also use If-Match and are idempotent by resource state. No access decisions rely on a caller-provided actor/role header.

Lists return `{items: [Schema], next_cursor: string|null}`; bounded `limit` defaults 20, max 100. Cursors use stable `(created_at,id)` or explicit search ordering, reject malformed cursors. Search uses `q` for prefix, `limit` max 20, minimum normalized prefix length 2, maximum 100 characters. Mutation status responses include version and state. Pending cross-service effects are explicit, even when the initiating local operation returns 201.

Errors: `{error: {code: string, message: string, request_id: uuid, details: object?}}`. Details must not reveal private records or credentials. Use 200 read/update/replayed successful response, 201 local resource committed, 202 durable request pending, 204 idempotent removal, 400 malformed protocol, 401 missing/invalid identity, 403 insufficient permission, 404 absent or hidden unauthorized resource, 409 business conflict/idempotency mismatch, 410 expired public link, 412 version conflict, 422 field/state validation, 428 missing If-Match, 429 rate limited with Retry-After, 503 unavailable/backlog admission failure with Retry-After, 504 downstream deadline. A replay normally returns the original stored code/body. Auth login/refresh/logout do not use persisted response replay. Short-link issuance and anonymous emergency token issuance store sanitized results only: a repeated key returns 409 `token_response_unavailable` with the nonsecret resource ID. If the first response was lost, authenticated users explicitly reissue links with a new key (revoking earlier links); anonymous tracking recovery requires staff assistance. Do not automatically retry these token-issuing POSTs. Anonymous submissions require a random 128-bit `X-Anonymous-Command-ID` nonce for deduplication, which is not an authentication credential. Any endpoint-specific statuses below supplement these defaults.

## Identity and authorization

Patient service is the identity issuer. Role names: `patient`, `doctor`, `receptionist`, `pharmacist`, `billing_staff`, `emergency_staff`, `hospital_admin`, `ops`. Self-registration grants patient only. Administrative role changes require hospital_admin and audit; medical-record access requires clinical assignment or explicit scoped grant even for hospital_admin. Service-to-service calls require a scoped service token, and delegated access where a user is involved. Full rules are in security.md.

## Patient (`/api/v1/patients`) and auth (`/api/v1/auth`)

| Method / route | Request | Response | Access / special outcomes |
|---|---|---|---|
| GET `/auth/csrf` | Credentialed request with allowed Origin (or GET Referer) | `{csrf_token,header_name:"X-CSRF-Token",expires_in:3600}` + HttpOnly cookie | Exact configured origin |
| POST `/auth/register` | `Registration {email, password, display_name, date_of_birth?, synthetic_contact?}` | 201 `PatientProfile` | Allowed Origin, Idempotency-Key (16–128 chars), X-Anonymous-Command-ID (256-bit base64url nonce); 409 email unavailable with generic safe message; distributed quotas deferred |
| POST `/auth/login` | `{email,password}` | 200 `TokenSet` | Allowed Origin + CSRF cookie/header; generic 401 |
| POST `/auth/refresh` | Rotating refresh cookie + CSRF header | 200 `TokenSet` | Refresh session; replay revokes family |
| POST `/auth/logout` | Refresh cookie + CSRF header | 204 | Idempotent revocation |
| GET `/patients/me` | None | `PatientProfile` | patient |
| PATCH `/patients/me` | `{display_name?,synthetic_contact?}` | `PatientProfile` | Self + If-Match |
| GET `/patients/{patient_id}` | None | Minimal `PatientProfile` | Scoped care/administration need; private fields filtered |
| PATCH `/patients/users/{user_id}/roles` | `{roles:[Role]}` | `{user_id,roles,auth_version,version}` | hospital_admin, current authority, If-Match |
| PATCH `/patients/users/{user_id}/account-state` | `{state:"active"|"disabled",reason}` | `{user_id,state,auth_version,version}` | hospital_admin, audited, If-Match |

Only register/login/refresh/logout/csrf and GET me are implemented in this public section. Cookie Secure defaults to true; explicit development loopback HTTP is the sole exception. See [actual integration](authentication-integration.md).

`PatientProfile {id,user_id,display_name,date_of_birth?,synthetic_contact?,version}`. `TokenSet {access_token,token_type:"Bearer",expires_in:integer}`; refresh token is a Secure HttpOnly cookie, never response JSON. Client role hints can be derived from token but server remains authority.

## Doctor (`/api/v1/doctors`)

| Method / route | Request | Response | Access / special outcomes |
|---|---|---|---|
| GET `/doctors` | specialty, cursor, limit | page of `DoctorProfile` | Authenticated discovery |
| GET `/doctors/search` | q, specialty?, limit | `{items:[SearchMatch],catalog_version,observed_at}` | Authenticated; trie or DB baseline |
| GET `/doctors/{doctor_id}` | None | `DoctorProfile` | Authenticated |
| POST `/doctors` | `{staff_user_id,display_name,specialty_ids:[ID]}` | 201 `DoctorProfile` | hospital_admin; validate staff identity |
| PATCH `/doctors/{doctor_id}` | `{display_name?,specialty_ids?,active?}` | `DoctorProfile` | Assigned doctor or hospital_admin; If-Match; active status changes require schedule coordination |
| POST `/doctors/{doctor_id}/schedules` | `{timezone,slot_minutes,intervals:[{starts_at,ends_at}],expected_revision}` | 202 `ScheduleProposal` | Assigned doctor or hospital_admin; no immediate availability promise |
| GET `/doctors/{doctor_id}/schedules` | None | page of `ScheduleProposal` | Assigned doctor, receptionist, hospital_admin |

`DoctorProfile {id,display_name,specialties:[{id,name}],active,version}`. `ScheduleProposal {id,doctor_id,revision,status:"pending"|"accepted"|"rejected",conflicts:[ID],version}`. Doctor deactivation requires proposing closure of future availability; conflicts must be resolved explicitly before activation of that proposal. `SearchMatch {id,label,matched_prefix}`; medicine search uses the same envelope.

## Appointment (`/api/v1/appointments`)

| Method / route | Request | Response | Access / special outcomes |
|---|---|---|---|
| GET `/appointments/availability` | doctor_id, from, to (max 31 days) | `{slots:[Slot],accepted_revision,observed_at}` | Authenticated; cached hint |
| POST `/appointments` | `{patient_id,slot_id,expected_schedule_revision}` | 201 `Appointment` | patient self or receptionist; 409 occupied/overlap/waitlist priority |
| GET `/appointments` | patient_id?, doctor_id?, state?, cursor | page of `Appointment` | Self, assigned doctor, receptionist |
| GET `/appointments/{id}` | None | `Appointment` | Ownership/assignment |
| POST `/appointments/{id}/cancel` | `{reason}` | `Appointment` with cancelled state | Self/receptionist; If-Match; 409 already in consultation/completed |
| POST `/appointments/{id}/reschedule` | `{target_slot_id,expected_schedule_revision}` | `Appointment` | Self/receptionist; If-Match; 409 preserves original booking |
| POST `/appointments/waitlists` | `{patient_id,slot_id}` | 201 `WaitlistEntry` | Self/receptionist; existing waiting entry replay-safe |
| GET `/appointments/waitlists` | patient_id?, slot_id?, cursor | page of `WaitlistEntry` | Self/receptionist |
| DELETE `/appointments/waitlists/{id}` | None | 204 | Self/receptionist; If-Match |
| POST `/appointments/{id}/checkin-links` | `{purpose:"checkin"}` | 201 `{link_id,url,expires_at}` | Self/receptionist; reissue revokes earlier link |
| GET `/s/{token}` | Opaque token in path | `{purpose,expires_at,login_required:true}` | Public, no patient identifiers; 404 unknown / 410 expired; no side effect |
| POST `/appointments/check-ins` | `{token}` | `{appointment_id,queue_entry_id,token_number,state,version}` | Self/receptionist; token verification + consumption; 409 reused for another command |
| GET `/appointments/queues` | doctor_id, local_date | `{entries:[QueueEntry],observed_at}` | Assigned doctor/receptionist; patient gets own token and anonymized positions only |
| POST `/appointments/queue-entries/{id}/start` | None | `QueueEntry` | Assigned doctor, If-Match; 409 if another consultation in progress |
| GET `/appointments/journeys/{id}` | None | `Journey` | Self/receptionist; clinical text omitted |
| POST `/appointments/journeys/{id}/discharge` | None | `Journey` | receptionist/assigned doctor; If-Match; 409 stages pending/unpaid |

`Slot {id,doctor_id,starts_at,ends_at,state,revision}`. `Appointment {id,journey_id,patient_id,doctor_id,slot_id,starts_at,ends_at,state,version}`. States: confirmed -> checked_in -> in_consultation -> completed; confirmed/checked_in may cancel. Rescheduling allowed before check-in. Missed visits use a separately audited receptionist transition to `no_show` through POST `/appointments/{id}/no-show` with If-Match; it releases capacity and updates the queue. No automatic cancellation from wall-clock assumptions.

`WaitlistEntry {id,slot_id,patient_id,state,joined_at,version}` with states waiting/promoted/withdrawn/skipped. `QueueEntry {id,appointment_id,token_number,state,position?,version}` with waiting/in_consultation/completed/cancelled/no_show. `Journey {id,appointment_id,state,stages:[{name,state,source_resource_id?,observed_at}],version}`; stage values pending/complete/skipped/reopened. `observed_at` is projection freshness, not clinical completion time.

## Records (`/api/v1/records`)

| Method / route | Request | Response | Access / special outcomes |
|---|---|---|---|
| GET `/records/patients/{patient_id}` | cursor | page of `RecordSummary` | Self, assigned doctor/scoped grant |
| GET `/records/{record_id}` | None | `MedicalRecord` | Resource access policy; read audited |
| POST `/records/consultations` | `{appointment_id,clinical_content}` | 201 `Consultation` draft | Assigned doctor; verify active consultation |
| PATCH `/records/consultations/{id}` | `{clinical_content}` | `Consultation` | Author doctor; draft only + If-Match |
| POST `/records/consultations/{id}/finalize` | `{prescription_items:[PrescriptionItemInput]}` (may be empty) | `{consultation:Consultation,prescription:Prescription|null}` | Assigned doctor; If-Match; medicine refs validated |
| POST `/records/{record_id}/amendments` | `{content,reason}` | 201 `MedicalRecord` new revision | Authorized doctor, audited, If-Match |
| GET `/records/prescriptions/{id}` | None | `Prescription` | Self, assigned doctor, pharmacist minimum scope |
| POST `/records/prescriptions/{id}/revoke` | `{reason}` | `Prescription` | Authorized doctor, If-Match; asynchronous reservation release |
| POST `/records/access-grants` | `{patient_id,grantee_user_id,scope,expires_at}` | 201 `AccessGrant` | Patient self or designated authorized clinical policy |
| DELETE `/records/access-grants/{id}` | None | 204 | Grant owner, If-Match |

`PrescriptionItemInput {medicine_id,quantity:positive_integer,dosage,instructions}`. `Prescription {id,consultation_id,patient_id,journey_id,revision,state,items:[{id,medicine_id,quantity,dosage,instructions}],version}`. `Consultation {id,appointment_id,patient_id,doctor_id,status,clinical_content,revision,version}`. `MedicalRecord {id,consultation_id,patient_id,content,revision,supersedes_id?,version}`. `RecordSummary` omits clinical content. `AccessGrant {id,patient_id,grantee_user_id,scope,expires_at,version}`; scopes are explicit `records:read` or `prescriptions:read`, never role elevation.

## Pharmacy (`/api/v1/pharmacy`)

| Method / route | Request | Response | Access / special outcomes |
|---|---|---|---|
| GET `/pharmacy/medicines` | cursor, limit | page of `Medicine` | Authenticated |
| GET `/pharmacy/medicines/search` | q, limit | search envelope | Authenticated |
| GET `/pharmacy/medicines/{id}` | None | `Medicine` | Authenticated; stock availability is a hint |
| POST `/pharmacy/medicines` | `{sku,name}` | 201 `Medicine` | pharmacist/hospital_admin |
| POST `/pharmacy/inventory-adjustments` | `{medicine_id,batch_code,expires_on,delta,reason}` | 201 `{movement_id,inventory_version}` | pharmacist; reject negative balance |
| POST `/pharmacy/reservations` | `{prescription_id,items:[{prescription_item_id,quantity}]}` | 201 `Reservation` | Self/pharmacist; 409 insufficient stock/allowance; 409 prescription projection pending with retry hint |
| GET `/pharmacy/reservations/{id}` | None | `Reservation` | Self/pharmacist |
| DELETE `/pharmacy/reservations/{id}` | None | 204 | Self/pharmacist; If-Match; cannot undo dispensing |
| POST `/pharmacy/reservations/{id}/dispense` | None | 201 `{dispensing_id,reservation_id,state,version}` | pharmacist, If-Match, current prescription validation |

`Medicine {id,sku,name,active,availability:"available"|"unavailable"|"unknown",catalog_version}`. `Reservation {id,patient_id,prescription_id,state,items:[{medicine_id,quantity}],expires_at,version}` states reserved/expired/released/dispensed. Reservations may fulfill partial quantities, but each reservation dispenses exactly once; cumulative quantity constraints apply across reservations.

## Billing (`/api/v1/billing`)

| Method / route | Request | Response | Access / special outcomes |
|---|---|---|---|
| GET `/billing/invoices` | patient_id?, cursor | page of `Invoice` | Self/billing_staff |
| GET `/billing/invoices/{id}` | None | `Invoice` | Self/billing_staff |
| POST `/billing/invoices/{id}/payments` | `{amount_minor,currency,simulated_outcome:"success"|"decline"}` | 201 `Payment` | Self/billing_staff, If-Match; Idempotency-Key mandatory; 409 overpayment |
| POST `/billing/invoices/{id}/adjustments` | `{amount_minor,reason}` | 201 `InvoiceAdjustment` | billing_staff, If-Match, audited |
| GET `/billing/invoices/{id}/insurance-estimates` | None | `{estimate_minor,currency,rules_revision,source_fetched_at,freshness_state}` | Self/billing_staff; unavailable estimate explicitly represented |
| POST `/billing/insurance-refreshes` | `{provider_id}` | 202 `{run_id,state:"pending"}` | billing_staff/hospital_admin; allowlisted fixtures only |
| GET `/billing/insurance-refreshes/{run_id}` | None | `{run_id,state,fetched_at?,error_code?}` | billing_staff/hospital_admin |
| POST `/billing/tariffs` | `{charge_code,unit_amount_minor,currency}` | 201 `{id,charge_code,revision,unit_amount_minor,currency}` | billing_staff; new immutable tariff version |

`Invoice {id,journey_id,patient_id,status,items:[{id,charge_code,source_service,source_item_id,quantity,unit_amount_minor}],total_minor,paid_minor,balance_minor,currency,version}`. `Payment {id,invoice_id,amount_minor,currency,status,version}` success/declined. Decline is a committed simulated result, not an HTTP transport error. Tariff revisions and posted item price snapshots prevent late price changes from silently altering invoices. `InvoiceAdjustment {id,invoice_id,amount_minor,reason,version}`. Reversals use POST `/billing/payments/{id}/reverse` with `{reason}`, billing_staff, If-Match, returning updated Payment and emitting payment reversal; idempotent and audited. No card/bank fields are accepted.

## Emergency (`/api/v1/emergencies`)

| Method / route | Request | Response | Access / special outcomes |
|---|---|---|---|
| POST `/emergencies` | `{description,reported_urgency,synthetic_contact?,patient_id?}` | 201 `{request:EmergencyRequest,tracking_token?}` | Self or limited anonymous submission; token only for anonymous |
| GET `/emergencies/{id}` | Identity or `Authorization: EmergencyTracking <token>` | `EmergencyRequest` filtered | Self/emergency_staff or minimal anonymous status |
| GET `/emergencies` | state?, cursor | page of `EmergencyRequest` | emergency_staff; age/priority ordered |
| PATCH `/emergencies/{id}/priority` | `{assigned_priority:1..5,reason}` | `EmergencyRequest` | emergency_staff; If-Match; 1 highest |
| POST `/emergencies/{id}/claim` | None | `EmergencyRequest` | emergency_staff; If-Match; 409 already claimed |
| POST `/emergencies/{id}/transitions` | `{state,reason}` | `EmergencyRequest` | Assigned emergency_staff; If-Match |

`EmergencyRequest {id,state,reported_urgency,assigned_priority,created_at,updated_at,version}`; privileged views include description/contact/claim. States submitted -> triaged -> claimed -> processing -> resolved, with audited cancellation allowed before processing; expired claim returns triaged for reclaim. Client urgency is advisory, priority initially defaults to an untriaged queue category and must be staff-assigned; never treat anonymous assertions as highest clinical severity. Raw tracking token is returned once and never logged.

## Service-to-service APIs

Use private service DNS and service authentication; Traefik need not expose these routes. User token context accompanies delegated checks; service token never grants blanket clinical access. Responses expose the minimum needed.

| Owner / route | Caller / purpose | Request -> response |
|---|---|---|
| Patient GET `/internal/v1/auth/jwks` | Service verifier key refresh | Standard public-key JWKS, no private keys |
| Patient POST `/internal/v1/authorization/check` | Any service on privileged mutation | `{subject_user_id,required_role,auth_version}` -> `{active,allowed,current_auth_version}`; stale version denies until reauth |
| Patient GET `/internal/v1/patients/{id}/status` | Appointment/ref validation | `{patient_id,active,version}` |
| Patient GET `/internal/v1/users/{id}/staff-status` | Doctor staff validation | `{user_id,active,roles,version}` |
| Appointment GET `/internal/v1/appointments/{id}/consultation-context` | Records assignment check | `{appointment_id,patient_id,doctor_id,journey_id,state,version}` |
| Records GET `/internal/v1/prescriptions/{id}/dispensing-context` | Pharmacy current authorization | `{prescription_id,patient_id,journey_id,revision,state,items:[{id,medicine_id,quantity}],version}` |
| Pharmacy POST `/internal/v1/medicines/validate` | Records prescription construction | `{medicine_ids:[ID]}` -> `{items:[{id,active,catalog_version,name}]}` |
| Each owner GET `/internal/v1/reconciliation/{aggregate_type}/{id}` | Allowlisted event consumer | Owner-specific minimal snapshot, `aggregate_version`, event cursor/time; no clinical text in journey reconciliation |

Internal calls use common deadlines, request/trace IDs, documented 403/404/409/503/504 failures and circuit breakers. Reconciliation aggregate allowlists: Patient patient status; Doctor schedule proposal; Appointment schedule decision/consultation/journey context; Records prescription/consultation completion; Pharmacy reservation/dispensing summaries; Billing invoice/payment summaries; Emergency request state. Apply the same minimal-data service scopes as event subscriptions. No generic reflection or arbitrary aggregate retrieval.

## Compatibility

Add optional fields and new routes within v1; consumers ignore unknown optional fields. Renaming/removing fields, changing meaning/requiredness or narrowing accepted values requires v2 and a documented migration period. Event versions evolve separately. Keep OpenAPI and actual examples synchronized in later phases. Contract checks, concurrent command tests and authorized/unauthorized response tests are future acceptance gates, not Phase 1.1 runtime evidence.
