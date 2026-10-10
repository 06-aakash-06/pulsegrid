# PulseGrid Billing Service

Independent FastAPI application scaffold for the **billing** domain. The API prefix reserved by the contract is `/api/v1/billing`. Business routes are intentionally absent in Phase 1.2.

## Run locally

From this directory, create an isolated environment, install the package and its test extra, then start the ASGI app:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
uvicorn billing_service.main:app --host 127.0.0.1 --port 8000
```

Configuration is read from `PULSEGRID_BILLING_ENVIRONMENT` and `PULSEGRID_BILLING_LOG_LEVEL`. Defaults are `development` and `INFO`. Database configuration uses the same service prefix with `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` and pool/deadline settings. See [the infrastructure runbook](../../docs/infrastructure.md).

`GET /health/live` reports process liveness. `GET /health/ready` checks PostgreSQL with a bounded SELECT: 200 when connected, 503 when unconfigured/unavailable. Redis and RabbitMQ are not yet required. The same routes are exposed through the gateway under the domain API prefix.

This package owns `billing_db`, `billing_app` runtime credentials and an independent Alembic history. Compose runs `billing-migrate` with the separate `billing_migration` owner before starting the API. From the repository root, run `docker compose run --rm billing-migrate` to apply outstanding revisions. Do not use runtime schema creation or another service's models/database.

Run the colocated tests with `python -m pytest`. Build an independent container from this directory with `docker build -t pulsegrid-billing .`.

This is a synthetic educational prototype scaffold. It has no business operations and is not a clinical or emergency-response system.
