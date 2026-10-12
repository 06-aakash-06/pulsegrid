from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "components/autocomplete/src"))
sys.path.insert(0, str(ROOT / "services/doctor"))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pulsegrid_autocomplete import IndexRegistry, Suggestion, build_snapshot
from doctor_service.errors import ApiError, error_response

from doctor_service.features.autocomplete.routes import register_routes


class FakePorts:
    owner = "doctor"
    observer = None

    def __init__(self) -> None:
        self.index_registry = IndexRegistry()
        self.events: list[str] = []
        self.revision = 1
        self.database_items = (
            Suggestion("4", "doctor", "Ada Lovelace"),
            Suggestion("9", "specialty", "Advanced Computation"),
        )

    @asynccontextmanager
    async def read_session(self):
        self.events.append("session")
        yield object()

    async def authorize(self, request, roles, resource_id, write):
        self.events.append("authorize")
        assert roles and resource_id is None and write is False
        return object()

    async def read_revision(self, session):
        return self.revision

    async def load_snapshot(self, session):
        return self.revision, self.database_items

    async def prefix_query(self, session, normalized_prefix, kinds, limit):
        self.events.append("database")
        return tuple(
            item for item in self.database_items
            if item.kind in kinds and item.label.casefold().startswith(normalized_prefix)
        )[:limit]

    async def filter_visible(self, session, suggestions):
        self.events.append("visible")
        current = {(item.kind, item.id): item for item in self.database_items}
        return tuple(
            current[(item.kind, item.id)] for item in suggestions
            if (item.kind, item.id) in current
        )


def create_client(ports: FakePorts) -> TestClient:
    app = FastAPI()

    @app.exception_handler(ApiError)
    async def doctor_error_handler(request, error):
        return error_response(request, error.status_code, error.code, error.message)

    register_routes(app, ports)
    return TestClient(app)


def test_fresh_index_revalidates_and_returns_only_safe_directory_fields() -> None:
    ports = FakePorts()
    ports.index_registry.publish(build_snapshot(1, ports.database_items))
    response = create_client(ports).get("/api/v1/doctors/autocomplete?prefix=ada")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "items": [{"id": "4", "kind": "doctor", "label": "Ada Lovelace"}],
        "index_version": 1,
        "source": "trie",
    }
    assert ports.events[0] == "authorize"
    assert "visible" in ports.events


def test_missing_or_renamed_selected_id_uses_database_top_k() -> None:
    ports = FakePorts()
    ports.index_registry.publish(
        build_snapshot(1, [Suggestion("4", "doctor", "Ada Older")])
    )
    response = create_client(ports).get("/api/v1/doctors/autocomplete?prefix=ada")
    assert response.status_code == 200
    assert response.json()["source"] == "database"
    assert response.json()["index_version"] is None
    assert response.json()["items"][0]["label"] == "Ada Lovelace"
    assert "database" in ports.events


def test_stale_index_falls_back_and_invalid_prefix_is_checked_after_auth() -> None:
    ports = FakePorts()
    ports.revision = 2
    ports.index_registry.publish(build_snapshot(1, ports.database_items))
    client = create_client(ports)
    stale = client.get("/api/v1/doctors/autocomplete?prefix=ada")
    assert stale.status_code == 200
    assert stale.json()["source"] == "database"
    ports.events.clear()
    invalid = client.get("/api/v1/doctors/autocomplete?prefix=%20%20")
    assert invalid.status_code == 422
    assert ports.events == ["authorize"]
