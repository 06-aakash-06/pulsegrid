# PulseGrid Billing Service

Independent FastAPI service for the synthetic Phase 2 billing workflow. The public API prefix is `/api/v1/billing`. PostgreSQL `billing_db` is the only database this service reads or writes; Appointment, Records, Pharmacy and Patient are accessed only through their documented private REST interfaces. No RabbitMQ publisher/consumer, insurance crawler, real payment processor, refund path or discharge workflow is implemented.

## Endpoints

| Method and path | Purpose | Access |
|---|---|---|
| `GET /api/v1/billing/tariffs` | Filter and page immutable tariff revisions by `charge_code` | Current `billing_staff` |
| `POST /api/v1/billing/tariffs` | Create the next revision for `consultation` or `medicine:<id>` | Current `billing_staff` |
| `POST /api/v1/billing/invoices` | Create one invoice for a verified appointment | Current `billing_staff` |
| `GET /api/v1/billing/invoices` | Filter and page invoices; patients see their own billing history | Patient self or current `billing_staff` |
| `GET /api/v1/billing/invoices/{invoice_id}` | Retrieve one invoice and line items | Patient self or current `billing_staff` |
| `POST /api/v1/billing/invoices/{invoice_id}/charges` | Import a finalized consultation and/or completed dispensings | Current `billing_staff` |
| `GET /api/v1/billing/invoices/{invoice_id}/payments` | Filter and page payment attempts | Patient self or current `billing_staff` |
| `POST /api/v1/billing/invoices/{invoice_id}/payments` | Record a simulated success or decline | Patient self or current `billing_staff` |

New routes require an RS256 bearer access token and a current Patient authority check. Resource ownership is checked in Billing; a patient request for another patient's invoice returns 404. Lists apply ownership and query filters in SQL before cursor pagination. Single invoice reads and mutations use quoted decimal ETags. Every POST requires an `Idempotency-Key`; payment response keys are retained for seven days and other response keys for 24 hours.

## Billing behavior

Amounts are integer INR minor units from request validation through PostgreSQL `BIGINT`; binary floating-point is never used. A charge line is `quantity * unit_amount_minor`. The exact integer subtotal is the sum of posted line items, and Phase 2 total equals that subtotal because adjustments, discounts and taxes are not exposed. The frozen `Invoice` response contains `total_minor`, `paid_minor` and `balance_minor`; it does not add a `subtotal_minor` field.

Tariff revisions are immutable and assigned monotonically per charge code. Billing snapshots the latest matching tariff when a new source item is imported. It accepts only a finalized Records consultation or completed Pharmacy dispensing context, and verifies each source's appointment and patient against the invoice before starting the local transaction. Missing owner data, unavailable owners, mismatched sources and missing tariffs do not create charges. Lifetime uniqueness on `(source_service, source_item_id)` prevents duplicate line items; a repeated identical import is a no-op, while changed source values conflict.

Invoice creation is unique by appointment. Success and decline attempts both append an immutable payment row and increment the invoice version. A decline leaves `paid_minor` unchanged. Success is rejected if its amount exceeds the currently permitted balance; invoice row locks serialize payments. A later priced charge increases the total and reopens a previously paid invoice when a balance is due.

`paid` means the balance of currently imported charges is zero. Billing does not receive or acknowledge the complete set of expected charge sources in Phase 2, so this status is not proof of charge coverage or financial discharge completion. Source import is explicit and staff-driven.

Each committed tariff, invoice, charge or payment mutation writes its audit-chain entry and an unpublished outbox envelope in the same Billing database transaction as the response and business rows. No publisher is active; pending outbox rows are not delivery confirmation. Money and source IDs are kept out of free-form audit text; there is no clinical content in these APIs.

## Private dependencies and configuration

Use private service DNS only: `http://appointment:8000`, `http://records:8000`, and `http://pharmacy:8000`. Optional service URL settings are accepted only with the matching private hostname and port. The Billing service calls:

- Appointment `GET /internal/v1/appointments/{appointment_id}/billing-context` with `appointments:billing-context`.
- Records `GET /internal/v1/consultations/{consultation_id}/charge-context` with `consultations:charge-context`.
- Pharmacy `GET /internal/v1/dispensings/{dispensing_id}/charge-context` with `dispensings:charge-context`.
- Patient's existing `POST /internal/v1/authorization/check` for current `patient` or `billing_staff` authority.

Every owner context call carries both the short-lived Billing service token and delegated user access token, along with request/correlation IDs and valid `traceparent`. Dependency calls are bounded, retry only safe GETs, and complete before Billing row locks. Missing signing/JWKS configuration and unavailable owners fail closed.

Billing authentication settings use the `PULSEGRID_BILLING_AUTH_` prefix: `JWKS_PATH`, `SERVICE_JWKS_PATH`, `SERVICE_PRIVATE_KEY_PATH`, `SERVICE_KID`, `AUTHORITY_URL`, and optional `APPOINTMENT_URL`, `RECORDS_URL`, `PHARMACY_URL`. Database settings use `PULSEGRID_BILLING_DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`, with the existing pool/deadline settings. Do not commit keys or credentials.

## Migrations and local use

The service owns `billing_db`, runtime role `billing_app`, migration owner `billing_migration`, and its Alembic history. Phase 2 appends `0003_billing_phase2` to the Phase 1 head; it makes `journey_id` nullable, adds explicit appointment/source references, immutable ledger protections, tariff revision heads and the constrained Billing audit append function. Existing invoices without appointment references are left without fabricated IDs and are not exposed through the Phase 2 API.

From this directory, create an isolated environment and install the service plus test extra, then configure the service's DB and auth settings before running the app:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
alembic upgrade head
uvicorn billing_service.main:app --host 127.0.0.1 --port 8000
```

`GET /health/live` reports liveness. `GET /health/ready` reports bounded PostgreSQL readiness. Do not use runtime schema creation or another service's database. The billing package builds independently with its existing Dockerfile; this phase does not require changes to shared Compose infrastructure.

## Tests

The PostgreSQL integration tests require a dedicated disposable database URL in `PULSEGRID_BILLING_TEST_DATABASE_URL`. The suite upgrades only the Billing migrations and uses separate `billing_migration` and `billing_app` roles. It must not point at a shared development or production database. For example, set the variable to an isolated PostgreSQL test database and run:

```sh
python -m pytest
```

The suite checks exact integer calculations and validation, source states, duplicate invoices and charges, idempotency replay/body conflicts, payment transitions and concurrency, ownership/current authority, filtering/cursors, outbox/audit rows and persisted balances. Mocked owner APIs validate the private wire calls; cross-service deployment behavior remains an integration gate.

This service uses synthetic data exclusively. It is an educational prototype, not a certified clinical or emergency-response platform.
