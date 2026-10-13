#!/usr/bin/env python3
"""Run the fixed six-condition, tracing-free Phase 8.2 Doctor matrix."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Mapping, Sequence

import httpx

import run_matrix as phase8
from benchmark import AuthenticatedActor, load_private_fixture, workload_specs


ROOT = phase8.ROOT
OUTPUT_ROOT = ROOT / "experiments/phase8/results"
API_SERVICES = tuple(phase8.PHASE82_API_CONTAINERS)
NORMAL_COMPOSE_SERVICES = (
    "patient",
    "doctor",
    "doctor_replica",
    "appointment",
    "records",
    "pharmacy",
    "billing",
    "emergency",
    "traefik",
    "grafana",
    "tempo",
    "otel-collector",
)


async def wait_for_containers(
    names: Sequence[str], timeout_seconds: float = 120.0
) -> dict[str, dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, dict[str, Any]] = {}
    while time.monotonic() < deadline:
        last = {name: phase8.inspect_container(name) for name in names}
        if all(
            item["status"] == "running" and item["health"] in ("healthy", None)
            for item in last.values()
        ):
            return last
        await asyncio.sleep(2.0)
    raise phase8.ExperimentStopped(f"services did not become healthy: {last}")


async def wait_for_all_prometheus_targets(timeout_seconds: float = 60.0) -> tuple[dict[str, Any], dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    last_snapshot: dict[str, Any] = {}
    last_health: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last_snapshot = phase8.prometheus_snapshot("final-restored-targets")
        try:
            last_health = phase8.verify_all_prometheus_targets(last_snapshot)
            return last_snapshot, last_health
        except phase8.ExperimentStopped:
            await asyncio.sleep(2.0)
    raise phase8.ExperimentStopped(f"Prometheus targets did not all recover: {last_health}")


async def wait_for_hospital_prometheus_targets(
    timeout_seconds: float = 60.0,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    attempts = 0
    transient_failures: list[str] = []
    last_snapshot: dict[str, Any] = {}
    while time.monotonic() < deadline:
        attempts += 1
        last_snapshot = phase8.prometheus_snapshot("phase8-2-tracing-disabled-before-load")
        try:
            api_health = phase8.verify_prometheus_targets(last_snapshot)
            all_health = phase8.verify_all_prometheus_targets(last_snapshot)
            return last_snapshot, api_health, all_health, {
                "attempts": attempts,
                "waited_seconds": round(min(time.monotonic() - (deadline - timeout_seconds), timeout_seconds), 2),
                "transient_failures": transient_failures,
                "all_targets_recovered": True,
            }
        except phase8.ExperimentStopped as error:
            transient_failures.append(str(error))
            await asyncio.sleep(2.0)
    raise phase8.ExperimentStopped(
        "Prometheus hospital API targets did not recover after service recreation; "
        f"attempts={attempts}, last_failure={transient_failures[-1] if transient_failures else 'none'}"
    )


def host_load_average_1m() -> float | None:
    try:
        return float(os.getloadavg()[0])
    except (AttributeError, OSError):
        return None


def check_baseline_pressure(snapshot: Mapping[str, Any], free_memory: float | None) -> None:
    if float(snapshot["docker_vm_memory_percent"]) >= 90.0:
        raise phase8.ExperimentStopped("Docker VM memory was already at 90% before the matrix")
    cpu_limit = 100.0 * float(snapshot["docker_vm_cpu_count"])
    if float(snapshot["docker_container_cpu_percent_sum"]) >= 0.90 * cpu_limit:
        raise phase8.ExperimentStopped("Docker VM CPU was already at 90% before the matrix")
    if free_memory is not None and free_memory < phase8.PHASE82_HOST_FREE_MEMORY_STOP_PERCENT:
        raise phase8.ExperimentStopped("macOS reported less than 10% free memory before the matrix")
    host_load_1m = host_load_average_1m()
    host_cpu_count = os.cpu_count() or 0
    if host_load_1m is not None and host_cpu_count and host_load_1m >= 0.90 * host_cpu_count:
        raise phase8.ExperimentStopped("macOS one-minute load was already at 90% of host CPUs")
    hot = [
        item["container"]
        for item in snapshot["pulsegrid_container_samples"]
        if item.get("memory_percent_of_limit") is not None
        and float(item["memory_percent_of_limit"]) >= 90.0
    ]
    if hot:
        raise phase8.ExperimentStopped(
            "a PulseGrid container was already at 90% of its limit: " + ", ".join(hot)
        )


def assert_patient_tracing_disabled() -> dict[str, Any]:
    container = phase8.PHASE82_API_CONTAINERS["patient"]
    enabled = phase8.compose_env_value(container, "PULSEGRID_TELEMETRY_ENABLED")
    endpoint = phase8.compose_env_value(container, "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    expected_command = "--configFile=/etc/traefik/traefik.phase8-benchmark.yaml"
    command = json.loads(
        phase8.run_command(
            "docker", "inspect", "--format", "{{json .Config.Cmd}}", "pulsegrid-traefik-1"
        )
    ) or []
    static_hash = phase8.mounted_traefik_static_sha256(
        "/etc/traefik/traefik.phase8-benchmark.yaml"
    )
    expected_hash = phase8.sha256(phase8.PHASE82_TRAEFIK_CONFIG.read_bytes())
    if enabled != "false" or endpoint not in (None, ""):
        raise phase8.ExperimentStopped("Patient tracing was not disabled before authenticated setup")
    if expected_command not in command or static_hash != expected_hash:
        raise phase8.ExperimentStopped("Traefik tracing was not disabled before authenticated setup")
    return {
        "patient_telemetry_enabled": enabled,
        "patient_trace_endpoint": endpoint,
        "traefik_command": command,
        "traefik_static_config_sha256": static_hash,
    }


def assert_benchmark_policy_enabled(principal_id: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in ("pulsegrid-doctor-1", "pulsegrid-doctor_replica-1"):
        phase8.run_command(
            "docker",
            "exec",
            name,
            "python",
            "-c",
            "from doctor_service.admission import PHASE8_BENCHMARK_HOSTS; "
            "assert PHASE8_BENCHMARK_HOSTS == "
            "frozenset({'phase8-one.localhost', 'phase8-two.localhost'})",
        )
        enabled = phase8.compose_env_value(name, "PULSEGRID_DOCTOR_PHASE8_BENCHMARK_ENABLED")
        configured_id = phase8.compose_env_value(
            name, "PULSEGRID_DOCTOR_PHASE8_BENCHMARK_PRINCIPAL_ID"
        )
        if enabled != "true" or configured_id != principal_id:
            raise phase8.ExperimentStopped(f"the reviewed benchmark policy was not active in {name}")
        result[name] = {"enabled": enabled, "principal_matches_verified_jwt": True}
    return result


async def run_phase82_matrix(args: argparse.Namespace) -> None:
    output = Path(args.output).resolve()
    if not output.is_relative_to(OUTPUT_ROOT):
        raise RuntimeError("Phase 8.2 results must be stored under experiments/phase8/results")
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise RuntimeError("the Phase 8.2 result directory is not empty; refusing to overwrite")

    starting_commit = phase8.run_command("git", "rev-parse", "HEAD")
    branch = phase8.run_command("git", "branch", "--show-current")
    if branch != "main":
        raise RuntimeError(f"Phase 8.2 requires local main; current branch is {branch}")
    fixture_state, doctor_id = load_private_fixture(Path(args.fixture).resolve())
    fixture_seed_hash = phase8.sha256(str(fixture_state.get("run", "")).encode())[:16]
    patient_data = fixture_state["actors"]["patient"]
    admin_data, admin_seed_hash = phase8.load_private_admin_fixture(
        Path(args.admin_fixture).resolve()
    )

    progress_path = output / "progress.json"
    progress = phase8.load_progress(progress_path, args.run_id, starting_commit)
    if progress.get("started_cases") or progress.get("completed_cases") or progress.get("interrupted_cases"):
        raise RuntimeError("Phase 8.2 runs are not resumed or repeated under the same run ID")
    if Path(phase8.mounted_traefik_route_source()) != phase8.ROUTE_PATH.resolve():
        raise phase8.ExperimentStopped(
            "live Traefik route mount differs from the inspected Phase 4 route source"
        )
    for name in ("pulsegrid-doctor-1", "pulsegrid-doctor_replica-1"):
        enabled = phase8.compose_env_value(name, "PULSEGRID_DOCTOR_PHASE8_BENCHMARK_ENABLED")
        principal = phase8.compose_env_value(
            name, "PULSEGRID_DOCTOR_PHASE8_BENCHMARK_PRINCIPAL_ID"
        )
        if enabled == "true" or principal is not None:
            raise phase8.ExperimentStopped(
                f"benchmark-only Doctor admission was already configured in {name} before setup"
            )
    original_route_hash = phase8.sha256(phase8.ROUTE_PATH.read_bytes())

    patient = AuthenticatedActor(args.base_url, patient_data)
    admin = AuthenticatedActor(args.base_url, admin_data)
    benchmark_client: httpx.AsyncClient | None = None
    trace_overlay_attempted = False
    benchmark_overlay_attempted = False
    benchmark_routes_attempted = False
    tracing_components_stopped = False
    completion_error: str | None = None
    normal_policy_path = ROOT / "components/rate_limiter/src/pulsegrid_rate_limiter/policies.py"
    normal_policy_hash_before = phase8.sha256(normal_policy_path.read_bytes())
    previous_principal = os.environ.get("PHASE8_BENCHMARK_PRINCIPAL_ID")
    initial_context = phase8.capture_host_context()
    initial_context["host_load_average_1m"] = host_load_average_1m()
    phase8.assert_core_healthy(initial_context["containers"])
    initial_readiness = await phase8.api_readiness(args.base_url)
    if any(status != 200 for status in initial_readiness.values()):
        raise phase8.ExperimentStopped("all seven readiness routes must be healthy before setup")
    initial_prometheus = phase8.prometheus_snapshot("normal-before-phase8-2")
    initial_api_targets = phase8.verify_prometheus_targets(initial_prometheus)
    initial_all_targets = phase8.verify_all_prometheus_targets(initial_prometheus)
    initial_pressure = phase8.capture_docker_pressure()
    initial_mac_free = phase8.capture_mac_memory_free_percent()
    original_tracing: dict[str, Any] = {}
    original_tracing = phase8.restored_tracing_snapshot()
    if phase8.mounted_traefik_route_sha256() != original_route_hash:
        raise phase8.ExperimentStopped("live Traefik route hash differs from the original route file")
    check_baseline_pressure(initial_pressure, initial_mac_free)

    route = phase8.DoctorRoute(phase8.ROUTE_PATH)

    manifest: dict[str, Any] = {
        "run_id": args.run_id,
        "status": "running",
        "label": "Authenticated HTTP scalability, distributed tracing disabled.",
        "started_utc": phase8.utc_now(),
        "branch": branch,
        "starting_commit": starting_commit,
        "requested_base_commit": "2a6df3a",
        "benchmark_harness_commit": starting_commit,
        "active_traefik_route_file": str(phase8.ROUTE_PATH.relative_to(ROOT)),
        "route_file_sha256_before": route.original_hash,
        "normal_traefik_static_sha256_before": phase8.sha256(
            (ROOT / "infra/traefik/traefik.yaml").read_bytes()
        ),
        "phase8_2_traefik_static_sha256": phase8.sha256(
            phase8.PHASE82_TRAEFIK_CONFIG.read_bytes()
        ),
        "phase8_2_tracing_compose_sha256": phase8.sha256(
            (ROOT / phase8.PHASE82_COMPOSE_FILE).read_bytes()
        ),
        "benchmark_admission_compose_sha256": phase8.sha256(
            (ROOT / phase8.BENCHMARK_COMPOSE_FILE).read_bytes()
        ),
        "normal_compose_configuration_sha256": phase8.compose_configuration_hash(),
        "normal_policy_source_sha256_before": normal_policy_hash_before,
        "fixture_seed_sha256_prefix": fixture_seed_hash,
        "admin_fixture_seed_sha256_prefix": admin_seed_hash,
        "dataset": {
            "actor_role": "synthetic patient",
            "doctor_profiles": "preflight counts recorded without names or IDs",
            "synthetic_fixture": str(Path(args.fixture).resolve()),
            "admin_fixture": str(Path(args.admin_fixture).resolve()),
        },
        "request_mix": {"directory": 0.5, "autocomplete": 0.3, "profile": 0.2},
        "endpoint_methods": "authenticated GET only",
        "query_seed": 20261013,
        "concurrency_levels": list(phase8.PHASE82_CONCURRENCIES),
        "replica_counts": list(phase8.PHASE82_REPLICAS),
        "trial_order": [
            {"trial": index, "replicas": replicas, "concurrency": concurrency}
            for index, (replicas, concurrency) in enumerate(phase8.PHASE82_CASES, start=1)
        ],
        "trials_per_condition": 1,
        "planned_trial_count": 6,
        "warmup_seconds": 5,
        "measurement_seconds": 30,
        "timeout_seconds": 5,
        "retry_policy": "none",
        "single_trial_statistical_limit": "limited repeatability evidence; not a population estimate",
        "tracing": {
            "disabled_components": [
                "OpenTelemetry SDK span creation and OTLP export in Patient, Doctor, Doctor replica, Appointment, Records, Pharmacy, Billing and Emergency",
                "Traefik OTLP tracing exporter (benchmark static config; Prometheus metrics retained)",
                "OpenTelemetry Collector container stopped during all trials",
                "Tempo container stopped during all trials",
            ],
            "prometheus_and_http_metrics_remain_enabled": True,
            "same_configuration_for_both_topologies": True,
            "trace_data_or_volumes_modified": False,
        },
        "benchmark_admission_policy": {
            "policy_id": "doctor_directory_search_phase8_benchmark",
            "redis_enabled": True,
            "separate_finite_policy_namespace": True,
            "normal_keyspace_unchanged": True,
            "preauth_budgets_capacity_and_milli_tokens_per_second": {
                "source": [10000, 2000000],
                "aggregate": [20000, 2000000],
            },
            "authenticated_budgets_capacity_and_milli_tokens_per_second": {
                "principal": [10000, 2000000],
                "aggregate": [20000, 2000000],
            },
            "identity": "one synthetic patient principal; Doctor verifies it against the JWT subject",
            "operation_class": "server-derived directory read; no Emergency or staff priority",
        },
        "resource_stop_conditions": {
            "container_memory_percent": "stop at or above 90% of configured cap for any monitored service",
            "docker_vm_memory_percent": "stop at or above 90% of allocated memory",
            "docker_vm_cpu_percent": "stop after three consecutive 2-second samples at or above 90% of allocated CPUs",
            "macos_free_memory_percent": "stop below 10% free memory",
            "macos_load_average": "stop after three consecutive 2-second samples at or above 90% of host CPU count",
            "http_5xx": "stop if more than 5% in five consecutive 1-second buckets",
            "service_health_or_restart": "stop on required service health failure or restart",
            "resource_sampling": "stop if Docker resource sampling fails",
        },
        "grafana_benchmark_limit": {
            "original_limit_bytes": 256 * 1024 * 1024,
            "temporary_limit_bytes": 384 * 1024 * 1024,
            "reason": "baseline Grafana was at 87.44% of its 256 MiB cap; the uniform temporary 384 MiB cap clears the existing 90% stop threshold while retaining Grafana and Prometheus",
        },
        "hardware_software_before_setup": initial_context,
        "hospital_api_readiness_before_setup": initial_readiness,
        "prometheus_api_targets_before_setup": initial_api_targets,
        "prometheus_targets_before_setup": initial_all_targets,
        "docker_resources_before_setup": initial_pressure,
        "macos_free_memory_percent_before_setup": initial_mac_free,
        "macos_load_average_1m_before_setup": initial_context["host_load_average_1m"],
        "normal_tracing_before_setup": original_tracing,
        "normal_admission_policy_source_sha256_before": normal_policy_hash_before,
        "status_events": [],
    }
    phase8.write_json(output / "manifest.json", manifest)
    phase8.write_json(progress_path, progress)
    specs = workload_specs(doctor_id)
    trace_state: dict[str, Any] | None = None

    try:
        phase8.compose_command("config", "--quiet", tracing_disabled=True)
        trace_overlay_attempted = True
        phase8.compose_command(
            "up",
            "-d",
            "--no-deps",
            "--no-build",
            "--force-recreate",
            "patient",
            "traefik",
            tracing_disabled=True,
            timeout=180.0,
        )
        await wait_for_containers(("pulsegrid-patient-1", "pulsegrid-traefik-1"))
        partial_trace_state = assert_patient_tracing_disabled()
        manifest["authenticated_setup_trace_configuration"] = partial_trace_state

        patient_token = patient.login()
        admin.login()
        principal_id = phase8.access_token_subject(patient_token)
        initial_surge = phase8.surge_status(admin.client)
        manifest["initial_surge_status"] = initial_surge
        if initial_surge.get("http_status") != 200 or initial_surge.get("state") != "NORMAL":
            raise phase8.ExperimentStopped("Surge Mode was not NORMAL before the experiment")

        os.environ["PHASE8_BENCHMARK_PRINCIPAL_ID"] = principal_id
        try:
            phase8.compose_command(
                "config", "--quiet", tracing_disabled=True, benchmark_enabled=True
            )
        except BaseException:
            if previous_principal is None:
                os.environ.pop("PHASE8_BENCHMARK_PRINCIPAL_ID", None)
            else:
                os.environ["PHASE8_BENCHMARK_PRINCIPAL_ID"] = previous_principal
            raise

        image_policy_present = phase8.doctor_image_has_benchmark_policy()
        manifest["doctor_image_policy_present_before_setup"] = image_policy_present
        if not image_policy_present:
            phase8.compose_command(
                "build", "doctor", benchmark_enabled=True, tracing_disabled=True, timeout=600.0
            )
        manifest["doctor_image_build_performed"] = not image_policy_present
        benchmark_overlay_attempted = True
        # Traefik reserves the first edge address. Recreate it before API
        # containers so Docker cannot hand that address to a dynamically
        # addressed service while the gateway is absent.
        phase8.compose_command(
            "up",
            "-d",
            "--no-deps",
            "--no-build",
            "--force-recreate",
            "traefik",
            "grafana",
            benchmark_enabled=True,
            tracing_disabled=True,
            timeout=240.0,
        )
        await wait_for_containers(("pulsegrid-traefik-1", "pulsegrid-grafana-1"))
        phase8.compose_command(
            "up",
            "-d",
            "--no-deps",
            "--no-build",
            "--force-recreate",
            *API_SERVICES,
            benchmark_enabled=True,
            tracing_disabled=True,
            timeout=240.0,
        )
        await wait_for_containers(
            (*phase8.PHASE82_API_CONTAINERS.values(), "pulsegrid-prometheus-1", "pulsegrid-grafana-1")
        )
        trace_overlay_verified = phase8.assert_tracing_disabled(require_stopped=False)
        manifest["tracing_disabled_configuration_before_stop"] = trace_overlay_verified
        manifest["benchmark_policy_process_checks"] = assert_benchmark_policy_enabled(principal_id)
        readiness_before = await phase8.api_readiness(args.base_url)
        manifest["hospital_api_readiness_before_matrix"] = readiness_before
        if any(status != 200 for status in readiness_before.values()):
            raise phase8.ExperimentStopped("one or more hospital API readiness routes failed")
        manifest["doctor_http_metrics_active"] = phase8.assert_doctor_http_metrics_active()
        (
            prometheus_before,
            api_targets_before_matrix,
            all_targets_before_matrix,
            prometheus_target_wait,
        ) = await wait_for_hospital_prometheus_targets()
        manifest["prometheus_api_targets_before_matrix"] = api_targets_before_matrix
        manifest["prometheus_targets_before_matrix"] = all_targets_before_matrix
        manifest["prometheus_target_readiness_wait_before_matrix"] = prometheus_target_wait
        phase8.write_snapshot(output / "metrics" / "tracing-disabled-before-load.json", prometheus_before)
        phase8.compose_command(
            "stop",
            "tempo",
            "otel-collector",
            benchmark_enabled=True,
            tracing_disabled=True,
            timeout=60.0,
        )
        tracing_components_stopped = True
        trace_state = phase8.assert_tracing_disabled()
        manifest["tracing_disabled_configuration"] = trace_state
        manifest["tracing_component_stop_utc"] = phase8.utc_now()

        after_setup_pressure = phase8.capture_docker_pressure()
        after_setup_mac_free = phase8.capture_mac_memory_free_percent()
        check_baseline_pressure(after_setup_pressure, after_setup_mac_free)
        manifest["docker_resources_after_setup"] = after_setup_pressure
        manifest["macos_free_memory_percent_after_setup"] = after_setup_mac_free
        manifest["macos_load_average_1m_after_setup"] = host_load_average_1m()
        phase8.write_json(output / "metrics" / "tracing-disabled-resource-preflight.json", after_setup_pressure)

        token = patient.refresh_if_expiring()
        normal_before = phase8.doctor_normal_admission_counters()
        async with httpx.AsyncClient(
            base_url=args.base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=5.0,
            trust_env=False,
        ) as normal_client:
            normal_response = await normal_client.get(
                "/api/v1/doctors", params={"q": "Synthetic", "limit": "20"}
            )
        normal_after = phase8.doctor_normal_admission_counters()
        normal_delta = sum(normal_after.values()) - sum(normal_before.values())
        if normal_response.status_code != 200 or normal_delta <= 0:
            raise phase8.ExperimentStopped(
                "normal Doctor quota was not active through Redis before benchmark preflight"
            )
        manifest["normal_admission_control"] = {
            "normal_host_status": normal_response.status_code,
            "redis_counter_before_by_replica": normal_before,
            "redis_counter_after_by_replica": normal_after,
            "redis_counter_delta": normal_delta,
            "policy_source_sha256": normal_policy_hash_before,
        }

        benchmark_client = phase8.http_client(args.base_url, token, 64, benchmark_host=True)
        phase8_route_hash_before = phase8.mounted_traefik_route_sha256()
        benchmark_routes_attempted = True
        route.activate()
        phase8.compose_command(
            "up",
            "-d",
            "--no-deps",
            "--no-build",
            "--force-recreate",
            "traefik",
            benchmark_enabled=True,
            tracing_disabled=True,
            timeout=180.0,
        )
        manifest["traefik_route_sha256_before_benchmark_reload"] = phase8_route_hash_before
        manifest["benchmark_traefik_container"] = await phase8.wait_for_traefik_service()
        mounted_hash = phase8.mounted_traefik_route_sha256()
        manifest["benchmark_traefik_route_sha256"] = mounted_hash
        if mounted_hash != phase8.sha256(route.benchmark_routes):
            raise phase8.ExperimentStopped("live Traefik did not load the benchmark route file")
        if Path(phase8.mounted_traefik_route_source()) != route.path.resolve():
            raise phase8.ExperimentStopped("live benchmark routing uses an unexpected route source")
        phase8.assert_tracing_disabled()

        benchmark_client.headers["Host"] = route.set_replicas(1)
        manifest["authenticated_endpoint_preflight"] = await phase8.preflight(
            benchmark_client, specs
        )
        topology: dict[str, Any] = {}
        for replicas in phase8.PHASE82_REPLICAS:
            benchmark_client.headers["Host"] = route.set_replicas(replicas)
            topology[str(replicas)] = await phase8.verify_replica_topology(
                benchmark_client, specs["profile"], output, replicas
            )
        manifest["replica_routing_preflight"] = topology

        benchmark_client.headers["Host"] = route.set_replicas(1)
        normal_before_preflight = phase8.doctor_normal_admission_counters()
        preflight = await phase8.admission_preflight(
            output=output,
            run_id=args.run_id,
            client=benchmark_client,
            specs=specs,
            tracing_disabled=True,
        )
        normal_after_preflight = phase8.doctor_normal_admission_counters()
        normal_preflight_delta = sum(normal_after_preflight.values()) - sum(
            normal_before_preflight.values()
        )
        if normal_preflight_delta != 0:
            raise phase8.ExperimentStopped(
                "benchmark preflight also incremented the normal Doctor admission counters"
            )
        if not preflight.get("prometheus_backend", {}).get("redis_observed"):
            raise phase8.ExperimentStopped("benchmark-specific Redis admission was not observed")
        manifest["normal_admission_counters_unchanged_during_preflight"] = {
            "before_by_replica": normal_before_preflight,
            "after_by_replica": normal_after_preflight,
            "delta": normal_preflight_delta,
        }
        manifest["admission_preflight"] = preflight
        trace_state_after_preflight = phase8.assert_tracing_disabled()
        if trace_state_after_preflight != trace_state:
            raise phase8.ExperimentStopped("the tracing configuration changed after the preflight")
        trace_state = trace_state_after_preflight
        manifest["tracing_disabled_configuration"] = trace_state
        manifest["preflight_completed_utc"] = phase8.utc_now()
        phase8.write_json(output / "manifest.json", manifest)
        progress.setdefault("completed_stages", []).append("preflight")
        phase8.write_json(progress_path, progress)

        for trial_number, (replicas, concurrency) in enumerate(phase8.PHASE82_CASES, start=1):
            case_id = f"r{replicas}-c{concurrency}-t1"
            if trace_state != phase8.assert_tracing_disabled():
                raise phase8.ExperimentStopped("tracing-free settings changed between matrix trials")
            benchmark_client.headers["Host"] = route.set_replicas(replicas)
            token = patient.refresh_if_expiring()
            benchmark_client.headers["Authorization"] = f"Bearer {token}"
            summary = await phase8.run_trial(
                output=output,
                run_id=args.run_id,
                progress=progress,
                progress_path=progress_path,
                client=benchmark_client,
                specs=specs,
                case_id=case_id,
                scenario="mixed_read",
                concurrency=concurrency,
                trial=1,
                level={4: "low", 16: "medium", 64: "high"}[concurrency],
                replicas=replicas,
                seed=20261013,
                tracing_disabled=True,
            )
            if summary.get("partial_measurement"):
                raise phase8.ExperimentStopped(f"{case_id} did not complete its full 30-second window")
            manifest.setdefault("completed_trials", []).append(
                {"trial": trial_number, "case_id": case_id, "summary": summary}
            )
            manifest.setdefault("tracing_configuration_by_trial", {})[case_id] = trace_state
            phase8.write_json(output / "manifest.json", manifest)

        expected_cases = {f"r{replicas}-c{concurrency}-t1" for replicas, concurrency in phase8.PHASE82_CASES}
        if set(progress.get("completed_cases", [])) != expected_cases:
            raise phase8.ExperimentStopped("the fixed six-trial matrix did not complete exactly once")
        if len(manifest.get("completed_trials", [])) != 6:
            raise phase8.ExperimentStopped("the six planned HTTP conditions were not all recorded")
        normal_after_matrix = phase8.doctor_normal_admission_counters()
        normal_matrix_delta = sum(normal_after_matrix.values()) - sum(normal_after_preflight.values())
        if normal_matrix_delta != 0:
            raise phase8.ExperimentStopped(
                "measured benchmark traffic incremented the normal Doctor admission counters"
            )
        manifest["normal_admission_counters_unchanged_during_matrix"] = {
            "before_by_replica": normal_after_preflight,
            "after_by_replica": normal_after_matrix,
            "delta": normal_matrix_delta,
        }
        manifest["matrix_summary"] = phase8.matrix_summary(output, trial_numbers=(1,))
        manifest["matrix_summary"]["trial_order"] = manifest["trial_order"]
        manifest["status"] = "completed"
        manifest["matrix_completed_utc"] = phase8.utc_now()
        phase8.write_json(output / "summaries" / "matrix_summary.json", manifest["matrix_summary"])
        progress.setdefault("completed_stages", []).append("matrix")
        phase8.write_json(progress_path, progress)
    except BaseException as error:
        completion_error = f"{type(error).__name__}: {str(error)[:600]}"
        manifest["status"] = "partial"
        manifest["error"] = completion_error
        if isinstance(error, phase8.ExperimentStopped):
            manifest["stop_condition"] = str(error)
        progress["last_error"] = completion_error
        phase8.write_json(progress_path, progress)
    finally:
        if benchmark_client is not None:
            await benchmark_client.aclose()

        try:
            restored_hash = route.restore()
            manifest["route_file_sha256_after"] = restored_hash
            manifest["route_restored"] = restored_hash == route.original_hash
        except Exception as restore_error:
            manifest["route_restore_error"] = f"{type(restore_error).__name__}: {str(restore_error)[:400]}"
            manifest["status"] = "partial"

        if trace_overlay_attempted or benchmark_overlay_attempted or benchmark_routes_attempted or tracing_components_stopped:
            try:
                if benchmark_overlay_attempted:
                    await asyncio.sleep(12.0)
                    manifest["benchmark_redis_bucket_ttl_wait_seconds"] = 12
                # Recreate the gateway first to claim its reserved edge IP;
                # the API containers use dynamically assigned edge addresses.
                phase8.compose_command(
                    "up",
                    "-d",
                    "--no-deps",
                    "--no-build",
                    "--force-recreate",
                    "traefik",
                    timeout=240.0,
                )
                await wait_for_containers(("pulsegrid-traefik-1",))
                phase8.compose_command(
                    "up",
                    "-d",
                    "--no-deps",
                    "--no-build",
                    "--force-recreate",
                    *API_SERVICES,
                    "grafana",
                    "tempo",
                    "otel-collector",
                    timeout=240.0,
                )
                await wait_for_containers(
                    (*phase8.PHASE82_API_CONTAINERS.values(), "pulsegrid-prometheus-1", "pulsegrid-grafana-1", "pulsegrid-tempo-1", "pulsegrid-otel-collector-1")
                )
                normal_route_hash = phase8.mounted_traefik_route_sha256()
                normal_route_source = phase8.mounted_traefik_route_source()
                if (
                    normal_route_hash != route.original_hash
                    or Path(normal_route_source) != route.path.resolve()
                    or phase8.DoctorRoute.BENCHMARK_NAME in route.path.read_bytes()
                ):
                    raise phase8.ExperimentStopped("normal Traefik route was not fully restored")
                manifest["normal_traefik_route_sha256"] = normal_route_hash
                manifest["normal_traefik_route_source"] = normal_route_source
                manifest["tracing_restored"] = phase8.restored_tracing_snapshot()

                tempo_ready = phase8.run_command(
                    "docker", "exec", "pulsegrid-grafana-1", "curl", "-fsS", "--max-time", "5",
                    "http://tempo:3200/ready",
                )
                if tempo_ready != "ready":
                    raise phase8.ExperimentStopped("Tempo readiness did not recover after restoration")
                manifest["tempo_ready_after_restore"] = True

                for name in ("pulsegrid-doctor-1", "pulsegrid-doctor_replica-1"):
                    enabled = phase8.compose_env_value(name, "PULSEGRID_DOCTOR_PHASE8_BENCHMARK_ENABLED")
                    principal = phase8.compose_env_value(name, "PULSEGRID_DOCTOR_PHASE8_BENCHMARK_PRINCIPAL_ID")
                    if enabled == "true" or principal is not None:
                        raise phase8.ExperimentStopped("benchmark-only Doctor admission remained configured")
                manifest["benchmark_admission_restored"] = True
                manifest["normal_policy_source_sha256_after"] = phase8.sha256(normal_policy_path.read_bytes())
                if manifest["normal_policy_source_sha256_after"] != normal_policy_hash_before:
                    raise phase8.ExperimentStopped("normal admission policy source changed during the run")

                readiness_after = await phase8.api_readiness(args.base_url)
                manifest["hospital_api_readiness_after"] = readiness_after
                if any(status != 200 for status in readiness_after.values()):
                    raise phase8.ExperimentStopped("one or more API readiness routes failed after restoration")

                if patient.access_token is not None:
                    patient_token = patient.refresh_if_expiring()
                    normal_before = phase8.doctor_normal_admission_counters()
                    async with httpx.AsyncClient(
                        base_url=args.base_url.rstrip("/"),
                        headers={"Authorization": f"Bearer {patient_token}"},
                        timeout=5.0,
                        trust_env=False,
                    ) as normal_client:
                        directory = await normal_client.get(
                            "/api/v1/doctors", params={"q": "Synthetic", "limit": "20"}
                        )
                    normal_after = phase8.doctor_normal_admission_counters()
                    normal_delta = sum(normal_after.values()) - sum(normal_before.values())
                    manifest["normal_admission_restored"] = {
                        "authenticated_directory_status": directory.status_code,
                        "redis_counter_delta": normal_delta,
                        "redis_counter_before_by_replica": normal_before,
                        "redis_counter_after_by_replica": normal_after,
                    }
                    if directory.status_code != 200 or normal_delta <= 0:
                        raise phase8.ExperimentStopped("normal Redis-backed Doctor admission did not recover")

                async with httpx.AsyncClient(
                    base_url=args.base_url.rstrip("/"), timeout=5.0, trust_env=False
                ) as unauthenticated:
                    emergency = await unauthenticated.get("/api/v1/emergencies")
                manifest["unauthenticated_emergency_status"] = emergency.status_code
                if emergency.status_code not in (401, 403):
                    raise phase8.ExperimentStopped("Emergency authorization did not reject an unauthenticated read")

                if admin.access_token is not None:
                    admin.refresh_if_expiring()
                    final_surge = phase8.surge_status(admin.client)
                    manifest["final_surge_status"] = final_surge
                    if final_surge.get("http_status") != 200 or final_surge.get("state") != "NORMAL":
                        raise phase8.ExperimentStopped("Surge Mode was not NORMAL after restoration")

                final_snapshot, all_target_health = await wait_for_all_prometheus_targets()
                manifest["prometheus_api_targets_after_restore"] = phase8.verify_prometheus_targets(final_snapshot)
                manifest["prometheus_targets_after_restore"] = all_target_health
                phase8.write_snapshot(output / "metrics" / "final-restored-targets.json", final_snapshot)
                manifest["doctor_http_metrics_active_after_restore"] = phase8.assert_doctor_http_metrics_active()
                manifest["docker_resources_after_restore"] = phase8.capture_docker_pressure()
                deployment_config_status = phase8.run_command(
                    "git",
                    "status",
                    "--short",
                    "--",
                    "compose.yaml",
                    "compose.phase4.yaml",
                    "compose.observability.yaml",
                    "compose.phase8-benchmark.yaml",
                    phase8.PHASE82_COMPOSE_FILE,
                    "infra/phase4/routes.yaml",
                    "infra/traefik/traefik.yaml",
                    phase8.PHASE82_TRAEFIK_CONFIG.relative_to(ROOT).as_posix(),
                )
                if deployment_config_status:
                    raise phase8.ExperimentStopped("deployment configuration has uncommitted changes after restoration")
                manifest["uncommitted_deployment_configuration_changes"] = False
                manifest["deployment_restoration_verified"] = True
            except Exception as verify_error:
                manifest["status"] = "partial"
                manifest["deployment_restoration_verified"] = False
                manifest["restoration_verification_error"] = (
                    f"{type(verify_error).__name__}: {str(verify_error)[:600]}"
                )

        if previous_principal is None:
            os.environ.pop("PHASE8_BENCHMARK_PRINCIPAL_ID", None)
        else:
            os.environ["PHASE8_BENCHMARK_PRINCIPAL_ID"] = previous_principal
        for actor in (patient, admin):
            try:
                actor.refresh_if_expiring()
                actor.logout()
            except Exception as logout_error:
                manifest.setdefault("cleanup_errors", []).append(
                    f"synthetic actor logout failed: {type(logout_error).__name__}: {str(logout_error)[:300]}"
                )
                actor.client.close()
        manifest["ended_utc"] = phase8.utc_now()
        if completion_error:
            manifest["error"] = completion_error
        if manifest.get("status") == "completed" and manifest.get("deployment_restoration_verified") is not True:
            manifest["status"] = "partial"
        phase8.write_json(output / "manifest.json", manifest)

    if completion_error or manifest.get("status") != "completed":
        raise SystemExit(completion_error or "Phase 8.2 matrix or deployment restoration was incomplete")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path("/tmp/pulsegrid-phase3-live-fixture.json"),
    )
    parser.add_argument(
        "--admin-fixture",
        type=Path,
        default=Path("/tmp/pulsegrid-phase29-live-fixture.json"),
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--run-id", default="phase8-2-20261013-run1")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output is None:
        args.output = OUTPUT_ROOT / args.run_id
    try:
        asyncio.run(run_phase82_matrix(args))
    except KeyboardInterrupt:
        print("interrupted; normal deployment restoration and logout were attempted", file=sys.stderr)
        raise SystemExit(130)


if __name__ == "__main__":
    main()
