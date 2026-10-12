"""Small observer port helpers; metric failures never affect search behavior."""

from __future__ import annotations

from typing import Mapping, Protocol


class MetricsObserver(Protocol):
    def increment(
        self, name: str, labels: Mapping[str, str], value: int = 1
    ) -> None: ...

    def observe(
        self, name: str, seconds: float, labels: Mapping[str, str]
    ) -> None: ...

    def gauge(self, name: str, value: float, labels: Mapping[str, str]) -> None: ...


class NoopMetrics:
    """Default structural observer for tests and disabled instrumentation."""

    __slots__ = ()

    def increment(
        self, name: str, labels: Mapping[str, str], value: int = 1
    ) -> None:
        return None

    def observe(
        self, name: str, seconds: float, labels: Mapping[str, str]
    ) -> None:
        return None

    def gauge(self, name: str, value: float, labels: Mapping[str, str]) -> None:
        return None


NOOP_METRICS = NoopMetrics()


def increment_safely(
    observer: MetricsObserver,
    name: str,
    labels: Mapping[str, str],
    value: int = 1,
) -> None:
    try:
        observer.increment(name, labels, value)
    except Exception:
        return None


def observe_safely(
    observer: MetricsObserver,
    name: str,
    seconds: float,
    labels: Mapping[str, str],
) -> None:
    try:
        observer.observe(name, seconds, labels)
    except Exception:
        return None


def gauge_safely(
    observer: MetricsObserver,
    name: str,
    value: float,
    labels: Mapping[str, str],
) -> None:
    try:
        observer.gauge(name, value, labels)
    except Exception:
        return None
