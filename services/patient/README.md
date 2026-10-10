# PulseGrid Patient Service

Independent FastAPI application scaffold for the **patient** domain. The API prefix reserved by the contract is `/api/v1/patients`. Phase 1.4C-A adds Patient-owned authentication; hospital business routes remain absent. See [authentication setup and frontend contract](AUTHENTICATION.md).

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

Run the colocated tests with `python -m pytest`. Build an independent container from this directory with `docker build -t pulsegrid-patient .`.

This is a synthetic educational prototype scaffold. It has no hospital business operations and is not a clinical or emergency-response system.
