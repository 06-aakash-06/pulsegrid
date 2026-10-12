"""Frozen owner ports for the Appointment short-link adapter."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, AsyncContextManager, Protocol


Operation = Callable[[Any, Any], Awaitable[tuple[int, dict[str, Any], int]]]


class Observer(Protocol):
    def increment(
        self, name: str, labels: Mapping[str, str], value: int = 1
    ) -> None: ...

    def observe(
        self, name: str, seconds: float, labels: Mapping[str, str]
    ) -> None: ...

    def gauge(
        self, name: str, value: float, labels: Mapping[str, str]
    ) -> None: ...


class ShortLinksPorts(Protocol):
    """Coordinator adapters; no authentication or transaction policy is local."""

    async def authorize(
        self,
        request: Any,
        roles: tuple[str, ...],
        resource_id: str | None,
        write: bool,
    ) -> Any: ...

    async def allocate_id(self) -> int: ...

    async def command(
        self,
        request: Any,
        principal: Any,
        route_key: str,
        body: dict[str, Any],
        if_match: str | None,
        operation: Operation,
    ) -> Any: ...

    def read_session(self) -> AsyncContextManager[Any]: ...

    @property
    def observer(self) -> Observer: ...

    async def read_workflow(self, session: Any, appointment_id: str) -> dict[str, Any] | None: ...

    async def lock_context(
        self, session: Any, request: Any, principal: Any, appointment_id: str
    ) -> Any: ...

    def stage_effect(
        self,
        session: Any,
        context: Any,
        action: str,
        resource_id: int,
        version: int,
        payload: dict[str, Any],
    ) -> None: ...

    def token_response(self, safe_response: Any, ephemeral_fields: dict[str, Any]) -> Any: ...


class NoopObserver:
    """Observer used by isolated tests and disabled feature wiring."""

    def increment(self, name: str, labels: Mapping[str, str], value: int = 1) -> None:
        return None

    def observe(self, name: str, seconds: float, labels: Mapping[str, str]) -> None:
        return None

    def gauge(self, name: str, value: float, labels: Mapping[str, str]) -> None:
        return None
