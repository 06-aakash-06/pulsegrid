# Phase 1.4C-C authentication integration

Implemented for the synthetic single-hospital prototype. Patient owns accounts, profiles, roles, password hashes, sessions, signing keys, registration idempotency, outbox and auth audit. Each of the other six services verifies user JWTs independently and uses separately authenticated Patient authority calls for future privileged commands. No hospital business workflows or RabbitMQ publishers were added. The exact executed checks are in [the verification record](phase-1.4c-c-verification.md).

## Actual public API

| Method and path | Required request | Successful response |
|---|---|---|
| GET `/api/v1/auth/csrf` | Credentials, allowlisted Origin or GET Referer | `{csrf_token,header_name:"X-CSRF-Token",expires_in:3600}` and HttpOnly cookie |
| POST `/api/v1/auth/register` | Allowed Origin, registration payload, `Idempotency-Key`, `X-Anonymous-Command-ID` | 201 PatientProfile; no automatic login |
| POST `/api/v1/auth/login` | `{email,password}`, allowed Origin, CSRF header/cookie, credentials | TokenSet and HttpOnly refresh cookie |
| POST `/api/v1/auth/refresh` | Allowed Origin, CSRF header/cookie, refresh cookie, credentials | TokenSet and rotated refresh cookie |
| POST `/api/v1/auth/logout` | Allowed Origin, CSRF header/cookie, credentials | 204, session-family revocation and cookie deletion |
| GET `/api/v1/patients/me` | Bearer access token; current Patient account and patient role | PatientProfile and ETag |

Registration returns a generic 409 `conflict` for an unavailable email so the
response does not confirm whether a particular address has an account. A 409
`idempotency_conflict` instead means the same registration key was replayed with
different form content; the browser clears that attempt so the next submission
can start with a fresh key. Same-key, same-body retries replay the original
sanitized 201 response.

Before sending registration fields, the browser checks that the Patient
readiness endpoint returns a ready Patient service. A static demo deployment
without the API reports that account creation is unavailable and does not send
the user's registration fields to a missing route. Production frontend hosting
must proxy the Patient readiness and authentication routes to a configured
service-backed environment.

TokenSet is `{access_token,token_type:"Bearer",expires_in}`. PatientProfile is `{id,user_id,display_name,version,date_of_birth?,synthetic_contact?}`. IDs are decimal strings. Error envelopes expose only safe code/message/request ID. Unknown registration fields, including privileged roles, are rejected. GET me is available through the authenticated API client; dashboard business data remains an empty shell, with no new profile editor.

## Browser lifecycle and CSRF

At startup and on reload, AuthProvider performs a single refresh flight. The default `window.pulseGridSecurity.getCsrfHeaders` provider first GETs the CSRF endpoint with credentials and validates the returned token, header name and lifetime. An explicitly installed host provider is preserved. The token is read from JSON and remains in memory; JavaScript never reads the HttpOnly CSRF cookie.

The document retains `no-referrer`. Only the CSRF GET sets fetch `referrerPolicy: "origin"`, allowing the browser to send an origin-only Referer on same-origin GETs that omit Origin. No URL path is disclosed. Cross-origin GETs use the browser Origin. All mutations retain the browser's actual Origin; neither the proxy nor application fabricates an actor or Origin header. The backend rejects missing/null/foreign origins and invalid or missing CSRF protection.

CSRF initialization and each login/refresh/logout command are serialized together. Same-origin tabs coordinate cookie changes using the Web Locks API where available. AuthProvider deduplicates refresh across concurrent domain requests, refreshes at expiry and retries one protected 401 after refresh. A failed refresh clears memory state. Login and logout advance the local session epoch so an older refresh cannot restore logged-out state. Cookies rotate without automatic transport retries. Access tokens and registration passwords are never written to localStorage or sessionStorage.

Registration creates a CSPRNG UUID `Idempotency-Key` and a 32-byte random base64url `X-Anonymous-Command-ID`. The form retains both in memory after an ambiguous network/server failure or cancellation, and reuses them if the submitted payload is unchanged. Changing the payload, a definitive 4xx rejection, a successful result, or opening a fresh form starts a new attempt. No password or request fingerprint is stored in browser storage. Reload loses the attempt; the backend email uniqueness constraint still prevents duplicate accounts. Backend replay returns the sanitized original profile; a distinct-key duplicate shows the generic account-conflict message. Password hashing and account/profile/role/outbox/audit/idempotency persistence remain one Patient-owned transaction.

## Development launch and environment

Use [README launch commands](../README.md) with `compose.yaml` plus `services/patient/compose.auth.yaml`. Keep the same Compose project and persistent volumes. Generate keys once with `services/patient/generate_auth_keys.py` after installing Patient dependencies; never overwrite existing keys or DB credentials. Add settings from [auth.env.example](../services/patient/auth.env.example) to the ignored root `.env`.

