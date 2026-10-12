FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY services/doctor/pyproject.toml services/doctor/README.md services/doctor/requirements.lock ./
COPY services/doctor/doctor_service ./doctor_service
COPY components/rate_limiter /components/rate_limiter
COPY components/consistent_hashing /components/consistent_hashing
COPY components/key_value_cache /components/key_value_cache
COPY components/autocomplete /components/autocomplete
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-cache-dir --no-deps .
RUN pip install --no-cache-dir --no-deps /components/rate_limiter /components/consistent_hashing /components/key_value_cache /components/autocomplete
COPY services/doctor/alembic.ini ./
COPY services/doctor/migrations ./migrations
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "doctor_service.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-access-log"]
