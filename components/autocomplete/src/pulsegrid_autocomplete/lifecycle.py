"""Revision-checked immutable index construction and atomic publication."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any, AsyncContextManager, Protocol

from .errors import IndexTooLarge
from .metrics import (
    NOOP_METRICS,
    MetricsObserver,
    gauge_safely,
    increment_safely,
    observe_safely,
)
from .trie import IndexSnapshot, Suggestion, Trie

MAX_REVISION = 9_007_199_254_740_991
DEFAULT_REFRESH_INTERVAL_SECONDS = 5.0
MAX_REVISION_RETRIES = 2


@dataclass(frozen=True, slots=True)
class IndexLimits:
    max_entries: int = 100_000
    max_estimated_bytes: int = 64 * 1024 * 1024

    def __post_init__(self) -> None:
        if type(self.max_entries) is not int or self.max_entries < 1:
            raise ValueError("max_entries must be a positive integer")
        if type(self.max_estimated_bytes) is not int or self.max_estimated_bytes < 1024:
            raise ValueError("max_estimated_bytes must be at least 1024")


DEFAULT_INDEX_LIMITS = IndexLimits()


@dataclass(frozen=True, slots=True)
class RegistryView:
    snapshot: IndexSnapshot | None
    state: str
    reason: str | None


class IndexRegistry:
    """An atomic reference to one immutable per-process owner index."""

    __slots__ = ("_view", "refresh_lock")

    def __init__(self) -> None:
        self._view = RegistryView(None, "degraded", "index_unavailable")
        self.refresh_lock = asyncio.Lock()

    @property
    def view(self) -> RegistryView:
        return self._view

    @property
    def snapshot(self) -> IndexSnapshot | None:
        return self._view.snapshot

    def publish(self, snapshot: IndexSnapshot) -> None:
        current = self._view.snapshot
        if current is not None and snapshot.generation < current.generation:
            raise ValueError("cannot publish an older owner revision")
        self._view = RegistryView(snapshot, "ok", None)

    def mark_degraded(self, reason: str) -> None:
        if not reason:
            reason = "index_unavailable"
        self._view = RegistryView(self._view.snapshot, "degraded", reason)

    def disable(self, reason: str | None = None) -> None:
        self._view = RegistryView(None, "disabled", reason)

    async def health(self) -> dict[str, str | None]:
        view = self._view
        return {"state": view.state, "reason": view.reason}


class RefreshPorts(Protocol):
    index_registry: IndexRegistry
    index_limits: IndexLimits
    observer: MetricsObserver

    def read_session(self) -> AsyncContextManager[Any]: ...

    async def read_revision(self, session: Any) -> int: ...

    async def load_snapshot(
        self, session: Any
    ) -> tuple[int, Iterable[Suggestion]]: ...


async def rebuild(
    owner_snapshot_loader: Callable[[], Awaitable[tuple[int, Iterable[Suggestion]]]],
    *,
    limits: IndexLimits = DEFAULT_INDEX_LIMITS,
) -> IndexSnapshot:
    """Build and validate an immutable snapshot from one owner-owned snapshot."""
    generation, entries = await owner_snapshot_loader()
    return await asyncio.to_thread(build_snapshot, generation, entries, limits)


def build_snapshot(
    generation: int,
    entries: Iterable[Suggestion],
    limits: IndexLimits = DEFAULT_INDEX_LIMITS,
) -> IndexSnapshot:
    """Synchronous builder used in a worker thread, before atomic publication."""
    if type(generation) is not int or not 1 <= generation <= MAX_REVISION:
        raise ValueError("owner revision must be a positive JSON-safe integer")
    trie = Trie()
    seen: dict[tuple[str, str], Suggestion] = {}
    for suggestion in entries:
        identity = (suggestion.kind, suggestion.id)
        previous = seen.get(identity)
        if previous is not None:
            if previous != suggestion:
                raise ValueError("owner snapshot contains conflicting duplicate identities")
            continue
        seen[identity] = suggestion
        previous_count = trie.entry_count
        trie.insert(suggestion)
        if trie.entry_count != previous_count and trie.entry_count > limits.max_entries:
            estimated = trie.estimated_bytes()
            raise IndexTooLarge(
                "entry_limit_exceeded",
                entries=trie.entry_count,
                nodes=trie.node_count,
                estimated_bytes=estimated,
            )
    estimated = trie.estimated_bytes()
    if estimated > limits.max_estimated_bytes:
        raise IndexTooLarge(
            "memory_limit_exceeded",
            entries=trie.entry_count,
            nodes=trie.node_count,
            estimated_bytes=estimated,
        )
    return IndexSnapshot(generation=generation, trie=trie, _estimated_bytes=estimated)


async def refresh_index(ports: RefreshPorts) -> None:
    """Load, build off the request path, recheck revision, and publish atomically.

    Two retries are allowed after the initial attempt. On a persistent owner
    revision race, size overflow, or owner read error, callers keep serving the
    existing owner database fallback and never serve the stale snapshot.
    """
    registry = ports.index_registry
    observer = getattr(ports, "observer", NOOP_METRICS)
    owner = str(getattr(ports, "owner", "unknown"))
    started = time.perf_counter()

    async with registry.refresh_lock:
        for attempt in range(MAX_REVISION_RETRIES + 1):
            try:
                async with ports.read_session() as session:
                    before = _valid_revision(await ports.read_revision(session))
                    loaded_revision, entries = await ports.load_snapshot(session)
                    loaded_revision = _valid_revision(loaded_revision)
                    entries = tuple(entries)
                    after = _valid_revision(await ports.read_revision(session))
                if before != loaded_revision or after != before:
                    continue

                snapshot = await asyncio.to_thread(
                    build_snapshot,
                    loaded_revision,
                    entries,
                    getattr(ports, "index_limits", DEFAULT_INDEX_LIMITS),
                )

                async with ports.read_session() as session:
                    current_revision = _valid_revision(
                        await ports.read_revision(session)
                    )
                if current_revision != loaded_revision:
                    continue

                registry.publish(snapshot)
                _record_index_metrics(observer, owner, snapshot)
                _record_rebuild(observer, owner, "success", started)
                return None
            except IndexTooLarge as error:
                registry.mark_degraded(error.reason)
                increment_safely(
                    observer,
                    "pulsegrid_autocomplete_index_refreshes_total",
                    {"owner": owner, "outcome": error.reason},
                )
                gauge_safely(
                    observer,
                    "pulsegrid_autocomplete_index_entries",
                    float(error.entries),
                    {"owner": owner},
                )
                gauge_safely(
                    observer,
                    "pulsegrid_autocomplete_index_nodes",
                    float(error.nodes),
                    {"owner": owner},
                )
                gauge_safely(
                    observer,
                    "pulsegrid_autocomplete_index_estimated_bytes",
                    float(error.estimated_bytes),
                    {"owner": owner},
                )
                _record_rebuild(observer, owner, error.reason, started)
                return None
            except Exception:
                registry.mark_degraded("owner_unavailable")
                increment_safely(
                    observer,
                    "pulsegrid_autocomplete_index_refreshes_total",
                    {"owner": owner, "outcome": "owner_unavailable"},
                )
                _record_rebuild(observer, owner, "owner_unavailable", started)
                return None

        registry.mark_degraded("revision_race")
        increment_safely(
            observer,
            "pulsegrid_autocomplete_index_refreshes_total",
            {"owner": owner, "outcome": "revision_race"},
        )
        _record_rebuild(observer, owner, "revision_race", started)
        return None


async def refresh_loop(
    ports: RefreshPorts,
    stop_event: asyncio.Event,
    *,
    interval_seconds: float = DEFAULT_REFRESH_INTERVAL_SECONDS,
) -> None:
    """Poll the owner revision every five seconds until the app lifespan stops."""
    if interval_seconds <= 0:
        raise ValueError("refresh interval must be positive")
    while not stop_event.is_set():
        await refresh_index(ports)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            continue


def _valid_revision(value: int) -> int:
    if type(value) is not int or not 1 <= value <= MAX_REVISION:
        raise ValueError("owner revision must be a positive JSON-safe integer")
    return value


def _record_index_metrics(
    observer: MetricsObserver, owner: str, snapshot: IndexSnapshot
) -> None:
    labels = {"owner": owner}
    increment_safely(
        observer,
        "pulsegrid_autocomplete_index_refreshes_total",
        {"owner": owner, "outcome": "success"},
    )
    gauge_safely(
        observer,
        "pulsegrid_autocomplete_index_entries",
        float(snapshot.entries),
        labels,
    )
    gauge_safely(
        observer,
        "pulsegrid_autocomplete_index_nodes",
        float(snapshot.nodes),
        labels,
    )
    gauge_safely(
        observer,
        "pulsegrid_autocomplete_index_estimated_bytes",
        float(snapshot.estimated_bytes),
        labels,
    )


def _record_rebuild(
    observer: MetricsObserver, owner: str, outcome: str, started: float
) -> None:
    observe_safely(
        observer,
        "pulsegrid_autocomplete_index_rebuild_seconds",
        max(0.0, time.perf_counter() - started),
        {"owner": owner, "outcome": outcome},
    )


async def health() -> dict[str, str | None]:
    """Pure component health; owner replica state is reported by IndexRegistry."""
    return {"state": "ok", "reason": None}
