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
OPERATION_CLASSES = frozenset({'A', 'B', 'C'})
SURGE_MODES = frozenset({'NORMAL', 'SURGE', 'RECOVERY', 'UNKNOWN'})
_CLASS_SCALE = {
    'NORMAL': {'A': (1.0, 1.0), 'B': (1.0, 1.0), 'C': (1.0, 1.0)},
    'SURGE': {'A': (1.0, 1.0), 'B': (0.60, 0.60), 'C': (0.15, 0.15)},
    'RECOVERY': {'A': (1.0, 1.0), 'B': (0.80, 0.80), 'C': (0.50, 0.50)},
    # Unknown shared state must preserve the protected class while reducing
    # optional work until Redis can provide the authoritative mode again.
    'UNKNOWN': {'A': (1.0, 1.0), 'B': (0.60, 0.60), 'C': (0.15, 0.15)},
}


def operation_class_for(owner: str, method: str, path: str) -> str:
    """Return a server-owned class for one reviewed route template."""
    method = method.upper()
    if owner == 'emergency':
        if method == 'POST' and path == '/api/v1/emergencies':
            return 'A'
        if method in ('PATCH', 'POST') and path.endswith(('/priority', '/claim', '/release')):
            return 'A'
        if method == 'POST' and path.endswith('/transitions'):
            return 'A'
    if owner == 'appointment' and method == 'POST':
        if path == '/api/v1/appointments/operations/surge-mode':
            return 'A'
        if path.endswith(('/check-ins', '/queue-entries/{entry_id}/start',
                          '/clinical-hold/finalize')):
            return 'A'
    if owner == 'records' and method == 'POST' and path.endswith('/consultations/{consultation_id}/finalize'):
        return 'A'
    if owner == 'pharmacy' and method == 'POST' and path.endswith('/reservations/{reservation_id}/dispense'):
        return 'A'
    if owner in ('doctor', 'pharmacy') and method == 'GET':
        if 'autocomplete' in path or path.endswith(('/doctors', '/specialties', '/medicines')):
            return 'C'
    if owner == 'billing' and ('/insurance/' in path or '/insurance-estimates' in path or '/insurance-refreshes' in path):
        return 'C'
    return 'B'

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
    operation_class: str = 'B'

    def __post_init__(self):
        if (self.owner not in OWNERS or self.policy not in BUDGETS or
                not POLICY.fullmatch(self.family) or self.operation_class not in OPERATION_CLASSES):
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
                  *, preauth=False, budgets=None, surge_mode='NORMAL'):
    if surge_mode not in SURGE_MODES:
        raise InvalidConfiguration('Invalid Surge Mode')
    budget_mode = 'SURGE' if surge_mode == 'UNKNOWN' else surge_mode
    # Preserve the Phase 4 key namespace and shared route quotas in NORMAL.
    # Surge/recovery use reviewed class-and-mode namespaces so policy changes
    # never collide with an existing Redis bucket configuration.
    mode_partition = '' if budget_mode == 'NORMAL' else (
        '_class_' + route.operation_class.lower() + '_mode_' + budget_mode.lower())
    partition = route.policy_id + mode_partition + ('_preauth' if preauth else '')
    values = budgets if budgets is not None else (PREAUTH if preauth else BUDGETS[route.policy])
    if not 1 <= len(values) <= 3 or 'aggregate' not in values:
        raise InvalidConfiguration('Every route needs an aggregate; max three buckets')
    capacity_scale, refill_scale = _CLASS_SCALE[surge_mode][route.operation_class]
    result = []
    for kind, (capacity, rate) in values.items():
        capacity = max(1, int(capacity * capacity_scale))
        rate = max(1, int(rate * refill_scale))
        if kind == 'aggregate':
            digest = deriver.digest('aggregate', partition)
        else:
            if kind not in identities:
                raise InvalidConfiguration('Required verified identity missing')
            digest = identities[kind]
        ttl = (capacity*1000000 + rate-1)//rate + 1000
        result.append(BucketRequest(digest, BucketSpec(partition, capacity, rate, 1, ttl)))
    return tuple(result)
