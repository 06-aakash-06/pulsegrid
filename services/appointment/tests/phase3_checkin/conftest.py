"""Check-in tests use actual reviewed migrations on isolated PostgreSQL."""
import pytest


@pytest.fixture
def checkin_database(database):
    return database
