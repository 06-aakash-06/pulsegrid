# PulseGrid Records Service

Independent FastAPI application scaffold for the **records** domain. The API prefix reserved by the contract is `/api/v1/records`. Business routes are intentionally absent in Phase 1.2.

## Run locally

From this directory, create an isolated environment, install the package and its test extra, then start the ASGI app:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
uvicorn records_service.main:app --host 127.0.0.1 --port 8000
```

Configuration is read from `PULSEGRID_RECORDS_ENVIRONMENT` and `PULSEGRID_RECORDS_LOG_LEVEL`. Defaults are `development` and `INFO`. No credentials or database connection settings are defined in this scaffold.

`GET /health/live` reports process liveness. `GET /health/ready` returns HTTP 503: the application process is ready, while the required database dependency is `unconfigured` because no database adapter or infrastructure exists yet. It does not claim database readiness.

Run the colocated tests with `python -m pytest`. Build an independent container from this directory with `docker build -t pulsegrid-records .`.

This is a synthetic educational prototype scaffold. It has no business operations and is not a clinical or emergency-response system.
