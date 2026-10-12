"""Small concurrency-safe resilience primitives for optional owner reads."""
from collections import deque
from dataclasses import dataclass
import asyncio
import time


class CircuitOpen(RuntimeError):
    """No request permit is available while a dependency circuit is open."""


@dataclass(frozen=True)
class BreakerPermit:
    half_open_probe: bool = False


class CircuitBreaker:
    """Rolling-window breaker with one bounded half-open probe."""

    def __init__(self, *, threshold=3, window_seconds=10.0, cooldown_seconds=5.0,
                 clock=time.monotonic, on_state=None):
        if threshold < 1 or window_seconds <= 0 or cooldown_seconds <= 0:
            raise ValueError("Invalid circuit-breaker settings")
        self.threshold = threshold
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds
        self.clock = clock
        self.on_state = on_state
        self.state = "CLOSED"
        self.failures = deque()
        self.open_until = 0.0
        self.probe_in_flight = False
        self.lock = asyncio.Lock()

    def _emit_state(self, state):
        if self.on_state is not None:
            try:
                self.on_state(state)
            except Exception:
                pass

    async def acquire(self):
        changed = None
        async with self.lock:
            now = self.clock()
            if self.state == "OPEN":
                if now < self.open_until:
                    raise CircuitOpen("dependency circuit open")
                self.state = "HALF_OPEN"
                self.probe_in_flight = False
                changed = self.state
            if self.state == "HALF_OPEN":
                if self.probe_in_flight:
                    if changed:
                        self._emit_state(changed)
                    raise CircuitOpen("half-open probe already in flight")
                self.probe_in_flight = True
                permit = BreakerPermit(half_open_probe=True)
            else:
                permit = BreakerPermit()
        if changed:
            self._emit_state(changed)
        return permit

    async def succeeded(self, permit):
        changed = None
        async with self.lock:
            if permit.half_open_probe and self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failures.clear()
                self.open_until = 0.0
                self.probe_in_flight = False
                changed = self.state
        if changed:
            self._emit_state(changed)

    async def failed(self, permit):
        changed = None
        async with self.lock:
            now = self.clock()
            if permit.half_open_probe and self.state == "HALF_OPEN":
                self.probe_in_flight = False
                self.state = "OPEN"
                self.open_until = now + self.cooldown_seconds
                self.failures.clear()
                changed = self.state
            elif self.state == "CLOSED":
                cutoff = now - self.window_seconds
                while self.failures and self.failures[0] < cutoff:
                    self.failures.popleft()
                self.failures.append(now)
                if len(self.failures) >= self.threshold:
                    self.state = "OPEN"
                    self.open_until = now + self.cooldown_seconds
                    self.failures.clear()
                    changed = self.state
        if changed:
            self._emit_state(changed)

    async def cancelled(self, permit):
        if not permit.half_open_probe:
            return
        async with self.lock:
            if self.state == "HALF_OPEN":
                self.probe_in_flight = False
