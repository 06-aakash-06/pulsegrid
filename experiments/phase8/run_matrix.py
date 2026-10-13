#!/usr/bin/env python3
"""Run the predeclared, bounded Phase 8 synthetic read matrix."""

from __future__ import annotations

import argparse
import asyncio
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import signal
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping, Sequence

import httpx

from benchmark import (
    AuthenticatedActor,
    RequestSpec,
    load_private_fixture,
    run_burst,
    run_fixed_window,
    summarize_samples,
    warm_up,
    workload_specs,
    write_samples,
)


ROOT = Path(__file__).resolve().parents[2]
ROUTE_PATH = ROOT / "infra/traefik/routes.yaml"
COMPOSE_FILES = (
    "compose.yaml",
    "services/patient/compose.auth.yaml",
    "compose.phase4.yaml",
    "compose.observability.yaml",
)
COMPOSE_PREFIX = [part for filename in COMPOSE_FILES for part in ("-f", filename)]
REQUIRED_CONTAINERS = (
    "pulsegrid-patient-1",
    "pulsegrid-doctor-1",
    "pulsegrid-doctor_replica-1",
    "pulsegrid-appointment-1",
    "pulsegrid-records-1",
    "pulsegrid-pharmacy-1",
    "pulsegrid-billing-1",
    "pulsegrid-emergency-1",
    "pulsegrid-postgres-1",
    "pulsegrid-redis-1",
    "pulsegrid-rabbitmq-1",
    "pulsegrid-traefik-1",
)
RESOURCE_CONTAINERS = (
    "doctor",
    "doctor_replica",
    "postgres",
    "redis",
    "rabbitmq",
    "traefik",
    "prometheus",
    "tempo",
    "grafana",
    "otel-collector",
    "blackbox",
)
PROM_QUERIES = {
    "api_targets": 'sum by (job, service, replica_source) (up{job=~"pulsegrid_api|pulsegrid_readiness"})',
    "doctor_http": 'sum by (replica_source, route, status_class) (pulsegrid_http_requests_total{service="doctor"})',
    "doctor_admission": 'sum by (replica_source, policy, class, state, outcome) (pulsegrid_http_admission_requests_total{owner="doctor"})',
    "doctor_cache": 'sum by (replica_source, outcome) (pulsegrid_cache_requests_total{service="doctor"})',
    "doctor_autocomplete": 'sum by (replica_source, backend, outcome) (pulsegrid_autocomplete_queries_total{service="doctor"})',
    "rabbitmq_queues": 'sum by (queue) (rabbitmq_queue_messages_ready)',
}


