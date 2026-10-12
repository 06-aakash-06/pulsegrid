"""Proposed frozen seed budgets, partitioned by owner and route family."""
from dataclasses import dataclass
import hashlib
import hmac
import ipaddress
from types import MappingProxyType
from .types import BucketRequest, BucketSpec, InvalidConfiguration, POLICY

OWNERS = frozenset('patient doctor appointment records pharmacy billing emergency'.split())
# capacity / milli-tokens per second (cost is one token)
BUDGETS = MappingProxyType({
    'auth_registration': {'source': (5, 100), 'aggregate': (50, 5000)},
    'auth_login': {'source': (10, 500), 'account': (5, 100), 'aggregate': (100, 10000)},
    'auth_session': {'source': (30, 2000), 'aggregate': (300, 30000)},
    'directory_search': {'principal': (60, 10000), 'aggregate': (600, 100000)},
    'appointment_command': {'principal': (30, 5000), 'aggregate': (300, 50000)},
    'critical_staff': {'principal': (120, 20000), 'aggregate': (1200, 200000)},
    'emergency_public': {'source': (5, 200), 'aggregate': (100, 20000)},
    'emergency_authenticated': {'principal': (30, 5000), 'aggregate': (600, 100000)},
    'emergency_staff': {'principal': (120, 20000), 'aggregate': (1200, 200000)},
    'owner_read': {'principal': (120, 20000), 'aggregate': (1200, 200000)},
    'internal_worker': {'principal': (120, 20000), 'aggregate': (1200, 200000)},
})
# Pre-auth gates use independent source + aggregate keys, not principal budgets.
BUDGETS = MappingProxyType({key: MappingProxyType(value) for key, value in BUDGETS.items()})
PREAUTH = MappingProxyType({'source': (30, 2000), 'aggregate': (300, 30000)})

class IdentityDeriver:
    def __init__(self, secret: bytes):
        if not isinstance(secret, bytes) or len(secret) < 32:
            raise InvalidConfiguration('HMAC requires >=32 secret bytes')
        self._secret = secret

    def digest(self, kind: str, value: str) -> str:
        if kind not in ('source', 'principal', 'account', 'aggregate', 'service'):
            raise InvalidConfiguration('Invalid identity kind')
        if not isinstance(value, str) or not 1 <= len(value) <= 512 or '\x00' in value:
            raise InvalidConfiguration('Invalid identity')
        # Explicit versioned length framing avoids concatenation collisions.
        raw = value.encode('utf-8')
        framed = b'pg-admission-identity-v1\0' + kind.encode() + b'\0' + str(len(raw)).encode() + b'\0' + raw
        return hmac.new(self._secret, framed, hashlib.sha256).hexdigest()

    def source(self, request) -> str:
        # ASGI peer, already processed by reviewed Uvicorn trusted proxy handling.
        # Never read forwarded/actor/identity headers here.
        try:
            host = request.scope['client'][0]
            address = ipaddress.ip_address(host)
            if getattr(address, 'ipv4_mapped', None):
                address = address.ipv4_mapped
            host = str(address)
        except (KeyError, IndexError, TypeError, ValueError):
            host = 'unknown-peer'
        return self.digest('source', host)

    def principal(self, user_id: str) -> str:
        if not isinstance(user_id, str) or not user_id.isascii() or not user_id.isdecimal() or user_id.startswith('0') or len(user_id) > 19 or int(user_id) >= 2**63:
            raise InvalidConfiguration('Expected verified canonical principal ID')
        return self.digest('principal', user_id)

@dataclass(frozen=True)
class RoutePolicy:
    owner: str
    policy: str
    family: str

    def __post_init__(self):
        if self.owner not in OWNERS or self.policy not in BUDGETS or not POLICY.fullmatch(self.family):
            raise InvalidConfiguration('Invalid route policy')
        if self.policy.startswith('emergency_') and self.owner != 'emergency':
            raise InvalidConfiguration('Emergency policies belong to Emergency')

    @property
    def policy_id(self):
        value = f'{self.owner}_{self.policy}_{self.family}'
        if not POLICY.fullmatch(value):
            raise InvalidConfiguration('Partition label too long')
        return value


def build_buckets(route: RoutePolicy, identities: dict[str, str], deriver: IdentityDeriver,
                  *, preauth=False, budgets=None):
    partition = route.policy_id + ('_preauth' if preauth else '')
    values = budgets if budgets is not None else (PREAUTH if preauth else BUDGETS[route.policy])
    if not 1 <= len(values) <= 3 or 'aggregate' not in values:
        raise InvalidConfiguration('Every route needs an aggregate; max three buckets')
    result = []
    for kind, (capacity, rate) in values.items():
        if kind == 'aggregate':
            digest = deriver.digest('aggregate', partition)
        else:
            if kind not in identities:
                raise InvalidConfiguration('Required verified identity missing')
            digest = identities[kind]
        ttl = (capacity*1000000 + rate-1)//rate + 1000
        result.append(BucketRequest(digest, BucketSpec(partition, capacity, rate, 1, ttl)))
    return tuple(result)
