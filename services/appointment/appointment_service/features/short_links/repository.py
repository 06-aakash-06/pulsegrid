"""Appointment-owned PostgreSQL repository for digest-only short links."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError

from ... import models
from .schema_spec import table_for


class ShortLinkRepository:
    """Small async repository; transaction and lock ownership stay with caller."""

    def __init__(self, session: Any):
        self.session = session
        self.links = table_for()

    async def database_now(self) -> datetime:
        return (await self.session.execute(select(func.clock_timestamp()))).scalar_one()

    async def by_digest(self, token_hash: str) -> dict[str, Any] | None:
        row = (
            await self.session.execute(
                select(self.links).where(self.links.c.token_hash == token_hash)
            )
        ).mappings().first()
        return dict(row) if row is not None else None

    async def by_id(self, link_id: int) -> dict[str, Any] | None:
        row = (
            await self.session.execute(select(self.links).where(self.links.c.id == link_id))
        ).mappings().first()
        return dict(row) if row is not None else None

    async def booking(self, appointment_id: int) -> dict[str, Any] | None:
        row = (
            await self.session.execute(
                select(models.appointments).where(models.appointments.c.id == appointment_id)
            )
        ).mappings().first()
        return dict(row) if row is not None else None

    async def has_active_hold(self, appointment_id: int) -> bool:
        value = (
            await self.session.execute(
                select(models.clinical_holds.c.appointment_id).where(
                    models.clinical_holds.c.appointment_id == appointment_id,
                    models.clinical_holds.c.state == "active",
                )
            )
        ).first()
        return value is not None

    async def insert(self, values: dict[str, Any]) -> None:
        """Insert inside a caller-owned nested transaction for hash collision retry."""
        async with self.session.begin_nested():
            await self.session.execute(insert(self.links).values(**values))

    async def revoke_open_for_appointment(
        self, appointment_id: int, now: datetime, purpose: str | None = None
    ) -> list[dict[str, Any]]:
        conditions = [
            self.links.c.appointment_id == appointment_id,
            self.links.c.revoked_at.is_(None),
        ]
        if purpose is not None:
            conditions.append(self.links.c.purpose == purpose)
        rows = (
            await self.session.execute(
                update(self.links)
                .where(*conditions)
                .values(
                    revoked_at=now,
                    version=self.links.c.version + 1,
                    updated_at=now,
                )
                .returning(
                    self.links.c.id,
                    self.links.c.appointment_id,
                    self.links.c.purpose,
                    self.links.c.version,
                )
            )
        ).mappings().all()
        return [dict(row) for row in rows]

    async def revoke_one(
        self, link_id: int, appointment_id: int, expected_version: int, now: datetime
    ) -> dict[str, Any] | None:
        row = (
            await self.session.execute(
                update(self.links)
                .where(
                    self.links.c.id == link_id,
                    self.links.c.appointment_id == appointment_id,
                    self.links.c.version == expected_version,
                    self.links.c.revoked_at.is_(None),
                )
                .values(
                    revoked_at=now,
                    version=self.links.c.version + 1,
                    updated_at=now,
                )
                .returning(self.links)
            )
        ).mappings().first()
        return dict(row) if row is not None else None

    async def expired_or_revoked_by_digest(self, token_hash: str) -> tuple[dict[str, Any] | None, datetime]:
        """Read link and PostgreSQL time in one statement for resolution checks."""
        row = (
            await self.session.execute(
                select(self.links, func.clock_timestamp().label("database_now")).where(
                    self.links.c.token_hash == token_hash
                )
            )
        ).mappings().first()
        if row is None:
            return None, await self.database_now()
        value = dict(row)
        database_now = value.pop("database_now")
        return value, database_now


def is_token_hash_collision(exc: IntegrityError) -> bool:
    """Return true only for the unique alias digest constraint."""
    original = getattr(exc, "orig", None)
    sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    constraint = getattr(getattr(original, "diag", None), "constraint_name", None)
    return sqlstate == "23505" and constraint == "uq_short_links_token_hash"
