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
import stat
import statistics
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
    run_fixed_window,
    summarize_samples,
    warm_up,
    workload_specs,
    write_samples,
)


ROOT = Path(__file__).resolve().parents[2]
ROUTE_PATH = ROOT / "infra/phase4/routes.yaml"
BENCHMARK_COMPOSE_FILE = "compose.phase8-benchmark.yaml"
BENCHMARK_HOST = "phase8-one.localhost"
BENCHMARK_HOSTS = {1: "phase8-one.localhost", 2: "phase8-two.localhost"}
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
    "pulsegrid-tempo-1",
)
RESOURCE_CONTAINERS = (
    "patient",
    "doctor",
    "doctor_replica",
    "appointment",
    "records",
    "pharmacy",
    "billing",
    "emergency",
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
PHASE82_REQUIRED_CONTAINERS = tuple(
    name for name in REQUIRED_CONTAINERS if name != "pulsegrid-tempo-1"
) + (
    "pulsegrid-prometheus-1",
    "pulsegrid-grafana-1",
    "pulsegrid-blackbox-1",
)
PHASE82_API_CONTAINERS = {
    "patient": "pulsegrid-patient-1",
    "doctor": "pulsegrid-doctor-1",
    "doctor_replica": "pulsegrid-doctor_replica-1",
    "appointment": "pulsegrid-appointment-1",
    "records": "pulsegrid-records-1",
    "pharmacy": "pulsegrid-pharmacy-1",
    "billing": "pulsegrid-billing-1",
    "emergency": "pulsegrid-emergency-1",
}
PHASE82_REPLICAS = (1, 2)
PHASE82_CONCURRENCIES = (4, 16, 64)
PHASE82_CASES = ((1, 4), (2, 4), (1, 16), (2, 16), (1, 64), (2, 64))
PHASE82_CPU_STOP_FRACTION = 0.90
PHASE82_CPU_STOP_CONSECUTIVE_SAMPLES = 3
PHASE82_HOST_FREE_MEMORY_STOP_PERCENT = 10.0
PHASE82_COMPOSE_FILE = "compose.phase8-tracing-free.yaml"
PHASE82_TRAEFIK_CONFIG = ROOT / "infra/traefik/traefik.phase8-benchmark.yaml"
PROM_QUERIES = {
    "all_targets": "up",
    "api_targets": 'sum by (job, service, replica_source) (up{job=~"pulsegrid_api|pulsegrid_readiness"})',
    "doctor_http": 'sum by (replica_source, route, status_class) (pulsegrid_http_requests_total{service="doctor"})',
    "doctor_admission": 'sum by (replica_source, policy, class, state, outcome) (pulsegrid_http_admission_requests_total{owner="doctor"})',
    "doctor_admission_backend": 'sum by (replica_source, policy, backend, outcome) (pulsegrid_admission_requests_total{service="doctor"})',
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


def trial_container_snapshot(tracing_disabled: bool) -> dict[str, dict[str, Any]]:
    names = PHASE82_REQUIRED_CONTAINERS if tracing_disabled else REQUIRED_CONTAINERS
    return container_snapshot(names)


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
        "containers": container_snapshot(
            (*REQUIRED_CONTAINERS, "pulsegrid-prometheus-1", "pulsegrid-grafana-1", "pulsegrid-otel-collector-1", "pulsegrid-blackbox-1")
        ),
    }


def capture_docker_pressure() -> dict[str, Any]:
    raw = run_command("docker", "stats", "--no-stream", "--format", "{{json .}}")
    docker_vm_memory = int(run_command("docker", "info", "--format", "{{.MemTotal}}"))
    docker_vm_cpus = int(run_command("docker", "info", "--format", "{{.NCPU}}"))
    pulsegrid: list[dict[str, Any]] = []
    aggregate_memory = 0
    aggregate_cpu = 0.0
    running_container_count = 0
    for line in raw.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        running_container_count += 1
        usage = str(item.get("MemUsage", "")).split("/", 1)
        used = DockerStatsSampler._bytes(usage[0]) if usage else None
        try:
            cpu = float(str(item.get("CPUPerc", "0%")).rstrip("%"))
        except ValueError:
            cpu = None
        if used is None:
            continue
        aggregate_memory += used
        aggregate_cpu += cpu or 0.0
        name = str(item.get("Name", ""))
        if name.startswith("pulsegrid-"):
            service = name.removeprefix("pulsegrid-").rsplit("-", 1)[0]
            try:
                memory_percent = float(str(item.get("MemPerc", "0%" )).rstrip("%"))
            except ValueError:
                memory_percent = None
            pulsegrid.append(
                {
                    "service": service,
                    "memory_used_bytes": used,
                    "cpu_percent": cpu,
                    "memory_percent_of_limit": memory_percent,
                }
            )
    return {
        "captured_utc": utc_now(),
        "running_container_count": running_container_count,
        "docker_vm_memory_limit_bytes": docker_vm_memory,
        "docker_vm_memory_used_bytes": aggregate_memory,
        "docker_vm_memory_percent": 100.0 * aggregate_memory / docker_vm_memory,
        "docker_vm_cpu_count": docker_vm_cpus,
        "docker_container_cpu_percent_sum": aggregate_cpu,
        "pulsegrid_container_samples": pulsegrid,
    }


def capture_mac_memory_free_percent() -> float | None:
    result = subprocess.run(
        ["memory_pressure"],
        check=False,
        capture_output=True,
        text=True,
        timeout=5.0,
    )
    if result.returncode:
        return None
    match = re.search(r"System-wide memory free percentage:\s*([0-9]+)%", result.stdout)
    return float(match.group(1)) if match else None


def compose_configuration_hash() -> str:
    data = b"\0".join((ROOT / filename).read_bytes() for filename in COMPOSE_FILES)
    return sha256(data)


class DoctorRoute:
    """Add two temporary isolated Traefik hosts for matched upstream counts."""

    ROUTER_MARKER = b"    appointment:\n"
    SERVICE_MARKER = b"    appointment:\n"
    BENCHMARK_NAME = b"doctor-phase8-benchmark-"

    def __init__(self, path: Path):
        self.path = path
        self.original = path.read_bytes()
        self.mode = stat.S_IMODE(path.stat().st_mode)
        self.original_hash = sha256(self.original)
        if self.BENCHMARK_NAME in self.original:
            raise RuntimeError("the Traefik route file already contains a Phase 8 benchmark route")
        self.benchmark_routes = self._benchmark_bytes()
        self.backup = Path(tempfile.gettempdir()) / f"pulsegrid-phase8-routes-{os.getpid()}-{time.time_ns()}.bak"
        self.backup.write_bytes(self.original)
        self.backup.chmod(self.mode)

    def _benchmark_bytes(self) -> bytes:
        parts = self.original.split(b"  services:\n")
        if len(parts) != 2:
            raise RuntimeError("Traefik route file does not have one router/services boundary")
        routers, services = parts
        if routers.count(self.ROUTER_MARKER) != 1 or services.count(self.SERVICE_MARKER) != 1:
            raise RuntimeError("Traefik route structure differs from the reviewed baseline")
        router = b""
        backend = b""
        for replicas, suffix in ((1, "one"), (2, "two")):
            name = f"doctor-phase8-benchmark-{suffix}"
            host = BENCHMARK_HOSTS[replicas]
            router += (
                f"    {name}:\n"
                "      entryPoints: [web]\n"
                f'      rule: "Host(`{host}`) && (Path(`/api/v1/doctors`) || PathPrefix(`/api/v1/doctors/`))"\n'
                f"      service: {name}\n"
            ).encode()
            backend += (
                f"    {name}:\n"
                "      loadBalancer:\n"
                "        servers:\n"
                "          - url: http://doctor:8000\n"
            ).encode()
            if replicas == 2:
                backend += b"          - url: http://doctor_replica:8000\n"
        routers = routers.replace(self.ROUTER_MARKER, router + self.ROUTER_MARKER, 1)
        services = services.replace(self.SERVICE_MARKER, backend + self.SERVICE_MARKER, 1)
        return routers + b"  services:\n" + services

    def activate(self) -> str:
        current = self.path.read_bytes()
        if current not in (self.original, self.benchmark_routes):
            raise RuntimeError("route file changed outside this Phase 8 runner")
        self._replace_file(self.benchmark_routes)
        return sha256(self.path.read_bytes())

    def set_replicas(self, count: int) -> str:
        if count not in BENCHMARK_HOSTS:
            raise ValueError("only the predeclared one/two upstream conditions are allowed")
        current = self.path.read_bytes()
        if current != self.benchmark_routes:
            raise RuntimeError("the isolated benchmark routes are not active")
        return BENCHMARK_HOSTS[count]

    def _replace_file(self, data: bytes) -> None:
        temporary = self.path.with_suffix(".yaml.phase8-tmp")
        temporary.write_bytes(data)
        temporary.chmod(self.mode)
        os.replace(temporary, self.path)

    def restore(self) -> str:
        current = self.path.read_bytes()
        if current not in (self.original, self.benchmark_routes):
            raise RuntimeError("route file has an unexpected edit; refusing to overwrite it")
        self._replace_file(self.original)
        result = sha256(self.path.read_bytes())
        if result != self.original_hash:
            raise RuntimeError("Traefik route restoration hash mismatch")
        self.backup.unlink(missing_ok=True)
        return result


class DockerStatsSampler:
    def __init__(self, interval_seconds: float = 2.0, *, tracing_disabled: bool = False):
        self.interval_seconds = interval_seconds
        self.tracing_disabled = tracing_disabled
        self.resource_containers = set(RESOURCE_CONTAINERS)
        if tracing_disabled:
            self.resource_containers.difference_update({"tempo", "otel-collector"})
        self.rows: list[dict[str, Any]] = []
        self.phase = "setup"
        self.task: asyncio.Task[None] | None = None
        self.errors: list[str] = []
        self.stop_event = asyncio.Event()
        self.stop_reason: str | None = None
        self.tempo_restart_baseline: int | None = None
        self.docker_vm_memory_bytes: int | None = None
        self.docker_vm_cpus: int | None = None
        self.host_memory_bytes: int | None = None
        self.host_cpu_count: int | None = None
        self.high_cpu_samples = 0
        self.high_host_load_samples = 0

    def _request_stop(self, reason: str) -> None:
        if self.stop_reason is None:
            self.stop_reason = reason
            self.stop_event.set()

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
            message = stderr.decode("utf-8", errors="replace")[:300]
            self.errors.append(message)
            self._request_stop("Docker resource sampling failed")
            return
        now = utc_now()
        selected = self.resource_containers
        docker_memory = 0
        docker_cpu = 0.0
        docker_memory_samples = 0
        for line in stdout.decode("utf-8", errors="replace").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = str(item.get("Name", ""))
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
            if used_bytes is not None:
                docker_memory += used_bytes
                docker_memory_samples += 1
            if cpu_percent is not None:
                docker_cpu += cpu_percent
            service = name.removeprefix("pulsegrid-").rsplit("-", 1)[0]
            if not name.startswith("pulsegrid-") or service not in selected:
                continue
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
            if memory_percent is not None and memory_percent >= 90.0:
                self._request_stop(f"{name} reached 90% of its container memory limit")
        if docker_memory_samples and self.docker_vm_memory_bytes:
            vm_percent = 100.0 * docker_memory / self.docker_vm_memory_bytes
            self.rows.append(
                {
                    "sampled_utc": now,
                    "phase": self.phase,
                    "container": "docker-vm",
                    "cpu_percent": docker_cpu,
                    "cpu_limit_percent": (self.docker_vm_cpus or 0) * 100.0,
                    "memory_used_bytes": docker_memory,
                    "memory_limit_bytes": self.docker_vm_memory_bytes,
                    "memory_percent": vm_percent,
                }
            )
            if vm_percent >= 90.0:
                self._request_stop("Docker VM reached 90% of configured memory")
            cpu_limit = (self.docker_vm_cpus or 0) * 100.0 * PHASE82_CPU_STOP_FRACTION
            if (
                self.tracing_disabled
                and self.phase in ("warmup", "measurement")
                and cpu_limit > 0
                and docker_cpu >= cpu_limit
            ):
                self.high_cpu_samples += 1
            else:
                self.high_cpu_samples = 0
            if self.high_cpu_samples >= PHASE82_CPU_STOP_CONSECUTIVE_SAMPLES:
                self._request_stop("Docker VM CPU remained at or above 90% of its allocated CPUs")
        host_free_percent = (
            await asyncio.to_thread(capture_mac_memory_free_percent)
            if self.tracing_disabled
            else None
        )
        if self.tracing_disabled and host_free_percent is not None and self.host_memory_bytes:
            host_used_percent = 100.0 - host_free_percent
            try:
                host_load_1m = os.getloadavg()[0]
            except (AttributeError, OSError):
                host_load_1m = None
            self.rows.append(
                {
                    "sampled_utc": now,
                    "phase": self.phase,
                    "container": "mac-host",
                    "cpu_percent": None,
                    "host_load_1m": host_load_1m,
                    "host_cpu_count": self.host_cpu_count,
                    "memory_used_bytes": int(self.host_memory_bytes * host_used_percent / 100.0),
                    "memory_limit_bytes": self.host_memory_bytes,
                    "memory_percent": host_used_percent,
                }
            )
            if host_free_percent < PHASE82_HOST_FREE_MEMORY_STOP_PERCENT:
                self._request_stop("macOS free memory fell below 10%")
            load_limit = (self.host_cpu_count or 0) * PHASE82_CPU_STOP_FRACTION
            if host_load_1m is not None and load_limit > 0 and host_load_1m >= load_limit:
                self.high_host_load_samples += 1
            else:
                self.high_host_load_samples = 0
            if self.high_host_load_samples >= PHASE82_CPU_STOP_CONSECUTIVE_SAMPLES:
                self._request_stop("macOS one-minute load remained at or above 90% of host CPUs")
        if self.tempo_restart_baseline is not None and not self.tracing_disabled:
            try:
                state_text, restart_text = run_command(
                    "docker", "inspect", "--format", "{{json .State}}|{{.RestartCount}}", "pulsegrid-tempo-1"
                ).rsplit("|", 1)
                tempo_state = json.loads(state_text)
                if tempo_state.get("Status") != "running":
                    self._request_stop(f"Tempo state changed to {tempo_state.get('Status')}")
                if int(restart_text) != self.tempo_restart_baseline:
                    self._request_stop("Tempo restart-count change detected during trial")
            except Exception as error:
                self.errors.append(f"Tempo state sampling failed: {type(error).__name__}")
                self._request_stop("Tempo state sampling failed")

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        next_at = loop.time()
        while True:
            await self._sample_once()
            next_at += self.interval_seconds
            await asyncio.sleep(max(0.0, next_at - loop.time()))

    def start(self, before: Mapping[str, Mapping[str, Any]] | None = None) -> None:
        try:
            self.docker_vm_memory_bytes = int(
                run_command("docker", "info", "--format", "{{.MemTotal}}")
            )
            self.docker_vm_cpus = int(run_command("docker", "info", "--format", "{{.NCPU}}"))
            self.host_memory_bytes = int(run_command("sysctl", "-n", "hw.memsize"))
            self.host_cpu_count = os.cpu_count()
        except Exception as error:
            self.errors.append(f"Docker VM capacity sampling failed: {type(error).__name__}")
            self._request_stop("Docker VM capacity sampling failed")
        if before is not None and not self.tracing_disabled:
            tempo = before.get("pulsegrid-tempo-1", {})
            self.tempo_restart_baseline = int(tempo.get("restart_count", 0))
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
            "cpu_limit_percent",
            "host_load_1m",
            "host_cpu_count",
            "memory_used_bytes",
            "memory_limit_bytes",
            "memory_percent",
        )
        with path.open("w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
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
            "cpu_limit_percent": next(
                (row.get("cpu_limit_percent") for row in samples if row.get("cpu_limit_percent")),
                None,
            ),
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
            "host_load_1m_max": max(
                (float(row["host_load_1m"]) for row in samples if row.get("host_load_1m") is not None),
                default=None,
            ),
            "host_cpu_count": next(
                (row.get("host_cpu_count") for row in samples if row.get("host_cpu_count")),
                None,
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
    vm_cpu = sorted(
        (
            str(item.get("sampled_utc", "")),
            float(item["cpu_percent"]),
            float(item.get("cpu_limit_percent") or 0.0),
        )
        for item in resources
        if item.get("container") == "docker-vm"
        and item.get("phase") in ("warmup", "measurement")
        and item.get("cpu_percent") is not None
    )
    high_cpu_count = 0
    for _, cpu_percent, cpu_limit_percent in vm_cpu:
        if cpu_limit_percent > 0 and cpu_percent >= PHASE82_CPU_STOP_FRACTION * cpu_limit_percent:
            high_cpu_count += 1
            if high_cpu_count >= PHASE82_CPU_STOP_CONSECUTIVE_SAMPLES:
                return "Docker VM CPU remained at or above 90% of its allocated CPUs"
        else:
            high_cpu_count = 0
    host_load = sorted(
        (
            str(item.get("sampled_utc", "")),
            float(item["host_load_1m"]),
            int(item.get("host_cpu_count") or 0),
        )
        for item in resources
        if item.get("container") == "mac-host"
        and item.get("phase") in ("warmup", "measurement")
        and item.get("host_load_1m") is not None
    )
    high_host_load_count = 0
    for _, load_1m, host_cpu_count in host_load:
        if host_cpu_count > 0 and load_1m >= PHASE82_CPU_STOP_FRACTION * host_cpu_count:
            high_host_load_count += 1
            if high_host_load_count >= PHASE82_CPU_STOP_CONSECUTIVE_SAMPLES:
                return "macOS one-minute load remained at or above 90% of host CPUs"
        else:
            high_host_load_count = 0
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


def http_client(
    base_url: str,
    token: str,
    concurrency: int = 64,
    *,
    benchmark_host: bool = False,
) -> httpx.AsyncClient:
    headers = {"Authorization": f"Bearer {token}"}
    if benchmark_host:
        headers["Host"] = BENCHMARK_HOST
    return httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        headers=headers,
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
    tracing_disabled: bool = False,
) -> dict[str, Any]:
    if case_id in progress.get("completed_cases", []):
        return json.loads((output / "summaries" / f"{case_id}.json").read_text())
    if case_id in progress.get("started_cases", []):
        raise ExperimentStopped(f"{case_id} was previously interrupted and will not be repeated")
    mark_case_started(progress, progress_path, case_id)
    sampler = DockerStatsSampler(tracing_disabled=tracing_disabled)
    before = trial_container_snapshot(tracing_disabled)
    sampler.start(before)
    samples: list[dict[str, Any]] = []
    warmup_result: dict[str, Any] = {}
    measurement_started = time.monotonic()
    measurement_ended = measurement_started
    started_utc = utc_now()
    ended_utc = started_utc
    after: dict[str, dict[str, Any]] = before
    try:
        sampler.phase = "warmup"
        warmup_result = await warm_up(
            client,
            specs,
            concurrency=concurrency,
            seconds=5.0,
            scenario=scenario,
            seed=seed,
            stop_event=sampler.stop_event,
        )
        if not sampler.stop_event.is_set():
            sampler.phase = "measurement"
            started_utc = utc_now()
            measurement_started = time.monotonic()
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
                stop_event=sampler.stop_event,
            )
            ended_utc = utc_now()
            measurement_ended = time.monotonic()
        after = trial_container_snapshot(tracing_disabled)
    finally:
        sampler.phase = "drain"
        await sampler.stop()

    request_path = output / "requests" / f"{case_id}.csv"
    resource_path = output / "resources" / f"{case_id}.csv"
    summary_path = output / "summaries" / f"{case_id}.json"
    write_samples(request_path, samples)
    sampler.write(resource_path)
    measured_seconds = min(30.0, max(0.001, measurement_ended - measurement_started))
    summary = summarize_samples(samples, measured_seconds)
    if summary["attempted"] != sum(summary["classification_counts"].values()):
        raise RuntimeError("attempted requests do not reconcile with classified outcomes")
    if abs(
        summary["successful_rps"] - summary["successful"] / summary["measurement_seconds"]
    ) > 1e-9:
        raise RuntimeError("successful RPS does not match successes divided by measured duration")
    summary.update(
        {
            "case_id": case_id,
            "scenario": scenario,
            "concurrency": concurrency,
            "trial": trial,
            "level": level,
            "replicas": replicas,
            "warmup_seconds": 5,
            "requested_measurement_seconds": 30,
            "actual_duration_seconds": measured_seconds,
            "distributed_tracing_disabled": tracing_disabled,
            "partial_measurement": measured_seconds < 29.0,
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
    rejection_percent = summary.get("rejection_percent")
    admission_gate_passed = rejection_percent is not None and float(rejection_percent) < 10.0
    summary["admission_rejection_gate"] = {
        "maximum_rejection_percent": 10.0,
        "passed": admission_gate_passed,
    }
    write_json(summary_path, summary)
    reason = sampler.stop_reason or guardrail_reason(samples, sampler.rows, before, after)
    if sampler.errors and reason is None:
        reason = "Docker resource or Tempo state sampling failed"
    if reason is None and not admission_gate_passed:
        reason = "trial admission rejection reached the 10% validity limit"
    if reason:
        progress.setdefault("guardrail_stops", []).append({"case_id": case_id, "reason": reason})
        write_json(progress_path, progress)
        raise ExperimentStopped(reason)
    mark_case_completed(progress, progress_path, case_id)
    return summary


def surge_status(client: httpx.Client) -> dict[str, Any]:
    response = client.get("/api/v1/appointments/operations/surge-mode")
    try:
        body = response.json()
    except ValueError:
        body = {}
    return {
        "captured_utc": utc_now(),
        "http_status": response.status_code,
        "state": body.get("state"),
        "version": body.get("version"),
    }


def compose_command(
    *args: str,
    benchmark_enabled: bool = False,
    tracing_disabled: bool = False,
    timeout: float = 30.0,
) -> str:
    files = list(COMPOSE_PREFIX)
    if tracing_disabled:
        files.extend(("-f", PHASE82_COMPOSE_FILE))
    if benchmark_enabled:
        files.extend(("-f", BENCHMARK_COMPOSE_FILE))
    return run_command("docker", "compose", *files, *args, timeout=timeout)


def doctor_image_has_benchmark_policy() -> bool:
    try:
        run_command(
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "python",
            "pulsegrid-auth-doctor:local",
            "-c",
            "from doctor_service.admission import PHASE8_BENCHMARK_HOSTS; assert PHASE8_BENCHMARK_HOSTS == frozenset({'phase8-one.localhost', 'phase8-two.localhost'})",
        )
        return True
    except RuntimeError:
        return False


async def wait_for_doctor_services(timeout_seconds: float = 90.0) -> dict[str, dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, dict[str, Any]] = {}
    while time.monotonic() < deadline:
        last = {
            name: inspect_container(name)
            for name in ("pulsegrid-doctor-1", "pulsegrid-doctor_replica-1")
        }
        if all(
            item["status"] == "running" and item["health"] in ("healthy", None)
            for item in last.values()
        ):
            return last
        await asyncio.sleep(2.0)
    raise ExperimentStopped(f"Doctor services did not become healthy: {last}")


async def wait_for_traefik_service(timeout_seconds: float = 90.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = inspect_container("pulsegrid-traefik-1")
        if last["status"] == "running" and last["health"] in ("healthy", None):
            return last
        await asyncio.sleep(2.0)
    raise ExperimentStopped(f"Traefik did not become healthy: {last}")


def mounted_traefik_route_sha256() -> str:
    raw = run_command(
        "docker", "exec", "pulsegrid-traefik-1", "sha256sum", "/etc/traefik/routes.yaml"
    )
    return raw.split()[0]


def mounted_traefik_route_source() -> str:
    raw = run_command("docker", "inspect", "--format", "{{json .Mounts}}", "pulsegrid-traefik-1")
    mounts = json.loads(raw)
    source = next(
        (item.get("Source") for item in mounts if item.get("Destination") == "/etc/traefik/routes.yaml"),
        None,
    )
    if not source:
        raise ExperimentStopped("the live Traefik container has no /etc/traefik/routes.yaml mount")
    return str(Path(source).resolve())


def mounted_traefik_static_sha256(path: str) -> str:
    raw = run_command("docker", "exec", "pulsegrid-traefik-1", "sha256sum", path)
    return raw.split()[0]


def doctor_normal_admission_counters() -> dict[str, float]:
    command = (
        "import urllib.request; "
        "print(urllib.request.urlopen('http://127.0.0.1:8000/metrics', timeout=3).read().decode())"
    )
    result: dict[str, float] = {}
    for container in ("pulsegrid-doctor-1", "pulsegrid-doctor_replica-1"):
        raw = run_command("docker", "exec", container, "python", "-c", command, timeout=10.0)
        total = 0.0
        for line in raw.splitlines():
            if not line.startswith("pulsegrid_admission_requests_total{"):
                continue
            labels, separator, value = line.partition("} ")
            if (
                separator
                and 'policy="doctor_directory_search_directory"' in labels
                and 'backend="redis"' in labels
            ):
                total += float(value)
        result[container] = total
    return result


def access_token_subject(token: str) -> str:
    import base64

    try:
        payload = token.split(".")[1]
        decoded = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        subject = json.loads(decoded).get("sub")
    except (IndexError, ValueError, TypeError, json.JSONDecodeError) as error:
        raise RuntimeError("authenticated access token did not contain a readable subject") from error
    if (
        not isinstance(subject, str)
        or not re.fullmatch(r"[1-9][0-9]{0,18}", subject)
        or int(subject) >= 2**63
    ):
        raise RuntimeError("authenticated access token subject was not a canonical user ID")
    return subject


def verify_benchmark_redis_admission(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    rows = metric_vector(snapshot, "doctor_admission_backend")
    selected = [
        row
        for row in rows
        if row.get("metric", {}).get("policy") == "doctor_directory_search_phase8_benchmark"
    ]
    counts: dict[str, float] = {}
    for row in selected:
        labels = row.get("metric", {})
        counts[str(labels.get("backend", "unknown"))] = counts.get(
            str(labels.get("backend", "unknown")), 0.0
        ) + float(row.get("value", [None, "0"])[1])
    return {
        "policy_series": selected,
        "counter_values_by_backend": counts,
        "redis_observed": counts.get("redis", 0.0) > 0,
    }


def admission_backend_counter(
    snapshot: Mapping[str, Any], policy: str, backend: str
) -> float:
    return sum(
        float(row.get("value", [None, "0"])[1])
        for row in metric_vector(snapshot, "doctor_admission_backend")
        if row.get("metric", {}).get("policy") == policy
        and row.get("metric", {}).get("backend") == backend
    )


async def verify_replica_topology(
    client: httpx.AsyncClient,
    profile: RequestSpec,
    output: Path,
    replicas: int,
) -> dict[str, Any]:
    route_bytes = ROUTE_PATH.read_bytes()
    primary_count, replica_count = benchmark_route_upstream_counts(route_bytes, replicas)
    if primary_count != 1:
        raise ExperimentStopped("benchmark route must contain exactly one primary Doctor server")
    expected_replica_count = 1 if replicas == 2 else 0
    if replica_count != expected_replica_count:
        raise ExperimentStopped("benchmark route does not match the requested Doctor replica count")

    before = prometheus_snapshot(f"topology-{replicas}-before")
    statuses: list[int] = []
    for _ in range(12):
        response = await client.get(profile.path, params=profile.params)
        statuses.append(response.status_code)
    if any(status != 200 for status in statuses):
        after = prometheus_snapshot(f"topology-{replicas}-failed")
        result = {
            "replicas": replicas,
            "attempted": len(statuses),
            "statuses": statuses,
            "status_counts": {
                str(status): statuses.count(status) for status in sorted(set(statuses))
            },
            "profile_requests_by_replica": profile_replica_deltas(before, after),
            "benchmark_policy_redis_counter_delta": (
                admission_backend_counter(
                    after, "doctor_directory_search_phase8_benchmark", "redis"
                )
                - admission_backend_counter(
                    before, "doctor_directory_search_phase8_benchmark", "redis"
                )
            ),
            "prometheus_before": before,
            "prometheus_after": after,
        }
        write_json(output / "summaries" / f"topology_{replicas}_replica_probe.json", result)
        raise ExperimentStopped(
            f"the {replicas}-replica routing probe returned non-200 statuses {result['status_counts']}"
        )
    await asyncio.sleep(16.0)
    after = prometheus_snapshot(f"topology-{replicas}-after")
    deltas = profile_replica_deltas(before, after)
    benchmark_policy_redis_delta = (
        admission_backend_counter(after, "doctor_directory_search_phase8_benchmark", "redis")
        - admission_backend_counter(before, "doctor_directory_search_phase8_benchmark", "redis")
    )
    result = {
        "replicas": replicas,
        "attempted": len(statuses),
        "statuses": statuses,
        "profile_requests_by_replica": deltas,
        "benchmark_policy_redis_counter_delta": benchmark_policy_redis_delta,
        "prometheus_before": before,
        "prometheus_after": after,
    }
    write_json(output / "summaries" / f"topology_{replicas}_replica_probe.json", result)
    if deltas.get("doctor", 0) <= 0:
        raise ExperimentStopped(f"the {replicas}-replica probe reached no primary Doctor requests")
    if benchmark_policy_redis_delta <= 0:
        raise ExperimentStopped(f"the {replicas}-replica route did not use Redis-backed benchmark admission")
    if replicas == 1 and deltas.get("doctor_replica", 0) != 0:
        raise ExperimentStopped("the one-replica condition delivered requests to doctor_replica")
    if replicas == 2 and deltas.get("doctor_replica", 0) <= 0:
        raise ExperimentStopped("the two-replica condition did not deliver requests to doctor_replica")
    return result


def benchmark_route_upstream_counts(route_bytes: bytes, replicas: int) -> tuple[int, int]:
    if replicas not in BENCHMARK_HOSTS:
        raise ValueError("only one or two Doctor upstreams are supported")
    parts = route_bytes.split(b"  services:\n", 1)
    if len(parts) != 2:
        raise ExperimentStopped("Traefik route file has no services section")
    services = parts[1]
    markers = {
        1: b"    doctor-phase8-benchmark-one:\n",
        2: b"    doctor-phase8-benchmark-two:\n",
    }
    marker = markers[replicas]
    if any(services.count(value) != 1 for value in markers.values()):
        raise ExperimentStopped("Traefik route file must contain both isolated benchmark services")
    start = services.index(marker)
    end_candidates = [
        services.find(value, start + len(marker))
        for value in (markers[1], markers[2], b"    appointment:\n")
    ]
    end_candidates = [position for position in end_candidates if position > start]
    if not end_candidates:
        raise ExperimentStopped("benchmark service boundary does not match the reviewed route file")
    end = min(end_candidates)
    benchmark_service = services[start:end]
    return (
        benchmark_service.count(b"http://doctor:8000"),
        benchmark_service.count(b"http://doctor_replica:8000"),
    )


async def admission_preflight(
    *,
    output: Path,
    run_id: str,
    client: httpx.AsyncClient,
    specs: Mapping[str, RequestSpec],
    tracing_disabled: bool = False,
) -> dict[str, Any]:
    progress_before = trial_container_snapshot(tracing_disabled)
    sampler = DockerStatsSampler(tracing_disabled=tracing_disabled)
    sampler.start(progress_before)
    try:
        await warm_up(
            client,
            specs,
            concurrency=4,
            seconds=2.0,
            scenario="mixed_read",
            seed=20261013,
            stop_event=sampler.stop_event,
        )
        samples = await run_fixed_window(
            client,
            specs,
            concurrency=4,
            window_seconds=5.0,
            scenario="mixed_read",
            run_id=run_id + "-preflight",
            trial=0,
            level="preflight",
            replicas=1,
            seed=20261013,
            stop_event=sampler.stop_event,
        )
        progress_after = trial_container_snapshot(tracing_disabled)
    finally:
        await sampler.stop()
    write_samples(output / "requests" / "admission_preflight.csv", samples)
    sampler.write(output / "resources" / "admission_preflight.csv")
    summary = summarize_samples(samples, 5.0)
    summary.update(
        {
            "case_id": "admission_preflight",
            "concurrency": 4,
            "replicas": 1,
            "warmup_seconds": 2,
            "resource_summary": resource_summary(sampler.rows),
            "monitor_errors": sampler.errors,
            "docker_before": progress_before,
            "docker_after": progress_after,
        }
    )
    await asyncio.sleep(16.0)
    backend_snapshot = prometheus_snapshot("admission-preflight")
    summary["prometheus_backend"] = verify_benchmark_redis_admission(backend_snapshot)
    write_snapshot(output / "metrics" / "admission-preflight.json", backend_snapshot)
    write_json(output / "summaries" / "admission_preflight.json", summary)
    if summary["successful"] <= 0:
        raise ExperimentStopped("admission preflight had no successful authenticated Doctor responses")
    if (summary["rejection_percent"] or 0.0) >= 10.0:
        raise ExperimentStopped("admission preflight remained materially dominated by HTTP 429")
    if summary["http_5xx"] or summary["timeouts"] or summary["connection_failures"]:
        raise ExperimentStopped("admission preflight observed a server, timeout, or connection failure")
    if not summary["prometheus_backend"]["redis_observed"]:
        raise ExperimentStopped("Prometheus did not confirm Redis-backed benchmark admission")
    guardrail = guardrail_reason(
        samples, sampler.rows, progress_before, progress_after
    )
    if guardrail:
        raise ExperimentStopped("admission preflight resource guardrail: " + guardrail)
    if sampler.errors:
        raise ExperimentStopped("Docker resource sampling failed during admission preflight")
    return summary


def matrix_summary(
    output: Path,
    trial_numbers: Sequence[int] = (1, 2, 3),
) -> dict[str, Any]:
    def median_or_none(values: Sequence[float | None]) -> float | None:
        present = [float(value) for value in values if value is not None]
        return statistics.median(present) if present else None

    combinations: dict[str, Any] = {}
    for replicas in (1, 2):
        for concurrency, level in ((4, "low"), (16, "medium"), (64, "high")):
            trials = [
                json.loads((output / "summaries" / f"r{replicas}-c{concurrency}-t{trial}.json").read_text())
                for trial in trial_numbers
            ]
            if any(item.get("replicas") != replicas or item.get("concurrency") != concurrency for item in trials):
                raise RuntimeError("trial summary metadata does not match its matrix cell")
            combinations[f"r{replicas}-c{concurrency}"] = {
                "replicas": replicas,
                "concurrency": concurrency,
                "level": level,
                "trials": trials,
                "median_successful_rps": statistics.median(
                    float(item["successful_rps"]) for item in trials
                ),
                "median_attempted_rps": statistics.median(
                    float(item["attempted_rps"]) for item in trials
                ),
                "median_admitted_rps": statistics.median(
                    float(item["admitted_rps"]) for item in trials
                ),
                "median_success_mean_latency_ms": median_or_none(
                    [item["success_latency_ms"]["mean"] for item in trials]
                ),
                "median_success_p95_latency_ms": median_or_none(
                    [item["success_latency_ms"]["p95"] for item in trials]
                ),
                "median_rejection_percent": statistics.median(
                    float(item["rejection_percent"] or 0.0) for item in trials
                ),
                "median_server_error_percent": statistics.median(
                    100.0 * float(item["http_5xx"]) / max(1, int(item["completed_http_responses"]))
                    for item in trials
                ),
            }

    scaling: dict[str, Any] = {}
    for concurrency, level in ((4, "low"), (16, "medium"), (64, "high")):
        one = combinations[f"r1-c{concurrency}"]
        two = combinations[f"r2-c{concurrency}"]
        t1 = one["median_successful_rps"]
        t2 = two["median_successful_rps"]
        improvement = t2 / t1 if t1 > 0 else None
        efficiency = 100.0 * t2 / (2.0 * t1) if t1 > 0 else None
        scaling[level] = {
            "concurrency": concurrency,
            "one_replica_successful_rps": t1,
            "two_replica_successful_rps": t2,
            "throughput_improvement_ratio": improvement,
            "scaling_efficiency_percent": efficiency,
            "one_replica_success_mean_latency_ms": one["median_success_mean_latency_ms"],
            "two_replica_success_mean_latency_ms": two["median_success_mean_latency_ms"],
            "one_replica_success_p95_latency_ms": one["median_success_p95_latency_ms"],
            "two_replica_success_p95_latency_ms": two["median_success_p95_latency_ms"],
        }
    result = {
        "matrix": combinations,
        "scaling_comparison": scaling,
        "statistics_method": (
            "single observed trial per matrix cell; no population estimate"
            if len(trial_numbers) == 1
            else f"median across {len(trial_numbers)} trial summaries per matrix cell"
        ),
        "trial_count": len(trial_numbers),
        "limited_statistical_evidence": len(trial_numbers) == 1,
    }
    write_json(output / "summaries" / "matrix_summary.json", result)
    return result


async def api_readiness(base_url: str) -> dict[str, int | None]:
    paths = {
        "patient": "/api/v1/patients/health/ready",
        "doctor": "/api/v1/doctors/health/ready",
        "appointment": "/api/v1/appointments/health/ready",
        "records": "/api/v1/records/health/ready",
        "pharmacy": "/api/v1/pharmacy/health/ready",
        "billing": "/api/v1/billing/health/ready",
        "emergency": "/api/v1/emergencies/health/ready",
    }
    result: dict[str, int | None] = {}
    async with httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=4.0, trust_env=False) as client:
        for service, path in paths.items():
            try:
                response = await client.get(path)
                result[service] = response.status_code
            except httpx.RequestError:
                result[service] = None
    return result


def verify_prometheus_targets(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    rows = metric_vector(snapshot, "api_targets")
    values = [float(row.get("value", [None, "0"])[1]) for row in rows]
    services = {str(row.get("metric", {}).get("service", "")) for row in rows}
    replica_sources = {str(row.get("metric", {}).get("replica_source", "")) for row in rows}
    required = {"patient", "doctor", "appointment", "records", "pharmacy", "billing", "emergency"}
    result = {
        "series": rows,
        "services_observed": sorted(service for service in services if service),
        "all_up": bool(values) and all(value >= 1.0 for value in values),
        "all_services_observed": required.issubset(services),
        "doctor_replica_observed": "doctor_replica" in replica_sources,
    }
    if not result["all_up"] or not result["all_services_observed"] or not result["doctor_replica_observed"]:
        raise ExperimentStopped("Prometheus reports a missing or down hospital API/readiness target")
    return result


def verify_all_prometheus_targets(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    rows = metric_vector(snapshot, "all_targets")
    targets = [
        {
            "labels": row.get("metric", {}),
            "up": float(row.get("value", [None, "0"])[1]),
        }
        for row in rows
    ]
    down = [target for target in targets if target["up"] < 1.0]
    result = {"target_count": len(targets), "down_targets": down, "all_up": bool(targets) and not down}
    if not result["all_up"]:
        raise ExperimentStopped("one or more Prometheus scrape or blackbox targets are down")
    return result


def assert_doctor_http_metrics_active() -> dict[str, bool]:
    probe = (
        "import urllib.request; text=urllib.request.urlopen('http://127.0.0.1:8000/metrics', timeout=3).read().decode(); "
        "assert 'pulsegrid_http_requests_total' in text"
    )
    result = {}
    for container in ("pulsegrid-doctor-1", "pulsegrid-doctor_replica-1"):
        run_command("docker", "exec", container, "python", "-c", probe, timeout=10.0)
        result[container] = True
    return result


def compose_env_value(container: str, key: str) -> str | None:
    raw = run_command("docker", "inspect", "--format", "{{json .Config.Env}}", container)
    entries = json.loads(raw)
    prefix = key + "="
    return next((entry[len(prefix):] for entry in entries if entry.startswith(prefix)), None)


def assert_tracing_disabled(*, require_stopped: bool = True) -> dict[str, Any]:
    applications: dict[str, dict[str, str | None]] = {}
    for service, container in PHASE82_API_CONTAINERS.items():
        enabled = compose_env_value(container, "PULSEGRID_TELEMETRY_ENABLED")
        endpoint = compose_env_value(container, "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
        applications[service] = {"telemetry_enabled": enabled, "trace_endpoint": endpoint}
        if enabled != "false" or endpoint not in (None, ""):
            raise ExperimentStopped(f"distributed tracing remained enabled in {container}")
    command = json.loads(
        run_command("docker", "inspect", "--format", "{{json .Config.Cmd}}", "pulsegrid-traefik-1")
    ) or []
    expected_command = "--configFile=/etc/traefik/traefik.phase8-benchmark.yaml"
    if expected_command not in command:
        raise ExperimentStopped("Traefik is not using the tracing-free benchmark configuration")
    static_hash = mounted_traefik_static_sha256("/etc/traefik/traefik.phase8-benchmark.yaml")
    static_bytes = PHASE82_TRAEFIK_CONFIG.read_bytes()
    if static_hash != sha256(static_bytes) or b"\ntracing:\n" in static_bytes:
        raise ExperimentStopped("the active Traefik benchmark configuration is not tracing-free")
    grafana = inspect_container("pulsegrid-grafana-1")
    expected_grafana_limit = 384 * 1024 * 1024
    if grafana["memory_limit_bytes"] != expected_grafana_limit:
        raise ExperimentStopped("Grafana does not have the declared benchmark-only 384 MiB cap")
    tracing_container_states = {}
    if require_stopped:
        for name in ("pulsegrid-tempo-1", "pulsegrid-otel-collector-1"):
            status = inspect_container(name)["status"]
            tracing_container_states[name] = status
            if status != "exited":
                raise ExperimentStopped(f"{name} was not stopped for the tracing-free experiment")
    return {
        "applications": applications,
        "traefik_command": command,
        "traefik_static_config_sha256": static_hash,
        "grafana_memory_limit_bytes": grafana["memory_limit_bytes"],
        "tracing_container_states": tracing_container_states,
    }


def restored_tracing_snapshot() -> dict[str, Any]:
    applications: dict[str, dict[str, str | None]] = {}
    expected_endpoint = "http://otel-collector:4318/v1/traces"
    for service, container in PHASE82_API_CONTAINERS.items():
        enabled = compose_env_value(container, "PULSEGRID_TELEMETRY_ENABLED")
        endpoint = compose_env_value(container, "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
        applications[service] = {"telemetry_enabled": enabled, "trace_endpoint": endpoint}
        if enabled != "true" or endpoint != expected_endpoint:
            raise ExperimentStopped(f"normal tracing configuration was not restored in {container}")
    static_bytes = (ROOT / "infra/traefik/traefik.yaml").read_bytes()
    static_hash = mounted_traefik_static_sha256("/etc/traefik/traefik.yaml")
    if static_hash != sha256(static_bytes) or b"\ntracing:\n" not in static_bytes:
        raise ExperimentStopped("normal Traefik tracing configuration was not restored")
    command = json.loads(
        run_command("docker", "inspect", "--format", "{{json .Config.Cmd}}", "pulsegrid-traefik-1")
    ) or []
    if any("traefik.phase8-benchmark.yaml" in str(item) for item in command):
        raise ExperimentStopped("Traefik benchmark configuration remained active after restoration")
    grafana = inspect_container("pulsegrid-grafana-1")
    if grafana["memory_limit_bytes"] != 256 * 1024 * 1024:
        raise ExperimentStopped("normal Grafana memory cap was not restored")
    tracing_container_states = {}
    for name in ("pulsegrid-tempo-1", "pulsegrid-otel-collector-1"):
        status = inspect_container(name)["status"]
        tracing_container_states[name] = status
        if status != "running":
            raise ExperimentStopped(f"{name} did not return to the normal running state")
    return {
        "applications": applications,
        "traefik_static_config_sha256": static_hash,
        "traefik_command": command,
        "grafana_memory_limit_bytes": grafana["memory_limit_bytes"],
        "tracing_container_states": tracing_container_states,
    }


async def run_matrix(args: argparse.Namespace) -> None:
    output = Path(args.output).resolve()
    if not output.is_relative_to(ROOT):
        raise RuntimeError("results must be stored under experiments/phase8/results")
    output.mkdir(parents=True, exist_ok=True)
    existing = {item.name for item in output.iterdir()}
    allowed_existing = {"tempo"}
    if existing - allowed_existing and not (output / "progress.json").exists():
        raise RuntimeError("results path contains prior non-Tempo artifacts; refusing to overwrite")
    progress_path = output / "progress.json"
    starting_commit = run_command("git", "rev-parse", "HEAD")
    branch = run_command("git", "branch", "--show-current")
    if branch != "main":
        raise RuntimeError(f"Phase 8.1 requires local main; current branch is {branch}")
    fixture_state, doctor_id = load_private_fixture(Path(args.fixture).resolve())
    actor_data = fixture_state["actors"]["patient"]
    admin_data, admin_fixture_seed_hash = load_private_admin_fixture(
        Path(args.admin_fixture).resolve()
    )
    fixture_seed_hash = sha256(str(fixture_state.get("run", "")).encode())[:16]
    progress = load_progress(progress_path, args.run_id, starting_commit)
    if progress.get("interrupted_cases"):
        raise ExperimentStopped("a previously started trial is incomplete and will not be repeated")
    route = DoctorRoute(ROUTE_PATH)
    patient = AuthenticatedActor(args.base_url, actor_data)
    admin = AuthenticatedActor(args.base_url, admin_data)
    patient_token: str | None = None
    admin_token: str | None = None
    client: httpx.AsyncClient | None = None
    benchmark_compose_applied = False
    benchmark_routes_activated = False
    previous_principal = os.environ.get("PHASE8_BENCHMARK_PRINCIPAL_ID")
    completion_error: str | None = None
    manifest_path = output / "manifest.json"
    if progress.get("last_error") and not progress.get("started_cases"):
        prior_error = str(progress.pop("last_error"))
        attempt_dir = output / "setup_attempts"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        attempt_number = 1
        prior_manifest = attempt_dir / f"manifest-before-retry-{attempt_number}.json"
        while prior_manifest.exists():
            attempt_number += 1
            prior_manifest = attempt_dir / f"manifest-before-retry-{attempt_number}.json"
        if manifest_path.exists():
            prior_manifest.write_bytes(manifest_path.read_bytes())
            archived_manifest: str | None = str(prior_manifest.relative_to(output))
        else:
            archived_manifest = None
        progress.setdefault("recovered_setup_errors", []).append(
            {"error": prior_error, "manifest": archived_manifest}
        )
        write_json(progress_path, progress)
    manifest: dict[str, Any] = {
        "run_id": args.run_id,
        "status": "running",
        "started_utc": utc_now(),
        "branch": branch,
        "starting_commit": starting_commit,
        "recovered_setup_errors": progress.get("recovered_setup_errors", []),
        "invalidated_trials": progress.get("invalidated_cases", []),
        "route_file_sha256_before": route.original_hash,
        "active_traefik_route_file": str(ROUTE_PATH.relative_to(ROOT)),
        "compose_configuration_sha256": compose_configuration_hash(),
        "benchmark_compose_sha256": sha256((ROOT / BENCHMARK_COMPOSE_FILE).read_bytes()),
        "fixture_seed_sha256_prefix": fixture_seed_hash,
        "admin_fixture_seed_sha256_prefix": admin_fixture_seed_hash,
        "workload_seed": 20261013,
        "dataset": {
            "actor_role": "synthetic patient",
            "doctor_profiles": "preflight count recorded without names or IDs",
            "synthetic_fixture": str(Path(args.fixture).resolve()),
            "admin_fixture": str(Path(args.admin_fixture).resolve()),
        },
        "doctor_image_before_benchmark_build": run_command(
            "docker", "image", "inspect", "--format", "{{.Id}}", "pulsegrid-auth-doctor:local"
        ),
        "request_mix": {"directory": 0.5, "autocomplete": 0.3, "profile": 0.2},
        "endpoint_methods": "authenticated GET only",
        "benchmark_route_hosts": {
            "one_upstream": BENCHMARK_HOSTS[1],
            "two_upstream": BENCHMARK_HOSTS[2],
        },
        "benchmark_admission_policy": {
            "policy_id": "doctor_directory_search_phase8_benchmark",
            "redis_enabled": True,
            "normal_keyspace_unchanged": True,
            "preauth_budgets_capacity_and_milli_tokens_per_second": {
                "source": [10000, 2000000],
                "aggregate": [20000, 2000000],
            },
            "authenticated_budgets_capacity_and_milli_tokens_per_second": {
                "principal": [10000, 2000000],
                "aggregate": [20000, 2000000],
            },
            "identity": "one configured fixture principal, checked against the verified JWT principal",
            "operation_class": "retained server-derived route class; no emergency/admin priority",
        },
        "concurrency_levels": [4, 16, 64],
        "replica_counts": [1, 2],
        "warmup_seconds": 5,
        "measurement_seconds": 30,
        "trials_per_combination_predeclared": 3,
        "planned_trials": 18,
        "timeout_seconds": 5,
        "retry_policy": "none",
        "cache_state": "same persistent application state; five-second warm-up before each measurement; no cache flush",
        "normal_rate_policy_source": "components/rate_limiter/src/pulsegrid_rate_limiter/policies.py",
        "hardware_software": capture_host_context(),
        "docker_resource_snapshot_before_load": capture_docker_pressure(),
        "mac_memory_free_percent_before_load": capture_mac_memory_free_percent(),
    }
    write_json(manifest_path, manifest)
    try:
        if progress.get("completed_cases"):
            if not (output / "manifest.json").exists():
                raise RuntimeError("matrix progress exists without its manifest")
        if manifest["docker_resource_snapshot_before_load"]["docker_vm_memory_percent"] >= 90.0:
            raise ExperimentStopped("Docker VM memory was already at 90% before the matrix")
        mac_free = manifest["mac_memory_free_percent_before_load"]
        if mac_free is not None and mac_free < 10.0:
            raise ExperimentStopped("macOS reported less than 10% free memory before the matrix")
        assert_core_healthy(manifest["hardware_software"]["containers"])
        readiness_before = await api_readiness(args.base_url)
        if any(status != 200 for status in readiness_before.values()):
            raise ExperimentStopped("all seven hospital API readiness routes must return 200 before the matrix")
        if run_command(
            "docker", "exec", "pulsegrid-grafana-1", "curl", "-fsS", "--max-time", "3",
            "http://tempo:3200/ready"
        ) != "ready":
            raise ExperimentStopped("Tempo readiness failed before the matrix")

        patient_token = patient.login()
        admin_token = admin.login()
        initial_surge_status = surge_status(admin.client)
        manifest["initial_surge_status"] = initial_surge_status
        manifest["hospital_api_readiness_before"] = readiness_before
        if initial_surge_status.get("http_status") != 200 or initial_surge_status.get("state") != "NORMAL":
            raise ExperimentStopped("Surge Mode is not NORMAL before load; preserving the existing state")
        specs = workload_specs(doctor_id)
        normal_client = http_client(args.base_url, patient_token, 64)
        normal_response = await normal_client.get(specs["directory"].path, params=specs["directory"].params)
        if normal_response.status_code != 200:
            raise ExperimentStopped("normal authenticated Doctor directory request failed before isolated setup")
        await normal_client.aclose()

        principal_id = access_token_subject(patient_token)
        os.environ["PHASE8_BENCHMARK_PRINCIPAL_ID"] = principal_id
        run_command(
            "docker", "compose", *COMPOSE_PREFIX, "-f", BENCHMARK_COMPOSE_FILE,
            "config", "--quiet", timeout=30.0
        )
        image_policy_present = doctor_image_has_benchmark_policy()
        manifest["doctor_image_policy_present_before_setup"] = image_policy_present
        if not image_policy_present:
            compose_command("build", "doctor", timeout=600.0)
        manifest["doctor_image_build_performed"] = not image_policy_present
        doctor_image_id = run_command(
            "docker", "image", "inspect", "--format", "{{.Id}}", "pulsegrid-auth-doctor:local"
        )
        manifest["doctor_image_after_benchmark_build"] = doctor_image_id
        manifest["doctor_image_changed_for_benchmark_policy"] = (
            doctor_image_id != manifest["doctor_image_before_benchmark_build"]
        )
        compose_command(
            "up", "-d", "--no-deps", "--no-build", "doctor", "doctor_replica",
            benchmark_enabled=True, timeout=120.0
        )
        benchmark_compose_applied = True
        services = await wait_for_doctor_services()
        for name in ("pulsegrid-doctor-1", "pulsegrid-doctor_replica-1"):
            run_command(
                "docker", "exec", name, "python", "-c",
                "from doctor_service.admission import PHASE8_BENCHMARK_HOSTS; assert PHASE8_BENCHMARK_HOSTS == frozenset({'phase8-one.localhost', 'phase8-two.localhost'})",
            )
            if compose_env_value(name, "PULSEGRID_DOCTOR_PHASE8_BENCHMARK_ENABLED") != "true":
                raise ExperimentStopped(f"the benchmark admission overlay was not enabled in {name}")
            if compose_env_value(name, "PULSEGRID_DOCTOR_PHASE8_BENCHMARK_PRINCIPAL_ID") != principal_id:
                raise ExperimentStopped(f"the verified synthetic principal was not configured in {name}")
        manifest["benchmark_doctor_services"] = services
        manifest["benchmark_overlay_enabled"] = True
        manifest["benchmark_policy_import_verified_in_both_doctor_processes"] = True
        write_json(manifest_path, manifest)

        benchmark_client = http_client(args.base_url, patient_token, 64, benchmark_host=True)
        client = benchmark_client
        manifest["traefik_route_sha256_before_reload"] = mounted_traefik_route_sha256()
        route.activate()
        benchmark_routes_activated = True
        compose_command(
            "up", "-d", "--no-deps", "--no-build", "--force-recreate", "traefik",
            timeout=120.0,
        )
        manifest["benchmark_traefik_container"] = await wait_for_traefik_service()
        manifest["benchmark_traefik_route_sha256"] = mounted_traefik_route_sha256()
        if manifest["benchmark_traefik_route_sha256"] != sha256(route.benchmark_routes):
            raise ExperimentStopped("Traefik did not mount the active Phase 4 benchmark route file")
        await asyncio.sleep(2.0)
        benchmark_client.headers["Host"] = route.set_replicas(1)
        manifest["benchmark_route_enabled_one_upstream"] = True
        manifest["benchmark_route_enabled_two_upstream"] = True
        write_json(manifest_path, manifest)
        counts = await preflight(client, specs)
        manifest["authenticated_route_preflight"] = counts
        if "admission_preflight" not in progress.get("completed_stages", []):
            summary = await admission_preflight(
                output=output,
                run_id=args.run_id,
                client=client,
                specs=specs,
            )
            progress.setdefault("completed_stages", []).append("admission_preflight")
            write_json(progress_path, progress)
        else:
            summary = json.loads((output / "summaries" / "admission_preflight.json").read_text())
        manifest["admission_preflight"] = summary
        write_json(manifest_path, manifest)

        condition_order = [(1, 4), (2, 4), (2, 16), (1, 16), (1, 64), (2, 64)]
        topology_verified: set[int] = set()
        for trial in (1, 2, 3):
            rotation = ((trial - 1) * 2) % len(condition_order)
            ordered_conditions = condition_order[rotation:] + condition_order[:rotation]
            for replicas, concurrency in ordered_conditions:
                stage = f"topology_{replicas}_replica"
                if stage in progress.get("completed_stages", []):
                    topology_verified.add(replicas)
                benchmark_client.headers["Host"] = route.set_replicas(replicas)
                if replicas not in topology_verified:
                    await verify_replica_topology(client, specs["profile"], output, replicas)
                    topology_verified.add(replicas)
                    if stage not in progress.get("completed_stages", []):
                        progress.setdefault("completed_stages", []).append(stage)
                        write_json(progress_path, progress)
                token = patient.refresh_if_expiring()
                benchmark_client.headers["Authorization"] = f"Bearer {token}"
                case_id = f"r{replicas}-c{concurrency}-t{trial}"
                await run_trial(
                    output=output,
                    run_id=args.run_id,
                    progress=progress,
                    progress_path=progress_path,
                    client=benchmark_client,
                    specs=specs,
                    case_id=case_id,
                    scenario="mixed_read",
                    concurrency=concurrency,
                    trial=trial,
                    level={4: "low", 16: "medium", 64: "high"}[concurrency],
                    replicas=replicas,
                    seed=20261013,
                )
        expected_cases = {
            f"r{replicas}-c{concurrency}-t{trial}"
            for replicas in (1, 2)
            for concurrency in (4, 16, 64)
            for trial in (1, 2, 3)
        }
        if set(progress.get("completed_cases", [])) != expected_cases:
            raise ExperimentStopped("the fixed 18-trial matrix did not complete exactly as predeclared")
        result = matrix_summary(output)
        manifest["matrix_summary"] = result
        manifest["status"] = "completed"
        progress.setdefault("completed_stages", []).append("matrix")
        write_json(progress_path, progress)
    except BaseException as error:
        completion_error = f"{type(error).__name__}: {str(error)[:500]}"
        manifest["status"] = "partial"
        manifest["error"] = completion_error
        if isinstance(error, ExperimentStopped):
            manifest["stop_condition"] = str(error)
        progress["last_error"] = completion_error
        write_json(progress_path, progress)
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

        if benchmark_routes_activated:
            try:
                compose_command(
                    "up", "-d", "--no-deps", "--no-build", "--force-recreate", "traefik",
                    timeout=120.0,
                )
                manifest["normal_traefik_container"] = await wait_for_traefik_service()
                manifest["normal_traefik_route_sha256"] = mounted_traefik_route_sha256()
                manifest["traefik_route_restored"] = (
                    manifest["normal_traefik_route_sha256"] == route.original_hash
                )
                if not manifest["traefik_route_restored"]:
                    raise ExperimentStopped("Traefik did not reload the restored active route file")
                benchmark_routes_activated = False
            except Exception as restore_error:
                manifest["traefik_restore_error"] = f"{type(restore_error).__name__}: {str(restore_error)[:400]}"
                manifest["status"] = "partial"

        if benchmark_compose_applied:
            try:
                # The longest benchmark Redis bucket expires within 11 seconds.
                await asyncio.sleep(12.0)
                compose_command(
                    "up", "-d", "--no-deps", "--no-build", "doctor", "doctor_replica",
                    timeout=120.0
                )
                restored_services = await wait_for_doctor_services()
                manifest["normal_doctor_services"] = restored_services
                benchmark_compose_applied = False
            except Exception as restore_error:
                manifest["compose_restore_error"] = f"{type(restore_error).__name__}: {str(restore_error)[:400]}"
                manifest["status"] = "partial"

        if previous_principal is None:
            os.environ.pop("PHASE8_BENCHMARK_PRINCIPAL_ID", None)
        else:
            os.environ["PHASE8_BENCHMARK_PRINCIPAL_ID"] = previous_principal

        try:
            final_containers = container_snapshot()
            assert_core_healthy(final_containers)
            manifest["final_core_containers"] = final_containers
            for name in ("pulsegrid-doctor-1", "pulsegrid-doctor_replica-1"):
                enabled = compose_env_value(name, "PULSEGRID_DOCTOR_PHASE8_BENCHMARK_ENABLED")
                principal = compose_env_value(name, "PULSEGRID_DOCTOR_PHASE8_BENCHMARK_PRINCIPAL_ID")
                if enabled == "true" or principal is not None:
                    raise ExperimentStopped("benchmark admission configuration remained enabled after restoration")
            manifest["benchmark_admission_restored"] = True
        except Exception as health_error:
            manifest["status"] = "partial"
            manifest["restoration_health_error"] = f"{type(health_error).__name__}: {str(health_error)[:400]}"

        try:
            if patient.access_token is not None:
                patient_token = patient.refresh_if_expiring()
                async with httpx.AsyncClient(
                    base_url=args.base_url.rstrip("/"),
                    headers={"Authorization": f"Bearer {patient_token}"},
                    timeout=5.0,
                    trust_env=False,
                ) as normal_client:
                    normal_before = doctor_normal_admission_counters()
                    directory = await normal_client.get(
                        "/api/v1/doctors", params={"q": "Synthetic", "limit": "20"}
                    )
                    manifest["normal_doctor_directory_status"] = directory.status_code
                    if directory.status_code != 200:
                        raise ExperimentStopped("normal authenticated Doctor directory access did not recover")
                    normal_after = doctor_normal_admission_counters()
                    normal_before_total = sum(normal_before.values())
                    normal_after_total = sum(normal_after.values())
                    backend_snapshot = prometheus_snapshot("normal-admission-restored")
                    write_snapshot(
                        output / "metrics" / "normal-admission-restored.after.json",
                        backend_snapshot,
                    )
                    normal_rows = metric_vector(backend_snapshot, "doctor_admission_backend")
                    normal_policy = [
                        row for row in normal_rows
                        if row.get("metric", {}).get("policy") == "doctor_directory_search_directory"
                    ]
                    manifest["normal_admission_backend_series"] = normal_policy
                    manifest["normal_admission_redis_counter_before_by_container"] = normal_before
                    manifest["normal_admission_redis_counter_after_by_container"] = normal_after
                    manifest["normal_admission_redis_counter_delta"] = (
                        normal_after_total - normal_before_total
                    )
                    if normal_after_total <= normal_before_total:
                        raise ExperimentStopped("normal Doctor request did not use Redis-backed admission after restoration")
            async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), timeout=5.0, trust_env=False) as unauthenticated:
                emergency = await unauthenticated.get("/api/v1/emergencies")
                manifest["unauthenticated_emergency_status"] = emergency.status_code
                if emergency.status_code not in (401, 403):
                    raise ExperimentStopped("unauthenticated Emergency read was not rejected with 401/403")
            readiness_after = await api_readiness(args.base_url)
            manifest["hospital_api_readiness_after"] = readiness_after
            if any(status != 200 for status in readiness_after.values()):
                raise ExperimentStopped("hospital API readiness failed after restoring normal configuration")
            tempo_ready = run_command(
                "docker", "exec", "pulsegrid-grafana-1", "curl", "-fsS", "--max-time", "3",
                "http://tempo:3200/ready"
            )
            if tempo_ready != "ready":
                raise ExperimentStopped("Tempo readiness failed after the matrix")
            final_prometheus = prometheus_snapshot("final-restored-targets")
            manifest["prometheus_target_health"] = verify_prometheus_targets(final_prometheus)
            write_snapshot(output / "metrics" / "final-restored-targets.json", final_prometheus)
            if admin.access_token is not None:
                admin.refresh_if_expiring()
                final_surge = surge_status(admin.client)
                manifest["final_surge_status"] = final_surge
                if final_surge.get("http_status") != 200 or final_surge.get("state") != "NORMAL":
                    raise ExperimentStopped("Surge Mode was not NORMAL after restoration")
        except Exception as verify_error:
            manifest["status"] = "partial"
            manifest["restoration_verification_error"] = f"{type(verify_error).__name__}: {str(verify_error)[:400]}"

        for actor in (patient, admin):
            try:
                actor.refresh_if_expiring()
                actor.logout()
            except Exception as logout_error:
                manifest.setdefault("cleanup_errors", []).append(
                    f"synthetic actor logout failed: {type(logout_error).__name__}: {str(logout_error)[:250]}"
                )
                actor.client.close()

        manifest["ended_utc"] = utc_now()
        manifest["error"] = completion_error
        if manifest.get("status") == "completed" and (
            manifest.get("route_restored") is not True
            or manifest.get("benchmark_admission_restored") is not True
            or manifest.get("traefik_route_restored") is not True
            or any(status != 200 for status in manifest.get("hospital_api_readiness_after", {}).values())
        ):
            manifest["status"] = "partial"
        write_json(manifest_path, manifest)
    if completion_error or manifest.get("status") != "completed":
        raise SystemExit(completion_error or "Phase 8.1 matrix or restoration verification was incomplete")


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
    parser.add_argument("--run-id", default="phase8-1-20261013-run1")
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
