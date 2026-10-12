# Appointment short links

This module issues reusable navigation aliases for confirmed Appointment
workflows. It stores only a SHA-256 digest of each 128-bit, fixed-width Base62
alias. A raw alias appears only in the first committed `short_path` response;
same-key replay returns `409 token_response_unavailable` with the resource ID.
Aliases do not grant access and never contain or replace the Phase 3 QR secret.

`register_routes(app, ports)` mounts the frozen creation, revocation and `/s/`
resolution routes into a coordinator-supplied app. `register_tables(metadata)`
adds the table definition to Appointment metadata and executes no DDL.
`schema_spec()` is a handoff for forward migration `0010_phase4_short_links`.
`revoke_for_booking_change(session, context, appointment_id)` is a transaction
participant that revokes all unrevoked aliases, including expired rows.

The coordinator supplies authorization, command/idempotency, session, workflow,
lock, effect, ID, response and metrics ports. Database expiry checks use
PostgreSQL `clock_timestamp()`. Browser `Accept: text/html` gets a shape-checked
303 to the fixed `/short-link#alias=...` SPA route without a DB lookup. JSON
resolution requires current owner/receptionist scope and revalidates current
booking, workflow version, schedule fingerprint, hold state and expiry.

Run the owned checks from the repository root:

```sh
python -m pytest -q services/appointment/tests/phase4_short_links
```

The PostgreSQL tests use temporary owner databases and test-only DDL. They do
not claim that migration 0010 or the production feature mounting has been
integrated.
