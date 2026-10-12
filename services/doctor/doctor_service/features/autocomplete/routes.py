"""Unmounted authenticated Doctor autocomplete route and lifecycle exports."""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any, AsyncContextManager, Literal, Protocol

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from pulsegrid_autocomplete import (
    DEFAULT_RESULT_LIMIT,
    IndexRegistry,
    Suggestion,
    normalize_kinds,
    normalize_prefix,
    rank_suggestions,
    validate_limit,
)
from pulsegrid_autocomplete.errors import AutocompleteInputError
from pulsegrid_autocomplete.lifecycle import refresh_index, refresh_loop
from pulsegrid_autocomplete.metrics import (
    NOOP_METRICS,
    MetricsObserver,
    increment_safely,
    observe_safely,
)

from ...errors import ApiError

OWNER = "doctor"
_AUTHENTICATED_ROLES = (
    "patient", "doctor", "receptionist", "pharmacist", "billing_staff",
    "emergency_staff", "hospital_admin", "ops",
)
_ALLOWED_KINDS = ("doctor", "specialty")


class SuggestionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Literal["doctor", "specialty"]
    label: str


class SuggestionPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[SuggestionView]
    index_version: int | None = Field(default=None, ge=1, le=9_007_199_254_740_991)
    source: Literal["trie", "database"]


class OwnerPorts(Protocol):
    index_registry: IndexRegistry
    observer: MetricsObserver

    def read_session(self) -> AsyncContextManager[Any]: ...

    async def authorize(
        self,
        request: Request,
        roles: tuple[str, ...],
        resource_id: str | None,
        write: bool,
    ) -> Any: ...

    async def read_revision(self, session: Any) -> int: ...

    async def load_snapshot(
        self, session: Any
    ) -> tuple[int, Sequence[Suggestion]]: ...

    async def prefix_query(
        self, session: Any, normalized_prefix: str, kinds: Sequence[str], limit: int
    ) -> tuple[Suggestion, ...]: ...

    async def filter_visible(
        self, session: Any, suggestions: Sequence[Suggestion]
    ) -> tuple[Suggestion, ...]: ...


def create_router(ports: OwnerPorts) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/api/v1/doctors/autocomplete",
        include_in_schema=True,
        response_model=SuggestionPage,
    )
    async def doctor_autocomplete(request: Request) -> JSONResponse:
        started = time.perf_counter()
        backend = "database"
        outcome = "error"
        observer = getattr(ports, "observer", NOOP_METRICS)
        try:
            # Authentication deliberately precedes all query parsing and search.
            await ports.authorize(
                request,
                roles=_AUTHENTICATED_ROLES,
                resource_id=None,
                write=False,
            )
            normalized_prefix, kinds, limit = _parse_query(request)
            async with ports.read_session() as session:
                revision = _valid_revision(await ports.read_revision(session))
                registry_view = ports.index_registry.view
                snapshot = registry_view.snapshot
                if (
                    registry_view.state == "ok"
                    and snapshot is not None
                    and snapshot.generation == revision
                ):
                    candidates = snapshot.trie.search(
                        normalized_prefix, limit=limit, kinds=kinds
                    )
                    visible = await ports.filter_visible(session, candidates)
                    after_validation = _valid_revision(
                        await ports.read_revision(session)
                    )
                    if (
                        after_validation == revision
                        and _same_suggestions(candidates, visible)
                    ):
                        backend = "trie"
                        items = candidates
                        result = _page(items, revision, "trie")
                        outcome = "empty" if not items else "success"
                        return JSONResponse(result, headers={"Cache-Control": "no-store"})

                items = await ports.prefix_query(
                    session, normalized_prefix, kinds, limit
                )
                items = rank_suggestions(items, limit)
                outcome = "empty" if not items else "success"
                return JSONResponse(
                    _page(items, None, "database"),
                    headers={"Cache-Control": "no-store"},
                )
        except AutocompleteInputError:
            raise ApiError(422, "validation_error") from None
        finally:
            labels = {"owner": OWNER, "outcome": outcome, "backend": backend}
            increment_safely(
                observer,
                "pulsegrid_autocomplete_queries_total",
                labels,
            )
            observe_safely(
                observer,
                "pulsegrid_autocomplete_query_seconds",
                max(0.0, time.perf_counter() - started),
                labels,
            )

    return router


def register_routes(app: FastAPI, ports: OwnerPorts) -> None:
    """Mount only into the supplied app; the production entrypoint is coordinator-owned."""
    app.include_router(create_router(ports))


async def health(ports: OwnerPorts | None = None) -> dict[str, str | None]:
    if ports is None:
        return {"state": "degraded", "reason": "index_registry_not_supplied"}
    return await ports.index_registry.health()


def _parse_query(request: Request) -> tuple[str, tuple[str, ...], int]:
    params = request.query_params
    allowed = {"prefix", "kinds", "limit"}
    if set(params.keys()) - allowed or any(
        len(params.getlist(key)) != 1 for key in params.keys()
    ):
        raise AutocompleteInputError("unknown or repeated query parameter")
    raw_prefix = params.get("prefix")
    if raw_prefix is None:
        raise AutocompleteInputError("prefix is required")
    prefix = normalize_prefix(raw_prefix)

    raw_kinds = params.get("kinds")
    if raw_kinds is None:
        selected = normalize_kinds(_ALLOWED_KINDS)
    else:
        parsed_kinds = raw_kinds.split(",")
        if any(kind not in _ALLOWED_KINDS for kind in parsed_kinds):
            raise AutocompleteInputError("kind is outside the Doctor allowlist")
        selected = normalize_kinds(parsed_kinds)

    raw_limit = params.get("limit")
    if raw_limit is None:
        limit = DEFAULT_RESULT_LIMIT
    elif not raw_limit.isascii() or not raw_limit.isdecimal():
        raise AutocompleteInputError("limit must be a decimal integer")
    else:
        limit = validate_limit(int(raw_limit))
    return prefix, selected, limit


def _same_suggestions(
    expected: Sequence[Suggestion], actual: Sequence[Suggestion]
) -> bool:
    expected_by_id = {(item.kind, item.id): item for item in expected}
    actual_by_id = {(item.kind, item.id): item for item in actual}
    return len(expected_by_id) == len(expected) and expected_by_id == actual_by_id


def _page(
    items: Sequence[Suggestion], index_version: int | None, source: str
) -> dict[str, Any]:
    return {
        "items": [
            {"id": item.id, "kind": item.kind, "label": item.label}
            for item in items
        ],
        "index_version": index_version,
        "source": source,
    }


def _valid_revision(value: int) -> int:
    if type(value) is not int or not 1 <= value <= 9_007_199_254_740_991:
        raise ApiError(503, "dependency_unavailable")
    return value


__all__ = ["create_router", "health", "register_routes", "refresh_index", "refresh_loop"]
