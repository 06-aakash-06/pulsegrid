"""Frozen component values and validated deployment configuration."""
from dataclasses import dataclass, field
import re
from typing import Literal, Mapping, Protocol

MAX_INTEGER = 2**53 - 1
POLICY = re.compile(r"[a-z][a-z0-9_-]{0,95}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")

class InvalidConfiguration(ValueError):
    """Invalid server-owned policy; never a permissive admission."""


def positive(value: int, name: str) -> None:
    if type(value) is not int or not 1 <= value <= MAX_INTEGER:
        raise InvalidConfiguration(f"Invalid {name}")

@dataclass(frozen=True)
class BucketSpec:
    policy_id: str
    capacity: int
    refill_milli_tokens_per_second: int
    cost: int
    idle_ttl_ms: int

    def __post_init__(self):
        if not isinstance(self.policy_id, str) or not POLICY.fullmatch(self.policy_id):
            raise InvalidConfiguration("Invalid policy_id")
        for name in ("capacity", "refill_milli_tokens_per_second", "cost", "idle_ttl_ms"):
            positive(getattr(self, name), name)
        cap = self.capacity * 1000
        refill = self.refill_milli_tokens_per_second
        # Refill time in ms; elapsed is bounded to this before multiplication.
        fill_ms = (cap * 1000 + refill - 1) // refill
        if self.cost > self.capacity or cap * 1000 + refill + 999 > MAX_INTEGER:
            raise InvalidConfiguration("Unsafe capacity/cost/refill arithmetic")
        if fill_ms * refill + 999 > MAX_INTEGER or self.idle_ttl_ms < fill_ms + 1000:
            raise InvalidConfiguration("TTL must exceed full refill time by 1000ms")

@dataclass(frozen=True)
class BucketRequest:
    key_digest: str
    spec: BucketSpec

    def __post_init__(self):
        if not isinstance(self.key_digest, str) or not DIGEST.fullmatch(self.key_digest):
            raise InvalidConfiguration("Expected server-derived HMAC-SHA256 digest")
        if not isinstance(self.spec, BucketSpec):
            raise InvalidConfiguration("Expected BucketSpec")

@dataclass(frozen=True)
class Admission:
    allowed: bool
    retry_after_ms: int | None
    remaining_milli_tokens: int
    mode: Literal["redis", "local"]
    reason: Literal["accepted", "limited", "unavailable"]
    surge_mode: Literal["NORMAL", "SURGE", "RECOVERY", "UNKNOWN"] = "NORMAL"
    operation_class: Literal["A", "B", "C"] = "B"


@dataclass(frozen=True)
class SurgeModeSnapshot:
    state: Literal["NORMAL", "SURGE", "RECOVERY", "UNKNOWN"]
    version: int | None = None
    entered_at_ms: int | None = None
    expires_at_ms: int | None = None
    reason_code: str | None = None
    operation_id: str | None = None

    @property
    def available(self) -> bool:
        return self.state != "UNKNOWN"

@dataclass(frozen=True)
class LimiterConfig:
    enabled: bool = False
    redis_endpoint: str = field(default="redis://127.0.0.1:6379/0", repr=False)
    redis_username: str | None = field(default=None, repr=False)
    redis_password: str | None = field(default=None, repr=False)
    connect_timeout_ms: int = 50
    command_timeout_ms: int = 50
    decision_timeout_ms: int = 100
    policy_version: str = "v1"
    hmac_secret: bytes = field(default=b"", repr=False)
    max_replicas: int = 4
    local_bounded_key_capacity: int = 10000
    max_connections: int = 128

    def __post_init__(self):
        if type(self.enabled) is not bool or self.policy_version != "v1":
            raise InvalidConfiguration("Invalid enabled or unsupported policy_version")
        for name in ("connect_timeout_ms", "command_timeout_ms", "decision_timeout_ms",
                     "max_replicas", "local_bounded_key_capacity", "max_connections"):
            positive(getattr(self, name), name)
        if self.connect_timeout_ms > 50 or self.command_timeout_ms > 50 or self.decision_timeout_ms > 100:
            raise InvalidConfiguration("Deadlines exceed frozen contract")
        if self.enabled and (not isinstance(self.hmac_secret, bytes) or len(self.hmac_secret) < 32):
            raise InvalidConfiguration("Enabled admission requires >=32 secret bytes")
        if self.local_bounded_key_capacity > 10000:
            raise InvalidConfiguration("Local cardinality exceeds frozen bound")

class Observer(Protocol):
    def increment(self, name: str, labels: Mapping[str, str], value: int = 1) -> None: ...
    def observe(self, name: str, seconds: float, labels: Mapping[str, str]) -> None: ...
    def gauge(self, name: str, value: float, labels: Mapping[str, str]) -> None: ...

class NoopObserver:
    def increment(self, name, labels, value=1): pass
    def observe(self, name, seconds, labels): pass
    def gauge(self, name, value, labels): pass
