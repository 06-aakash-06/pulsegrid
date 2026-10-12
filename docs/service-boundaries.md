# Service boundaries

Phase 4.0 preparation: the [component contract freeze](phase-4-component-contracts.md)
and [parallel plan](phase-4-parallel-plan.md) define the current seven-component
scope and supersede older algorithm/phase proposals below where different.
They do not activate functionality. Phase 2/3 contracts and actual owner code
remain authoritative for existing hospital workflows; no runtime changes are
part of preparation.

All models below are proposals. Each service exclusively owns its database, migrations, credentials, API package, tests, and workers. Foreign service IDs are references, not foreign keys or permission grants. Staff identities and roles belong to Patient; staff clinical assignments belong to their respective domain.

| Service / logical DB | Responsibilities and owned entities | Dependencies and projections | Must NOT own |
|---|---|---|---|
| Patient / `patient_db` | Users, password credentials, refresh sessions, role assignments, patient profiles, current authorization decisions | Publishes patient registration/profile/account-state events; no domain DB dependency | Doctor schedules, bookings, clinical records, pharmacy stock, billing amounts, emergency triage |
| Doctor / `doctor_db` | Doctor profiles, specialties, profile-specialty links, immutable schedule proposals, timezone and scheduling policy | Patient staff identity validated by API; Appointment schedule acknowledgements projected; doctor cache/trie owned here | Active bookings, authoritative operational availability, queue positions, medical prescriptions |
| Appointment / `appointment_db` | Accepted schedule versions, slots, appointments, waitlists, check-in links/tokens, queue counters/entries, consultation assignment/state, journey projections | Doctor proposal events; patient account-state snapshot; Records completion, Pharmacy and Billing events; internal assignment verification API | Credentials, original doctor policy, record text, drug stock, invoice arithmetic, emergency priority |
| Records / `records_db` | Record revisions, consultation clinical content, prescriptions and immutable item revisions, access grants | Appointment verifies assignment; Patient verifies current privileged role/account; publishes clinical workflow metadata | Queue authority, stock reservations, invoice totals, identity passwords |
| Pharmacy / `pharmacy_db` | Medicine catalog, batches, stock balances/movements, prescription delivery projection, reservations/items, dispensing/items | Records validates prescription before dispensing; prescription events; Patient staff authority | Prescribing or editing source prescriptions, clinical diagnoses, invoice accounting |
| Billing / `billing_db` | Price catalog/version, invoices/items, simulated payments, invoice adjustments, insurance provider fixtures, crawler runs and estimate provenance | Records/Pharmacy charge-source events; patient cancellation metadata where compensation needed; Patient staff authority | Drug stock, medical record text, bookings, live internet insurer crawling or real payment processing |
| Emergency / `emergency_db` | Emergency requests, staff-assigned priorities, claims, lifecycle history, priority work processing | Patient optional identity validation and current staff authorization; publishes request status events | Bed management, ambulance dispatch guarantees, bookings, clinical diagnosis, predictive triage |

## Ownership rules for ambiguous workflows

- Doctor proposes schedules; Appointment accepts operational revisions. Doctor's displayed activation acknowledgement is an eventual view, and booking always consults Appointment's accepted revision.
- Appointment owns check-in and queue coordination. Records owns the clinical consultation document and publishes finalization; Appointment consumes it to complete the queue entry.
- Records authors prescriptions. Pharmacy stores a minimal revisioned projection to reserve/dispense; it cannot change instructions or create a prescription. Medicine identifiers originate in Pharmacy and are validated at prescription creation.
- Billing owns final monetary calculations, including versioned tariff snapshots. Events carry charge source identities and quantities, not trusted client totals. Pharmacy's optional displayed prices are informational. Insurance estimates do not constitute coverage approval.
- Appointment's patient journey is a workflow projection per episode. Source documents remain in their owners; the projection carries resource IDs, stage states and times, not medical text. Emergency requests have a separate lifecycle and do not create a normal appointment journey.
- No notification microservice is added. Domain events and frontend status views provide notifications initially; durable external messaging would require a separate decision and user authorization.
- ID generation is local to each service under a shared specification. Autocomplete lives in Doctor/Pharmacy. Cache placement is infrastructure tooling, not domain storage. Billing owns the synthetic crawler. Appointment owns short-link records.

## Dependencies and failure isolation

Read workflows should avoid chains: the frontend fetches each owner through Traefik. Strict mutation validation dependencies (Patient for privileged writes, Appointment for Records assignment, Records for Pharmacy dispensing) fail closed. A noncritical cache, crawler, metrics or insurance failure must not block consultation booking or authoritative local reads. Cross-service events may lag, so APIs expose pending state and `observed_at`; consumers never assume another service committed because an HTTP call was attempted.

Internally authenticated reconciliation interfaces export only a scoped aggregate/version snapshot. Never implement a generic remote SQL/query endpoint. Keep dependencies acyclic where possible; Patient identity has no reverse domain dependency. Doctor/Appointment schedule acknowledgement is an asynchronous handshake, not a synchronous recursive call.

## Future directory ownership

- `services/<service>/`: exclusively that domain, including database migrations and colocated unit tests.
- `frontend/`: browser application, API clients, accessible routes and UI tests; never authoritative booking logic or secret storage.
- `contracts/`: coordinated API/event source schemas; changes require consumer review and compatibility checks.
- `infra/`: routing, deployment, service credentials references and observability configuration; no business models.
- `tests/`: cross-service integration and contract tests. `experiments/`: load/chaos/algorithm measurements.
- `docs/`, `README.md`, `AGENTS.md`, `.gitignore`: coordinated foundation ownership. Parallel agents must not concurrently edit these shared paths without an explicit owner.
