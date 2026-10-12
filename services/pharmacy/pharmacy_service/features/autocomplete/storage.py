"""Pharmacy-only SQL projection ports for the autocomplete adapter.

The suggestion projection intentionally contains only active medicine IDs and
display names. Inventory, prices, prescriptions, and fulfillment are excluded.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pulsegrid_autocomplete import Suggestion, normalize_label, rank_suggestions

from ...models import medicines


async def read_revision(session: AsyncSession) -> int:
    row = (
        await session.execute(
            text("SELECT revision FROM catalog_revision WHERE singleton IS TRUE")
        )
    ).scalar_one_or_none()
    if row is None or type(row) is not int or row < 1:
        raise HTTPException(503, detail={"code": "dependency_unavailable"})
    return row


async def load_snapshot(
    session: AsyncSession,
) -> tuple[int, tuple[Suggestion, ...]]:
    revision = await read_revision(session)
    rows = list(
        (
            await session.execute(
                select(medicines.c.id, medicines.c.name)
                .where(medicines.c.active.is_(True))
                .order_by(medicines.c.id)
            )
        ).mappings()
    )
    entries = tuple(
        Suggestion(id=str(row["id"]), kind="medicine", label=row["name"])
        for row in rows
    )
    return revision, entries


async def prefix_query(
    session: AsyncSession,
    normalized_prefix: str,
    kinds: Sequence[str],
    limit: int,
) -> tuple[Suggestion, ...]:
    """Exact Unicode baseline against Pharmacy's active owner catalog.

    The stored `normalized_name` field follows the existing Pharmacy search
    semantics. Phase 4's frozen NFKC/casefold/whitespace behavior is new-route
    only, so this fallback applies that shared normalizer to current display names
    in Python rather than changing catalog columns or existing search behavior.
    """
    if "medicine" not in set(kinds):
        return ()
    rows = list(
        (
            await session.execute(
                select(medicines.c.id, medicines.c.name)
                .where(medicines.c.active.is_(True))
                .order_by(medicines.c.id)
            )
        ).mappings()
    )
    entries = (
        Suggestion(id=str(row["id"]), kind="medicine", label=row["name"])
        for row in rows
        if normalize_label(row["name"]).startswith(normalized_prefix)
    )
    return rank_suggestions(entries, limit)


async def filter_visible(
    session: AsyncSession, suggestions: Iterable[Suggestion]
) -> tuple[Suggestion, ...]:
    """Revalidate current active IDs and names without reading stock or pricing."""
    selected = tuple(
        item for item in suggestions if item.kind == "medicine"
    )
    ids = sorted({item.id for item in selected}, key=int)
    if not ids:
        return ()
    rows = list(
        (
            await session.execute(
                select(medicines.c.id, medicines.c.name)
                .where(medicines.c.active.is_(True), medicines.c.id.in_([int(x) for x in ids]))
                .order_by(medicines.c.id)
            )
        ).mappings()
    )
    current = {
        str(row["id"]): Suggestion(
            id=str(row["id"]), kind="medicine", label=row["name"]
        )
        for row in rows
    }
    return tuple(current[item.id] for item in selected if item.id in current)


def schema_spec() -> dict[str, Any]:
    """Non-executable owner migration handoff; this feature owns no table."""
    return {
        "tables": [],
        "columns": [],
        "indexes": [],
        "constraints": [],
        "preflight": [
            "Pharmacy migration 0005_phase4_catalog_revision must provide "
            "catalog_revision(singleton BOOLEAN PRIMARY KEY CHECK(singleton), "
            "revision BIGINT NOT NULL CHECK(revision >= 1)) with one seeded row.",
            "Owner revision changes transactionally when medicines.name, "
            "medicines.active, or other catalog fields change; inventory-only "
            "writes must not bump this revision.",
        ],
        "runtime_grants": [
            {"table": "catalog_revision", "privileges": ["SELECT"]},
            {"table": "medicines", "privileges": ["SELECT"]},
        ],
        "audit_actions": [],
    }


def register_tables(metadata: Any) -> None:
    """Autocomplete owns no ORM table; the coordinator owns revision DDL."""
    del metadata
