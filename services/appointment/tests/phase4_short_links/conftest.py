"""Fixtures limited to an owned disposable Appointment test database."""

import pytest
from fastapi import HTTPException

from appointment_service import phase3_core


@pytest.fixture
def current_authority(monkeypatch):
    async def current(_request, principal, roles):
        if principal is None:
            raise HTTPException(401, detail="unauthorized")
        for role in roles:
            if role in principal.roles:
                return role
        raise HTTPException(403, detail="forbidden")

    monkeypatch.setattr(phase3_core, "current", current)
