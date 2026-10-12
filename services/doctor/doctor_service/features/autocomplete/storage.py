"""Doctor-only SQL projection ports for the autocomplete adapter.

These reads use only Doctor-owned tables. `read_session` supplied by the owner
must give each request/rebuild a consistent read-only snapshot.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pulsegrid_autocomplete import Suggestion, normalize_label, rank_suggestions

from ...errors import ApiError


async def read_revision(session: AsyncSession) -> int:
    row = (
        await session.execute(
            text(
                "SELECT revision FROM directory_revision "
                "WHERE singleton IS TRUE"
            )
        )
    ).scalar_one_or_none()
    if row is None or type(row) is not int or row < 1:
        raise ApiError(503, "dependency_unavailable")
    return row


async def load_snapshot(
    session: AsyncSession,
) -> tuple[int, tuple[Suggestion, ...]]:
    revision = await read_revision(session)
    doctors = (
        await session.execute(
            text(
                "SELECT id,display_name FROM doctors "
                "WHERE active IS TRUE ORDER BY id"
            )
        )
    ).mappings().all()
    specialties = (
        await session.execute(
            text("SELECT id,name FROM specialties ORDER BY id")
        )
    ).mappings().all()
    entries = tuple(
        [
            Suggestion(id=str(row["id"]), kind="doctor", label=row["display_name"])
            for row in doctors
        ]
        + [
            Suggestion(id=str(row["id"]), kind="specialty", label=row["name"])
            for row in specialties
        ]
    )
    return revision, entries


async def prefix_query(
    session: AsyncSession,
    normalized_prefix: str,
    kinds: Sequence[str],
    limit: int,
) -> tuple[Suggestion, ...]:
    """Exact Unicode baseline over current active Doctor-owned directory rows.

    PostgreSQL does not provide the frozen Python NFKC/casefold normalization
    without an extra generated column or extension. Fetch the current owner
    projection and apply the shared normalization here so compatibility and
    Unicode-equivalent prefixes are never omitted by a lossy SQL prefilter.
    """
    selected = set(kinds)
    entries: list[Suggestion] = []
    if "doctor" in selected:
        rows = (
            await session.execute(
                text(
                    "SELECT id,display_name FROM doctors "
                    "WHERE active IS TRUE ORDER BY id"
                )
            )
        ).mappings().all()
        entries.extend(
            Suggestion(id=str(row["id"]), kind="doctor", label=row["display_name"])
            for row in rows
            if normalize_label(row["display_name"]).startswith(normalized_prefix)
        )
    if "specialty" in selected:
        rows = (
            await session.execute(text("SELECT id,name FROM specialties ORDER BY id"))
        ).mappings().all()
        entries.extend(
            Suggestion(id=str(row["id"]), kind="specialty", label=row["name"])
            for row in rows
            if normalize_label(row["name"]).startswith(normalized_prefix)
        )
    return rank_suggestions(entries, limit)


async def filter_visible(
    session: AsyncSession, suggestions: Iterable[Suggestion]
) -> tuple[Suggestion, ...]:
    """Revalidate selected IDs and current names in the Doctor-owned snapshot."""
    selected = tuple(suggestions)
    doctor_ids = sorted(
        {item.id for item in selected if item.kind == "doctor"}, key=int
    )
    specialty_ids = sorted(
        {item.id for item in selected if item.kind == "specialty"}, key=int
    )
    current: dict[tuple[str, str], Suggestion] = {}

    if doctor_ids:
        params = {f"id_{index}": int(value) for index, value in enumerate(doctor_ids)}
        placeholders = ",".join(f":id_{index}" for index in range(len(doctor_ids)))
        rows = (
            await session.execute(
                text(
                    "SELECT id,display_name FROM doctors "
                    f"WHERE active IS TRUE AND id IN ({placeholders})"
                ),
                params,
            )
        ).mappings().all()
        current.update(
            (
                ("doctor", str(row["id"])),
                Suggestion(
                    id=str(row["id"]), kind="doctor", label=row["display_name"]
                ),
            )
            for row in rows
        )

    if specialty_ids:
        params = {f"id_{index}": int(value) for index, value in enumerate(specialty_ids)}
        placeholders = ",".join(f":id_{index}" for index in range(len(specialty_ids)))
        rows = (
            await session.execute(
                text(
                    "SELECT id,name FROM specialties "
                    f"WHERE id IN ({placeholders})"
                ),
                params,
            )
        ).mappings().all()
        current.update(
            (
                ("specialty", str(row["id"])),
                Suggestion(id=str(row["id"]), kind="specialty", label=row["name"]),
            )
            for row in rows
        )

    return tuple(
        current[(item.kind, item.id)]
        for item in selected
        if (item.kind, item.id) in current
    )


def schema_spec() -> dict[str, Any]:
    """Non-executable owner migration handoff; this feature owns no table."""
    return {
        "tables": [],
        "columns": [],
        "indexes": [],
        "constraints": [],
        "preflight": [
            "Doctor migration 0005_phase4_directory_revision must provide "
            "directory_revision(singleton BOOLEAN PRIMARY KEY CHECK(singleton), "
            "revision BIGINT NOT NULL CHECK(revision >= 1)) with one seeded row.",
            "Owner revision changes transactionally on doctors, specialties, "
            "and doctor_specialties inserts, updates, and deletes.",
        ],
        "runtime_grants": [
            {"table": "directory_revision", "privileges": ["SELECT"]},
            {"table": "doctors", "privileges": ["SELECT"]},
            {"table": "specialties", "privileges": ["SELECT"]},
        ],
        "audit_actions": [],
    }


def register_tables(metadata: Any) -> None:
    """Autocomplete owns no ORM table; the coordinator owns revision DDL."""
    del metadata
