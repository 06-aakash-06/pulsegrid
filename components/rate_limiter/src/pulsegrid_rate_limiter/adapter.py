"""Unmounted admission hooks. Owner verifier/authorization remain authoritative."""
from dataclasses import dataclass
from types import MappingProxyType
from uuid import uuid4
from .policies import IdentityDeriver, RoutePolicy, build_buckets
from .types import Admission, InvalidConfiguration

@dataclass(frozen=True)
class VerifiedIdentity:
    """Returned ONLY by coordinator's existing verifier/current-authority adapter.

    This is a trusted Python port value, never constructed from public headers,
    decoded-but-unverified JWT claims, body roles or route/query IDs.
    """
    subject: str
    kind: str = 'user'
    current_staff: bool = False

class AdmissionAdapter:
    def __init__(self, limiter, owner: str, routes, *, exempt_routes=()):
        self.limiter = limiter
        self.owner = owner
        self.deriver = IdentityDeriver(limiter.config.hmac_secret)
        self.routes = MappingProxyType(dict(routes))
        self.exempt_routes = frozenset(exempt_routes)
        for (method, template), route in self.routes.items():
            if method != method.upper() or not template.startswith('/') or route.owner != owner:
                raise InvalidConfiguration('Invalid reviewed route inventory')
            route.policy_id
        if self.exempt_routes.intersection(self.routes):
            raise InvalidConfiguration('Conflicting exemption')
        # Unknown routes remain bounded, even when no route has matched.
        self.unknown = RoutePolicy(owner, 'auth_session', 'unknown')

    def classify(self, request):
        template = getattr(request.scope.get('route'), 'path', None)
        key = (request.method.upper(), template)
        if request.method.upper() == 'OPTIONS' or key in self.exempt_routes:
            return None
        return self.routes.get(key, self.unknown)

    async def pre_auth(self, request):
        if not self.limiter.config.enabled:
            return Admission(True, None, 0, 'local', 'accepted')
        route = self.classify(request)
        if route is None:
            return Admission(True, None, 0, 'local', 'accepted')
        return await self.limiter.admit(build_buckets(route, {'source': self.deriver.source(request)},
                                                     self.deriver, preauth=True))

    async def post_auth(self, request, verify_identity, *, normalized_account_digest=None):
        """verify_identity awaits retained auth and raises existing 401/403 errors.

        normalized_account_digest comes from Patient's owner-only normalization
        and HMAC helper. Raw passwords/accounts never enter this library.
        """
        route = self.classify(request)
        if route is None or not self.limiter.config.enabled:
            return Admission(True, None, 0, 'local', 'accepted')
        identities = {'source': self.deriver.source(request)}
        try:
            if route.policy not in ('auth_login', 'auth_registration', 'auth_session', 'emergency_public'):
                identity = await verify_identity(request)
                if not isinstance(identity, VerifiedIdentity):
                    raise InvalidConfiguration('Unverified principal port value')
                if route.policy == 'internal_worker':
                    from .policies import OWNERS
                    if identity.kind != 'service' or identity.subject not in OWNERS:
                        raise InvalidConfiguration('Expected verified scoped service')
                    identities['principal'] = self.deriver.digest('service', identity.subject)
                else:
                    if identity.kind != 'user':
                        raise InvalidConfiguration('Expected verified user')
                    identities['principal'] = self.deriver.principal(identity.subject)
                if route.policy in ('critical_staff', 'emergency_staff') and identity.current_staff is not True:
                    raise InvalidConfiguration('Current staff authority required')
            if normalized_account_digest is not None:
                identities['account'] = normalized_account_digest
            buckets = build_buckets(route, identities, self.deriver)
        except (InvalidConfiguration, ValueError, TypeError):
            return Admission(False, 1000, 0, 'local', 'unavailable')
        return await self.limiter.admit(buckets)


def rejection_metadata(admission):
    if admission.allowed:
        return None
    unavailable = admission.reason == 'unavailable'
    status = 503 if unavailable else 429
    code = 'admission_unavailable' if unavailable else 'rate_limited'
    delay = 1 if unavailable else max(1, ((admission.retry_after_ms or 0)+999)//1000)
    return status, code, {'Retry-After': str(delay), 'Cache-Control': 'no-store'}


def rejection_response(request, admission, *, error_response=None):
    """Use owner's safe envelope helper in production; standalone default for tests."""
    metadata = rejection_metadata(admission)
    if metadata is None:
        return None
    status, code, headers = metadata
    message = 'Admission is temporarily unavailable.' if status == 503 else 'Too many requests.'
    if error_response is not None:
        return error_response(request, status, code=code, message=message, headers=headers)
    from fastapi.responses import JSONResponse
    request_id = str(getattr(request.state, 'request_id', uuid4()))
    return JSONResponse(status_code=status, content={'error': {
        'code': code, 'message': message, 'request_id': request_id}}, headers=headers)
