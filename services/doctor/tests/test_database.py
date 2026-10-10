"""Configuration, lifecycle and safe dependency failure checks."""

import asyncio
from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from doctor_service.constants import API_PREFIX, SERVICE_NAME
from doctor_service.database import Database
from doctor_service.main import create_app
from doctor_service.settings import Settings


def configured():
    return Settings(
        db_host="localhost",
        db_name="doctor_db",
        db_user="doctor_app",
        db_password="test-password",
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("DB_POOL_SIZE", "0"),
        ("DB_MAX_OVERFLOW", "-1"),
        ("DB_HEALTH_TIMEOUT", "nan"),
        ("DB_POOL_TIMEOUT", "inf"),
        ("DB_PORT", "65536"),
        ("DB_CONNECT_TIMEOUT", "oops"),
    ],
)
def test_rejects_invalid_database_limits(field, value):
    with pytest.raises(ValueError):
        Settings.from_env({f"PULSEGRID_{SERVICE_NAME.upper()}_{field}": value})


def test_rejects_partial_configuration_and_hides_password():
    with pytest.raises(ValueError):
        Settings.from_env({f"PULSEGRID_{SERVICE_NAME.upper()}_DB_HOST": "localhost"})
    assert "test-password" not in repr(configured())
    assert "test-password" not in str(configured().database_url)


def test_lifespan_disposes_pool_and_exposes_gateway_health():
    app = create_app(configured())
    with TestClient(app) as client:
        assert app.state.database.engine is not None
        assert app.state.database.session_factory is not None
        assert client.get(API_PREFIX + "/health/live").status_code == 200
        with patch.object(
            app.state.database, "readiness", AsyncMock(return_value="available")
        ):
            response = client.get(API_PREFIX + "/health/ready")
            assert response.status_code == 200
            assert response.json()["dependencies"]["database"]["status"] == "available"
        with patch.object(
            app.state.database, "readiness", AsyncMock(return_value="unavailable")
        ):
            assert client.get("/health/ready").status_code == 503
    assert app.state.database.engine is None
    assert app.state.database.session_factory is None


def test_unreachable_database_is_unavailable():
    async def run():
        db = Database(configured())
        await db.start()
        with patch.object(
            type(db.engine),
            "connect",
            side_effect=OperationalError("", {}, Exception("private detail")),
        ):
            assert await db.readiness() == "unavailable"
        await db.close()

    asyncio.run(run())


def test_database_errors_use_safe_envelope():
    app = create_app()

    @app.get("/failure")
    async def fail():
        raise OperationalError("secret query", {}, Exception("secret password"))

    with TestClient(app) as client:
        result = client.get("/failure")
        assert result.status_code == 503
        assert "secret" not in result.text
        assert result.json()["error"]["request_id"]
