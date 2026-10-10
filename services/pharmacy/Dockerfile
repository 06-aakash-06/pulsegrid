FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml README.md ./
COPY pharmacy_service ./pharmacy_service
RUN pip install --no-cache-dir .

USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "pharmacy_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
