FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY services/emergency/pyproject.toml services/emergency/README.md services/emergency/requirements.lock ./
COPY services/emergency/emergency_service ./emergency_service
COPY components/rate_limiter /components/rate_limiter
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-cache-dir --no-deps .
RUN pip install --no-cache-dir --no-deps /components/rate_limiter
COPY services/emergency/alembic.ini ./
COPY services/emergency/migrations ./migrations
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "emergency_service.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-access-log"]
