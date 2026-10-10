# PulseGrid frontend

React, TypeScript, Vite, and React Router application for the synthetic, single-hospital PulseGrid prototype. Patient registration, sign-in, in-memory access-token sessions, cookie-based session restoration, and role-gated workspace shells are implemented. Phase 2.8 connects hospital forms and views to the frozen Phase 2 owner APIs. No operational data is fabricated.

## Run locally

```sh
npm ci
npm run dev
npm run typecheck
npm test
npm run build
```

Keep `VITE_API_BASE_URL` empty for same-origin development. Vite proxies `/api` and `/s/` to `PULSEGRID_GATEWAY_URL`, defaulting to `http://127.0.0.1:8080`. Copy `.env.example` to `.env.local` to customize the gateway URL. The coordinator manages the shared gateway and Compose stack; see [the infrastructure runbook](../docs/infrastructure.md). Do not start a separate stack from an agent worktree. A production static host needs an equivalent proxy or a separately reviewed CORS policy. Authentication uses the implemented `/api/v1/auth/register`, `/api/v1/auth/login`, `/api/v1/auth/refresh`, and `/api/v1/auth/logout` routes. Domain pages issue real authenticated requests and display loading, empty, error and owner-confirmed results. Mock HTTP fixtures are restricted to tests.

The application installs a default `window.pulseGridSecurity.getCsrfHeaders` provider while preserving an explicitly supplied host provider. It requests `/api/v1/auth/csrf` with credentials before cookie-authenticated mutations and reads the signed token from JSON. Only this GET uses an origin-only referrer policy so same-origin requests satisfy the backend origin check without disclosing URL paths. The HttpOnly cookie remains unreadable. It validates the response header name and sends `X-CSRF-Token`; invalid delivery fails closed. CSRF initialization and each mutation are serialized, with Web Locks coordinating same-origin tabs where available. See [the integration runbook](../docs/authentication-integration.md).

Access tokens are held only in React memory and refreshed from the rotating HttpOnly cookie at startup, before expiry, or once after a protected request receives 401. Concurrent refreshes share one request. The frontend decodes subject and role claims only for authenticated state and navigation hints; each owning API remains responsible for identity, role, ownership, and assignment checks. Refresh tokens are never read by the application. Registration sends the documented payload plus a secure UUID Idempotency-Key and 256-bit base64url X-Anonymous-Command-ID. Both remain in memory for retries after ambiguous failures; changing the submitted payload or starting a new form creates a new attempt. Successful registration does not sign the user in.

## Routes

- Public: `/`
- Authentication: `/login`, `/register`
- Patient: `/patient/dashboard`, `/patient/doctors`, `/patient/appointments`, `/patient/waitlist`, `/patient/check-in`, `/patient/queue`, `/patient/journey`, `/patient/records`, `/patient/prescriptions`, `/patient/pharmacy`, `/patient/billing`, `/patient/emergency`
- Doctor: `/doctor/dashboard`, `/doctor/consultations`, `/doctor/queue`, `/doctor/prescriptions`
- Pharmacist: `/pharmacist/dashboard`, `/pharmacist/inventory`, `/pharmacist/prescriptions`
- Billing staff: `/billing/dashboard`, `/billing/invoices`, `/billing/payments`, `/billing/insurance`
- Emergency staff: `/emergency/dashboard`, `/emergency/requests`
- Hospital administrator: `/admin/dashboard`, `/admin/staff`, `/admin/doctors`, `/admin/settings`
- Receptionist: `/receptionist/dashboard`, `/receptionist/appointments`
- Operations: `/ops/dashboard`, `/ops/traces`

Workspace paths require an in-memory access-token session with the matching role hint. Direct service authorization is not delegated to the frontend.

## Phase 2.8 implementation and handoff

Base: `de63867adb7f5863c708ee19f4376ccbb49a0691`. Ownership: `frontend/**` only. No backend, shared contract, Docker or infrastructure edits. Existing authentication behavior is retained. No runtime dependency declarations or lockfile changes.

