"""One limiter per API process, one dedicated shared standalone Redis."""
import asyncio
from dataclasses import dataclass
import hashlib
from importlib.resources import files
from time import perf_counter
from typing import Sequence
from redis.asyncio import Redis
from redis.backoff import NoBackoff
from redis.retry import Retry
from redis.exceptions import NoScriptError, RedisError, ResponseError, OutOfMemoryError, AuthenticationError
from .local import LocalBuckets
from .types import Admission, BucketRequest, InvalidConfiguration, LimiterConfig, NoopObserver

SCRIPT = files(__package__).joinpath('bucket.lua').read_text()
SCRIPT_SHA = hashlib.sha1(SCRIPT.encode()).hexdigest()

@dataclass(frozen=True)
class KeyedBucket:
    key: str
    spec: object

class RateLimiter:
    def __init__(self, config: LimiterConfig, *, observer=None, redis_client=None, clock=None):
        self.config = config
        self.observer = observer or NoopObserver()
        self.redis = redis_client
        if self.redis is None and config.enabled:
            self.redis = Redis.from_url(
                config.redis_endpoint, username=config.redis_username, password=config.redis_password,
                socket_connect_timeout=config.connect_timeout_ms/1000,
                socket_timeout=config.command_timeout_ms/1000,
                max_connections=config.max_connections,
                retry=Retry(NoBackoff(), 0), retry_on_timeout=False,
            )
        kwargs = {} if clock is None else {'clock': clock}
        self.local = LocalBuckets(config.max_replicas, config.local_bounded_key_capacity, **kwargs)
        self.mode = None
        self.reason = None

    def _emit(self, method, *args):
        try:
            getattr(self.observer, method)(*args)
        except Exception:
            pass

    def key(self, bucket):
        return f'pg:admission:v1:{bucket.spec.policy_id}:{bucket.key_digest}'

    def _validate(self, buckets):
        if not 1 <= len(buckets) <= 3 or any(not isinstance(b, BucketRequest) for b in buckets):
            raise InvalidConfiguration('Expected one to three BucketRequest values')
        rows = [KeyedBucket(self.key(b), b.spec) for b in buckets]
        if len({r.key for r in rows}) != len(rows):
            raise InvalidConfiguration('Duplicate bucket would double-charge')
        for b in buckets:
            self.local.parameters(b.spec)
        return rows

    async def _redis_decide(self, buckets, rows):
        args = [v for b in buckets for v in (
            b.spec.capacity*1000, b.spec.refill_milli_tokens_per_second,
            b.spec.cost*1000, b.spec.idle_ttl_ms)]
        keys = [r.key for r in rows]
        try:
            result = await self.redis.evalsha(SCRIPT_SHA, len(keys), *keys, *args)
        except NoScriptError:
            # NOSCRIPT proves that this consumption did not execute; only safe retry.
            await self.redis.script_load(SCRIPT)
            result = await self.redis.evalsha(SCRIPT_SHA, len(keys), *keys, *args)
        if not isinstance(result, (list, tuple)) or len(result) != 3:
            raise InvalidConfiguration('Invalid Redis response')
        allowed, retry, remaining = result
        if any(type(v) is not int for v in result) or allowed not in (0, 1) or retry < 0 or remaining < 0:
            raise InvalidConfiguration('Invalid Redis response')
        if (allowed == 1) != (retry == 0):
            raise InvalidConfiguration('Inconsistent Redis response')
        return Admission(bool(allowed), None if allowed else retry, remaining,
                         'redis', 'accepted' if allowed else 'limited')

    async def admit(self, buckets: Sequence[BucketRequest]) -> Admission:
        started = perf_counter()
        policy = 'invalid'
        try:
            rows = self._validate(buckets)
            policy = buckets[0].spec.policy_id
            if not self.config.enabled:
                result = Admission(True, None, 0, 'local', 'accepted')
            else:
                try:
                    # Reserve 5ms of the total deadline for bounded local decision work.
                    remaining = self.config.decision_timeout_ms/1000 - (perf_counter()-started) - .005
                    if remaining <= 0:
                        raise TimeoutError('Decision budget exhausted')
                    async with asyncio.timeout(remaining):
                        result = await self._redis_decide(buckets, rows)
                    # Shadow actual accepted traffic, so an outage grants no fresh local burst.
                    if result.allowed:
                        self.local.decide(rows, shadow=True)
                except AuthenticationError:
                    raise InvalidConfiguration('Redis authentication configuration is invalid') from None
                except ResponseError as exc:
                    if not isinstance(exc, OutOfMemoryError) and not str(exc).startswith(('OOM ', 'BUSY ')):
                        raise InvalidConfiguration('Redis policy/state/configuration is invalid') from None
                    result = self.local.decide(rows)
                except (RedisError, TimeoutError, OSError):
                    result = self.local.decide(rows)
        except (InvalidConfiguration, MemoryError, TypeError, ValueError, OverflowError):
            result = Admission(False, 1000, 0, 'local', 'unavailable')
        if self.config.enabled and self.mode != result.mode:
            if self.mode is not None:
                self._emit('increment', 'pulsegrid_admission_mode_transitions_total',
                           {'policy': policy, 'backend': result.mode})
            self.mode = result.mode
        self.reason = 'fallback' if self.config.enabled and result.mode == 'local' else None
        labels = {'policy': policy, 'outcome': result.reason, 'backend': result.mode}
        self._emit('increment', 'pulsegrid_admission_requests_total', labels)
        self._emit('observe', 'pulsegrid_admission_duration_seconds', perf_counter()-started, labels)
        return result

    async def health(self):
        if not self.config.enabled:
            return {'state': 'disabled', 'reason': None}
        return {'state': 'degraded' if self.reason else 'ok', 'reason': self.reason}

    async def close(self):
        if self.redis is not None:
            await self.redis.aclose()
