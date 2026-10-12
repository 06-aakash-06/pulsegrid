# Security

Phase 4.0 preparation: the [component contract freeze](phase-4-component-contracts.md)
and [parallel plan](phase-4-parallel-plan.md) define the current seven-component
scope and supersede older algorithm/phase proposals below where different.
They do not activate functionality. Phase 2/3 contracts and actual owner code
remain authoritative for existing hospital workflows; no runtime changes are
part of preparation.

PulseGrid uses synthetic identities, records, prescriptions, provider websites and payments exclusively. It is an educational prototype, not a certified clinical or emergency-response platform. Never import real patient data, send real emergency dispatches, or collect real payment credentials. Authentication controls are implemented and verified in Phase 1.4C-C; future hospital workflow controls remain requirements, not certified guarantees.

## Authentication and lifecycle

Patient is the identity authority. Use short-lived asymmetrically signed JWT access tokens (initial 10 min), allowlisted algorithms, issuer `pulsegrid-patient`, explicit audience `pulsegrid-api`, subject user ID, `jti`, `iat`, `exp`, roles and `auth_version`. Private signing keys stay in Patient; other services consume public keys through a planned private JWKS endpoint (`/internal/v1/auth/jwks`). Rotate keys with overlap covering maximum token lifetime. Do not invent your own cryptographic primitives.

Refresh tokens are cryptographically random at least 256 bits, stored hashed in Patient, carried only in Secure HttpOnly SameSite cookies on the auth routes. Seven-day idle expiry and 30-day absolute session family expiry are initial configurable limits. Rotate on each refresh; reuse revokes the entire family. Logout/account disable revokes sessions and increments auth_version. Access tokens already issued remain usable for low-risk reads until their short expiry; sensitive mutations check current account/role status through Patient and fail closed during its outage. Denied current auth_version requires refresh or reauthentication. Never claim immediate universal revocation from JWT alone.

SPA holds access token in memory, never localStorage. Refresh/login/logout use CSRF protections (origin validation plus CSRF token) when cookies are involved. Tight CORS allowlist; production-like local demos terminate TLS at Traefik. Plain HTTP is permitted only on explicitly documented isolated local development, without exposing the host to untrusted networks. No credentials in URLs except deliberately opaque short-link token; redact it everywhere and use `Referrer-Policy: no-referrer` on link pages.

Passwords use Argon2id through a maintained library, per-password salt, and configurable cost calibrated on the deployment host. Allow long passphrases, enforce minimum length and bounded input size, reject known synthetic demo weak passwords outside demo fixtures, and never log credentials. Login response is generic for absent/wrong password; throttle by principal and source with bounded global quotas. Password reset and MFA are beyond the initial required auth workflow; document them as future security hardening before expanding beyond the prototype.

## RBAC plus resource authorization

| Role | Allowed scope | Restrictions |
|---|---|---|
| patient | Own profile, bookings/check-in/waitlists, records, prescriptions, medicine reservations, invoices/payments, emergency tracking | Cannot choose another patient ID or mutate staff-only states |
| doctor | Own schedule proposals, assigned queue, assigned consultation documents and prescriptions | Care relationship or explicit grant for historical records; no general patient export |
| receptionist | Booking/waitlist/check-in/queue and simulated discharge coordination | No clinical text, prescribing, stock adjustment or role management |
| pharmacist | Minimum prescription fulfillment context, stock, reservations, dispensing | No record history or prescription authorship |
| billing_staff | Invoices, tariff revisions, adjustments, simulated payments, fixture insurance refresh | No diagnoses or record contents |
| emergency_staff | Emergency triage/claim/processing and limited request context | No normal medical-record access merely from role |
| hospital_admin | Staff roles, doctor administration, operational configuration | Role alone does not authorize medical text or prescription modification |
| ops | Restricted read-only control room, telemetry and runbooks | No clinical data or business mutation; chaos requires explicit experiment authorization |

Resources always check ownership, current assignment, or Records-owned scoped access grants. Services derive patient/doctor identifiers from trusted identity mappings and verify client-supplied IDs. IDs and unguessable tokens are not substitutes for authorization. Privileged staff writes check Patient's current authority before local transaction. A user cannot grant themselves a staff role; synthetic bootstrap admin must be an explicit local setup mechanism with hashed credentials and audit, implemented later.

Doctors can access records for an active assigned consultation; historical access after the episode requires a time-limited scoped grant or documented ongoing care assignment. Records verifies Appointment consultation context for sensitive writes. Pharmacists receive only prescription IDs/items/dosage needed to dispense, not clinical history. Patient access is to their own records; unauthorized existence can be concealed with 404. All sensitive reads and writes are audited, including denied access where safely attributable.

## Interservice trust and revocation races

Use short-lived service JWTs with distinct `aud` for each target service, `sub` identifying caller, and explicit scopes; manage keys/config through infrastructure secrets. Direct internal routes reject public user-only tokens. User-initiated calls carry delegated identity separately from service identity, with aud/issuer verification; background workers have narrowly allowlisted scopes and cannot masquerade as clinicians. TLS is required outside an isolated local network; network isolation alone is insufficient. RabbitMQ publishers/consumers have per-exchange/queue permissions; PostgreSQL runtime accounts have no cross-service credentials or DDL rights. Redis has authenticated restricted access and is never publicly exposed.

