import asyncio
import hashlib
from uuid import uuid4

from pulsegrid_rate_limiter import IdentityDeriver, RateLimiter, RoutePolicy, build_buckets
from pulsegrid_rate_limiter.limiter import SURGE_KEY
from .test_limiter import SECRET, bucket, config


def actor_digest():
    return hashlib.sha256(b'synthetic-hospital-admin').hexdigest()


async def transition(limiter, snapshot, target, *, reason='capacity_pressure', override=False):
    return await limiter.transition_surge_mode(
        snapshot, target, reason_code=reason, operation_id=str(uuid4()),
        actor_digest=actor_digest(), override=override)


async def test_shared_state_cas_cooldown_override_and_recovery(redis_server):
    first = RateLimiter(config(redis_server))
    second = RateLimiter(config(redis_server))
    try:
        normal = await first.surge_mode()
        assert normal.state == 'NORMAL' and normal.version == 0
        assert (await second.surge_mode()).state == 'NORMAL'

        competing = await asyncio.gather(
            transition(first, normal, 'SURGE'),
            transition(second, normal, 'SURGE'))
        assert sorted(result[0] for result in competing) == ['applied', 'conflict']
        surge = await second.surge_mode()
        assert surge.state == 'SURGE' and surge.version == 1

        denied = await transition(second, surge, 'RECOVERY', reason='planned_recovery')
        assert denied[0] == 'cooldown'
        status, previous, recovery = await transition(
            second, surge, 'RECOVERY', reason='incident_override', override=True)
        assert (status, previous, recovery.state, recovery.version) == ('applied', 'SURGE', 'RECOVERY', 2)
        assert (await first.surge_mode()).state == 'RECOVERY'

        denied = await transition(second, recovery, 'SURGE')
        assert denied[0] == 'cooldown'
        status, _, surge_again = await transition(
            first, recovery, 'SURGE', reason='incident_override', override=True)
        assert status == 'applied' and surge_again.state == 'SURGE' and surge_again.version == 3
    finally:
        await first.close()
        await second.close()


async def test_expiry_derives_shared_recovery_then_normal(redis_server):
    limiter = RateLimiter(config(redis_server))
    try:
        now_seconds, now_microseconds = await limiter.redis.time()
        now_ms = now_seconds * 1000 + now_microseconds // 1000
        await limiter.redis.hset(SURGE_KEY, mapping={
            'state': 'SURGE', 'version': '9', 'entered_at_ms': str(now_ms - 30001),
            'expires_at_ms': str(now_ms - 1), 'reason_code': 'capacity_pressure',
            'operation_id': str(uuid4()), 'actor_digest': actor_digest()})
        recovered = await limiter.surge_mode()
        assert recovered.state == 'RECOVERY' and recovered.version == 9
        assert recovered.reason_code == 'surge_expired'

        await limiter.redis.hset(SURGE_KEY, mapping={
            'state': 'RECOVERY', 'version': '10', 'entered_at_ms': str(now_ms - 120001),
            'expires_at_ms': str(now_ms - 1), 'reason_code': 'planned_recovery',
            'operation_id': str(uuid4()), 'actor_digest': actor_digest()})
        normal = await limiter.surge_mode()
        assert normal.state == 'NORMAL' and normal.version == 10
        assert normal.reason_code == 'recovery_elapsed'
    finally:
        await limiter.close()


def test_class_profiles_keep_normal_budget_and_isolate_surge_quotas():
    deriver = IdentityDeriver(SECRET)
    identity = {'principal': deriver.principal('71'), 'source': deriver.digest('source', 'synthetic')}
    critical = RoutePolicy('pharmacy', 'critical_staff', 'command', 'A')
    important = RoutePolicy('appointment', 'appointment_command', 'command', 'B')

    normal = build_buckets(important, identity, deriver)
    assert normal[0].spec.capacity == 30
    assert normal[0].spec.policy_id == important.policy_id
    surge_a = build_buckets(critical, identity, deriver, surge_mode='SURGE')
    surge_b = build_buckets(important, identity, deriver, surge_mode='SURGE')
    recovery_b = build_buckets(important, identity, deriver, surge_mode='RECOVERY')
    unknown_b = build_buckets(important, identity, deriver, surge_mode='UNKNOWN')
    assert surge_a[0].spec.capacity == 120
    assert surge_b[0].spec.capacity == 18
    assert recovery_b[0].spec.capacity == 24
    assert unknown_b[0].spec.capacity == surge_b[0].spec.capacity
    assert surge_a[-1].key_digest != surge_b[-1].key_digest
    assert surge_a[-1].spec.policy_id != surge_b[-1].spec.policy_id


