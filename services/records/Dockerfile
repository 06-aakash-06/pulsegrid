FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY services/records/pyproject.toml services/records/README.md services/records/requirements.lock ./
COPY services/records/records_service ./records_service
COPY components/rate_limiter /components/rate_limiter
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-cache-dir --no-deps .
RUN pip install --no-cache-dir --no-deps /components/rate_limiter
COPY services/records/alembic.ini ./
COPY services/records/migrations ./migrations
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "records_service.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-access-log"]