class ExperimentStopped(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_command(*args: str, timeout: float = 15.0) -> str:
    result = subprocess.run(
        list(args),
        cwd=ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "command failed"
        raise RuntimeError(f"{shlex.join(args[:2])}: {message[:500]}")
    return result.stdout.strip()


def write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def load_progress(path: Path, run_id: str, starting_commit: str) -> dict[str, Any]:
    if path.exists():
        progress = json.loads(path.read_text())
        if progress.get("run_id") != run_id or progress.get("starting_commit") != starting_commit:
            raise RuntimeError("existing progress file belongs to a different run or commit")
        if progress.get("guardrail_stops"):
            raise RuntimeError("this run stopped on a guardrail and cannot be resumed")
        started = set(progress.get("started_cases", []))
        completed = set(progress.get("completed_cases", []))
        interrupted = sorted(started - completed)
        if interrupted:
            progress.setdefault("interrupted_cases", []).extend(
                case for case in interrupted if case not in progress.get("interrupted_cases", [])
            )
        return progress
    return {
        "run_id": run_id,
        "starting_commit": starting_commit,
        "started_cases": [],
        "completed_cases": [],
        "interrupted_cases": [],
        "guardrail_stops": [],
        "completed_stages": [],
    }


def load_private_admin_fixture(path: Path) -> tuple[dict[str, str], str]:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise ValueError("private admin fixture permissions must be 0600")
    state = json.loads(path.read_text())
    admin = state.get("actors", {}).get("admin")
    if not isinstance(admin, dict) or not admin.get("email") or not admin.get("password"):
        raise ValueError("admin fixture must contain the existing synthetic admin actor")
    fixture_run = str(state.get("run", ""))
    return admin, sha256(fixture_run.encode())[:16]


def mark_case_started(progress: dict[str, Any], path: Path, case_id: str) -> None:
    if case_id in progress.get("started_cases", []):
        raise RuntimeError(f"case {case_id} was already started; it will not be repeated")
    progress.setdefault("started_cases", []).append(case_id)
    write_json(path, progress)


def mark_case_completed(progress: dict[str, Any], path: Path, case_id: str) -> None:
    progress.setdefault("completed_cases", []).append(case_id)
    write_json(path, progress)


def inspect_container(name: str) -> dict[str, Any]:
    state = json.loads(run_command("docker", "inspect", "--format", "{{json .State}}", name))
    raw = run_command(
        "docker",
        "inspect",
        "--format",
        "{{.HostConfig.Memory}} {{.HostConfig.NanoCpus}} {{.RestartCount}} {{.Config.Image}}",
        name,
    )
    memory, nano_cpus, restarts, image = raw.split(" ", 3)
    health = (state.get("Health") or {}).get("Status")
    return {
        "name": name,
        "status": state.get("Status"),
        "health": health,
        "exit_code": state.get("ExitCode"),
        "oom_killed": state.get("OOMKilled"),
        "started_at": state.get("StartedAt"),
        "restart_count": int(restarts),
        "memory_limit_bytes": int(memory),
        "nano_cpus": int(nano_cpus),
        "image": image,
    }


def container_snapshot(names: Sequence[str] = REQUIRED_CONTAINERS) -> dict[str, dict[str, Any]]:
    return {name: inspect_container(name) for name in names}


def assert_core_healthy(snapshot: Mapping[str, Mapping[str, Any]]) -> None:
    unhealthy = [
        name
        for name, item in snapshot.items()
        if item.get("status") != "running" or item.get("health") not in ("healthy", None)
    ]
    if unhealthy:
        raise ExperimentStopped("required containers are not healthy: " + ", ".join(unhealthy))


def capture_host_context() -> dict[str, Any]:
    docker_info = run_command(
        "docker",
        "info",
        "--format",
        "{{.ServerVersion}}|{{.OperatingSystem}}|{{.NCPU}}|{{.MemTotal}}|{{.Containers}}",
    )
    engine, operating_system, cpus, memory, container_count = docker_info.split("|", 4)
    return {
        "host_platform": platform.platform(),
        "host_architecture": platform.machine(),
        "host_cpu_count": os.cpu_count(),
        "host_memory_bytes": int(run_command("sysctl", "-n", "hw.memsize")),
        "python": sys.version.split()[0],
        "docker_engine": engine,
        "docker_vm_os": operating_system,
        "docker_vm_cpus": int(cpus),
        "docker_vm_memory_bytes": int(memory),
        "docker_daemon_container_count": int(container_count),
        "compose_version": run_command("docker", "compose", "version", "--short"),
        "postgres_version": run_command(
            "docker", "exec", "pulsegrid-postgres-1", "psql", "--version"
        ),
        "redis_version": run_command(
            "docker", "exec", "pulsegrid-redis-1", "redis-server", "--version"
        ),
        "rabbitmq_version": run_command(
            "docker", "exec", "pulsegrid-rabbitmq-1", "rabbitmq-diagnostics", "server_version"
        ),
        "containers": container_snapshot(),
    }


def compose_configuration_hash() -> str:
    data = b"\0".join((ROOT / filename).read_bytes() for filename in COMPOSE_FILES)
    return sha256(data)


class DoctorRoute:
    """Temporarily expose the existing Doctor replica through Traefik."""

    PRIMARY_LINE = b"          - url: http://doctor:8000\n"
    REPLICA_LINE = b"          - url: http://doctor_replica:8000\n"

    def __init__(self, path: Path):
        self.path = path
        self.original = path.read_bytes()
        self.mode = stat.S_IMODE(path.stat().st_mode)
        self.original_hash = sha256(self.original)
        self.two_upstream = self._two_upstream_bytes()
        self.backup = Path(tempfile.gettempdir()) / f"pulsegrid-phase8-routes-{self.original_hash[:16]}.bak"
        if self.backup.exists():
            saved = self.backup.read_bytes()
            if saved != self.original:
                current = self.path.read_bytes()
                expected = saved.replace(self.PRIMARY_LINE, self.PRIMARY_LINE + self.REPLICA_LINE, 1)
                if current == expected:
                    self._atomic_write(saved)
                elif current != saved:
                    raise RuntimeError("stale Phase 8 route backup conflicts with current file")
            self.backup.unlink(missing_ok=True)
        self.backup.write_bytes(self.original)
        self.backup.chmod(self.mode)

    def _two_upstream_bytes(self) -> bytes:
        if self.original.count(self.PRIMARY_LINE) != 1 or self.REPLICA_LINE in self.original:
            raise RuntimeError("Doctor route does not match the reviewed single-upstream baseline")
        return self.original.replace(
            self.PRIMARY_LINE, self.PRIMARY_LINE + self.REPLICA_LINE, 1
        )

    def set_replicas(self, count: int) -> None:
        if count == 1:
            desired = self.original
        elif count == 2:
            desired = self.two_upstream
        else:
            raise ValueError("only the predeclared one/two upstream conditions are allowed")
        current = self.path.read_bytes()
        if current not in (self.original, self.two_upstream):
            raise RuntimeError("Traefik route file changed outside this Phase 8 runner")
        self._atomic_write(desired)

    def _atomic_write(self, data: bytes) -> None:
        temporary = self.path.with_suffix(".yaml.phase8-tmp")
        temporary.write_bytes(data)
        temporary.chmod(self.mode)
        os.replace(temporary, self.path)

    def restore(self) -> str:
        current = self.path.read_bytes()
        if current not in (self.original, self.two_upstream):
            raise RuntimeError("route file has an unexpected edit; refusing to overwrite it")
        self._atomic_write(self.original)
        result = sha256(self.path.read_bytes())
        if result != self.original_hash:
            raise RuntimeError("Traefik route restoration hash mismatch")
        self.backup.unlink(missing_ok=True)
        return result


class DockerStatsSampler:
    def __init__(self, interval_seconds: float = 2.0):
        self.interval_seconds = interval_seconds
        self.rows: list[dict[str, Any]] = []
        self.phase = "setup"
        self.task: asyncio.Task[None] | None = None
        self.errors: list[str] = []

    @staticmethod
    def _bytes(value: str) -> int | None:
        match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]+)\s*", value)
        if not match:
            return None
        amount = float(match.group(1))
        unit = match.group(2)
        multipliers = {
            "B": 1,
            "kB": 1000,
            "KB": 1000,
            "KiB": 1024,
            "MB": 1000**2,
            "MiB": 1024**2,
            "GB": 1000**3,
            "GiB": 1024**3,
        }
        multiplier = multipliers.get(unit)
        return int(amount * multiplier) if multiplier is not None else None

    async def _sample_once(self) -> None:
        process = await asyncio.create_subprocess_exec(
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{json .}}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            self.errors.append(stderr.decode("utf-8", errors="replace")[:300])
            return
        now = utc_now()
        selected = set(RESOURCE_CONTAINERS)
        for line in stdout.decode("utf-8", errors="replace").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = str(item.get("Name", ""))
            if not name.startswith("pulsegrid-"):
                continue
            service = name.removeprefix("pulsegrid-").rsplit("-", 1)[0]
            if service not in selected:
                continue
            memory_text = str(item.get("MemUsage", "")).split("/", 1)
            used_bytes = self._bytes(memory_text[0]) if memory_text else None
            limit_bytes = self._bytes(memory_text[1]) if len(memory_text) == 2 else None
            try:
                cpu_percent = float(str(item.get("CPUPerc", "0%")).rstrip("%"))
            except ValueError:
                cpu_percent = None
            try:
                memory_percent = float(str(item.get("MemPerc", "0%")).rstrip("%"))
            except ValueError:
                memory_percent = None
            self.rows.append(
                {
                    "sampled_utc": now,
                    "phase": self.phase,
                    "container": name,
                    "cpu_percent": cpu_percent,
                    "memory_used_bytes": used_bytes,
                    "memory_limit_bytes": limit_bytes,
                    "memory_percent": memory_percent,
                }
            )

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        next_at = loop.time()
        while True:
            await self._sample_once()
            next_at += self.interval_seconds
            await asyncio.sleep(max(0.0, next_at - loop.time()))

    def start(self) -> None:
        self.task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fields = (
            "sampled_utc",
            "phase",
            "container",
            "cpu_percent",
            "memory_used_bytes",
            "memory_limit_bytes",
            "memory_percent",
        )
        with path.open("w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader()
            writer.writerows(self.rows)


def resource_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_container: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        by_container.setdefault(str(row["container"]), []).append(row)
    result: dict[str, Any] = {}
    for container, samples in sorted(by_container.items()):
        cpu = [float(row["cpu_percent"]) for row in samples if row.get("cpu_percent") is not None]
        memory = [
            int(row["memory_used_bytes"])
            for row in samples
            if row.get("memory_used_bytes") is not None
        ]
        result[container] = {
            "samples": len(samples),
            "cpu_percent_mean": sum(cpu) / len(cpu) if cpu else None,
            "cpu_percent_max": max(cpu) if cpu else None,
            "memory_bytes_mean": sum(memory) / len(memory) if memory else None,
            "memory_bytes_max": max(memory) if memory else None,
            "memory_limit_bytes": next(
                (row.get("memory_limit_bytes") for row in samples if row.get("memory_limit_bytes")),
                None,
            ),
            "memory_percent_max": max(
                (float(row["memory_percent"]) for row in samples if row.get("memory_percent") is not None),
                default=None,
            ),
        }
    return result


def guardrail_reason(
    samples: Sequence[Mapping[str, Any]],
    resources: Sequence[Mapping[str, Any]],
    before: Mapping[str, Mapping[str, Any]],
    after: Mapping[str, Mapping[str, Any]],
) -> str | None:
    if any(
        item.get("memory_percent") is not None and float(item["memory_percent"]) >= 90.0
        for item in resources
    ):
        return "a sampled container reached 90% of its memory limit"
    unhealthy = [
        name
        for name, item in after.items()
        if item.get("status") != "running" or item.get("health") not in ("healthy", None)
    ]
    if unhealthy:
        return "required service health failed: " + ", ".join(unhealthy)
    restarted = [
        name
        for name, item in after.items()
        if int(item.get("restart_count", 0)) > int(before.get(name, {}).get("restart_count", 0))
    ]
    if restarted:
        return "container restart detected: " + ", ".join(restarted)

    by_second: dict[int, list[Mapping[str, Any]]] = {}
    for sample in samples:
        monotonic = sample.get("started_monotonic_s")
        if monotonic is None:
            continue
        by_second.setdefault(int(float(monotonic)), []).append(sample)
    bad_seconds: set[int] = set()
    for second, group in by_second.items():
        if len(group) < 10:
            continue
        failed = sum(sample.get("classification") == "server_error" for sample in group)
        if failed / len(group) > 0.05:
            bad_seconds.add(second)
    if any(all(second + offset in bad_seconds for offset in range(5)) for second in bad_seconds):
        return "HTTP 5xx exceeded 5% in five consecutive one-second buckets"
    return None


def query_prometheus(expression: str) -> dict[str, Any]:
    raw = run_command(
        "docker",
        "exec",
        "pulsegrid-grafana-1",
        "curl",
        "-fsSG",
        "--max-time",
        "5",
        "http://prometheus:9090/api/v1/query",
        "--data-urlencode",
        f"query={expression}",
    )
    value = json.loads(raw)
    if value.get("status") != "success":
        raise RuntimeError("Prometheus query did not succeed")
    return value.get("data", {})


def prometheus_snapshot(stage: str) -> dict[str, Any]:
    return {
        "stage": stage,
        "captured_utc": utc_now(),
        "queries": {
            name: {"expression": expression, "data": query_prometheus(expression)}
            for name, expression in PROM_QUERIES.items()
        },
    }


def write_snapshot(path: Path, snapshot: Mapping[str, Any]) -> None:
    write_json(path, snapshot)


def http_client(base_url: str, token: str, concurrency: int = 64) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        headers={"Authorization": f"Bearer {token}"},
        timeout=httpx.Timeout(5.0),
        limits=httpx.Limits(
            max_connections=concurrency,
            max_keepalive_connections=concurrency,
            keepalive_expiry=10.0,
        ),
        trust_env=False,
    )


