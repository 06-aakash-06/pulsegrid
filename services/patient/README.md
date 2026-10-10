# PulseGrid Patient Service

Independent FastAPI application for the **patient** domain. It owns identity, roles, patient profiles, and current authority checks. Phase 1 authentication remains documented in [the authentication setup and frontend contract](AUTHENTICATION.md). Cross-service hospital workflows remain out of scope.

## Run locally

From this directory, create an isolated environment, install the package and its test extra, then start the ASGI app:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
uvicorn patient_service.main:app --host 127.0.0.1 --port 8000
```

Configuration is read from `PULSEGRID_PATIENT_ENVIRONMENT` and `PULSEGRID_PATIENT_LOG_LEVEL`. Defaults are `development` and `INFO`. Database configuration uses the same service prefix with `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` and pool/deadline settings. See [the infrastructure runbook](../../docs/infrastructure.md).

`GET /health/live` reports process liveness. `GET /health/ready` checks PostgreSQL with a bounded SELECT: 200 when connected, 503 when unconfigured/unavailable. Redis and RabbitMQ are not yet required. The same routes are exposed through the gateway under the domain API prefix.

This package owns `patient_db`, `patient_app` runtime credentials and an independent Alembic history. Compose runs `patient-migrate` with the separate `patient_migration` owner before starting the API. From the repository root, run `docker compose run --rm patient-migrate` to apply outstanding revisions. Do not use runtime schema creation or another service's models/database.

## Patient management

The service implements the frozen Phase 2.1 routes:

- `GET /api/v1/patients/me` and `PATCH /api/v1/patients/me` for the authenticated patient's own profile.
- `GET /api/v1/patients` and `GET /api/v1/patients/{patient_id}` for scoped demographic lookup.
- `PATCH /api/v1/patients/{patient_id}` for receptionist/admin profile edits.
- `GET /api/v1/patients/users` and `GET /api/v1/patients/users/{user_id}` for hospital-admin account management.
- `PATCH /api/v1/patients/users/{user_id}/roles` and `/account-state` for current hospital administrators.
- Private `GET /internal/v1/patients/{patient_id}/status` and `/internal/v1/users/{user_id}/staff-status` leaves for their frozen callers and scopes.

Profile fields use independent profile versions. Role/account changes increment both account version and `auth_version`, revoke refresh sessions, and persist an unpublished outbox event and a constrained Patient-domain audit entry in the same PostgreSQL transaction. These routes use only Patient's own database. Private routes verify the caller service JWT and delegated user JWT; they are not exposed by the public gateway. Appointment, Records, Doctor, and Emergency integration must wire their service credentials and call the private leaves over private service DNS; those callers are not exercised together in this phase.

To bootstrap the first administrator in an isolated local/test environment, first register an account using a synthetic `.test` email, then run `python -m patient_service.bootstrap_admin` from this directory with Patient's loopback database settings and migrations applied. The command promotes that existing account only when no active administrator exists, asks for an explicit confirmation, revokes its refresh sessions, and requires a fresh login. It does not accept a password or create a default credential. Use the admin role API to assign later synthetic staff roles.

Run the colocated and cross-service authorization regression tests from this directory with `PYTHONPATH=.:../doctor:../appointment:../records:../pharmacy:../billing:../emergency python -m pytest`. The Patient management PostgreSQL tests run only when `PULSEGRID_PATIENT_MANAGEMENT_TEST_DB_URL` points to a migrated, password-configured loopback database whose name ends in `_test`. They reject other database targets. Existing auth-stack integration tests remain opt-in through their separate `PULSEGRID_AUTH_INTEGRATION` setup.

Build an independent container from this directory with `docker build -t pulsegrid-patient .`.

This is a synthetic educational prototype. It is not a clinical or emergency-response system.
