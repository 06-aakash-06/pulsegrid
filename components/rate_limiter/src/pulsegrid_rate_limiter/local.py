"""Replica-partitioned fixed-point fallback; never clear on backend transitions."""
from dataclasses import dataclass
from collections import OrderedDict
from threading import Lock
from time import monotonic_ns
from .types import Admission, InvalidConfiguration

@dataclass
class State:
    tokens: int
    last_ms: int
    carry: int
    spec: object

class LocalBuckets:
    def __init__(self, max_replicas=4, key_capacity=10000, clock=monotonic_ns):
        self.max_replicas = max_replicas
        self.key_capacity = key_capacity
        self.clock = clock
        self.states = OrderedDict()
        self.lock = Lock()

    def parameters(self, spec):
        cap = spec.capacity // self.max_replicas
        rate = spec.refill_milli_tokens_per_second // self.max_replicas
        if cap < spec.cost or rate < 1:
            raise InvalidConfiguration("Budget cannot be partitioned across max_replicas")
        return cap * 1000, rate

    def _refill(self, state, now):
        cap, rate = self.parameters(state.spec)
        fill = (cap*1000 + rate-1)//rate
        elapsed = min(fill, max(0, now-state.last_ms))
        credit = elapsed*rate + state.carry
        tokens = min(cap, state.tokens + credit//1000)
        return State(tokens, max(now, state.last_ms), 0 if tokens == cap else credit % 1000, state.spec)

    def decide(self, buckets, *, shadow=False):
        with self.lock:
            now = self.clock()//1000000
            protected = {b.key for b in buckets}
            missing = sum(b.key not in self.states for b in buckets)
            if len(self.states)+missing > self.key_capacity:
                # Evict only fully replenished idle keys; no LRU quota reset.
                # Probe a fixed budget, rotating live candidates; never scan 10000
                # keys on an already timed-out request. Only full idle keys evict.
                for _ in range(min(32, len(self.states))):
                    if len(self.states)+missing <= self.key_capacity:
                        break
                    key = next(iter(self.states))
                    s = self.states[key]
                    if key not in protected and now-s.last_ms >= s.spec.idle_ttl_ms and self._refill(s, now).tokens == self.parameters(s.spec)[0]:
                        del self.states[key]
                    else:
                        self.states.move_to_end(key)
                if len(self.states)+missing > self.key_capacity:
                    return Admission(False, 1000, 0, 'local', 'unavailable')
            rows, retry = [], 0
            for b in buckets:
                cap, rate = self.parameters(b.spec)
                old = self.states.get(b.key)
                if old is not None and old.spec != b.spec:
                    old_parameters = (old.spec.policy_id, old.spec.capacity, old.spec.refill_milli_tokens_per_second, old.spec.idle_ttl_ms)
                    new_parameters = (b.spec.policy_id, b.spec.capacity, b.spec.refill_milli_tokens_per_second, b.spec.idle_ttl_ms)
                    if old_parameters != new_parameters:
                        raise InvalidConfiguration("Policy changed without namespace change")
                s = self._refill(old, now) if old else State(cap, now, 0, b.spec)
                deficit = (b.spec.cost*1000-s.tokens)*1000-s.carry
                retry = max(retry, max(0, (deficit+rate-1)//rate))
                s.spec = b.spec
                rows.append((b, s))
            allowed = retry == 0
            for b, s in rows:
                if allowed or shadow:
                    s.tokens = max(0, s.tokens-b.spec.cost*1000)
                    if s.tokens == 0 and shadow:
                        s.carry = 0
                # Denied identity churn must not pin a new full bucket in memory.
                if allowed or shadow or b.key in self.states:
                    self.states[b.key] = s
            return Admission(allowed, None if allowed else retry,
                             min(s.tokens for _, s in rows), 'local',
                             'accepted' if allowed else 'limited')
