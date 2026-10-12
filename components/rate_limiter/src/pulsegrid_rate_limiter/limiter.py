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
from .types import Admission, BucketRequest, InvalidConfiguration, LimiterConfig, NoopObserver, SurgeModeSnapshot

SCRIPT = files(__package__).joinpath('bucket.lua').read_text()
SCRIPT_SHA = hashlib.sha1(SCRIPT.encode()).hexdigest()
SURGE_KEY = 'pg:admission:v1:surge-mode'
SURGE_READ_SCRIPT = files(__package__).joinpath('surge_read.lua').read_text()
SURGE_READ_SHA = hashlib.sha1(SURGE_READ_SCRIPT.encode()).hexdigest()
SURGE_TRANSITION_SCRIPT = files(__package__).joinpath('surge_transition.lua').read_text()
SURGE_TRANSITION_SHA = hashlib.sha1(SURGE_TRANSITION_SCRIPT.encode()).hexdigest()
SURGE_RECOVERY_MS = 120_000
SURGE_MINIMUM_SURGE_MS = 30_000
SURGE_MINIMUM_RECOVERY_MS = 15_000
SURGE_MAXIMUM_TTL_MS = 1_800_000
SURGE_REASONS = frozenset({'capacity_pressure', 'dependency_degraded', 'planned_recovery', 'incident_override'})


class SurgeModeUnavailable(RuntimeError):
    """The shared Surge Mode control could not be safely updated."""

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

    async def admit(self, buckets: Sequence[BucketRequest], *, surge_mode='NORMAL', operation_class='B') -> Admission:
        started = perf_counter()
        policy = 'invalid'
        try:
            if surge_mode not in ('NORMAL', 'SURGE', 'RECOVERY', 'UNKNOWN') or operation_class not in ('A', 'B', 'C'):
                raise InvalidConfiguration('Invalid admission mode or operation class')
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
        return Admission(result.allowed, result.retry_after_ms, result.remaining_milli_tokens,
                         result.mode, result.reason, surge_mode, operation_class)

    async def _eval_script(self, script, sha, numkeys, *args):
        if self.redis is None:
            raise SurgeModeUnavailable('shared_admission_unavailable')
        try:
            result = await self.redis.evalsha(sha, numkeys, *args)
        except NoScriptError:
            # NOSCRIPT proves that a state-changing script did not execute.
            await self.redis.script_load(script)
            result = await self.redis.evalsha(sha, numkeys, *args)
        return result

    @staticmethod
    def _decode_surge_result(values):
        if not isinstance(values, (list, tuple)) or len(values) != 6:
            return SurgeModeSnapshot('UNKNOWN')
        state, version, entered, expires, reason, operation_id = values
        try:
            state = state.decode('ascii') if isinstance(state, bytes) else str(state)
            version = int(version)
            entered = int(entered)
            expires = int(expires)
            reason = reason.decode('ascii') if isinstance(reason, bytes) else str(reason)
            operation_id = operation_id.decode('ascii') if isinstance(operation_id, bytes) else str(operation_id)
        except (UnicodeDecodeError, TypeError, ValueError, OverflowError):
            return SurgeModeSnapshot('UNKNOWN')
        if state not in ('NORMAL', 'SURGE', 'RECOVERY') or version < 0 or entered < 0 or expires < 0:
            return SurgeModeSnapshot('UNKNOWN')
        return SurgeModeSnapshot(state, version, entered or None, expires or None,
                                 None if reason == 'none' else reason,
                                 None if operation_id == 'none' else operation_id)

    async def surge_mode(self) -> SurgeModeSnapshot:
        """Read one shared, expiring mode snapshot; unknown uses protective budgets."""
        if not self.config.enabled:
            return SurgeModeSnapshot('NORMAL', version=0)
        try:
            async with asyncio.timeout(self.config.decision_timeout_ms / 1000):
                values = await self._eval_script(SURGE_READ_SCRIPT, SURGE_READ_SHA, 1,
                                                 SURGE_KEY, SURGE_RECOVERY_MS)
            return self._decode_surge_result(values)
        except (RedisError, TimeoutError, OSError, SurgeModeUnavailable):
            self._emit('increment', 'pulsegrid_surge_mode_state_errors_total', {'state': 'UNKNOWN'})
            return SurgeModeSnapshot('UNKNOWN')

    async def transition_surge_mode(self, snapshot: SurgeModeSnapshot, target: str, *,
                                    reason_code: str, operation_id: str, actor_digest: str,
                                    override: bool = False):
        """CAS the shared Redis control after the caller has durably audited intent."""
        import re
        operation_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
        if (not self.config.enabled or snapshot.state not in ('NORMAL', 'SURGE', 'RECOVERY') or
                snapshot.version is None or target not in ('SURGE', 'RECOVERY') or
                reason_code not in SURGE_REASONS or
                override != (reason_code == 'incident_override') or
                not re.fullmatch(operation_pattern, operation_id) or
                not re.fullmatch(r'[0-9a-f]{64}', actor_digest) or type(override) is not bool):
            raise SurgeModeUnavailable('invalid_surge_transition')
        args = (SURGE_KEY, snapshot.version, snapshot.state, target, reason_code,
                operation_id, actor_digest, int(override), SURGE_MINIMUM_SURGE_MS,
                SURGE_MINIMUM_RECOVERY_MS, SURGE_MAXIMUM_TTL_MS,
                SURGE_RECOVERY_MS, SURGE_RECOVERY_MS)
        try:
            async with asyncio.timeout(self.config.decision_timeout_ms / 1000):
                values = await self._eval_script(SURGE_TRANSITION_SCRIPT, SURGE_TRANSITION_SHA, 1, *args)
        except (RedisError, TimeoutError, OSError) as exc:
            raise SurgeModeUnavailable('shared_admission_unavailable') from exc
        if not isinstance(values, (list, tuple)) or len(values) != 7:
            raise SurgeModeUnavailable('invalid_surge_transition_result')
        try:
            decoded = [v.decode('ascii') if isinstance(v, bytes) else str(v) for v in values]
            status, previous, state, version, entered, expires, result_reason = decoded
            result = SurgeModeSnapshot(state, int(version), int(entered) or None,
                                       int(expires) or None, result_reason,
                                       operation_id if status == 'applied' else snapshot.operation_id)
        except (UnicodeDecodeError, TypeError, ValueError, OverflowError) as exc:
            raise SurgeModeUnavailable('invalid_surge_transition_result') from exc
        if status not in ('applied', 'noop', 'conflict', 'cooldown') or result.state not in ('NORMAL', 'SURGE', 'RECOVERY'):
            raise SurgeModeUnavailable('invalid_surge_transition_result')
        if status == 'applied':
            self._emit('increment', 'pulsegrid_surge_mode_transitions_total', {'state': state})
        return status, previous, result

    async def health(self):
        if not self.config.enabled:
            return {'state': 'disabled', 'reason': None}
        return {'state': 'degraded' if self.reason else 'ok', 'reason': self.reason}

    async def close(self):
        if self.redis is not None:
            await self.redis.aclose()
