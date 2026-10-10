# PulseGrid Appointment Service

Independent FastAPI application scaffold for the **appointment** domain. The API prefix reserved by the contract is `/api/v1/appointments`. Business routes are intentionally absent in Phase 1.2.

## Run locally

From this directory, create an isolated environment, install the package and its test extra, then start the ASGI app:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
uvicorn appointment_service.main:app --host 127.0.0.1 --port 8000
```

Configuration is read from `PULSEGRID_APPOINTMENT_ENVIRONMENT` and `PULSEGRID_APPOINTMENT_LOG_LEVEL`. Defaults are `development` and `INFO`. Database configuration uses the same service prefix with `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` and pool/deadline settings. See [the infrastructure runbook](../../docs/infrastructure.md).

`GET /health/live` reports process liveness. `GET /health/ready` checks PostgreSQL with a bounded SELECT: 200 when connected, 503 when unconfigured/unavailable. Redis and RabbitMQ are not yet required. The same routes are exposed through the gateway under the domain API prefix.

This package owns `appointment_db`, `appointment_app` runtime credentials and an independent Alembic history. Compose runs `appointment-migrate` with the separate `appointment_migration` owner before starting the API. From the repository root, run `docker compose run --rm appointment-migrate` to apply outstanding revisions. Do not use runtime schema creation or another service's models/database.

Run the colocated tests with `python -m pytest`. Build an independent container from this directory with `docker build -t pulsegrid-appointment .`.

This is a synthetic educational prototype scaffold. It has no business operations and is not a clinical or emergency-response system.
