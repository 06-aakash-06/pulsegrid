"""SQL helpers for Doctor-owned profiles, specialties, and proposal history."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .wire import escape_like_prefix


DOCTOR_SELECT = """
SELECT d.id,d.staff_user_id,d.display_name,d.active,d.profile_version,d.version,
       d.created_at,d.updated_at,
       COALESCE((
         SELECT jsonb_agg(jsonb_build_object('id',s.id::text,'name',s.name) ORDER BY s.id)
           FROM doctor_specialties ds JOIN specialties s ON s.id=ds.specialty_id
          WHERE ds.doctor_id=d.id
       ),'[]'::jsonb) AS specialties
  FROM doctors d
"""


async def get_doctor(
    session: AsyncSession, doctor_id: str, *, for_update: bool = False
) -> dict[str, Any] | None:
    query = DOCTOR_SELECT + " WHERE d.id=:doctor_id"
    if for_update:
        query += " FOR UPDATE OF d"
    row = (await session.execute(text(query), {"doctor_id": int(doctor_id)})).mappings().first()
    return dict(row) if row is not None else None


def doctor_profile(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "display_name": row["display_name"],
        "specialties": [
            {"id": str(item["id"]), "name": item["name"]}
            for item in row["specialties"]
        ],
        "active": row["active"],
        "version": row["version"],
    }


def specialty_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "slug": row["slug"],
        "name": row["name"],
        "version": row["version"],
    }


def proposal_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "doctor_id": row["doctor_id"],
        "revision": row["revision"],
        "status": row["status"],
        "timezone": row["timezone"],
        "slot_minutes": row["slot_minutes"],
        "intervals": row["intervals"],
        "conflicts": row["conflicts"],
        "version": row["version"],
    }


async def list_doctors(
    session: AsyncSession,
    *,
    active: bool,
    specialty_id: str | None,
    query: str | None,
    cursor: tuple[datetime, str] | None,
    limit: int,
) -> list[dict[str, Any]]:
    conditions = ["d.active=:active"]
    params: dict[str, Any] = {"active": active, "limit": limit}
    if specialty_id is not None:
        conditions.append(
            "EXISTS (SELECT 1 FROM doctor_specialties ds "
            "WHERE ds.doctor_id=d.id AND ds.specialty_id=:specialty_id)"
        )
        params["specialty_id"] = int(specialty_id)
    if query is not None:
        conditions.append("lower(d.display_name) LIKE :name_prefix ESCAPE '!' ")
        params["name_prefix"] = escape_like_prefix(query)
    if cursor is not None:
        conditions.append(
            "(d.created_at>:cursor_created_at OR "
            "(d.created_at=:cursor_created_at AND d.id>:cursor_id))"
        )
        params["cursor_created_at"], params["cursor_id"] = cursor[0], int(cursor[1])
    query_sql = (
        DOCTOR_SELECT
        + " WHERE "
        + " AND ".join(conditions)
        + " ORDER BY d.created_at,d.id LIMIT :limit"
    )
    rows = (await session.execute(text(query_sql), params)).mappings().all()
    return [dict(row) for row in rows]


async def list_specialties(
    session: AsyncSession,
    *,
    cursor: tuple[datetime, str] | None,
    limit: int,
) -> list[dict[str, Any]]:
    conditions = []
    params: dict[str, Any] = {"limit": limit}
    if cursor is not None:
        conditions.append(
            "(created_at>:cursor_created_at OR "
            "(created_at=:cursor_created_at AND id>:cursor_id))"
        )
        params["cursor_created_at"], params["cursor_id"] = cursor[0], int(cursor[1])
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    rows = (
        await session.execute(
            text(
                "SELECT id,slug,name,version,created_at FROM specialties"
                + where
                + " ORDER BY created_at,id LIMIT :limit"
            ),
            params,
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def list_schedules(
    session: AsyncSession,
    *,
    doctor_id: str,
    cursor: tuple[datetime, str] | None,
    limit: int,
    proposal_id: str | None = None,
    for_update: bool = False,
) -> list[dict[str, Any]]:
    if proposal_id is not None:
        conditions = ["sv.doctor_id=:doctor_id", "sv.id=:proposal_id"]
        params: dict[str, Any] = {
            "doctor_id": int(doctor_id),
            "proposal_id": int(proposal_id),
        }
    else:
        conditions = ["sv.doctor_id=:doctor_id"]
        params = {"doctor_id": int(doctor_id), "limit": limit}
        if cursor is not None:
            conditions.append(
                "(sv.created_at>:cursor_created_at OR "
                "(sv.created_at=:cursor_created_at AND sv.id>:cursor_id))"
            )
            params["cursor_created_at"], params["cursor_id"] = cursor[0], int(cursor[1])
    if proposal_id is None:
        cte_limit = " LIMIT :limit"
    else:
        cte_limit = ""
    lock_clause = " FOR UPDATE OF sv" if for_update and proposal_id is not None else ""
    query = text(
        """WITH selected AS (
             SELECT sv.id,sv.doctor_id,sv.revision,sv.timezone,sv.slot_minutes,
                    sv.status,sv.version,sv.created_at
               FROM schedule_versions sv WHERE """
        + " AND ".join(conditions)
        + " ORDER BY sv.created_at,sv.id"
        + cte_limit
        + lock_clause
        + " ) SELECT s.id,s.doctor_id,s.revision,s.timezone,s.slot_minutes,s.status,s.version,"
        + "s.created_at,si.starts_at,si.ends_at,"
        + "COALESCE(sa.conflicts,'[]'::jsonb) AS conflicts "
        + "FROM selected s LEFT JOIN schedule_intervals si ON si.schedule_version_id=s.id "
        + "LEFT JOIN schedule_acknowledgements sa ON sa.schedule_version_id=s.id "
        + "ORDER BY s.created_at,s.id,si.starts_at"
    )
    rows = (await session.execute(query, params)).mappings().all()
    proposals: list[dict[str, Any]] = []
    by_id: dict[int, dict[str, Any]] = {}
    for row in rows:
        resource_id = row["id"]
        proposal = by_id.get(resource_id)
        if proposal is None:
            proposal = {
                "id": str(resource_id),
                "doctor_id": str(row["doctor_id"]),
                "revision": row["revision"],
                "status": row["status"],
                "timezone": row["timezone"],
                "slot_minutes": row["slot_minutes"],
                "intervals": [],
                "conflicts": [str(value) for value in row["conflicts"]],
                "version": row["version"],
                "created_at": row["created_at"],
            }
            by_id[resource_id] = proposal
            proposals.append(proposal)
        if row["starts_at"] is not None:
            proposal["intervals"].append(
                {"starts_at": row["starts_at"], "ends_at": row["ends_at"]}
            )
    return proposals