Remote assignment or prescription checks precede local transactions, and no cross-service lock is held. Consequently an authorization/grant/prescription can be revoked just after validation. Bounded tokens and current checks minimize the window but cannot prove global instantaneous revocation. Events reconcile: Pharmacy releases unfilled reservations and flags already-dispensed items for staff review; Records amendment/revocation reopens relevant journey stages. Do not silently undo historical clinical actions. A stricter globally coordinated authorization protocol would add latency/availability costs and requires a separate design decision.

## Security-sensitive commands

- Booking, rescheduling, queue start and QR redemption: ownership, state/version, idempotency and local constraints; no trust in cached availability.
- Prescription creation/amendment/revocation and medical reads: role, assignment/grant, immutable revision and audit.
- Dispensing/stock adjustment: current prescription validity and quantity allowances, staff role, inventory audit.
- Payments/adjustments/reversals: simulated only, integer money, role/ownership, local transaction and idempotency.
- Emergency priority changes/claims: authorized staff and atomic state transitions; protect submission capacity but do not trust patient severity as professional triage.
- Role administration, token refresh, audit/telemetry export and chaos execution: restrictive scopes, rate limits, secret redaction and operator history.

Short-link tokens use 128 bits of secure randomness and Base62 encoding; digest with SHA-256 at rest, avoid enumerable IDs as tokens. Initial check-in expiry is appointment check-in-window end (window starts 30 min before and ends 15 min after planned start, configurable); reissue revokes previous token. Check-in requires authenticated owner or receptionist after appointment verification, one-time atomic token consumption, and no GET side effects. Anonymous Emergency tracking uses a separate random 128-bit token, hashed at rest, initially valid 24 h with minimal status output; renewals/longer access require authenticated staff policy. Never log raw tokens, even in gateway access paths or trace attributes.

## Tamper-evident audit history

Each service writes a local ordered chain for sensitive operations: lock audit head, allocate sequence, canonicalize metadata deterministically, compute `entry_hash = SHA256(prev_hash || canonical_entry_bytes)`, insert entry and update head in the same mutation transaction. The canonical entry includes chain_id, sequence, actor/service identity, action, resource IDs, result, UTC timestamp, request/correlation IDs and a content digest where needed, not raw clinical text. Sensitive reads/denials write their own audit transaction before releasing sensitive content; audit storage failure fails closed for such access. Non-sensitive operational metrics are separate.

Runtime credentials cannot update/delete audit entries; append through a constrained database function/role. Hash chaining detects modification/reordering when verified against a trusted anchor; a privileged attacker who rewrites the whole chain and head can defeat an unanchored chain. Periodically export/checkpoint chain-head hashes to separately permissioned append-only infrastructure storage (initial local development artifact). Test modification, deletion and reordering detection. This is tamper-evident, not tamper-proof, and has no global ordering across seven services. Audit head locking may be a throughput bottleneck; measure before scoped partitioning.

## Privacy and input handling

Validate payload types/sizes, SQL parameters, normalized search prefixes, identifiers and upload formats if uploads are later introduced. No file upload is required in this foundation. Do not leak exception traces to clients. Audit/log synthetic IDs only as needed; access tokens, contacts, passwords, clinical text and QR URLs never appear in metrics/logs/traces. Label metrics by low-cardinality service/route/status, not patient/record/user identifiers. Control-room graphs show aggregate emergency wait statistics, not request descriptions.

Synthetic crawler runs only against explicitly allowlisted provider fixtures with bounded redirects, timeouts, response size, page count and recursion depth. Reject nonallowlisted redirect targets, arbitrary user URLs, metadata/private unrelated destinations and unbounded fetches; fixture services are intentionally permitted private destinations by explicit hostname/port allowlist. Parse without executing scripts and store content hashes/provenance. Crawler credentials must not grant clinical DB access.

Retention is configurable and documented: broker/outbox/inbox defaults in database-design.md; prototype audit/domain histories persist until explicit synthetic environment reset; telemetry has bounded retention/rotation configured in Phase 8. Privacy deletion requirements for real systems are out of scope and must not be inferred from this prototype policy. Synthetic resets must verify data origin and be explicit, not automatic cleanup of history. No secrets, generated synthetic bulk datasets, private exports or `.env` files in Git.

## Phase 1.4B development infrastructure

The implemented Compose environment publishes only the loopback HTTP gateway. APIs and databases have no host ports; database runtime and migration credentials remain separate and service-scoped. Runtime roles cannot create schema objects, connect to another database or modify audit storage. Random ignored local credentials, trusted-proxy boundaries and path-template application logs prepare later integration. See [infrastructure.md](infrastructure.md) for commands, privileges and limits. Authentication, signed CSRF delivery, private signing keys and Patient auth audit append are implemented. Production TLS remains unimplemented; local readiness is not an authorization claim. See [authentication integration](authentication-integration.md).
