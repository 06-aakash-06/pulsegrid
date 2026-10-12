"""Durable, owner-local Snowflake allocation. IDs remain opaque to consumers."""
import asyncio
import time
from dataclasses import dataclass
from typing import Protocol

EPOCH_MS = 1767225600000


class IdUnavailable(Exception):
    """Allocation failed closed; callers must not use a fallback allocator."""


@dataclass(frozen=True)
class Reservation:
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class Config:
    worker_id: int
    epoch_ms: int = EPOCH_MS
    timestamp_bits: int = 41
    worker_bits: int = 10
    sequence_bits: int = 12
    span_ms: int = 100
    wait_ms: int = 2000

    def __post_init__(self):
        values = vars(self)
        if any(type(v) is not int for v in values.values()):
            raise ValueError("configuration requires integers")
        if min(self.timestamp_bits, self.worker_bits, self.sequence_bits) < 1:
            raise ValueError("bit allocations must be positive")
        if self.timestamp_bits + self.worker_bits + self.sequence_bits != 63:
            raise ValueError("layout must occupy 63 unsigned payload bits")
        if not 0 <= self.worker_id < 1 << self.worker_bits:
            raise ValueError("worker outside layout")
        if self.worker_bits == 10 and self.worker_id >= 896:
            raise ValueError("service code 7 is reserved")
        if self.epoch_ms < 0 or not 1 <= self.span_ms <= 1000 or not 1 <= self.wait_ms <= 2000:
            raise ValueError("invalid epoch/span/deadline")


def worker_identity(service_code: int, replica_code: int) -> int:
    if type(service_code) is not int or type(replica_code) is not int:
        raise ValueError("explicit integer process codes required")
    if not 0 <= service_code <= 6 or not 0 <= replica_code <= 127:
        raise ValueError("service or replica outside assigned partition")
    return (service_code << 7) | replica_code


class WorkerStore(Protocol):
    async def open(self, worker_id: int) -> None: ...
    async def reserve(self, worker_id: int, now_ms: int, span_ms: int) -> Reservation: ...
    async def assert_owned(self, worker_id: int) -> None: ...
    async def close(self) -> None: ...


class Generator:
    def __init__(self, config: Config, store: WorkerStore, *, clock=None, sleep=None,
                 observer=None):
        self.config, self.store = config, store
        self.clock = clock or (lambda: time.time_ns() // 1_000_000)
        self.sleep = sleep or asyncio.sleep
        self.observer = observer
        self._lock = asyncio.Lock()
        self._active = False
        self._poisoned = False
        self._observed = None
        self._last = None
        self._sequence = -1
        self._range = None

    def _metric(self, method, name, value=1):
        try:
            labels = {"component": "unique_id"}
            if method == "observe":
                self.observer.observe("pulsegrid_id_" + name, value, labels)
            else:
                self.observer.increment("pulsegrid_id_" + name, labels, value)
        except Exception:
            pass

    def _now(self):
        now = self.clock()
        if type(now) is not int or not 0 <= now - self.config.epoch_ms < 1 << self.config.timestamp_bits:
            raise IdUnavailable("invalid_timestamp")
        if self._observed is not None and now < self._observed:
            self._metric("increment", "rollback_total")
            raise IdUnavailable("clock_rollback")
        self._observed = now
        return now

    async def start(self):
        async with self._lock:
            if self._active or self._poisoned:
                raise IdUnavailable("explicit_close_required")
            try:
                now = self._now()
                await asyncio.wait_for(self.store.open(self.config.worker_id), self.config.wait_ms / 1000)
                self._range = await asyncio.wait_for(self.store.reserve(
                    self.config.worker_id, now, self.config.span_ms), self.config.wait_ms / 1000)
                self._active = True
            except BaseException as exc:
                self._poisoned = True
                await self.store.close()
                if isinstance(exc, (IdUnavailable, asyncio.CancelledError)):
                    raise
                raise IdUnavailable("store_unavailable") from exc

    async def next_id(self):
        started = time.perf_counter()
        try:
            async with asyncio.timeout(self.config.wait_ms / 1000):
                async with self._lock:
                    if not self._active or self._poisoned:
                        raise IdUnavailable("not_owned")
                    try:
                        while True:
                            if self._poisoned:
                                raise IdUnavailable("not_owned")
                            now = self._now()
                            r = self._range
                            if now > r.end_ms:
                                r = await self.store.reserve(self.config.worker_id, now, self.config.span_ms)
                                self._range = r
                            if not (type(r.start_ms) is int and type(r.end_ms) is int
                                    and r.start_ms <= r.end_ms
                                    and 0 <= r.start_ms - self.config.epoch_ms < 1 << self.config.timestamp_bits):
                                raise IdUnavailable("invalid_reservation")
                            if now < r.start_ms:
                                await self.sleep(.001)
                                continue
                            seq = self._sequence + 1 if now == self._last else 0
                            if now == self.config.epoch_ms and self.config.worker_id == 0 and seq == 0:
                                seq = 1  # Zero is not a valid wire ID; leave this one slot unused.
                            if seq >= 1 << self.config.sequence_bits:
                                self._metric("increment", "overflow_total")
                                await self.sleep(.001)
                                continue
                            await self.store.assert_owned(self.config.worker_id)
                            # Re-read after I/O: never emit a stale/future timestamp or conceal rollback.
                            now = self._now()
                            if now > r.end_ms:
                                continue
                            seq = self._sequence + 1 if now == self._last else 0
                            if now == self.config.epoch_ms and self.config.worker_id == 0 and seq == 0:
                                seq = 1
                            if seq >= 1 << self.config.sequence_bits:
                                self._metric("increment", "overflow_total")
                                await self.sleep(.001)
                                continue
                            if self._poisoned:
                                raise IdUnavailable("not_owned")
                            value = ((now - self.config.epoch_ms) << (self.config.worker_bits + self.config.sequence_bits)) | (self.config.worker_id << self.config.sequence_bits) | seq
                            if value <= 0:
                                raise IdUnavailable("invalid_timestamp")
                            self._last, self._sequence = now, seq
                            self._metric("increment", "generated_total")
                            return value
                    except BaseException:
                        self._poisoned = True
                        raise
        except TimeoutError as exc:
            self._poisoned = True
            raise IdUnavailable("deadline_exceeded") from exc
        except Exception as exc:
            self._poisoned = True
            if isinstance(exc, IdUnavailable):
                raise
            self._metric("increment", "ownership_loss_total")
            raise IdUnavailable("store_unavailable") from exc
        finally:
            self._metric("observe", "generation_seconds", time.perf_counter() - started)

    async def close(self):
        async with self._lock:
            self._active = False
            await self.store.close()
            self._poisoned = False
            self._observed = self._last = self._range = None
            self._sequence = -1

    def decode(self, value):
        if type(value) is not int or not 0 < value < 1 << 63:
            raise ValueError("positive signed BIGINT required")
        c = self.config
        return {"timestamp_ms": (value >> (c.worker_bits + c.sequence_bits)) + c.epoch_ms,
                "worker_id": (value >> c.sequence_bits) & ((1 << c.worker_bits) - 1),
                "sequence": value & ((1 << c.sequence_bits) - 1)}

    def health(self):
        return {"state": "ok" if self._active and not self._poisoned else "degraded",
                "reason": None if self._active and not self._poisoned else "unowned_or_poisoned"}


from .postgres import PostgresWorkerStore
