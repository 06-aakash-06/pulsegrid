# PulseGrid Doctor Service

Independent FastAPI application for the **doctor** domain. Its public API prefix is `/api/v1/doctors`; the private Appointment integration uses `/internal/v1/doctors`.

## Phase 2.2 surface

- `GET /specialties`, `POST /specialties`: browse specialties and create them as a current hospital administrator.
- `GET /me`, `GET /`, `GET /{doctor_id}`: read the signed-in doctor's private view, or browse permitted public profiles with specialty/name/active filters and stable cursor pagination.
- `POST /`, `PATCH /{doctor_id}`: create a profile after Patient confirms an active Doctor-role account; an assigned doctor may edit only their own display name, while a hospital administrator may manage all profile fields.
- `POST /{doctor_id}/schedules`, `GET /{doctor_id}/schedules`, `GET /{doctor_id}/schedules/{proposal_id}`, `POST /{doctor_id}/schedules/{proposal_id}/reconcile`: submit immutable schedule proposals, read them, and reconcile Appointment's recorded decision.
- `GET /internal/v1/doctors/{doctor_id}/identity`, `GET /internal/v1/doctors/{doctor_id}/schedule-proposals/{proposal_id}`: scoped, audited Appointment-only leaves using service and delegated-user tokens.

Doctor owns profile data and schedule proposals. It does not own confirmed appointment state and does not access Appointment's database. Appointment accepts or rejects each proposal and owns actual slot allocation and availability; clients must use Appointment's availability API for accepted slots. A proposal with no intervals is a closure. Schedule input uses absolute UTC RFC 3339 intervals and an IANA timezone label. The contract has no Doctor availability endpoint, weekly recurrence, waitlist, live queue, or autocomplete trie.

Profile writes validate Doctor staff status against Patient. Deactivation also checks Appointment's operational status after an accepted empty closure. Reconciliation reads Appointment's schedule-decision leaf before the local transaction. These calls have bounded retries and process-local circuit breakers; an unavailable owner leaves the Doctor operation pending or unavailable, and a remote status check cannot make cross-service changes atomic. Unit/API tests mock these owner calls; live Patient and Appointment integration remains dependent on those services and their service keys being configured.

## Run locally

From this directory, create an isolated environment, install the package and its test extra, then start the ASGI app:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
uvicorn doctor_service.main:app --host 127.0.0.1 --port 8000
```

Configuration is read from `PULSEGRID_DOCTOR_ENVIRONMENT` and `PULSEGRID_DOCTOR_LOG_LEVEL`. Defaults are `development` and `INFO`. Database configuration uses the same service prefix with `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` and pool/deadline settings. Private-key/JWKS and owner URL settings use `PULSEGRID_DOCTOR_AUTH_*`; defaults target the Compose Patient and Appointment service names. See [the infrastructure runbook](../../docs/infrastructure.md).

`GET /health/live` reports process liveness. `GET /health/ready` checks PostgreSQL with a bounded SELECT: 200 when connected, 503 when unconfigured/unavailable. Redis and RabbitMQ are not yet required. The same routes are exposed through the gateway under the domain API prefix.

This package owns `doctor_db`, `doctor_app` runtime credentials and an independent Alembic history. Compose runs `doctor-migrate` with the separate `doctor_migration` owner before starting the API. From the repository root, run `docker compose run --rm doctor-migrate` to apply outstanding revisions. Do not use runtime schema creation or another service's models/database.

Run the colocated tests with `python -m pytest`. The API/integration suite requires `PULSEGRID_DOCTOR_TEST_DATABASE_URL` pointing to a disposable loopback PostgreSQL database named `pulsegrid_doctor_test_<unique-suffix>`; it applies this service's Alembic migrations and truncates only that database. External owner APIs are mocked. Build an independent container from this directory with `docker build -t pulsegrid-doctor .`.

This is a synthetic educational prototype. It is not a clinical or emergency-response system.
