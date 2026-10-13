#!/usr/bin/env python3
"""Run one bounded Tempo observation with low-rate authenticated trace traffic."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import statistics
import subprocess
import time
from typing import Any
import uuid

import httpx

try:
    from .benchmark import AuthenticatedActor, load_private_fixture
except ImportError:
    from benchmark import AuthenticatedActor, load_private_fixture


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "experiments/phase8/results/phase8-1-20261013-run1/tempo"
DEFAULT_FIXTURE = Path("/tmp/pulsegrid-phase3-live-fixture.json")
TEMPO = "pulsegrid-tempo-1"
PROBE = "pulsegrid-grafana-1"
BASE_URL = "http://127.0.0.1:8080"
DOCTOR_DIRECTORY = "/api/v1/doctors"
SAMPLE_FIELDS = (
    "timestamp_utc",
    "elapsed_seconds",
    "status",
    "exit_code",
    "oom_killed",
    "restart_count",
    "started_at",
    "ready",
    "memory_bytes",
    "memory_limit_bytes",
    "memory_percent",
    "cpu_percent",
)
WORKLOAD_FIELDS = (
    "timestamp_utc",
    "elapsed_seconds",
    "trace_id",
    "status_code",
    "latency_ms",
    "classification",
)
API_READINESS_PATHS = {
    "patient": "/api/v1/patients/health/ready",
    "doctor": "/api/v1/doctors/health/ready",
    "appointment": "/api/v1/appointments/health/ready",
    "records": "/api/v1/records/health/ready",
    "pharmacy": "/api/v1/pharmacy/health/ready",
    "billing": "/api/v1/billing/health/ready",
    "emergency": "/api/v1/emergencies/health/ready",
}


def run(*args: str, timeout: float = 8.0) -> str:
    result = subprocess.run(
        list(args),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode:
        message = result.stderr.strip() or result.stdout.strip() or "command failed"
        raise RuntimeError(f"{args[0]} failed: {message[:300]}")
    return result.stdout.strip()


def inspect_tempo() -> dict[str, Any]:
    state = json.loads(run("docker", "inspect", "--format", "{{json .State}}", TEMPO))
    restart_count = int(run("docker", "inspect", "--format", "{{.RestartCount}}", TEMPO))
    limit = int(run("docker", "inspect", "--format", "{{.HostConfig.Memory}}", TEMPO))
    return {
        "status": state.get("Status"),
        "exit_code": state.get("ExitCode"),
        "oom_killed": state.get("OOMKilled"),
        "started_at": state.get("StartedAt"),
        "restart_count": restart_count,
        "memory_limit_bytes": limit,
    }


def parse_size(value: str) -> int:
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]+)\s*", value)
    if not match:
        raise ValueError(f"unsupported Docker memory size: {value!r}")
    scale = {
        "B": 1,
        "kB": 1000,
        "KB": 1000,
        "KiB": 1024,
        "MB": 1000**2,
        "MiB": 1024**2,
        "GB": 1000**3,
        "GiB": 1024**3,
    }.get(match.group(2))
    if scale is None:
        raise ValueError(f"unsupported Docker memory unit: {match.group(2)}")
    return int(float(match.group(1)) * scale)


def read_stats() -> tuple[int, int | None, float | None]:
    sample = json.loads(
        run("docker", "stats", "--no-stream", "--format", "{{json .}}", TEMPO)
    )
    usage, reported_limit = sample["MemUsage"].split("/", 1)
    memory_bytes = parse_size(usage)
    memory_limit_bytes = parse_size(reported_limit)
    cpu_match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)%\s*", sample["CPUPerc"])
    cpu_percent = float(cpu_match.group(1)) if cpu_match else None
    return memory_bytes, memory_limit_bytes, cpu_percent


def readiness_probe() -> bool:
    result = subprocess.run(
        [
            "docker",
            "exec",
            PROBE,
            "curl",
            "-fsS",
            "--max-time",
            "3",
            "http://tempo:3200/ready",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=5.0,
    )
    return result.returncode == 0 and result.stdout.strip() == "ready"


def api_readiness(base_url: str) -> dict[str, int | None]:
    results: dict[str, int | None] = {}
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=4.0, trust_env=False) as client:
        for service, path in API_READINESS_PATHS.items():
            try:
                response = client.get(path)
                results[service] = response.status_code
            except httpx.RequestError:
                results[service] = None
    return results


def generate_trace(actor: AuthenticatedActor, elapsed: float) -> dict[str, Any]:
    trace_id = uuid.uuid4().hex
    span_id = uuid.uuid4().hex[:16]
    started = time.perf_counter_ns()
    try:
        response = actor.client.get(
            DOCTOR_DIRECTORY,
            params={"q": "Synthetic", "limit": "1"},
            headers={"traceparent": f"00-{trace_id}-{span_id}-01"},
        )
        status_code: int | None = response.status_code
        classification = "success" if 200 <= response.status_code < 300 else f"http_{response.status_code}"
    except httpx.RequestError as error:
        status_code = None
        classification = type(error).__name__
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(elapsed, 3),
        "trace_id": trace_id,
        "status_code": status_code,
        "latency_ms": round((time.perf_counter_ns() - started) / 1_000_000, 3),
        "classification": classification,
    }


def count_spans(value: Any) -> int:
    if isinstance(value, list):
        return sum(count_spans(item) for item in value)
    if isinstance(value, dict):
        own_span = int(isinstance(value.get("spanId"), str))
        return own_span + sum(count_spans(item) for item in value.values())
    return 0


def trace_probe(trace_id: str) -> dict[str, Any]:
    result = subprocess.run(
        [
            "docker",
            "exec",
            PROBE,
            "curl",
            "-sS",
            "--max-time",
            "5",
            "-w",
            "\\n%{http_code}",
            f"http://tempo:3200/api/traces/{trace_id}",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=8.0,
    )
    body, _, status = result.stdout.rpartition("\n")
    try:
        data = json.loads(body) if result.returncode == 0 else {}
    except json.JSONDecodeError:
        data = {}
    spans = count_spans(data)
    return {
        "trace_id": trace_id,
        "http_status": int(status) if status.isdecimal() else None,
        "span_count": spans,
        "queryable": result.returncode == 0 and status == "200" and spans > 0,
        "body_bytes": len(body.encode("utf-8")),
    }


def query_new_trace(trace_id: str | None) -> dict[str, Any]:
    if trace_id is None:
        return {"trace_id": None, "http_status": None, "span_count": 0, "queryable": False}
    result = trace_probe(trace_id)
    for _ in range(5):
        if result["queryable"]:
            break
        time.sleep(2.0)
        result = trace_probe(trace_id)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-seconds", type=int, default=600)
    parser.add_argument("--interval-seconds", type=float, default=10.0)
    parser.add_argument("--workload-interval-seconds", type=float, default=20.0)
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if not 600 <= args.duration_seconds <= 900:
        parser.error("duration must be between 600 and 900 seconds")
    if not 5 <= args.interval_seconds <= 30:
        parser.error("sample interval must be between 5 and 30 seconds")
    if not 10 <= args.workload_interval_seconds <= 60:
        parser.error("trace workload interval must be between 10 and 60 seconds")
    return args


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_paths = (
        args.output_dir / "stability_samples.csv",
        args.output_dir / "stability_workload.csv",
        args.output_dir / "stability_summary.json",
        args.output_dir / "stability_relevant_logs.txt",
    )
    if any(path.exists() for path in output_paths):
        raise RuntimeError("stability output already exists; choose a new run directory")

    fixture_state, _ = load_private_fixture(args.fixture.resolve())
    actor = AuthenticatedActor(args.base_url, fixture_state["actors"]["patient"])
    started = datetime.now(timezone.utc)
    initial = inspect_tempo()
    if initial["status"] != "running":
        raise RuntimeError(f"Tempo must be running before observation; state={initial['status']}")
    initial_api_readiness = api_readiness(args.base_url)
    if any(value != 200 for value in initial_api_readiness.values()):
        raise RuntimeError("all seven hospital APIs must be ready before Tempo observation")
    rows: list[dict[str, Any]] = []
    workload_rows: list[dict[str, Any]] = []
    stop_reason: str | None = None
    trace_query: dict[str, Any] | None = None
    actor_logged_in = False
    started_monotonic = time.monotonic()
    deadline = started_monotonic + args.duration_seconds
    next_sample = started_monotonic
    next_workload = started_monotonic

    try:
        actor.login()
        actor_logged_in = True
        while True:
            elapsed = time.monotonic() - started_monotonic
            now = datetime.now(timezone.utc)
            state = inspect_tempo()
            ready = readiness_probe() if state["status"] == "running" else False
            if state["status"] == "running":
                memory_bytes, stats_limit, cpu_percent = read_stats()
                limit = stats_limit or state["memory_limit_bytes"]
                memory_percent = round(100 * memory_bytes / limit, 2) if limit else None
            else:
                memory_bytes, limit, cpu_percent, memory_percent = None, state["memory_limit_bytes"], None, None
            rows.append(
                {
                    "timestamp_utc": now.isoformat(),
                    "elapsed_seconds": round(elapsed, 3),
                    "status": state["status"],
                    "exit_code": state["exit_code"],
                    "oom_killed": state["oom_killed"],
                    "restart_count": state["restart_count"],
                    "started_at": state["started_at"],
                    "ready": ready,
                    "memory_bytes": memory_bytes,
                    "memory_limit_bytes": limit,
                    "memory_percent": memory_percent,
                    "cpu_percent": cpu_percent,
                }
            )
            if state["status"] != "running":
                stop_reason = f"Tempo state changed to {state['status']}"
            elif state["restart_count"] != initial["restart_count"]:
                stop_reason = "Tempo restart-count change detected"
            elif not ready:
                stop_reason = "Tempo readiness failed"
            elif memory_percent is not None and memory_percent >= 90.0:
                stop_reason = "Tempo reached 90% of its configured memory limit"
            if stop_reason:
                break

            if time.monotonic() >= next_workload:
                workload_rows.append(generate_trace(actor, elapsed))
                next_workload += args.workload_interval_seconds
            if time.monotonic() >= deadline:
                break
            next_sample += args.interval_seconds
            time.sleep(max(0.0, min(next_sample, deadline, next_workload) - time.monotonic()))
    finally:
        if actor_logged_in:
            try:
                actor.logout()
            except Exception:
                actor.client.close()
        else:
            actor.client.close()

    ended = datetime.now(timezone.utc)
    final = inspect_tempo()
    final_api_readiness = api_readiness(args.base_url)
    trace_query = query_new_trace(
        next((str(row["trace_id"]) for row in reversed(workload_rows) if row["status_code"] == 200), None)
    )
    log_result = subprocess.run(
        [
            "docker",
            "logs",
            "--timestamps",
            "--since",
            started.isoformat(),
            "--until",
            ended.isoformat(),
            TEMPO,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10.0,
    )
    if log_result.returncode:
        raise RuntimeError("could not capture the bounded Tempo log window")
    logs = "\n".join(part for part in (log_result.stdout, log_result.stderr) if part)
    log_lines = [line for line in logs.splitlines() if "level=warn" in line or "level=error" in line]
    log_lines = [
        re.sub(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", "<uuid>", line)
        for line in log_lines
    ]
    event_result = subprocess.run(
        [
            "docker",
            "events",
            "--since",
            started.isoformat(),
            "--until",
            ended.isoformat(),
            "--filter",
            f"container={TEMPO}",
            "--format",
            "{{json .}}",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10.0,
    )
    if event_result.returncode:
        event_lines = []
        event_error = event_result.stderr.strip()[:300]
    else:
        event_lines = [line for line in event_result.stdout.splitlines() if line.strip()]
        event_error = None
    log_counts = {
        "warning_lines": sum("level=warn" in line for line in log_lines),
        "error_lines": sum("level=error" in line for line in log_lines),
        "idle_no_jobs_errors": sum("level=error" in line and "no jobs found" in line for line in log_lines),
        "other_error_lines": sum("level=error" in line and "no jobs found" not in line for line in log_lines),
        "incomplete_wal_meta_warnings": sum(
            "failed to replay block" in line and "meta.json" in line for line in log_lines
        ),
    }
    intervals = [
        rows[index]["elapsed_seconds"] - rows[index - 1]["elapsed_seconds"]
        for index in range(1, len(rows))
    ]
    with output_paths[0].open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SAMPLE_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    with output_paths[1].open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=WORKLOAD_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(workload_rows)

    memory_rows = [row for row in rows if row["memory_bytes"] is not None]
    memory_percent_rows = [row for row in rows if row["memory_percent"] is not None]
    cpu_rows = [row["cpu_percent"] for row in rows if row["cpu_percent"] is not None]
    successful_traces = sum(row["classification"] == "success" for row in workload_rows)
    duration_observed = rows[-1]["elapsed_seconds"] if rows else 0.0
    completed_window = duration_observed >= args.duration_seconds - args.interval_seconds
    api_ready = all(value == 200 for value in final_api_readiness.values())
    trace_queryable = bool(trace_query and trace_query["queryable"])
    restart_delta = final["restart_count"] - initial["restart_count"]
    if stop_reason is None and not completed_window:
        stop_reason = "observation ended before the requested duration"
    if stop_reason is None and restart_delta != 0:
        stop_reason = f"Tempo restart-count delta was {restart_delta}"
    if stop_reason is None and not api_ready:
        stop_reason = "one or more hospital API readiness checks failed"
    if stop_reason is None and not trace_queryable:
        stop_reason = "no newly generated trace was queryable by trace ID"
    if stop_reason is None and log_counts["other_error_lines"]:
        stop_reason = "unclassified Tempo error-level logs appeared during observation"
    success = stop_reason is None
    summary = {
        "started_utc": started.isoformat(),
        "ended_utc": ended.isoformat(),
        "requested_duration_seconds": args.duration_seconds,
        "observed_duration_seconds": round(duration_observed, 3),
        "sample_interval_seconds": args.interval_seconds,
        "trace_workload_interval_seconds": args.workload_interval_seconds,
        "samples": len(rows),
        "observed_sample_interval_median_seconds": statistics.median(intervals) if intervals else None,
        "initial_state": initial,
        "final_state": final,
        "restart_delta": restart_delta,
        "oom_killed_at_end": final["oom_killed"],
        "readiness_successes": sum(bool(row["ready"]) for row in rows),
        "readiness_failures": sum(not row["ready"] for row in rows),
        "memory_bytes_min": min((row["memory_bytes"] for row in memory_rows), default=None),
        "memory_bytes_max": max((row["memory_bytes"] for row in memory_rows), default=None),
        "memory_percent_max": max((row["memory_percent"] for row in memory_percent_rows), default=None),
        "cpu_percent_mean": sum(cpu_rows) / len(cpu_rows) if cpu_rows else None,
        "cpu_percent_max": max(cpu_rows, default=None),
        "hospital_api_readiness_start": initial_api_readiness,
        "hospital_api_readiness_end": final_api_readiness,
        "controlled_trace_workload": {
            "endpoint": "authenticated GET /api/v1/doctors?q=Synthetic&limit=1",
            "attempted": len(workload_rows),
            "successful": successful_traces,
            "http_status_counts": {
                str(status): sum(row["status_code"] == status for row in workload_rows)
                for status in sorted({row["status_code"] for row in workload_rows if row["status_code"] is not None})
            },
            "trace_query": trace_query,
        },
        "logs": log_counts,
        "docker_lifecycle_events": [json.loads(line) for line in event_lines],
        "docker_lifecycle_event_query_error": event_error,
        "log_inspection_scope": "Tempo container logs emitted during the observation window",
        "success": success,
        "stop_reason": stop_reason,
    }
    output_paths[3].write_text("\n".join(log_lines) + ("\n" if log_lines else ""), encoding="utf-8")
    output_paths[2].write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