def metric_vector(snapshot: Mapping[str, Any], query_name: str) -> list[dict[str, Any]]:
    return snapshot.get("queries", {}).get(query_name, {}).get("data", {}).get("result", [])


def profile_replica_deltas(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> dict[str, int]:
    route = "/api/v1/doctors/{doctor_id}"

    def values(snapshot: Mapping[str, Any]) -> dict[str, float]:
        result: dict[str, float] = {}
        for item in metric_vector(snapshot, "doctor_http"):
            labels = item.get("metric", {})
            if labels.get("route") != route or labels.get("status_class") != "2xx":
                continue
            pair = item.get("value", [None, "0"])
            result[str(labels.get("replica_source", "unknown"))] = float(pair[1])
        return result

    old = values(before)
    new = values(after)
    return {
        source: max(0, int(round(new.get(source, 0.0) - old.get(source, 0.0))))
        for source in set(old) | set(new)
    }


async def verify_two_upstreams(
    client: httpx.AsyncClient,
    profile: RequestSpec,
    output: Path,
) -> dict[str, Any]:
    before = prometheus_snapshot("topology-probe-before")
    statuses: list[int] = []
    for _ in range(12):
        response = await client.get(profile.path, params=profile.params)
        statuses.append(response.status_code)
    if any(status != 200 for status in statuses):
        raise ExperimentStopped("the two-upstream Doctor topology probe returned a non-200 response")
    await asyncio.sleep(16.0)
    after = prometheus_snapshot("topology-probe-after")
    deltas = profile_replica_deltas(before, after)
    result = {
        "attempted": len(statuses),
        "statuses": statuses,
        "profile_requests_by_replica": deltas,
        "prometheus_before": before,
        "prometheus_after": after,
    }
    write_json(output / "summaries" / "topology_probe.json", result)
    if deltas.get("doctor", 0) <= 0 or deltas.get("doctor_replica", 0) <= 0:
        raise ExperimentStopped("Traefik did not deliver the profile probe to both Doctor upstreams")
    return result


def save_stage_snapshots(output: Path, stage: str, before: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if before is not None:
        write_snapshot(output / "metrics" / f"{stage}.before.json", before)
    after = prometheus_snapshot(stage)
    write_snapshot(output / "metrics" / f"{stage}.after.json", after)
    return after


async def preflight(
    client: httpx.AsyncClient,
    specs: Mapping[str, RequestSpec],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, spec in specs.items():
        response = await client.get(spec.path, params=spec.params)
        if response.status_code != 200:
            code = "unknown"
            try:
                code = response.json().get("error", {}).get("code", "unknown")
            except (ValueError, AttributeError):
                pass
            raise ExperimentStopped(
                f"authenticated synthetic preflight for {name} returned {response.status_code} ({code})"
            )
        body = response.json()
        if name == "directory":
            count = len(body.get("items", []))
        elif name == "autocomplete":
            count = len(body.get("items", []))
        else:
            count = 1
        result[name] = {"status_code": response.status_code, "synthetic_result_count": count}
    return result


async def run_trial(
    *,
    output: Path,
    run_id: str,
    progress: dict[str, Any],
    progress_path: Path,
    client: httpx.AsyncClient,
    specs: Mapping[str, RequestSpec],
    case_id: str,
    scenario: str,
    concurrency: int,
    trial: int,
    level: str,
    replicas: int,
    seed: int,
) -> dict[str, Any]:
    if case_id in progress.get("completed_cases", []):
        return json.loads((output / "summaries" / f"{case_id}.json").read_text())
    if case_id in progress.get("started_cases", []):
        raise ExperimentStopped(f"{case_id} was previously interrupted and will not be repeated")
    mark_case_started(progress, progress_path, case_id)
    sampler = DockerStatsSampler()
    sampler.start()
    try:
        sampler.phase = "warmup"
        warmup_result = await warm_up(
            client,
            specs,
            concurrency=concurrency,
            seconds=5.0,
            scenario=scenario,
            seed=seed,
        )
        sampler.phase = "measurement"
        before = container_snapshot()
        started_utc = utc_now()
        samples = await run_fixed_window(
            client,
            specs,
            concurrency=concurrency,
            window_seconds=30.0,
            scenario=scenario,
            run_id=run_id,
            trial=trial,
            level=level,
            replicas=replicas,
            seed=seed,
        )
        ended_utc = utc_now()
        after = container_snapshot()
    finally:
        sampler.phase = "drain"
        await sampler.stop()

    request_path = output / "requests" / f"{case_id}.csv"
    resource_path = output / "resources" / f"{case_id}.csv"
    summary_path = output / "summaries" / f"{case_id}.json"
    write_samples(request_path, samples)
    sampler.write(resource_path)
    summary = summarize_samples(samples, 30.0)
    summary.update(
        {
            "case_id": case_id,
            "scenario": scenario,
            "concurrency": concurrency,
            "trial": trial,
            "level": level,
            "replicas": replicas,
            "warmup_seconds": 5,
            "warmup": warmup_result,
            "started_utc": started_utc,
            "ended_utc": ended_utc,
            "request_samples": str(request_path.relative_to(output)),
            "resource_samples": str(resource_path.relative_to(output)),
            "resource_summary": resource_summary(sampler.rows),
            "monitor_errors": sampler.errors,
            "docker_before": before,
            "docker_after": after,
        }
    )
    write_json(summary_path, summary)
    mark_case_completed(progress, progress_path, case_id)
    reason = guardrail_reason(samples, sampler.rows, before, after)
    if reason:
        progress.setdefault("guardrail_stops", []).append({"case_id": case_id, "reason": reason})
        write_json(progress_path, progress)
        raise ExperimentStopped(reason)
    return summary


async def run_burst_case(
    *,
    output: Path,
    run_id: str,
    progress: dict[str, Any],
    progress_path: Path,
    client: httpx.AsyncClient,
    spec: RequestSpec,
    case_id: str,
    mode: str,
    replicas: int,
) -> dict[str, Any]:
    if case_id in progress.get("completed_cases", []):
        return json.loads((output / "summaries" / f"{case_id}.json").read_text())
    if case_id in progress.get("started_cases", []):
        raise ExperimentStopped(f"{case_id} was previously interrupted and will not be repeated")
    mark_case_started(progress, progress_path, case_id)
    sampler = DockerStatsSampler()
    sampler.start()
    sampler.phase = f"surge_{mode.lower()}"
    before = container_snapshot()
    started_utc = utc_now()
    try:
        samples = await run_burst(
            client,
            spec,
            count=20,
            run_id=run_id,
            scenario=f"surge_{mode.lower()}",
            level=mode.lower(),
            replicas=replicas,
        )
    finally:
        await sampler.stop()
    after = container_snapshot()
    request_path = output / "requests" / f"{case_id}.csv"
    resource_path = output / "resources" / f"{case_id}.csv"
    summary = summarize_samples(samples, 1.0)
    # Fixed bursts report request counts and per-request latency; a throughput
    # denominator would be misleading because arrivals are simultaneous.
    summary.pop("attempted_rps", None)
    summary.pop("admitted_rps", None)
    summary.pop("successful_rps", None)
    summary.pop("measurement_seconds", None)
    response_statuses: dict[str, int] = {}
    for sample in samples:
        category = str(sample["classification"])
        response_statuses[category] = response_statuses.get(category, 0) + 1
    summary.update(
        {
            "case_id": case_id,
            "mode": mode,
            "attempted": len(samples),
            "response_statuses": dict(sorted(response_statuses.items())),
            "started_utc": started_utc,
            "ended_utc": utc_now(),
            "docker_before": before,
            "docker_after": after,
            "resource_summary": resource_summary(sampler.rows),
            "monitor_errors": sampler.errors,
            "request_samples": str(request_path.relative_to(output)),
            "resource_samples": str(resource_path.relative_to(output)),
        }
    )
    write_samples(request_path, samples)
    sampler.write(resource_path)
    write_json(output / "summaries" / f"{case_id}.json", summary)
    mark_case_completed(progress, progress_path, case_id)
    reason = guardrail_reason(samples, sampler.rows, before, after)
    if reason:
        progress.setdefault("guardrail_stops", []).append({"case_id": case_id, "reason": reason})
        write_json(progress_path, progress)
        raise ExperimentStopped(reason)
    return summary


def surge_request(
    client: httpx.Client,
    *,
    active: bool | None = None,
    reason_code: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    path = "/api/v1/appointments/operations/surge-mode"
    if active is None:
        response = client.get(path)
    else:
        response = client.post(
            path,
            json={"active": active, "reason_code": reason_code, "override": False},
            headers={"Idempotency-Key": idempotency_key or ""},
        )
    try:
        body = response.json()
    except ValueError:
        body = {}
    return {
        "captured_utc": utc_now(),
        "http_status": response.status_code,
        "state": body.get("state"),
        "version": body.get("version"),
        "reason_code": body.get("reason_code"),
        "error_code": body.get("error", {}).get("code") if isinstance(body.get("error"), dict) else None,
    }


def wait_for_normal_mode(
    admin: AuthenticatedActor,
    history: list[dict[str, Any]],
    *,
    timeout_seconds: float = 155.0,
) -> dict[str, Any]:
    started = time.monotonic()
    while time.monotonic() - started <= timeout_seconds:
        status = surge_request(admin.client)
        history.append(status)
        if status.get("http_status") == 200 and status.get("state") == "NORMAL":
            return status
        time.sleep(15.0)
    raise ExperimentStopped("Surge Mode did not return to NORMAL within the bounded recovery window")


async def run_surge_evaluation(
    *,
    output: Path,
    run_id: str,
    progress: dict[str, Any],
    progress_path: Path,
    patient_client: httpx.AsyncClient,
    admin: AuthenticatedActor,
    specs: Mapping[str, RequestSpec],
) -> dict[str, Any]:
    stage = "surge_evaluation"
    if stage in progress.get("completed_stages", []):
        return json.loads((output / "summaries" / "surge_evaluation.json").read_text())
    history: list[dict[str, Any]] = []
    initial = surge_request(admin.client)
    history.append(initial)
    if initial.get("http_status") != 200 or initial.get("state") != "NORMAL":
        raise ExperimentStopped("Surge Mode is not NORMAL at experiment start; preserving existing state")

    summaries: dict[str, Any] = {"initial_status": initial, "transitions_and_polls": history}
    activated = False
    try:
        before_normal = prometheus_snapshot("s2-before-normal")
        await asyncio.sleep(16.0)
        before_normal = prometheus_snapshot("s2-before-normal-aligned")
        summaries["normal"] = await run_burst_case(
            output=output,
            run_id=run_id,
            progress=progress,
            progress_path=progress_path,
            client=patient_client,
            spec=specs["autocomplete"],
            case_id="surge-normal",
            mode="NORMAL",
            replicas=2,
        )
        await asyncio.sleep(16.0)
        after_normal = prometheus_snapshot("s2-after-normal")
        write_snapshot(output / "metrics" / "s2-before-normal.json", before_normal)
        write_snapshot(output / "metrics" / "s2-after-normal.json", after_normal)
        activation = surge_request(
            admin.client,
            active=True,
            reason_code="capacity_pressure",
            idempotency_key=f"phase8-{run_id}-activate",
        )
        history.append(activation)
        if activation.get("http_status") != 200 or activation.get("state") != "SURGE":
            raise ExperimentStopped("audited Surge Mode activation did not return SURGE")
        activated = True
        progress["surge_activation_started"] = True
        progress["surge_activation_started_utc"] = activation["captured_utc"]
        write_json(progress_path, progress)
        surge_started = time.monotonic()
        summaries["surge"] = await run_burst_case(
            output=output,
            run_id=run_id,
            progress=progress,
            progress_path=progress_path,
            client=patient_client,
            spec=specs["autocomplete"],
            case_id="surge-active",
            mode="SURGE",
            replicas=2,
        )
        await asyncio.sleep(16.0)
        after_surge = prometheus_snapshot("s2-after-surge")
        write_snapshot(output / "metrics" / "s2-after-surge.json", after_surge)
        minimum_remaining = max(0.0, 30.0 - (time.monotonic() - surge_started))
        if minimum_remaining:
            time.sleep(minimum_remaining)
        deactivation = surge_request(
            admin.client,
            active=False,
            reason_code="planned_recovery",
            idempotency_key=f"phase8-{run_id}-deactivate",
        )
        history.append(deactivation)
        if deactivation.get("http_status") != 200 or deactivation.get("state") != "RECOVERY":
            raise ExperimentStopped("audited Surge Mode deactivation did not return RECOVERY")
        summaries["normal_after_recovery"] = wait_for_normal_mode(admin, history)
        await asyncio.sleep(16.0)
        after_recovery = prometheus_snapshot("s2-after-recovery")
        write_snapshot(output / "metrics" / "s2-after-recovery.json", after_recovery)
        activated = False
    finally:
        if activated:
            # Preserve an orderly audited recovery if a bounded burst fails.
            current = surge_request(admin.client)
            history.append(current)
            if current.get("http_status") == 200 and current.get("state") == "SURGE":
                elapsed = time.monotonic() - surge_started if "surge_started" in locals() else 0
                if elapsed < 30.0:
                    time.sleep(30.0 - elapsed)
                deactivation = surge_request(
                    admin.client,
                    active=False,
                    reason_code="planned_recovery",
                    idempotency_key=f"phase8-{run_id}-cleanup",
                )
                history.append(deactivation)
                if deactivation.get("http_status") == 200:
                    wait_for_normal_mode(admin, history)

    summaries["transitions_and_polls"] = history
    summaries["final_state"] = surge_request(admin.client)
    if summaries["final_state"].get("state") != "NORMAL":
        raise ExperimentStopped("final Surge Mode verification did not return NORMAL")
    write_json(output / "summaries" / "surge_evaluation.json", summaries)
    progress.setdefault("completed_stages", []).append(stage)
    progress["surge_activation_started"] = False
    progress.pop("surge_activation_started_utc", None)
    write_json(progress_path, progress)
    return summaries


async def run_matrix(args: argparse.Namespace) -> None:
    output = Path(args.output).resolve()
    if not output.is_relative_to(ROOT):
        raise RuntimeError("results must be stored under experiments/phase8/results")
    if output.exists() and not (output / "progress.json").exists():
        raise RuntimeError("results path exists without a progress file; refusing to overwrite")
    output.mkdir(parents=True, exist_ok=True)
    progress_path = output / "progress.json"
    starting_commit = run_command("git", "rev-parse", "HEAD")
    branch = run_command("git", "branch", "--show-current")
    fixture_state, doctor_id = load_private_fixture(Path(args.fixture).resolve())
    actor_data = fixture_state["actors"]["patient"]
    admin_data, admin_fixture_seed_hash = load_private_admin_fixture(
        Path(args.admin_fixture).resolve()
    )
    fixture_seed_hash = sha256(str(fixture_state.get("run", "")).encode())[:16]
    progress = load_progress(progress_path, args.run_id, starting_commit)
    route = DoctorRoute(ROUTE_PATH)
    patient = AuthenticatedActor(args.base_url, actor_data)
    admin = AuthenticatedActor(args.base_url, admin_data)
    patient_token: str | None = None
    admin_token: str | None = None
    completion_error: str | None = None
    manifest_path = output / "manifest.json"
    manifest: dict[str, Any] = {
        "run_id": args.run_id,
        "status": "running",
        "started_utc": utc_now(),
        "branch": branch,
        "starting_commit": starting_commit,
        "route_file_sha256_before": route.original_hash,
        "compose_configuration_sha256": compose_configuration_hash(),
        "fixture_seed_sha256_prefix": fixture_seed_hash,
        "admin_fixture_seed_sha256_prefix": admin_fixture_seed_hash,
        "workload_seed": 20261013,
        "dataset": {
            "actor_role": "patient",
            "doctor_profiles": "preflight count recorded without names or IDs",
            "synthetic_fixture": str(Path(args.fixture).resolve()),
            "admin_fixture": str(Path(args.admin_fixture).resolve()),
        },
        "request_mix": {"directory": 0.5, "autocomplete": 0.3, "profile": 0.2},
        "concurrency_levels": [4, 16, 64],
        "warmup_seconds": 5,
        "measurement_seconds": 30,
        "trials": 3,
        "timeout_seconds": 5,
        "retry_policy": "none",
        "cache_state": "warm after measured warm-up; no shared cache flush",
        "rate_policy_source": "components/rate_limiter/src/pulsegrid_rate_limiter/policies.py",
        "hardware_software": capture_host_context(),
    }
    write_json(manifest_path, manifest)
    client: httpx.AsyncClient | None = None
    try:
        assert_core_healthy(manifest["hardware_software"]["containers"])
        patient_token = patient.login()
        admin_token = admin.login()
        initial_surge_status = surge_request(admin.client)
        manifest["initial_surge_status"] = initial_surge_status
        write_json(manifest_path, manifest)
        if initial_surge_status.get("http_status") != 200 or initial_surge_status.get("state") != "NORMAL":
            raise ExperimentStopped("Surge Mode is not NORMAL before load; preserving the existing state")
        specs = workload_specs(doctor_id)
        client = http_client(args.base_url, patient_token, 64)
        counts = await preflight(client, specs)
        manifest["dataset"]["preflight"] = counts
        write_json(manifest_path, manifest)

        # The L1 matrix measures the two actual, separately configured Doctor
        # containers behind one Traefik service.
        route.set_replicas(2)
        if "two_upstream_probe" not in progress.get("completed_stages", []):
            await verify_two_upstreams(client, specs["profile"], output)
            progress.setdefault("completed_stages", []).append("two_upstream_probe")
            write_json(progress_path, progress)
        if "l1" not in progress.get("completed_stages", []):
            before = prometheus_snapshot("before_l1")
            await asyncio.sleep(16.0)
            before = prometheus_snapshot("before_l1_aligned")
            level_order = (4, 16, 64)
            for trial in range(1, 4):
                rotated = level_order[trial - 1 :] + level_order[: trial - 1]
                for concurrency in rotated:
                    case_id = f"l1-c{concurrency}-t{trial}"
                    await run_trial(
                        output=output,
                        run_id=args.run_id,
                        progress=progress,
                        progress_path=progress_path,
                        client=client,
                        specs=specs,
                        case_id=case_id,
                        scenario="mixed_read",
                        concurrency=concurrency,
                        trial=trial,
                        level={4: "low", 16: "medium", 64: "high"}[concurrency],
                        replicas=2,
                        seed=20261013,
                    )
                snapshot = prometheus_snapshot(f"l1-trial-{trial}-end")
                write_snapshot(output / "metrics" / f"l1-trial-{trial}-end.json", snapshot)
                await asyncio.sleep(16.0)
            # One later scrape captures the tail of the last load trial.
            snapshot = prometheus_snapshot("after_l1")
            write_snapshot(output / "metrics" / "after_l1.json", snapshot)
            write_snapshot(output / "metrics" / "before_l1.json", before)
            l1_deltas = profile_replica_deltas(before, snapshot)
            write_json(output / "summaries" / "l1_replica_counters.json", l1_deltas)
            if l1_deltas.get("doctor", 0) <= 0 or l1_deltas.get("doctor_replica", 0) <= 0:
                raise ExperimentStopped("the L1 two-upstream traffic did not reach both Doctor containers")
            progress.setdefault("completed_stages", []).append("l1")
            write_json(progress_path, progress)

        # Scaling uses a Class B profile read so Class C admission caps do not
        # masquerade as application throughput.
        if "s1" not in progress.get("completed_stages", []):
            scaling_vectors: dict[str, Any] = {}
            for replica_count in (1, 2):
                route.set_replicas(replica_count)
                await asyncio.sleep(16.0)
                stage_name = f"s1-{replica_count}-replica-before"
                before_metrics = prometheus_snapshot(stage_name)
                before_containers = container_snapshot()
                if replica_count == 2:
                    await asyncio.sleep(1.0)
                for trial in range(1, 4):
                    case_id = f"s1-r{replica_count}-t{trial}"
                    await run_trial(
                        output=output,
                        run_id=args.run_id,
                        progress=progress,
                        progress_path=progress_path,
                        client=client,
                        specs=specs,
                        case_id=case_id,
                        scenario="profile_read",
                        concurrency=16,
                        trial=trial,
                        level="medium",
                        replicas=replica_count,
                        seed=20261013,
                    )
                await asyncio.sleep(16.0)
                after_metrics = prometheus_snapshot(f"s1-{replica_count}-replica-after")
                write_snapshot(output / "metrics" / f"s1-{replica_count}-replica-before.json", before_metrics)
                write_snapshot(output / "metrics" / f"s1-{replica_count}-replica-after.json", after_metrics)
                scaling_vectors[str(replica_count)] = {
                    "before": metric_vector(before_metrics, "doctor_http"),
                    "after": metric_vector(after_metrics, "doctor_http"),
                    "profile_request_deltas": profile_replica_deltas(before_metrics, after_metrics),
                    "container_before": before_containers,
                    "container_after": container_snapshot(),
                }
                deltas = scaling_vectors[str(replica_count)]["profile_request_deltas"]
                if deltas.get("doctor", 0) <= 0:
                    raise ExperimentStopped(f"the {replica_count}-upstream profile workload reached no primary Doctor requests")
                if replica_count == 1 and deltas.get("doctor_replica", 0) > 0:
                    raise ExperimentStopped("the single-upstream condition received traffic on doctor_replica")
                if replica_count == 2 and deltas.get("doctor_replica", 0) <= 0:
                    raise ExperimentStopped("the two-upstream scaling workload did not reach doctor_replica")
            write_json(output / "summaries" / "scaling_prometheus.json", scaling_vectors)
            progress.setdefault("completed_stages", []).append("s1")
            write_json(progress_path, progress)

        if "s2" not in progress.get("completed_stages", []):
            surge = await run_surge_evaluation(
                output=output,
                run_id=args.run_id,
                progress=progress,
                progress_path=progress_path,
                patient_client=client,
                admin=admin,
                specs=specs,
            )
            manifest["surge_mode"] = surge
            write_json(manifest_path, manifest)
            progress.setdefault("completed_stages", []).append("s2")
            write_json(progress_path, progress)

        manifest["status"] = "completed"
    except BaseException as error:
        completion_error = f"{type(error).__name__}: {str(error)[:500]}"
        manifest["status"] = "partial"
        manifest["error"] = completion_error
        if isinstance(error, ExperimentStopped):
            manifest["stop_condition"] = str(error)
    finally:
        if client is not None:
            await client.aclose()
        try:
            restored_hash = route.restore()
            manifest["route_file_sha256_after"] = restored_hash
            manifest["route_restored"] = restored_hash == route.original_hash
        except Exception as restore_error:
            manifest["route_restore_error"] = f"{type(restore_error).__name__}: {str(restore_error)[:400]}"
            manifest["status"] = "partial"
        if admin_token is not None:
            try:
                final_surge = surge_request(admin.client)
                if final_surge.get("state") != "NORMAL" and progress.get("surge_activation_started"):
                    if final_surge.get("state") == "SURGE":
                        activation_text = progress.get("surge_activation_started_utc")
                        if activation_text:
                            activation_at = datetime.fromisoformat(activation_text)
                            elapsed = (datetime.now(timezone.utc) - activation_at).total_seconds()
                            if elapsed < 30.0:
                                time.sleep(30.0 - elapsed)
                        final_surge = surge_request(
                            admin.client,
                            active=False,
                            reason_code="planned_recovery",
                            idempotency_key=f"phase8-{args.run_id}-final-recovery",
                        )
                    if final_surge.get("state") == "RECOVERY":
                        final_surge = wait_for_normal_mode(admin, [final_surge])
                manifest["final_surge_status"] = final_surge
                if final_surge.get("http_status") != 200 or final_surge.get("state") != "NORMAL":
                    manifest["status"] = "partial"
                    manifest["final_surge_error"] = "shared Surge Mode state was not NORMAL at cleanup"
            except Exception as surge_error:
                manifest["status"] = "partial"
                manifest["final_surge_error"] = f"{type(surge_error).__name__}: {str(surge_error)[:300]}"
        for actor in (patient, admin):
            try:
                actor.logout()
            except Exception as logout_error:
                manifest.setdefault("cleanup_errors", []).append(
                    f"logout failed: {type(logout_error).__name__}: {str(logout_error)[:250]}"
                )
        try:
            final_containers = container_snapshot()
            assert_core_healthy(final_containers)
            manifest["final_core_containers"] = final_containers
        except Exception as health_error:
            manifest["status"] = "partial"
            manifest["final_health_error"] = f"{type(health_error).__name__}: {str(health_error)[:400]}"
        manifest["ended_utc"] = utc_now()
        manifest["error"] = completion_error
        write_json(manifest_path, manifest)
    if completion_error:
        raise SystemExit(completion_error)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path("/tmp/pulsegrid-phase3-live-fixture.json"),
        help="existing mode-0600 synthetic fixture with patient and admin credentials",
    )
    parser.add_argument(
        "--admin-fixture",
        type=Path,
        default=Path("/tmp/pulsegrid-phase29-live-fixture.json"),
        help="existing mode-0600 synthetic fixture with the hospital admin actor",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--run-id", default="phase8-20261013-run1")
    parser.add_argument(
        "--output",
        type=Path,
        help="must be under experiments/phase8/results; defaults to results/<run-id>",
    )
    args = parser.parse_args()
    if args.output is None:
        args.output = ROOT / "experiments/phase8/results" / args.run_id
    try:
        asyncio.run(run_matrix(args))
    except KeyboardInterrupt:
        print("interrupted; route restoration and logout were attempted", file=sys.stderr)
        raise SystemExit(130)


if __name__ == "__main__":
    main()
