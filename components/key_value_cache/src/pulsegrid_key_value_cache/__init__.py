"""Bounded, non-authoritative Redis cache with structural placement."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol


class CacheUnavailable(Exception):
    """A bounded cache attempt failed; use owner storage."""


class InvalidEntry(ValueError):
    pass


class Placement(Protocol):
    @property
    def epoch(self) -> int: ...
    def locate(self, key: bytes) -> str: ...


class Observer(Protocol):
    def increment(self, name: str, labels: Mapping[str, str], value: int = 1) -> None: ...
    def observe(self, name: str, seconds: float, labels: Mapping[str, str]) -> None: ...
    def gauge(self, name: str, value: float, labels: Mapping[str, str]) -> None: ...


@dataclass(frozen=True)
class CacheEntry:
    payload: bytes
    source_version: int
    expires_at_ms: int


def canonical_json(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def logical_key(*, owner: str, schema: int, visibility: Mapping[str, str],
                revision: int, filters: Mapping) -> bytes:
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", owner):
        raise ValueError("invalid owner")
    for value in (schema, revision):
        if type(value) is not int or not 1 <= value <= 9007199254740991:
            raise ValueError("invalid version")
    return canonical_json(dict(owner=owner, schema=schema, visibility=dict(visibility),
                               revision=revision, filters=dict(filters)))


def redis_client(url: str, *, max_connections: int = 32):
    """Coordinator provides a private ACL URL; never log it."""
    from redis.asyncio import Redis
    from redis.backoff import NoBackoff
    from redis.retry import Retry
    return Redis.from_url(url, socket_connect_timeout=.05, socket_timeout=.05,
                          max_connections=max_connections, decode_responses=False,
                          retry=Retry(NoBackoff(), 0), retry_on_timeout=False)


class Cache:
    def __init__(self, placement: Placement, clients: Mapping, *, owner="doctor",
                 observer: Observer | None = None, clock: Callable[[], int] | None = None,
                 ttl_ms=30000, max_loaders=32, wait_ms=100):
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", owner):
            raise ValueError("invalid owner")
        if any(type(v) is not int for v in (ttl_ms, max_loaders, wait_ms)) or not 1 <= ttl_ms <= 60000 or not 1 <= max_loaders <= 32 or not 0 < wait_ms <= 100:
            raise ValueError("invalid bounds")
        self.placement, self.clients, self.owner = placement, dict(clients), owner
        self.observer, self.clock = observer, clock or (lambda: time.time_ns() // 1000000)
        self.ttl_ms, self.wait_ms = ttl_ms, wait_ms
        self._loaders = asyncio.Semaphore(max_loaders)
        self._state, self._reason = "ok", None

    def _metric(self, method, name, value=None, **labels):
        if self.observer is None:
            return
        labels = {"component": "key_value_cache", "owner": self.owner, **labels}
        try:
            if method == "increment":
                self.observer.increment("pulsegrid_" + name, labels)
            else:
                getattr(self.observer, method)("pulsegrid_" + name, value, labels)
        except Exception:
            pass

    def _target(self, key):
        if not isinstance(key, bytes) or not 1 <= len(key) <= 8192:
            raise ValueError("invalid logical key")
        try:
            epoch = self.placement.epoch
            if type(epoch) is not int or not 1 <= epoch <= 9007199254740991:
                raise ValueError("invalid epoch")
            client = self.clients[self.placement.locate(key)]
        except Exception:
            raise CacheUnavailable("placement unavailable") from None
        return client, f"pg:cache:v1:{self.owner}:{epoch}:{hashlib.sha256(key).hexdigest()}"

    async def _call(self, client, method, *args, **kwargs):
        try:
            async with asyncio.timeout(.1):
                result = await getattr(client, method)(*args, **kwargs)
            self._state, self._reason = "ok", None
            return result
        except Exception:
            self._state, self._reason = "degraded", "cache_unavailable"
            raise CacheUnavailable("cache unavailable") from None

    def _encode(self, entry):
        if (not isinstance(entry, CacheEntry) or not isinstance(entry.payload, bytes)
            or type(entry.source_version) is not int
            or not 1 <= entry.source_version <= 9007199254740991
            or type(entry.expires_at_ms) is not int
            or not self.clock() < entry.expires_at_ms <= self.clock() + 60000):
            raise InvalidEntry("invalid entry")
        raw = canonical_json(dict(schema_version=1, payload=base64.b64encode(entry.payload).decode(),
                                  source_version=entry.source_version, expires_at_ms=entry.expires_at_ms))
        if len(raw) > 65536:
            raise InvalidEntry("entry exceeds 64KiB")
        return raw

    def _decode(self, raw):
        if not isinstance(raw, bytes) or len(raw) > 65536:
            raise InvalidEntry("invalid serialization")
        def unique(pairs):
            result = {}
            for k, v in pairs:
                if k in result:
                    raise InvalidEntry("duplicate field")
                result[k] = v
            return result
        try:
            value = json.loads(raw, object_pairs_hook=unique)
            if set(value) != {"schema_version", "payload", "source_version", "expires_at_ms"} or type(value['schema_version']) is not int or value['schema_version'] != 1:
                raise InvalidEntry("schema mismatch")
            entry = CacheEntry(base64.b64decode(value['payload'], validate=True),
                               value['source_version'], value['expires_at_ms'])
            self._encode(entry)
            return entry
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise InvalidEntry("invalid serialization") from None

    async def get(self, key: bytes) -> CacheEntry | None:
        start = time.perf_counter()
        try:
            client, physical = self._target(key)
            raw = await self._call(client, "get", physical)
            try:
                entry = self._decode(raw) if raw is not None else None
            except InvalidEntry:
                entry = None
            self._metric("increment", "cache_requests_total", outcome="hit" if entry else "miss")
            return entry
        except CacheUnavailable:
            self._state, self._reason = "degraded", "cache_unavailable"
            self._metric("increment", "cache_requests_total", outcome="unavailable")
            raise
        finally:
            self._metric("observe", "cache_lookup_seconds", time.perf_counter() - start)

    async def set(self, key: bytes, value: CacheEntry, ttl_ms: int) -> None:
        if type(ttl_ms) is not int or not 1 <= ttl_ms <= 60000:
            raise InvalidEntry("invalid TTL")
        raw = self._encode(value)
        client, physical = self._target(key)
        ttl = min(ttl_ms, value.expires_at_ms - self.clock())
        if ttl <= 0:
            return
        await self._call(client, "set", physical, raw, px=ttl)

    async def delete(self, key: bytes) -> None:
        client, physical = self._target(key)
        await self._call(client, "delete", physical)
        self._metric("increment", "cache_invalidations_total")

    async def invalidate(self, key: bytes) -> bool:
        """After commit only; revision bump is the actual freshness barrier."""
        try:
            await self.delete(key)
            return True
        except CacheUnavailable:
            self._metric("increment", "cache_errors_total", kind="invalidation")
            return False

    async def get_or_load(self, key: bytes, loader) -> CacheEntry:
        cache_start = time.perf_counter()
        available = True
        try:
            entry = await self.get(key)
            if entry is not None:
                return entry
        except CacheUnavailable:
            available = False
        remaining = max(0, .1 - (time.perf_counter() - cache_start))
        acquired = False
        try:
            try:
                async with asyncio.timeout(self.wait_ms / 1000):
                    await self._loaders.acquire()
                acquired = True
            except TimeoutError:
                self._metric("increment", "cache_requests_total", outcome="bypass")
            start = time.perf_counter()
            try:
                entry = await loader()  # caller's bounded owner pool; failures propagate
            finally:
                self._metric("observe", "cache_load_seconds", time.perf_counter() - start)
            if acquired and available and remaining > 0:
                try:
                    async with asyncio.timeout(remaining):
                        await self.set(key, entry, self.ttl_ms)
                except (CacheUnavailable, InvalidEntry, TimeoutError) as error:
                    if isinstance(error, TimeoutError):
                        self._state, self._reason = "degraded", "cache_unavailable"
                    self._metric("increment", "cache_errors_total", kind="population")
            return entry
        finally:
            if acquired:
                self._loaders.release()

    async def health(self):
        return {"state": self._state, "reason": self._reason}

    async def close(self):
        for client in {id(c): c for c in self.clients.values()}.values():
            try:
                async with asyncio.timeout(.1):
                    await client.aclose()
            except Exception:
                self._state, self._reason = "degraded", "close_failed"
