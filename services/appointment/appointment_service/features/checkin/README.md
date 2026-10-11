# Appointment check-in module (G1)

This module implements the frozen QR check-in resources. It exports
`register_routes`, `register_tables`, `schema_spec`, and the transactional
`revoke_for_booking_change` participant. The module does not register itself;
the G2 Appointment integrator supplies the reviewed `checkin` allowlist entry.

`POST /api/v1/appointments/{appointment_id}/check-in-links` returns the raw
22-character Base62 secret once. The QR/manual payload is the relative
same-origin landing path
`/patient/check-in#appointment_id=<ID>&token=<TOKEN>`. It contains no patient
profile or clinical data. The database stores only SHA-256 token digests plus
the workflow version and schedule fingerprint. Equal-key issuance replays
return `token_response_unavailable` with the nonsecret link ID.

Redemption and receptionist fallback authorize the appointment, check current
Patient/Doctor owner status before a command transaction, then use the G0
lock context. Queue creation is delegated to
`core.invoke_participant(app, "queue", "allocate_on_checkin", session,
context)`. The queue owner receives no token, opens no session, and must stage
its writes in the supplied transaction. Token consumption, workflow transition,
queue allocation, audit/outbox effect, and saved command response commit or
roll back together. `revoke_for_booking_change(session, context)` revokes
unconsumed links under locks already acquired by G0.

`schema_spec()` is the non-executable 0006 migration handoff. Agent 1 owns the
revision and shared metadata changes. G2 also needs the queue participant and
its migration before enabling redemption. G0 has no link-issued event in its
effect allowlist and no check-in journey projection participant; the integrator
must resolve those shared event/projection hooks before claiming the complete
cross-feature mutation contract. The module does not invent substitute event
names or update Agent 4's journey tables.

The PostgreSQL fixture under `tests/phase3_checkin/` applies only test-local
DDL for the manifest additions to a disposable G0 database. It does not execute
or claim the reserved 0006 migration.
