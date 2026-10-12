FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY services/appointment/pyproject.toml services/appointment/README.md services/appointment/requirements.lock ./
COPY components/rate_limiter /components/rate_limiter
COPY components/unique_id /components/unique_id
RUN pip install --no-cache-dir -r requirements.lock
COPY services/appointment/appointment_service ./appointment_service
RUN pip install --no-cache-dir --no-deps .
RUN pip install --no-cache-dir --no-deps /components/rate_limiter /components/unique_id
COPY services/appointment/alembic.ini ./
COPY services/appointment/migrations ./migrations
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "appointment_service.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-access-log"]
