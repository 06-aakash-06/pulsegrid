"""Patient profile, account-management and private reference APIs."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import date, datetime, timezone
from typing import Generic, Literal, TypeVar

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import and_, delete, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.exc import IntegrityError

from .authentication import new_id, now
from .authorization import (
    Principal,
    authenticated_user,
    bearer,
    valid_id,
)
from .constants import API_PREFIX
from .database import get_database_session
from .errors import APIError
from .models import (
    outbox_events,
    patient_profiles,
    refresh_sessions,
    role_assignments,
    users,
)

Role = Literal[
    "patient",
    "doctor",
    "receptionist",
    "pharmacist",
    "billing_staff",
    "emergency_staff",
    "hospital_admin",
    "ops",
]
AccountState = Literal["active", "disabled"]
MAX_VERSION = 9007199254740991
ADMIN_LOCK_KEY = 6077960308841371261
_HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class ProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, strict=True, max_length=200)
    date_of_birth: date | None = None
    synthetic_contact: str | None = Field(default=None, strict=True, max_length=256)

    @field_validator("display_name", mode="before")
    @classmethod
    def name(cls, value):
        if value is None:
            raise ValueError("Display name must be a nonempty name")
        if not isinstance(value, str):
            raise ValueError("Display name must be text")
        value = value.strip()
        if not value or len(value) > 200:
            raise ValueError("Display name must contain 1 to 200 characters")
        return value

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def wire_date(cls, value):
        if value is None or type(value) is date:
            return value
        if (
            not isinstance(value, str)
            or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value)
        ):
            raise ValueError("Date of birth must use YYYY-MM-DD")
        try:
            return date.fromisoformat(value)
        except ValueError:
            raise ValueError("Date of birth must use YYYY-MM-DD") from None

    @field_validator("date_of_birth")
    @classmethod
    def birth_date(cls, value):
        if value is not None and value > now().date():
            raise ValueError("Date of birth cannot be in the future")
        return value

    @model_validator(mode="after")
    def require_field(self):
        if not self.model_fields_set:
            raise ValueError("At least one profile field is required")
        return self


class UserRolesPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    roles: list[Role] = Field(min_length=1, max_length=8)

    @field_validator("roles")
    @classmethod
    def distinct_roles(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Roles must be distinct")
        return value


class AccountStatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: AccountState
    reason: str = Field(strict=True, min_length=1, max_length=500)

    @field_validator("reason", mode="before")
    @classmethod
    def trimmed_reason(cls, value):
        if not isinstance(value, str):
            raise ValueError("Reason must be text")
        value = value.strip()
        if not value:
            raise ValueError("Reason must be nonempty")
        return value


class PatientProfileResponse(BaseModel):
    id: str
    user_id: str
    display_name: str
    version: int = Field(ge=1, le=MAX_VERSION)
    date_of_birth: date | None = None
    synthetic_contact: str | None = None


class UserViewResponse(BaseModel):
    id: str
    email: str
    display_name: str
    roles: list[Role]
    state: AccountState
    auth_version: int = Field(ge=1, le=MAX_VERSION)
    version: int = Field(ge=1, le=MAX_VERSION)


T = TypeVar("T")


class PageResponse(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None


class PatientStatusResponse(BaseModel):
    patient_id: str
    active: bool
    version: int = Field(ge=1, le=MAX_VERSION)


class StaffStatusResponse(BaseModel):
    user_id: str
    active: bool
    roles: list[Role]
    version: int = Field(ge=1, le=MAX_VERSION)


api_router = APIRouter()
internal_router = APIRouter(tags=["patient-internal"])


def _version(value: int) -> int:
    if type(value) is not int or not 1 <= value <= MAX_VERSION:
        raise APIError(
            500, "internal_error", "A stored resource version is invalid."
        )
    return value


def _path_id(value: str) -> int:
    if not valid_id(value):
        raise APIError(400, "bad_request", "The resource identifier is invalid.")
    return int(value)


def _etag_version(value: str | None) -> int:
    if value is None:
        raise APIError(
            428,
            "precondition_required",
            "If-Match is required for this operation.",
        )
    match = re.fullmatch(r'"([1-9][0-9]*)"', value)
    if not match:
        raise APIError(400, "bad_request", "If-Match must contain one quoted version.")
    if len(match.group(1)) > 16:
        raise APIError(400, "bad_request", "If-Match contains an invalid version.")
    result = int(match.group(1))
    if result > MAX_VERSION:
        raise APIError(400, "bad_request", "If-Match contains an invalid version.")
    return result


def _set_etag(response: Response, version: int) -> None:
    response.headers["ETag"] = f'"{_version(version)}"'
    response.headers["Cache-Control"] = "no-store"


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


async def _load_account(
    session, user_id: int, *, lock: bool = False, write_lock: bool = False
):
    query = select(users).where(users.c.id == user_id)
    if lock:
        # Shared locks stabilize authority reads; writes take the user's row lock.
        query = query.with_for_update(read=not write_lock)
    user = (await session.execute(query)).mappings().first()
    if user is None:
        return None, None, []
    profile = (
        (
            await session.execute(
                select(patient_profiles).where(patient_profiles.c.user_id == user_id)
            )
        )
        .mappings()
        .first()
    )
    roles = list(
        (
            await session.execute(
                select(role_assignments.c.role)
                .where(role_assignments.c.user_id == user_id)
                .order_by(role_assignments.c.role)
            )
        ).scalars()
    )
    return user, profile, roles


async def _current_actor(session, principal: Principal, *, lock: bool = True):
    user, profile, roles = await _load_account(
        session, int(principal.user_id), lock=lock
    )
    if (
        user is None
        or user["account_state"] != "active"
        or user["auth_version"] != principal.auth_version
    ):
        raise HTTPException(403)
    current_roles = set(roles).intersection(principal.roles)
    return user, profile, roles, current_roles


def _require_role(current_roles: set[str], *allowed: str) -> str:
    selected = next((role for role in allowed if role in current_roles), None)
    if selected is None:
        raise HTTPException(403)
    return selected


def _profile_json(profile) -> dict:
    result = {
        "id": str(profile["id"]),
        "user_id": str(profile["user_id"]),
        "display_name": profile["display_name"],
        "version": _version(profile["version"]),
    }
    if profile["date_of_birth"] is not None:
        result["date_of_birth"] = profile["date_of_birth"].isoformat()
    if profile["synthetic_contact"] is not None:
        result["synthetic_contact"] = profile["synthetic_contact"]
    return result


def _user_json(user, profile, roles) -> dict:
    if profile is None:
        raise HTTPException(404)
    return {
        "id": str(user["id"]),
        "email": user["email_normalized"],
        "display_name": profile["display_name"],
        "roles": sorted(roles),
        "state": user["account_state"],
        "auth_version": _version(user["auth_version"]),
        "version": _version(user["version"]),
    }


async def _domain_audit(
    session,
    request: Request,
    action: str,
    *,
    actor_user_id: int | str | None = None,
    actor_type: str = "user",
    resource_user_id: int | str | None = None,
    patient_id: int | str | None = None,
    result: str = "success",
    content_digest: str | None = None,
) -> None:
    metadata = {
        "action": action,
        "result": result,
        "actor_type": actor_type,
        "request_id": str(request.state.request_id),
        "correlation_id": str(request.state.correlation_id),
        "occurred_at": now().isoformat(),
    }
    if actor_user_id is not None:
        metadata["actor_user_id"] = str(actor_user_id)
    if resource_user_id is not None:
        metadata["resource_user_id"] = str(resource_user_id)
    if patient_id is not None:
        metadata["patient_id"] = str(patient_id)
    if content_digest is not None:
        metadata["content_digest"] = content_digest
    for attempt in range(3):
        try:
            async with session.begin_nested():
                await session.execute(
                    text(
                        "SELECT public.patient_append_audit(:entry_id, "
                        "CAST(:metadata AS jsonb))"
                    ),
                    {
                        "entry_id": new_id(),
                        "metadata": json.dumps(
                            metadata, sort_keys=True, separators=(",", ":")
                        ),
                    },
                )
            return
        except IntegrityError as error:
            constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", "")
            if constraint != "uq_audit_entries_entry_id" or attempt == 2:
                raise HTTPException(503) from None
    raise HTTPException(503)


async def _outbox(
    session,
    request: Request,
    *,
    aggregate_type: str,
    aggregate_id: int,
    version: int,
    event_type: str,
    payload: dict,
) -> None:
    for _attempt in range(3):
        event_id = new_id()
        envelope = {
            "event_id": str(event_id),
            "event_type": event_type,
            "schema_version": 1,
            "producer": "patient",
            "occurred_at": now().isoformat(),
            "aggregate_type": aggregate_type,
            "aggregate_id": str(aggregate_id),
            "aggregate_version": version,
            "request_id": str(request.state.request_id),
            "correlation_id": str(request.state.correlation_id),
            "causation_id": None,
            "traceparent": getattr(request.state, "traceparent", None),
            "payload": payload,
        }
        result = await session.execute(
            postgres_insert(outbox_events)
            .values(
                event_id=event_id,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                aggregate_version=version,
                event_type=event_type,
                envelope=envelope,
            )
            .on_conflict_do_nothing(index_elements=[outbox_events.c.event_id])
            .returning(outbox_events.c.event_id)
        )
        if result.scalar_one_or_none() is not None:
            return
    raise HTTPException(503)


async def _insert_role(session, user_id: int, role: str) -> None:
    for _attempt in range(3):
        result = await session.execute(
            postgres_insert(role_assignments)
            .values(id=new_id(), user_id=user_id, role=role)
            .on_conflict_do_nothing(index_elements=[role_assignments.c.id])
            .returning(role_assignments.c.id)
        )
        if result.scalar_one_or_none() is not None:
            return
    raise HTTPException(503)


async def _append_user_action(
    session,
    request: Request,
    *,
    user_id: int,
    version: int,
    state: str,
    action: str,
) -> None:
    await _outbox(
        session,
        request,
        aggregate_type="user",
        aggregate_id=user_id,
        version=version,
        event_type=f"patient.user.{action}.v1",
        payload={"resource_id": str(user_id), "version": version, "state": state},
    )


def _query_values(request: Request, allowed: set[str]) -> dict[str, str]:
    items = list(request.query_params.multi_items())
    keys = [key for key, _ in items]
    if any(key not in allowed for key in keys) or len(keys) != len(set(keys)):
        raise HTTPException(422)
    return dict(items)


def _reject_query(request: Request) -> None:
    if request.query_params:
        raise HTTPException(422)


def _limit(raw: str | None) -> int:
    if raw is None:
        return 20
    if not re.fullmatch(r"[0-9]+", raw):
        raise HTTPException(422)
    value = int(raw)
    if not 1 <= value <= 100:
        raise HTTPException(422)
    return value


def _prefix(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip().lower()
    if not 2 <= len(value) <= 100 or "\x00" in value:
        raise HTTPException(422)
    return value


def _like_prefix(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _filter_hash(scope: dict, filters: dict) -> str:
    canonical = json.dumps(
        {"scope": scope, "filters": filters}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _cursor_datetime(value: str) -> datetime:
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("Invalid cursor timestamp")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("Cursor timestamp must be UTC")
    return parsed.astimezone(timezone.utc)


def _decode_cursor(value: str | None, expected_hash: str):
    if value is None:
        return None
    try:
        if not value or len(value) > 2048 or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("Invalid cursor")
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        if base64.urlsafe_b64encode(raw).decode().rstrip("=") != value:
            raise ValueError("Noncanonical cursor")

        def unique_object(pairs):
            result = {}
            for key, item in pairs:
                if key in result:
                    raise ValueError("Duplicate cursor field")
                result[key] = item
            return result

        payload = json.loads(raw, object_pairs_hook=unique_object)
        if not isinstance(payload, dict) or set(payload) != {
            "created_at",
            "id",
            "filter_hash",
        }:
            raise ValueError("Invalid cursor fields")
        if (
            not valid_id(payload["id"])
            or not isinstance(payload["filter_hash"], str)
            or not _HEX_DIGEST.fullmatch(payload["filter_hash"])
            or payload["filter_hash"] != expected_hash
        ):
            raise ValueError("Cursor filters changed")
        return _cursor_datetime(payload["created_at"]), int(payload["id"])
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        raise APIError(400, "bad_request", "The pagination cursor is invalid.") from None


def _encode_cursor(created_at: datetime, resource_id: int, filter_hash: str) -> str:
    if created_at.tzinfo is None:
        raise APIError(500, "internal_error", "A stored timestamp is invalid.")
    payload = {
        "created_at": created_at.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z"),
        "id": str(resource_id),
        "filter_hash": filter_hash,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _after_cursor(statement, table, cursor):
    if cursor is None:
        return statement
    created_at, resource_id = cursor
    return statement.where(
        or_(
            table.c.created_at > created_at,
            and_(table.c.created_at == created_at, table.c.id > resource_id),
        )
    )


def _check_last_admin(
    actor_user_id: str,
    target_user_id: int,
    current_state: str,
    current_roles: list[str],
    *,
    next_state: str | None = None,
    next_roles: list[str] | None = None,
) -> bool:
    if actor_user_id == str(target_user_id) and (
        ("hospital_admin" in current_roles and next_roles is not None and "hospital_admin" not in next_roles)
        or (next_state == "disabled")
    ):
        raise APIError(
            409,
            "last_admin",
            "This account cannot remove its own administrator access or disable itself.",
        )
    return (
        current_state == "active"
        and "hospital_admin" in current_roles
        and (
            (next_state == "disabled")
            or (next_roles is not None and "hospital_admin" not in next_roles)
        )
    )


async def _ensure_not_last_active_admin(session) -> None:
    count = await session.scalar(
        select(func.count())
        .select_from(
            users.join(role_assignments, role_assignments.c.user_id == users.c.id)
        )
        .where(
            users.c.account_state == "active",
            role_assignments.c.role == "hospital_admin",
        )
    )
    if count <= 1:
        raise APIError(
            409,
            "last_admin",
            "The last active hospital administrator cannot be removed or disabled.",
        )


@api_router.get(
    API_PREFIX,
    response_model=PageResponse[PatientProfileResponse],
    response_model_exclude_unset=True,
    tags=["patients"],
)
async def list_patients(
    request: Request,
    response: Response,
    principal: Principal = Depends(authenticated_user),
    session=Depends(get_database_session),
):
    query = _query_values(request, {"q", "cursor", "limit"})
    prefix = _prefix(query.get("q"))
    limit = _limit(query.get("limit"))
    filters = {"q": prefix}
    async with session.begin():
        _, _, _, current_roles = await _current_actor(session, principal)
        selected_role = _require_role(current_roles, "hospital_admin", "receptionist")
        filter_hash = _filter_hash(
            {
                "route": "patients",
                "user_id": principal.user_id,
                "role": selected_role,
            },
            filters,
        )
        cursor = _decode_cursor(query.get("cursor"), filter_hash)
        statement = select(patient_profiles)
        if prefix is not None:
            statement = statement.where(
                func.lower(patient_profiles.c.display_name).like(
                    _like_prefix(prefix), escape="\\"
                )
            )
        statement = _after_cursor(statement, patient_profiles, cursor).order_by(
            patient_profiles.c.created_at, patient_profiles.c.id
        ).limit(limit + 1)
        rows = (await session.execute(statement)).mappings().all()
        more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = (
            _encode_cursor(rows[-1]["created_at"], rows[-1]["id"], filter_hash)
            if more and rows
            else None
        )
        await _domain_audit(
            session,
            request,
            "patient.profile.list",
            actor_user_id=principal.user_id,
            content_digest=filter_hash,
        )
    _no_store(response)
    return {"items": [_profile_json(row) for row in rows], "next_cursor": next_cursor}


@api_router.get(
    API_PREFIX + "/users",
    response_model=PageResponse[UserViewResponse],
    response_model_exclude_unset=True,
    tags=["patient-users"],
)
async def list_users(
    request: Request,
    response: Response,
    principal: Principal = Depends(authenticated_user),
    session=Depends(get_database_session),
):
    query = _query_values(request, {"role", "state", "q", "cursor", "limit"})
    role = query.get("role")
    state = query.get("state")
    if role is not None and role not in Role.__args__:
        raise HTTPException(422)
    if state is not None and state not in ("active", "disabled"):
        raise HTTPException(422)
    prefix = _prefix(query.get("q"))
    limit = _limit(query.get("limit"))
    filters = {"role": role, "state": state, "q": prefix}
    async with session.begin():
        _, _, _, current_roles = await _current_actor(session, principal)
        _require_role(current_roles, "hospital_admin")
        filter_hash = _filter_hash(
            {"route": "patient-users", "user_id": principal.user_id}, filters
        )
        cursor = _decode_cursor(query.get("cursor"), filter_hash)
        statement = select(
            users.c.id,
            users.c.email_normalized,
            users.c.account_state,
            users.c.auth_version,
            users.c.version,
            users.c.created_at,
            patient_profiles.c.id.label("patient_id"),
            patient_profiles.c.display_name,
        ).select_from(users.join(patient_profiles, patient_profiles.c.user_id == users.c.id))
        if role is not None:
            statement = statement.where(
                users.c.id.in_(
                    select(role_assignments.c.user_id).where(
                        role_assignments.c.role == role
                    )
                )
            )
        if state is not None:
            statement = statement.where(users.c.account_state == state)
        if prefix is not None:
            pattern = _like_prefix(prefix)
            statement = statement.where(
                or_(
                    users.c.email_normalized.like(pattern, escape="\\"),
                    func.lower(patient_profiles.c.display_name).like(
                        pattern, escape="\\"
                    ),
                )
            )
        if cursor is not None:
            created_at, user_id = cursor
            statement = statement.where(
                or_(
                    users.c.created_at > created_at,
                    and_(users.c.created_at == created_at, users.c.id > user_id),
                )
            )
        statement = statement.order_by(users.c.created_at, users.c.id).limit(limit + 1)
        rows = (await session.execute(statement)).mappings().all()
        more = len(rows) > limit
        rows = rows[:limit]
        user_ids = [row["id"] for row in rows]
        roles_by_user: dict[int, list[str]] = {user_id: [] for user_id in user_ids}
        if user_ids:
            role_rows = await session.execute(
                select(role_assignments.c.user_id, role_assignments.c.role)
                .where(role_assignments.c.user_id.in_(user_ids))
                .order_by(role_assignments.c.role)
            )
            for user_id, assigned_role in role_rows:
                roles_by_user[user_id].append(assigned_role)
        items = [
            {
                "id": str(row["id"]),
                "email": row["email_normalized"],
                "display_name": row["display_name"],
                "roles": roles_by_user[row["id"]],
                "state": row["account_state"],
                "auth_version": _version(row["auth_version"]),
                "version": _version(row["version"]),
            }
            for row in rows
        ]
        next_cursor = (
            _encode_cursor(rows[-1]["created_at"], rows[-1]["id"], filter_hash)
            if more and rows
            else None
        )
        await _domain_audit(
            session,
            request,
            "patient.user.list",
            actor_user_id=principal.user_id,
            content_digest=filter_hash,
        )
    _no_store(response)
    return {"items": items, "next_cursor": next_cursor}


@api_router.get(
    API_PREFIX + "/users/{user_id}",
    response_model=UserViewResponse,
    response_model_exclude_unset=True,
    tags=["patient-users"],
)
async def get_user(
    user_id: str,
    request: Request,
    response: Response,
    principal: Principal = Depends(authenticated_user),
    session=Depends(get_database_session),
):
    _reject_query(request)
    target_id = _path_id(user_id)
    async with session.begin():
        _, _, _, current_roles = await _current_actor(session, principal)
        _require_role(current_roles, "hospital_admin")
        user, profile, roles = await _load_account(session, target_id, lock=True)
        if user is None or profile is None:
            raise HTTPException(404)
        await _domain_audit(
            session,
            request,
            "patient.user.read",
            actor_user_id=principal.user_id,
            resource_user_id=target_id,
            patient_id=profile["id"],
        )
        result = _user_json(user, profile, roles)
    _set_etag(response, result["version"])
    return result


@api_router.get(
    API_PREFIX + "/{patient_id}",
    response_model=PatientProfileResponse,
    response_model_exclude_unset=True,
    tags=["patients"],
)
async def get_patient(
    patient_id: str,
    request: Request,
    response: Response,
    principal: Principal = Depends(authenticated_user),
    session=Depends(get_database_session),
):
    _reject_query(request)
    target_id = _path_id(patient_id)
    async with session.begin():
        _, _, _, current_roles = await _current_actor(session, principal)
        staff_access = bool(
            current_roles.intersection({"receptionist", "hospital_admin"})
        )
        patient_self = "patient" in current_roles
        if not staff_access and not patient_self:
            raise HTTPException(403)
        if not staff_access and principal.patient_id != patient_id:
            raise HTTPException(404)
        profile = (
            (
                await session.execute(
                    select(patient_profiles).where(patient_profiles.c.id == target_id)
                )
            )
            .mappings()
            .first()
        )
        if profile is None:
            raise HTTPException(404)
        if patient_self and not staff_access and str(profile["user_id"]) != principal.user_id:
            raise HTTPException(404)
        await _domain_audit(
            session,
            request,
            "patient.profile.read",
            actor_user_id=principal.user_id,
            resource_user_id=profile["user_id"],
            patient_id=profile["id"],
        )
        result = _profile_json(profile)
    _set_etag(response, result["version"])
    return result


async def _patch_profile(
    *,
    patient_id: int,
    patch: ProfilePatch,
    request: Request,
    response: Response,
    principal: Principal,
    session,
    if_match: str | None,
    self_service: bool,
):
    async with session.begin():
        _, actor_profile, _, current_roles = await _current_actor(session, principal)
        if self_service:
            _require_role(current_roles, "patient")
            if principal.patient_id is None or principal.patient_id != str(patient_id):
                raise HTTPException(404)
        else:
            _require_role(current_roles, "hospital_admin", "receptionist")
        expected = _etag_version(if_match)
        profile = (
            (
                await session.execute(
                    select(patient_profiles)
                    .where(patient_profiles.c.id == patient_id)
                    .with_for_update()
                )
            )
            .mappings()
            .first()
        )
        if profile is None:
            raise HTTPException(404)
        if self_service and (
            actor_profile is None or actor_profile["id"] != patient_id
        ):
            raise HTTPException(404)
        if profile["version"] != expected:
            raise HTTPException(412)
        new_version = profile["version"] + 1
        _version(new_version)
        values = {
            name: getattr(patch, name)
            for name in patch.model_fields_set
        }
        values.update(version=new_version, updated_at=now())
        await session.execute(
            update(patient_profiles)
            .where(patient_profiles.c.id == patient_id)
            .values(**values)
        )
        updated = (
            (
                await session.execute(
                    select(patient_profiles).where(patient_profiles.c.id == patient_id)
                )
            )
            .mappings()
            .one()
        )
        await _domain_audit(
            session,
            request,
            "patient.profile.updated",
            actor_user_id=principal.user_id,
            resource_user_id=updated["user_id"],
            patient_id=patient_id,
        )
        await _outbox(
            session,
            request,
            aggregate_type="patient",
            aggregate_id=patient_id,
            version=new_version,
            event_type="patient.profile.updated.v1",
            payload={"resource_id": str(patient_id), "version": new_version},
        )
        result = _profile_json(updated)
    _set_etag(response, result["version"])
    return result


@api_router.patch(
    API_PREFIX + "/me",
    response_model=PatientProfileResponse,
    response_model_exclude_unset=True,
    tags=["patients"],
)
async def patch_me(
    patch: ProfilePatch,
    request: Request,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    principal: Principal = Depends(authenticated_user),
    session=Depends(get_database_session),
):
    _reject_query(request)
    if principal.patient_id is None:
        raise HTTPException(403)
    return await _patch_profile(
        patient_id=_path_id(principal.patient_id),
        patch=patch,
        request=request,
        response=response,
        principal=principal,
        session=session,
        if_match=if_match,
        self_service=True,
    )


@api_router.patch(
    API_PREFIX + "/users/{user_id}/roles",
    response_model=UserViewResponse,
    response_model_exclude_unset=True,
    tags=["patient-users"],
)
async def patch_user_roles(
    user_id: str,
    patch: UserRolesPatch,
    request: Request,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    principal: Principal = Depends(authenticated_user),
    session=Depends(get_database_session),
):
    _reject_query(request)
    target_id = _path_id(user_id)
    expected = _etag_version(if_match)
    next_roles = sorted(patch.roles)
    async with session.begin():
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": ADMIN_LOCK_KEY}
        )
        _, _, _, current_actor_roles = await _current_actor(session, principal)
        _require_role(current_actor_roles, "hospital_admin")
        user, profile, current_roles = await _load_account(
            session, target_id, lock=True, write_lock=True
        )
        if user is None or profile is None:
            raise HTTPException(404)
        if user["version"] != expected:
            raise HTTPException(412)
        removes_active_admin = _check_last_admin(
            principal.user_id,
            target_id,
            user["account_state"],
            current_roles,
            next_roles=next_roles,
        )
        changed = set(current_roles) != set(next_roles)
        new_version = _version(user["version"] + 1) if changed else user["version"]
        new_auth_version = (
            _version(user["auth_version"] + 1) if changed else user["auth_version"]
        )
        if changed:
            if removes_active_admin:
                await _ensure_not_last_active_admin(session)
            to_remove = set(current_roles) - set(next_roles)
            to_add = set(next_roles) - set(current_roles)
            if to_remove:
                await session.execute(
                    delete(role_assignments).where(
                        role_assignments.c.user_id == target_id,
                        role_assignments.c.role.in_(to_remove),
                    )
                )
            for assigned_role in sorted(to_add):
                await _insert_role(session, target_id, assigned_role)
            await session.execute(
                update(users)
                .where(users.c.id == target_id)
                .values(
                    version=new_version,
                    auth_version=new_auth_version,
                    updated_at=now(),
                )
            )
            await session.execute(
                update(refresh_sessions)
                .where(
                    refresh_sessions.c.user_id == target_id,
                    refresh_sessions.c.revoked_at.is_(None),
                )
                .values(revoked_at=now(), updated_at=now())
            )
            await _append_user_action(
                session,
                request,
                user_id=target_id,
                version=new_version,
                state=user["account_state"],
                action="roles_changed",
            )
        await _domain_audit(
            session,
            request,
            "patient.user.roles_changed",
            actor_user_id=principal.user_id,
            resource_user_id=target_id,
            patient_id=profile["id"],
            content_digest=hashlib.sha256(
                json.dumps(next_roles, separators=(",", ":")).encode()
            ).hexdigest(),
        )
        updated_user, updated_profile, updated_roles = await _load_account(
            session, target_id
        )
        result = _user_json(updated_user, updated_profile, updated_roles)
    _set_etag(response, result["version"])
    return result


@api_router.patch(
    API_PREFIX + "/users/{user_id}/account-state",
    response_model=UserViewResponse,
    response_model_exclude_unset=True,
    tags=["patient-users"],
)
async def patch_user_state(
    user_id: str,
    patch: AccountStatePatch,
    request: Request,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    principal: Principal = Depends(authenticated_user),
    session=Depends(get_database_session),
):
    _reject_query(request)
    target_id = _path_id(user_id)
    expected = _etag_version(if_match)
    async with session.begin():
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": ADMIN_LOCK_KEY}
        )
        _, _, _, current_actor_roles = await _current_actor(session, principal)
        _require_role(current_actor_roles, "hospital_admin")
        user, profile, current_roles = await _load_account(
            session, target_id, lock=True, write_lock=True
        )
        if user is None or profile is None:
            raise HTTPException(404)
        if user["version"] != expected:
            raise HTTPException(412)
        removes_active_admin = _check_last_admin(
            principal.user_id,
            target_id,
            user["account_state"],
            current_roles,
            next_state=patch.state,
        )
        changed = user["account_state"] != patch.state
        new_version = _version(user["version"] + 1) if changed else user["version"]
        new_auth_version = (
            _version(user["auth_version"] + 1) if changed else user["auth_version"]
        )
        if changed:
            if removes_active_admin:
                await _ensure_not_last_active_admin(session)
            await session.execute(
                update(users)
                .where(users.c.id == target_id)
                .values(
                    account_state=patch.state,
                    version=new_version,
                    auth_version=new_auth_version,
                    updated_at=now(),
                )
            )
            await session.execute(
                update(refresh_sessions)
                .where(
                    refresh_sessions.c.user_id == target_id,
                    refresh_sessions.c.revoked_at.is_(None),
                )
                .values(revoked_at=now(), updated_at=now())
            )
            await _append_user_action(
                session,
                request,
                user_id=target_id,
                version=new_version,
                state=patch.state,
                action="account_state_changed",
            )
        await _domain_audit(
            session,
            request,
            "patient.user.account_state_changed",
            actor_user_id=principal.user_id,
            resource_user_id=target_id,
            patient_id=profile["id"],
            content_digest=hashlib.sha256(patch.reason.encode()).hexdigest(),
        )
        updated_user, updated_profile, updated_roles = await _load_account(
            session, target_id
        )
        result = _user_json(updated_user, updated_profile, updated_roles)
    _set_etag(response, result["version"])
    return result


@api_router.patch(
    API_PREFIX + "/{patient_id}",
    response_model=PatientProfileResponse,
    response_model_exclude_unset=True,
    tags=["patients"],
)
async def patch_patient(
    patient_id: str,
    patch: ProfilePatch,
    request: Request,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    principal: Principal = Depends(authenticated_user),
    session=Depends(get_database_session),
):
    _reject_query(request)
    return await _patch_profile(
        patient_id=_path_id(patient_id),
        patch=patch,
        request=request,
        response=response,
        principal=principal,
        session=session,
        if_match=if_match,
        self_service=False,
    )


async def _private_identity(request: Request, scope: str, allowed_callers: set[str]):
    verifier = request.app.state.auth_verifier
    caller = verifier.service(bearer(request), scope)
    if caller not in allowed_callers:
        raise HTTPException(403)
    principal = verifier.user(bearer(request, "X-Delegated-Authorization"))
    return caller, principal


@internal_router.get(
    "/internal/v1/patients/{patient_id}/status",
    response_model=PatientStatusResponse,
    tags=["patients-internal"],
)
async def patient_status(
    patient_id: str,
    request: Request,
    response: Response,
    session=Depends(get_database_session),
):
    _reject_query(request)
    target_id = _path_id(patient_id)
    caller, principal = await _private_identity(
        request,
        "patients:status",
        {"appointment", "records", "emergency"},
    )
    async with session.begin():
        _, actor_profile, _, current_roles = await _current_actor(session, principal)
        is_self = (
            "patient" in current_roles
            and actor_profile is not None
            and actor_profile["id"] == target_id
            and principal.patient_id == patient_id
        )
        may_validate_reference = bool(
            current_roles.intersection(
                {"receptionist", "doctor", "emergency_staff"}
            )
        )
        if not is_self and not may_validate_reference:
            raise HTTPException(403)
        target = (
            (
                await session.execute(
                    select(
                        patient_profiles,
                        users.c.account_state,
                    )
                    .select_from(
                        patient_profiles.join(
                            users, users.c.id == patient_profiles.c.user_id
                        )
                    )
                    .where(patient_profiles.c.id == target_id)
                    .with_for_update(read=True, of=users)
                )
            )
            .mappings()
            .first()
        )
        if target is None:
            raise APIError(
                422,
                "invalid_reference",
                "The patient reference is invalid.",
            )
        has_patient_role = await session.scalar(
            select(role_assignments.c.id).where(
                role_assignments.c.user_id == target["user_id"],
                role_assignments.c.role == "patient",
            )
        )
        active = target["account_state"] == "active" and has_patient_role is not None
        await _domain_audit(
            session,
            request,
            "patient.patient.status_read",
            actor_user_id=principal.user_id,
            resource_user_id=target["user_id"],
            patient_id=target_id,
        )
        version = _version(target["version"])
    _set_etag(response, version)
    return {"patient_id": str(target_id), "active": active, "version": version}


@internal_router.get(
    "/internal/v1/users/{user_id}/staff-status",
    response_model=StaffStatusResponse,
    tags=["patients-internal"],
)
async def staff_status(
    user_id: str,
    request: Request,
    response: Response,
    session=Depends(get_database_session),
):
    _reject_query(request)
    target_id = _path_id(user_id)
    caller, principal = await _private_identity(
        request, "users:staff-status", {"doctor", "records"}
    )
    async with session.begin():
        _, actor_profile, _, current_roles = await _current_actor(session, principal)
        if caller == "doctor":
            _require_role(current_roles, "hospital_admin")
        elif not (
            target_id == int(principal.user_id)
            and "patient" in current_roles
            and actor_profile is not None
            and principal.patient_id == str(actor_profile["id"])
        ):
            raise HTTPException(403)
        user, profile, roles = await _load_account(session, target_id, lock=True)
        if user is None or profile is None:
            raise APIError(422, "invalid_reference", "The user reference is invalid.")
        await _domain_audit(
            session,
            request,
            "patient.user.staff_status_read",
            actor_user_id=principal.user_id,
            resource_user_id=target_id,
            patient_id=profile["id"],
        )
        version = _version(user["version"])
    _set_etag(response, version)
    return {
        "user_id": str(target_id),
        "active": user["account_state"] == "active",
        "roles": roles,
        "version": version,
    }


class WaitlistEligibilityRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    patient_ids:list[str]=Field(min_length=1,max_length=50)

    @field_validator('patient_ids')
    @classmethod
    def distinct_ids(cls,values):
        if len(set(values))!=len(values) or any(not valid_id(v) for v in values):
            raise ValueError('Distinct decimal IDs required')
        return values


@internal_router.post('/internal/v1/patients/waitlist-eligibility')
async def waitlist_eligibility(body:WaitlistEligibilityRequest,request:Request,
                              session=Depends(get_database_session)):
    _reject_query(request)
    if request.app.state.auth_verifier.service(bearer(request),'patients:waitlist-eligibility')!='appointment':
        raise HTTPException(403)
    ids=[int(value) for value in body.patient_ids]
    async with session.begin():
        patient_role=select(role_assignments.c.id).where(
            role_assignments.c.user_id==users.c.id,role_assignments.c.role=='patient').exists()
        rows=(await session.execute(select(patient_profiles.c.id,users.c.account_state,users.c.version,
            patient_role.label('patient_role')).join(users,users.c.id==patient_profiles.c.user_id)
            .where(patient_profiles.c.id.in_(ids)))).mappings().all()
        by_id={r['id']:r for r in rows}
        items=[dict(patient_id=str(pid),active=bool(pid in by_id and by_id[pid]['account_state']=='active'
            and by_id[pid]['patient_role']),version=by_id[pid]['version'] if pid in by_id else 0) for pid in ids]
        await _domain_audit(session,request,'patient.waitlist.eligibility_read',actor_type='service:appointment')
    from fastapi.responses import JSONResponse
    return JSONResponse({'items':items,'observed_at':now().isoformat()},headers={'Cache-Control':'no-store'})
