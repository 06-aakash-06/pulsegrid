"""Atomic command boundary for mutation, audit, outbox, and POST replay outcome."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .authorization import Principal
from .errors import ApiError, error_payload
from .idempotency import (
    StoredOutcome,
    fingerprint,
    outcome_response,
    replay_if_present,
    save_outcome,
)

CommandResult = tuple[int, dict[str, Any], str | None]


async def execute_idempotent(
    session: AsyncSession,
    request: Request,
    principal: Principal,
    *,
    route_key: str,
    key: str,
    body: dict[str, Any],
    if_match: str | None,
    operation: Callable[[], Awaitable[CommandResult]],
    no_store: bool = False,
) -> JSONResponse:
    scope = "user:" + principal.user_id
    request_hash = fingerprint(body, if_match)
    outcome: StoredOutcome
    async with session.begin():
        replay = await replay_if_present(
            session,
            scope=scope,
            route_key=route_key,
            key=key,
            request_hash=request_hash,
            lock=True,
        )
        if replay is not None:
            outcome = replay
        else:
            try:
                async with session.begin_nested():
                    status_code, response_body, entity_tag = await operation()
            except ApiError as error:
                if error.status_code != 409:
                    raise
                response_body = error_payload(
                    request,
                    error.status_code,
                    error.code,
                    error.message,
                )
                status_code, entity_tag = error.status_code, None
            except IntegrityError as error:
                constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
                codes = {
                    "uq_specialties_slug": "duplicate_slug",
                    "uq_doctors_staff_user_id": "duplicate_mapping",
                    "excl_schedule_intervals_overlap": "schedule_interval_overlap",
                }
                code = codes.get(constraint, "conflict")
                response_body = error_payload(request, 409, code)
                status_code, entity_tag = 409, None
            await save_outcome(
                session,
                scope=scope,
                route_key=route_key,
                key=key,
                request_hash=request_hash,
                status_code=status_code,
                body=response_body,
                entity_tag=entity_tag,
            )
            outcome = StoredOutcome(status_code, response_body, entity_tag)
    response = outcome_response(outcome)
    assert response is not None
    if no_store:
        response.headers["Cache-Control"] = "no-store"
    return response