- `AUTH_KEYS_DIRECTORY=./secrets/auth` uses a checkout-relative path. Only Patient mounts the user private signing key and idempotency secret. Each domain mounts only its own service private key and public verification files.
- `APP_ENVIRONMENT=development`, `AUTH_ALLOW_HTTP=true` permit non-Secure cookies only for explicit loopback HTTP development. Production rejects that exception and requires HTTPS, Secure cookies and `AUTH_ALLOW_HTTP=false`.
- `AUTH_ORIGINS=http://127.0.0.1:5173,http://127.0.0.1:8080` matches the standard browser and gateway. `localhost` is a different hostname; configure it explicitly before use. Never use wildcard credentialed CORS.
- `AUTH_KID=patient-dev-1`, `AUTH_ACCESS_SECONDS=600` (bounded 60–600), refresh idle seven days and absolute 30 days, Argon2id 64 MiB/three passes are defaults. The verification run temporarily used 60-second access tokens, then restored 600 seconds.
- Root `GATEWAY_PORT` defaults to 8080. Frontend `PULSEGRID_GATEWAY_URL` defaults to `http://127.0.0.1:8080`; browser `VITE_API_BASE_URL` stays empty for the same-origin Vite proxy. Vite listens on `127.0.0.1:5173`; use `npm run dev -- --strictPort` to avoid silent port changes.

Cookies have Path `/api/v1/auth`, HttpOnly, SameSite=Lax and no Domain. Same-site separate ports are supported by the exact allowlist; cross-site deployments are outside this contract. Traefik exposes only loopback public domain routes. `/internal/v1`, JWKS, authority, docs and administrative endpoints remain private. Production static hosting needs an equivalent API proxy or the reviewed same-site separate-origin deployment policy; a Vite build does not run a backend.

Build each domain image separately on small Docker VMs, then `up -d --no-build`. API and migration targets share image names; building duplicate targets together produced a Docker extraction snapshot error in this run. Sequential domain builds recovered without deleting images or volumes. All migration jobs must exit zero; Patient must reach `0003_auth_audit`. Preserve the idempotency HMAC secret over its retention window.

## Verification commands

Install all seven packages with test extras in one Python 3.12+ environment. Prefix imports with this checkout's service paths when reusing a test venv from another worktree:

```sh
export PYTHONPATH=services/patient:services/doctor:services/appointment:services/records:services/pharmacy:services/billing:services/emergency
python -m pytest --import-mode=importlib services -q
python tests/verify_infrastructure.py --authentication
python tests/verify_authentication.py
python tests/verify_authentication.py --base-url http://127.0.0.1:5173
cd frontend
npm run typecheck
npm test
npm run build
```

The ten PostgreSQL auth tests require `PULSEGRID_AUTH_INTEGRATION=1`, the ignored root keys/credentials and loopback PostgreSQL port 55433. Add `services/patient/compose.auth-test.yaml` to the same Compose project temporarily and start without rebuilding. These tests use fresh synthetic identities and retain audit history. Afterwards apply the ordinary auth overlay with `up -d --no-build` to remove that test port, preserving volumes. The tests construct ASGI apps against real PostgreSQL; they are distinct from the gateway HTTP and real browser checks.

For a bounded real expiry check, temporarily set `AUTH_ACCESS_SECONDS=60`, recreate Patient using the same auth overlays, then run `python tests/verify_authentication.py --expiry`. Restore 600 and recreate Patient afterwards. The check waits for actual expiry, verifies 401, refreshes and retries the profile. No tokens are printed. The HTTP verifier tests gateway CORS/private routes directly; Vite handles its own development preflights and SPA fallback, so the proxy run checks auth compatibility rather than pretending its `/internal` SPA HTML is an internal API.

Browser manual/automation journey: open `/register`, enter unique synthetic email/display name and a 12+ character passphrase, submit and confirm backend success; follow sign-in, verify `/patient/dashboard`, reload and confirm session restoration; attempt `/admin/dashboard` as a patient and confirm redirect; sign out and attempt `/patient/dashboard`, which must redirect to sign-in. Correlate Patient request logs and sanitized audit results, never record tokens/passwords. Missing/invalid CSRF, Origin rejection, expired/invalid JWTs and replay must also be checked against the real API.

## Known limits

No production TLS deployment, external abuse quotas, MFA, password reset, automatic JWKS refresh, production observability hardening or performance/HA evaluation is claimed. Phase 7's local observability deployment is documented in the [design](phase-7-observability-design.md) and [integration verification](phase-7-integration-verification.md). JWT role decoding in the browser is a navigation hint; backend authorization is independently tested. Browsers without Web Locks retain per-tab serialization but cannot coordinate different tabs; strict server replay detection fails closed and may require a new login. Different frontend origins do not share Web Locks. Logout does not broadcast immediate UI changes to other tabs; their next refresh/authorized request clears a revoked session. Existing low-risk JWT reads in other domains can remain valid until short expiry, as documented by the authority protocol. Browser concurrent-tab stress and separate-origin browser CORS were not exercised; HTTP CORS and unit single-flight checks were exercised. Future scopes require fresh authorization.
