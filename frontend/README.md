# PulseGrid frontend

React, TypeScript, Vite, and React Router application for the synthetic, single-hospital PulseGrid prototype. Patient registration, sign-in, in-memory access-token sessions, cookie-based session restoration, and role-gated workspace shells are implemented. Domain workflows remain unimplemented and no operational data is fabricated.

## Run locally

```sh
npm ci
npm run dev
npm run typecheck
npm test
npm run build
```

Keep `VITE_API_BASE_URL` empty for same-origin development. Vite proxies `/api` and `/s/` to `PULSEGRID_GATEWAY_URL`, defaulting to `http://127.0.0.1:8080`. Copy `.env.example` to `.env.local` to customize the gateway URL. Start Compose from the repository root first; see [the infrastructure runbook](../docs/infrastructure.md). A production static host needs an equivalent proxy or a separately reviewed CORS policy. Authentication uses the implemented `/api/v1/auth/register`, `/api/v1/auth/login`, `/api/v1/auth/refresh`, and `/api/v1/auth/logout` routes. Domain pages remain empty until their owner APIs and reviewed contracts are available.

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

## Foundation limits

This project is an educational prototype and not a certified clinical or emergency-response platform. Do not use real patient records, credentials, or payment information. Empty states indicate missing API integration; they do not imply that a workflow has completed or that live hospital activity exists.