| Workspace / pages | Connected functionality and owner paths |
|---|---|
| Patient dashboard | GET/PATCH `/api/v1/patients/me`; own profile ID comes from this response, never JWT subject |
| Patient doctors and appointments; Reception appointments | Doctor specialties/directory/detail; `/api/v1/appointments/availability`; appointment list/detail/book/cancel/reschedule. UTC bounds are explicit and cursor scope resets on filter changes |
| Patient records and prescriptions | `/api/v1/records/patients/{patient_id}`, record detail, consultations/list/detail, prescriptions/list/detail and patient access grant create/delete |
| Doctor dashboard; Admin doctors | `/api/v1/doctors/me`, specialty/doctor create and profile edit, schedule proposal/list/detail, `/api/v1/appointments/schedule-decisions` create/detail, explicit Doctor reconciliation, accepted availability display |
| Doctor consultations and prescriptions | Assigned appointment list, consultation create/edit/finalize, immutable record amendments, prescription revoke, authorized historical reads and medicine catalog. Prescription creation is part of finalization |
| Patient pharmacy; Pharmacist dashboard/inventory/prescriptions; Admin dashboard catalog | `/api/v1/pharmacy/medicines` list/detail/create/edit, inventory list/adjustment, reservations list/detail/create/release/revalidate/dispense and dispensing list. Pharmacists use Records prescription ID lookup, never the bulk clinical list |
| Patient billing; Billing dashboard/invoices/payments | `/api/v1/billing/invoices` list/detail/create, explicit source-ID charge import, nested invoice payments list/create; staff tariff list/revision creation. Simulated declines are committed outcomes and do not show a paid balance |
| Patient emergency; Emergency dashboard/requests | `/api/v1/emergencies` create/list/detail, priority, claim/release and permitted transitions. Patient urgency is advisory; assignment and transitions remain owner-authorized |
| Admin staff; Admin/Reception dashboard | Patient demographic search/detail/edit, user list/detail, roles and account-state changes using independent user ETags |

Forms validate required/trimmed bounded text, decimal IDs, dates/UTC intervals, integer quantities/money, distinct source IDs, roles and schedule limits. All mutations have a review/confirmation step. Single-resource ETags come from `requestWithMetadata`; missing ETags disable mutation. A stale 412 instructs the user to reload and review. POST attempts freeze the body, key and If-Match before sending; ambiguous transport/5xx failures offer explicit original-command retry. Inputs remain disabled while reviewing, submitting or retrying. The attempt is held in the mounted form memory, so keep the page open until its outcome is resolved. No automatic POST/PATCH retries beyond the retained existing one-401 authentication refresh are added.

Every list uses the frozen page envelope, 20-item opaque cursor pagination, Previous/Next controls and owner scoping. Refresh and filter changes never fabricate an empty successful response after a service error. Multi-role users can switch only to workspaces allowed by their role hints; the backend remains the authority. Existing mobile navigation and responsive layouts are preserved with small form styles.

Automatic waitlists, QR/check-in, live queues, patient journey automation, insurance, observability and unspecified admin settings remain explicitly unavailable and send no domain commands. No final visual redesign was attempted.

### Outstanding backend/coordinator dependencies

- All seven Phase 2 owner APIs, migrations, current-authority checks and private dependency adapters must be integrated by the coordinator. Mocked HTTP results are not evidence of backend/database correctness.
- Configure synthetic staff roles and Doctor staff mappings before staff workflows. No fixture credentials or real records are included. Verify gateway routing, sensitive-response no-store headers and ETag availability (including cross-origin exposure if a separate origin is chosen).
- Schedule proposal creation, Appointment decision and Doctor reconciliation are three explicit steps. Rejection/conflicts and recovery depend on persisted owner responses; automatic broker convergence is unavailable. Closure must precede deactivation.
- Records historical reads/amendments require owner assignment/holds or patient grants. The frozen grant contract has create/delete but no list or GET. This frontend retains the create response ETag for revocation during the current page session; older grants cannot be reloaded/revoked here without coordinator-reviewed lookup support.
- Pharmacy must validate prescription allowances and expiry on reserve/revalidate/dispense. Prescription revocation does not claim automatic reservation release. Billing requires configured tariffs and explicit finalized consultation/completed dispensing IDs; no automatic detection of missing charges or all-care reconciliation.
- Emergency lease expiry, claim ownership and legal transitions are enforced by Emergency; display state alone cannot authorize action. No dispatch or clinical reliability claim.

### Verification

Executed from `frontend/`: `npm ci` (pass, existing lockfile; audit reports zero vulnerabilities), `npm run typecheck` (pass), `npm test` (pass, 85 tests across four files) and `npm run build` (pass, Vite production bundle). `git diff --check` and frontend-only path inspection pass. Branch: `phase-2-8-frontend`. The HTTP tests cover existing auth/session/navigation regression plus profile validation, doctor filters/cursors, accepted-slot booking, cancellation/rescheduling, consultation finalization/prescription inputs, historical reads, pharmacy reservations/stock/fulfillment, manual billing imports/declines, emergency submissions/claims, schedule decisions/reconciliation, account roles and retry/ETag safety. See `tests/hospital.test.tsx`.

No real gateway/backend integration, PostgreSQL concurrency checks, shared Docker stack, measured performance or full browser visual pass was run. The coordinator owns end-to-end integration after all eight branches finish. Stop after Phase 2.8.

## Foundation limits

This project is an educational prototype and not a certified clinical or emergency-response platform. Do not use real patient records, credentials, or payment information. Empty states report empty successful owner pages; unavailable services show errors. Neither implies a completed workflow or clinical reliability.
