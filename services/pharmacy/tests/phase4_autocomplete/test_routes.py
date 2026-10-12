from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "components/autocomplete/src"))
sys.path.insert(0, str(ROOT / "services/pharmacy"))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pulsegrid_autocomplete import IndexRegistry, Suggestion, build_snapshot

from pharmacy_service.features.autocomplete.routes import register_routes


class FakePorts:
    owner = "pharmacy"
    observer = None

    def __init__(self) -> None:
        self.index_registry = IndexRegistry()
        self.authorized = False
        self.revision = 1
        self.database_items = (
            Suggestion("7", "medicine", "Acetaminophen 500 mg"),
        )

    @asynccontextmanager
    async def read_session(self):
        yield object()

    async def authorize(self, request, roles, resource_id, write):
        self.authorized = True
        assert roles and resource_id is None and write is False
        return object()

    async def read_revision(self, session):
        return self.revision

    async def load_snapshot(self, session):
        return self.revision, self.database_items

    async def prefix_query(self, session, normalized_prefix, kinds, limit):
        assert "medicine" in kinds
        return self.database_items[:limit]

    async def filter_visible(self, session, suggestions):
        current = {(item.kind, item.id): item for item in self.database_items}
        return tuple(
            current[(item.kind, item.id)] for item in suggestions
            if (item.kind, item.id) in current
        )


def create_client(ports: FakePorts) -> TestClient:
    app = FastAPI()
    register_routes(app, ports)
    return TestClient(app)


def test_medicine_results_contain_no_stock_or_price_fields() -> None:
    ports = FakePorts()
    ports.index_registry.publish(build_snapshot(1, ports.database_items))
    response = create_client(ports).get(
        "/api/v1/pharmacy/medicines/autocomplete?prefix=acetaminophen"
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert ports.authorized
    assert response.json() == {
        "items": [{"id": "7", "kind": "medicine", "label": "Acetaminophen 500 mg"}],
        "index_version": 1,
        "source": "trie",
    }
    assert set(response.json()["items"][0]) == {"id", "kind", "label"}


def test_outdated_catalog_index_uses_owner_database() -> None:
    ports = FakePorts()
    ports.revision = 2
    ports.index_registry.publish(build_snapshot(1, ports.database_items))
    response = create_client(ports).get(
        "/api/v1/pharmacy/medicines/autocomplete?prefix=acet"
    )
    assert response.status_code == 200
    assert response.json()["source"] == "database"
    assert response.json()["index_version"] is None


def test_empty_catalog_prefix_returns_empty_success() -> None:
    ports = FakePorts()
    ports.database_items = ()
    ports.index_registry.publish(build_snapshot(1, ()))
    response = create_client(ports).get(
        "/api/v1/pharmacy/medicines/autocomplete?prefix=not-found"
    )
    assert response.status_code == 200
    assert response.json()["items"] == []
