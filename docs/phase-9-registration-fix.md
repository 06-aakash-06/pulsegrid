# Patient registration repair — 25 October 2026

The deployed static demo unconditionally returned HTTP 409 with code `mock_registration_disabled` from POST `/api/v1/auth/register`. The registration UI treated every 409 as a duplicate email. No email could work. In addition, mock ownership checks assumed the single seeded patient ID, and demo mutations disappeared when the browser reloaded.

The demo now creates patient-only accounts with unique user/profile IDs, normalized email uniqueness, anonymous registration idempotency and salted PBKDF2 password verification. Only actual email-conflict error codes receive duplicate-account copy. The registration page identifies the storage scope and requires a password of at least eight characters.

Patient-scoped mock responses and mutations now resolve the authenticated patient's profile. Newly registered patients start without seeded appointments, records, prescriptions, invoices, emergencies, waitlists or journeys. Cross-patient resource lookup is rejected. Profile editing, booking, rescheduling/cancellation, waitlist joining/withdrawal and appointment workflow creation use the new patient's identity; existing role checks, API paths, ETags and command keys remain. A clinician must still author a prescription before a patient can reserve prescribed medicine.

The static demo serializes its synthetic database in browser local storage. It retains accounts, profiles and actions across reloads and sign-out/sign-in, and serializes writes across tabs with Web Locks when supported. It stores salted password derivations, never plaintext passwords or bearer tokens. If local storage cannot save a mutation, the demo rolls it back and returns a clear storage error rather than falsely reporting success. The development mock remains in-memory until the server restarts.

This is a functional browser-local educational demo, not a deployed identity backend. Accounts/data are not shared between devices or browsers, and clearing site storage removes them. The normal build remains connected to the real API and excludes the demo implementation.

Validation:

- Regression tests cover unique emails, normalized duplicates, wrong passwords, anonymous idempotency/replay, role escalation, own profile and empty patient collections, cross-patient access, profile edits, booking/emergency, persistence, storage failure rollback and waitlist/workflow transitions.
- All 158 frontend tests pass; TypeScript, normal production build and static demo build pass. The normal build has no `dev-mock` or demo database-key matches.
- Playwright against `dev:mock`: new registration → sign-in → own name → empty appointment list, with no page errors.
- Playwright against the static demo: registration → sign-in → reload → booking → reload; own booking remains visible and the session restores, with no page errors. All 12 patient routes load without error alerts.
- Browser scripts/logs: `/tmp/pulsegrid-audit/register-flow.js`, `register-flow.log`, `register-persistence.log`, `registration-tests.log`.