async def test_surge_quotas_are_shared_across_replicas_and_keep_critical_capacity(redis_server):
    first = RateLimiter(config(redis_server))
    second = RateLimiter(config(redis_server))
    deriver = IdentityDeriver(SECRET)
    identity = {'principal': deriver.principal('71')}
    critical = RoutePolicy('emergency', 'emergency_staff', 'staff', 'A')
    deferrable = RoutePolicy('doctor', 'directory_search', 'directory', 'C')
    small_budget = {'principal': (40, 40), 'aggregate': (40, 40)}
    try:
        critical_buckets = build_buckets(critical, identity, deriver,
                                        budgets=small_budget, surge_mode='SURGE')
        deferrable_buckets = build_buckets(deferrable, identity, deriver,
                                          budgets=small_budget, surge_mode='SURGE')
        critical_results = [await first.admit(critical_buckets, surge_mode='SURGE', operation_class='A')
                           for _ in range(8)]
        deferrable_results = [await first.admit(deferrable_buckets, surge_mode='SURGE', operation_class='C')
                              for _ in range(6)]
        deferrable_denied = await second.admit(deferrable_buckets, surge_mode='SURGE', operation_class='C')
        assert all(result.allowed for result in critical_results)
        assert all(result.allowed for result in deferrable_results)
        assert not deferrable_denied.allowed
        assert 165000 <= deferrable_denied.retry_after_ms <= 167000
        assert deferrable_denied.surge_mode == 'SURGE'
        assert deferrable_denied.operation_class == 'C'
    finally:
        await first.close()
        await second.close()


async def test_redis_failure_uses_unknown_protective_profile_and_finite_class_a():
    from .test_limiter import FailedRedis
    limiter = RateLimiter(config(), redis_client=FailedRedis(OSError('offline')))
    try:
        unknown = await limiter.surge_mode()
        assert unknown.state == 'UNKNOWN'
        deriver = IdentityDeriver(SECRET)
        identity = {'principal': deriver.principal('71'), 'aggregate': deriver.digest('aggregate', 'test')}
        def decision(route):
            buckets = build_buckets(route, identity, deriver, surge_mode=unknown.state)
            return limiter.admit(buckets, surge_mode=unknown.state, operation_class=route.operation_class)
        class_a = RoutePolicy('emergency', 'emergency_staff', 'mutation', 'A')
        class_c = RoutePolicy('doctor', 'directory_search', 'directory', 'C')
        protected = await decision(class_a)
        deferred = await decision(class_c)
        assert protected.allowed and protected.reason == 'accepted'
        assert protected.operation_class == 'A' and protected.surge_mode == 'UNKNOWN'
        assert deferred.allowed and deferred.surge_mode == 'UNKNOWN'
        assert len(limiter.local.states) > 0
        assert all(state.spec.capacity < 2**53 for state in limiter.local.states.values())
    finally:
        await limiter.close()


async def test_small_surge_auth_bucket_uses_bounded_four_replica_fallback():
    from pulsegrid_rate_limiter import AdmissionAdapter
    from .test_limiter import FailedRedis

    limiter = RateLimiter(config(max_replicas=4), redis_client=FailedRedis(OSError('offline')))
    adapter = AdmissionAdapter(limiter, 'patient', {})
    route = RoutePolicy('patient', 'auth_login', 'auth')
    identities = {
        'source': adapter.deriver.digest('source', 'synthetic-peer'),
        'account': adapter.deriver.digest('account', 'synthetic-account'),
    }
    try:
        first = await adapter.admit(route, identities)
        second = await adapter.admit(route, identities)
        assert first.allowed and first.mode == 'local' and first.surge_mode == 'UNKNOWN'
        assert not second.allowed and second.mode == 'local' and second.reason == 'limited'
        assert all(state.spec.capacity >= 4 for state in limiter.local.states.values())
        assert all(state.spec.capacity <= 100 for state in limiter.local.states.values())
    finally:
        await limiter.close()


def test_server_owned_operation_classification():
    from pulsegrid_rate_limiter import operation_class_for
    assert operation_class_for('emergency', 'POST', '/api/v1/emergencies') == 'A'
    assert operation_class_for('pharmacy', 'POST', '/api/v1/pharmacy/reservations/{reservation_id}/dispense') == 'A'
    assert operation_class_for('appointment', 'POST', '/api/v1/appointments/operations/surge-mode') == 'A'
    assert operation_class_for('emergency', 'POST', '/api/v1/emergencies/{request_id}/transitions') == 'A'
    assert operation_class_for('appointment', 'POST', '/api/v1/appointments') == 'B'
    assert operation_class_for('doctor', 'GET', '/api/v1/doctors/autocomplete') == 'C'
    assert operation_class_for('billing', 'POST', '/api/v1/billing/invoices/{invoice_id}/insurance-estimates') == 'C'
    assert operation_class_for('billing', 'POST', '/api/v1/billing/insurance-refreshes') == 'C'
