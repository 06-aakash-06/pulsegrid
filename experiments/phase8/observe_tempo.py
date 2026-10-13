#!/usr/bin/env python3
"""Collect a bounded, read-only Tempo stability observation."""

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


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "experiments/phase8/results/phase8-20261013-run1/tempo"
TEMPO = "pulsegrid-tempo-1"
PROBE = "pulsegrid-prometheus-1"
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
            "wget",
            "-q",
            "-T",
            "3",
            "-O",
            "-",
            "http://tempo:3200/ready",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=5.0,
    )
    return result.returncode == 0 and result.stdout.strip() == "ready"


def trace_probe() -> dict[str, Any]:
    raw = run(
        "docker",
        "exec",
        PROBE,
        "wget",
        "-q",
        "-T",
        "5",
        "-O",
        "-",
        "http://tempo:3200/api/search?limit=1",
        timeout=8.0,
    )
    data = json.loads(raw)
    return {
        "returned_trace_count": len(data.get("traces", [])),
        "inspected_traces": (data.get("metrics") or {}).get("inspectedTraces"),
        "completed_jobs": (data.get("metrics") or {}).get("completedJobs"),
        "total_jobs": (data.get("metrics") or {}).get("totalJobs"),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-seconds", type=int, default=120)
    parser.add_argument("--interval-seconds", type=float, default=2.0)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if not 30 <= args.duration_seconds <= 300:
        parser.error("duration must be between 30 and 300 seconds")
    if not 1 <= args.interval_seconds <= 10:
        parser.error("interval must be between 1 and 10 seconds")
    return args


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    initial = inspect_tempo()
    initial_traces = trace_probe()
    rows: list[dict[str, Any]] = []
    started_monotonic = time.monotonic()
    deadline = started_monotonic + args.duration_seconds
    next_sample = started_monotonic

    while True:
        elapsed = time.monotonic() - started_monotonic
        now = datetime.now(timezone.utc)
        state = inspect_tempo()
        memory_bytes, stats_limit, cpu_percent = read_stats()
        ready = readiness_probe()
        limit = stats_limit or state["memory_limit_bytes"]
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
                "memory_percent": round(100 * memory_bytes / limit, 2) if limit else None,
                "cpu_percent": cpu_percent,
            }
        )
        if time.monotonic() >= deadline:
            break
        next_sample += args.interval_seconds
        time.sleep(max(0.0, min(next_sample, deadline) - time.monotonic()))

    ended = datetime.now(timezone.utc)
    final = inspect_tempo()
    final_traces = trace_probe()
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
        raise RuntimeError("could not query Docker lifecycle events for the Tempo window")
    event_lines = [line for line in event_result.stdout.splitlines() if line.strip()]
    log_counts = {
        "warning_lines": sum("level=warn" in line for line in log_lines),
        "error_lines": sum("level=error" in line for line in log_lines),
        "incomplete_wal_meta_warnings": sum(
            "failed to replay block" in line and "meta.json" in line for line in log_lines
        ),
        "scheduler_no_jobs_warning_lines": sum(
            "NotFound desc = no jobs found" in line and "level=warn" in line
            for line in log_lines
        ),
        "scheduler_no_jobs_error_lines": sum(
            "NotFound desc = no jobs found" in line and "level=error" in line
            for line in log_lines
        ),
    }
    intervals = [
        rows[index]["elapsed_seconds"] - rows[index - 1]["elapsed_seconds"]
        for index in range(1, len(rows))
    ]
    with (args.output_dir / "stability_samples.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SAMPLE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "started_utc": started.isoformat(),
        "ended_utc": ended.isoformat(),
        "requested_duration_seconds": args.duration_seconds,
        "sample_interval_seconds": args.interval_seconds,
        "samples": len(rows),
        "observed_sample_interval_median_seconds": statistics.median(intervals) if intervals else None,
        "initial_state": initial,
        "final_state": final,
        "restart_delta": final["restart_count"] - initial["restart_count"],
        "oom_killed_at_end": final["oom_killed"],
        "readiness_successes": sum(bool(row["ready"]) for row in rows),
        "readiness_failures": sum(not row["ready"] for row in rows),
        "memory_bytes_min": min(row["memory_bytes"] for row in rows),
        "memory_bytes_max": max(row["memory_bytes"] for row in rows),
        "memory_percent_max": max(row["memory_percent"] for row in rows),
        "cpu_percent_max": max(
            (row["cpu_percent"] for row in rows if row["cpu_percent"] is not None),
            default=None,
        ),
        "logs": log_counts,
        "docker_lifecycle_events": [json.loads(line) for line in event_lines],
        "stored_trace_query_at_start": initial_traces,
        "stored_trace_query_at_end": final_traces,
        "log_inspection_scope": "Tempo container logs emitted during the observation window",
        "load_generated": False,
    }
    (args.output_dir / "stability_relevant_logs.txt").write_text(
        "\n".join(log_lines) + ("\n" if log_lines else "")
    )
    (args.output_dir / "stability_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
