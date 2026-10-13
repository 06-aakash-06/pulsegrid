from types import SimpleNamespace

from doctor_service.admission import (
    PHASE8_BENCHMARK_AUTH_BUDGETS,
    PHASE8_BENCHMARK_HOSTS,
    PHASE8_BENCHMARK_PREAUTH_BUDGETS,
    phase8_benchmark_identity_allowed,
    phase8_benchmark_policy,
    policy_for,
)
from pulsegrid_rate_limiter.policies import BUDGETS, PREAUTH


def request(host, method, template):
    return SimpleNamespace(
        url=SimpleNamespace(hostname=host),
        method=method,
        scope={"route": SimpleNamespace(path=template)},
    )


def test_benchmark_policy_is_disabled_by_default_and_for_normal_host():
    route = policy_for("doctor", "GET", "/api/v1/doctors")
    route_policy = SimpleNamespace(operation_class="C")
    assert phase8_benchmark_policy(
        request("phase8-one.localhost", "GET", "/api/v1/doctors"),
        route_policy,
        enabled=False,
    ) is None
    assert phase8_benchmark_policy(
        request("127.0.0.1", "GET", "/api/v1/doctors"), route_policy, enabled=True
    ) is None


def test_benchmark_policy_is_limited_to_authenticated_read_route_templates():
    assert PHASE8_BENCHMARK_HOSTS == {
        "phase8-one.localhost",
        "phase8-two.localhost",
    }
    for template, method, operation_class in (
        ("/api/v1/doctors", "GET", "C"),
        ("/api/v1/doctors/autocomplete", "GET", "C"),
        ("/api/v1/doctors/{doctor_id}", "GET", "B"),
    ):
        normal_policy, _ = policy_for("doctor", method, template)
        for host in PHASE8_BENCHMARK_HOSTS:
            policy = phase8_benchmark_policy(
                request(host, method, template),
                SimpleNamespace(operation_class=operation_class),
                enabled=True,
            )
            assert policy is not None
            assert policy.policy == "directory_search"
            assert policy.family == "phase8_benchmark"
            assert policy.policy_id == "doctor_directory_search_phase8_benchmark"
            assert policy.operation_class == operation_class
        assert normal_policy in ("directory_search", "owner_read")

    assert phase8_benchmark_policy(
        request("phase8-one.localhost", "POST", "/api/v1/doctors"),
        SimpleNamespace(operation_class="B"),
        enabled=True,
    ) is None
    assert phase8_benchmark_policy(
        request("phase8-two.localhost", "GET", "/api/v1/doctors/{doctor_id}/schedule-proposals"),
        SimpleNamespace(operation_class="B"),
        enabled=True,
    ) is None


def test_finite_benchmark_budgets_do_not_change_normal_quotas():
    assert PHASE8_BENCHMARK_PREAUTH_BUDGETS == {
        "source": (10000, 2000000),
        "aggregate": (20000, 2000000),
    }
    assert PHASE8_BENCHMARK_AUTH_BUDGETS == {
        "principal": (10000, 2000000),
        "aggregate": (20000, 2000000),
    }
    assert dict(PREAUTH) == {"source": (30, 2000), "aggregate": (300, 30000)}
    assert dict(BUDGETS["directory_search"]) == {
        "principal": (60, 10000),
        "aggregate": (600, 100000),
    }


def test_benchmark_budget_is_bound_to_the_configured_verified_principal():
    assert phase8_benchmark_identity_allowed("1234", "1234")
    assert not phase8_benchmark_identity_allowed("1235", "1234")
    assert not phase8_benchmark_identity_allowed("01234", "01234")
    assert not phase8_benchmark_identity_allowed("benchmark", "benchmark")
