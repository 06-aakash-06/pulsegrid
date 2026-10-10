# PulseGrid frontend

React, TypeScript, Vite, and React Router foundation for the synthetic, single-hospital PulseGrid prototype. The screens are layout shells; patient and staff workflows are not implemented and no operational data is fabricated.

## Run locally

```sh
npm ci
npm run dev
npm run typecheck
npm test
npm run build
```

Keep `VITE_API_BASE_URL` empty for same-origin development. Vite proxies `/api` and `/s/` to `PULSEGRID_GATEWAY_URL`, defaulting to `http://127.0.0.1:8080`. Copy `.env.example` to `.env.local` to customize the gateway URL. Start Compose from the repository root first; see [the infrastructure runbook](../docs/infrastructure.md). A production static host needs an equivalent proxy or a separately reviewed CORS policy. The API client uses the proposed `/api/v1/auth/login` and `/api/v1/auth/register` routes only. Domain pages remain empty until their owner APIs and reviewed contracts are available.

The identity contract leaves CSRF token delivery and the header name to deployment configuration. Before sign-in, the host must install `window.pulseGridSecurity.getCsrfHeaders`, which returns the required header or headers. The browser never guesses a CSRF header name. With no provider, sign-in, refresh, and sign-out fail clearly without sending a cookie-authenticated request.

Access tokens are held only in React memory. The frontend decodes role claims only as navigation hints; each owning API remains responsible for identity, role, ownership, and assignment checks. Refresh tokens are expected in Secure HttpOnly cookies and are never read by the application. Registration does not automatically sign the user in.

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
