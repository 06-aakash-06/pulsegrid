# Security, roles and owner integrity

Current evidence combines the executed service/PostgreSQL suites with 17 real gateway negative/session checks. [Test counts](evidence/final-test-results.json), [live cases](evidence/live-security-checks.json), [owner DB checks](evidence/schema-audit-isolation.json). This is scoped verification, not a penetration-test or production assurance claim.

| Role | Actual intended surface | Current evidence |
|---|---|---|
| Patient | Own profile, appointments/queue/journeys, scoped records/prescriptions, own invoice/payment/estimates, own Emergency requests | Real browser and complete gateway journeys; cross-patient appointment/journey/invoice/record/prescription/Emergency reads return 404. |
| Doctor | Own schedule proposals, assigned consultation queue, clinical authoring/finalization/history/amendments | Four browser routes visited; gateway authoring/finalization; actual Records/PostgreSQL care/grant tests. History/amendment is inside `/doctor/prescriptions` through RecordsPage, not absent. |
| Receptionist | Existing-patient lookup/book/walk-in/check-in/queue/journey/discharge within contract | Browser routes/read views; gateway workflows/permission assertions and owner tests. No clinical authoring privilege implied. |
| Pharmacist | Catalog/batches/reservations/revalidation/dispensing and minimum prescription context | Three browser routes; actual gateway fulfillment, exact stock and duplicate tests. |
| Billing staff | Tariffs, invoices, owner charge imports, simulated payment visibility, fixture refresh | Four browser routes; actual invoice/charge/payment/insurance flows. No real payment credentials or gateway. |
| Emergency staff | Staff case list, priority, lease claim/release, authorized processing/history | Two browser routes; actual claim replay, release/reclaim, resolution/history. |
| Hospital administrator | Staff/role/account authority, Doctor management and operational controls | Six browser routes; isolated staff role provisioning via owner API; patient admin attempt denied. |
| Ops | Read-only Control Room and bounded Trace Explorer | Two browser routes, authenticated summary/traces; Surge mutation denied 403. |

## Checks executed

- Invalid JWT and validly signed expired JWT both rejected 401. Current auth/protocol suites cover RS256 issuer/audience/algorithm/JWKS and Argon2id behavior. Browser-local demo password derivation is separate; it proves no backend password security.
- Login without required CSRF rejected 403. Refresh rotated successfully; replay of old refresh rejected 401 and revoked the family, so the newly rotated refresh also returned 401 afterward. HttpOnly and SameSite=Lax were observed. The explicit local development HTTP environment is not a production Secure-cookie deployment test.
- Patient cannot administer staff (403), inject a role via profile patch (422), or gain authority through spoofed public actor headers (403). Stale profile If-Match rejected 412; profile remained unchanged.
- Internal owner route through public gateway returned 404. References do not grant access. Sensitive owner leaf calls preserve service authentication/current authority; no direct foreign SQL was introduced by repairs.
- Seven actual owner DB heads match migrations; table/column/nullability/FK/unique/check/exclusion expectations and runtime-role restrictions checked. All 42 attempts to connect with one service credential to another service database were denied. Audit digests, ordered chains and heads were verified under a consistent read-only snapshot.
- Real PostgreSQL suites cover booking/overlap races, reservation/stock rules, source deduplication/payment arithmetic, clinical immutability/grants and Emergency transitions. The additional expiry regression uses actual PostgreSQL scheduling state.

The audit's direct SQL reads were operator verification against each owning database, not application cross-owner access. Three initial synthetic insurance provider rows used only the isolated Billing migration owner. No retained business record was changed for testing. The retained repair changed only a consumer's exact DLX write allowance and the Appointment application image; credentials/keys were not rotated.

## Limits

Persistent grant management after navigation remains L-01: create/revoke exists, but no frozen grant list/detail API. Current tests cover owner grant behavior; no live-browser grant mutation was performed. Exhaustive role × resource × transition denial combinations, adversarial scanning, production TLS/cookie behavior and every browser session-expiry interaction were not all exercised. Raw JWTs, refresh/QR tokens, aliases, passwords and private configuration are excluded from committed evidence.
