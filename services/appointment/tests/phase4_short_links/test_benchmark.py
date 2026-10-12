"""Disposable PostgreSQL adapter benchmark invoked by experiments/phase4/short_links/run.py."""

from __future__ import annotations

import asyncio
import csv
import importlib.metadata
import json
import math
import os
import platform
import random
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import insert, select, text, update

from appointment_service import models as m, operations as op, phase3_core as core
from appointment_service.features.short_links.registration import alias_digest, encode_alias
from ..test_concurrency import patient, run
from .test_short_links import (
    ShortLinksTestPorts,
    _create,
    _endpoint,
    _install_test_table,
    _json,
    _make_app,
    _request,
    _resolve,
)


LEVELS = {"low": (1_000, 1), "medium": (10_000, 8), "high": (50_000, 32)}
FIRST_ID = 10_000_000
FIRST_PATIENT_ID = 20_000_000


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def _latency_summary(samples: list[dict], *, successful_only: bool = True) -> dict:
    rows = [
        row for row in samples
        if (row["status_code"] in (200, 201, 303)) == successful_only
    ]
    values = [row["latency_ms"] for row in rows]
    return {
        "sample_count": len(values),
        "p50_ms": _percentile(values, 0.50),
        "p95_ms": _percentile(values, 0.95),
        "p99_ms": _percentile(values, 0.99),
        "min_ms": min(values) if values else None,
        "max_ms": max(values) if values else None,
    }


async def _seed_dataset(db, size: int, seed: int) -> list[dict]:
    randomizer = random.Random(seed)
    now = op.now()
    first_start = now + timedelta(days=30)
    slot_values = []
    appointment_values = []
    journey_values = []
    workflow_values = []
    alias_values = []

    for offset in range(size * 3):
        entity_id = FIRST_ID + offset
        patient_id = FIRST_PATIENT_ID + offset
        starts_at = first_start + timedelta(minutes=30 * offset)
        ends_at = starts_at + timedelta(minutes=20)
        slot_values.append({
            "id": entity_id,
            "doctor_id": 1,
            "schedule_revision": 1,
            "starts_at": starts_at,
            "ends_at": ends_at,
            "state": "bookable",
        })
        appointment = {
            "id": entity_id,
            "patient_id": patient_id,
            "slot_id": entity_id,
            "doctor_id": 1,
            "doctor_user_id": 101,
            "starts_at": starts_at,
            "ends_at": ends_at,
            "schedule_revision": 1,
            "state": "confirmed",
        }
        appointment_values.append(appointment)
        journey_values.append({
            "id": entity_id,
            "appointment_id": entity_id,
            "patient_id": patient_id,
            "state": "active",
        })
        workflow_values.append({
            "appointment_id": entity_id,
            "journey_id": entity_id,
            "patient_id": patient_id,
            "doctor_id": 1,
            "slot_id": entity_id,
            "schedule_revision": 1,
            "schedule_fingerprint": core.schedule_fingerprint(appointment),
            "state": "booked",
            "window_starts_at": starts_at - timedelta(minutes=30),
            "window_ends_at": starts_at + timedelta(minutes=15),
            "version": 1,
        })
        alias = encode_alias(randomizer.getrandbits(128).to_bytes(16, "big"))
        alias_values.append({
            "id": 100_000_000 + offset,
            "appointment_id": entity_id,
            "purpose": "appointment",
            "token_hash": alias_digest(alias),
            "expires_at": now + timedelta(hours=24),
            "revoked_at": None,
            "workflow_version": 1,
            "schedule_fingerprint": workflow_values[-1]["schedule_fingerprint"],
            "version": 1,
        })
        alias_values[-1]["_alias_for_test_only"] = alias

    async with db.session_factory() as session, session.begin():
        await session.execute(update(m.doctor_schedule_snapshots).where(
            m.doctor_schedule_snapshots.c.doctor_id == 1
        ).values(policy_snapshot={"timezone": "UTC"}))
        for offset in range(0, len(slot_values), 2_000):
            await session.execute(insert(m.slots), slot_values[offset:offset + 2_000])
        for offset in range(0, len(appointment_values), 2_000):
            await session.execute(insert(m.appointments), appointment_values[offset:offset + 2_000])
        for offset in range(0, len(journey_values), 2_000):
            await session.execute(insert(m.journeys), journey_values[offset:offset + 2_000])
        for offset in range(0, len(workflow_values), 2_000):
            await session.execute(insert(m.appointment_workflows), workflow_values[offset:offset + 2_000])
        alias_table = __import__(
            "appointment_service.features.short_links.schema_spec",
            fromlist=["table_for"],
        ).table_for()
        for offset in range(0, len(alias_values), 2_000):
            batch = [
                {key: value for key, value in row.items() if key != "_alias_for_test_only"}
                for row in alias_values[offset:offset + 2_000]
            ]
            await session.execute(insert(alias_table), batch)
    return alias_values


async def _drive(
    *, app, ports, rows, base_index: int, size: int, clients: int,
    mode: str, seed: int, trial: int, duration_seconds: float, record: bool,
) -> tuple[list[dict], float]:
    create_pool = max(1, size // 10)
    read_start = base_index + create_pool
    read_count = max(1, size - create_pool)
    start = time.perf_counter()
    deadline = start + duration_seconds
    samples: list[dict] = []
    idempotency_phase = "measurement" if record else "warmup"

    async def operation(client_id: int) -> None:
        rng = random.Random(seed + trial * 10_007 + client_id * 101)
        sequence = 0
        while time.perf_counter() < deadline:
            sequence += 1
            if mode == "baseline":
                index = read_start + rng.randrange(read_count)
                aid = FIRST_ID + index
                pid = FIRST_PATIENT_ID + index
                principal = patient(str(pid))
                request = _request(
                    app,
                    f"/api/v1/appointments/{aid}/workflow",
                    method="GET",
                    version=None,
                    principal=principal,
                )
                endpoint = _endpoint(app, "/api/v1/appointments/{appointment_id}/workflow", "GET")
                started_ns = time.perf_counter_ns()
                try:
                    response = await endpoint(
                        request, appointment_id=str(aid), p=principal
                    )
                    status = response.status_code
                except Exception:
                    status = 0
                operation_name = "baseline_workflow_lookup"
            elif rng.random() < 0.9:
                index = read_start + rng.randrange(read_count)
                row = rows[index]
                principal = patient(str(FIRST_PATIENT_ID + index))
                started_ns = time.perf_counter_ns()
                try:
                    response = await _resolve(app, row["_alias_for_test_only"], principal=principal)
                    status = response.status_code
                except Exception:
                    status = 0
                operation_name = "proposed_authenticated_resolution"
            else:
                index = base_index + rng.randrange(create_pool)
                principal = patient(str(FIRST_PATIENT_ID + index))
                started_ns = time.perf_counter_ns()
                try:
                    response = await _create(
                        app,
                        FIRST_ID + index,
                        principal=principal,
                        key=(
                            f"bench-{seed}-{trial}-{idempotency_phase}-"
                            f"{client_id}-{sequence:016d}"
                        ),
                    )
                    status = response.status_code
                except Exception:
                    status = 0
                operation_name = "proposed_creation"
            latency_ms = (time.perf_counter_ns() - started_ns) / 1_000_000
            if record:
                samples.append({
                    "trial": trial,
                    "mode": mode,
                    "operation": operation_name,
                    "status_code": status,
                    "latency_ms": latency_ms,
                })

    await asyncio.gather(*(operation(client) for client in range(clients)))
    elapsed = time.perf_counter() - start
    return samples, elapsed


async def _navigation_samples(app, alias: str, count: int = 1_000) -> list[dict]:
    samples = []
    endpoint = _endpoint(app, "/s/{alias}", "GET")
    for index in range(count):
        request = _request(
            app,
            f"/s/{alias}",
            method="GET",
            version=None,
            accept="text/html",
        )
        started_ns = time.perf_counter_ns()
        response = await endpoint(request, alias=alias)
        samples.append({
            "trial": 0,
            "mode": "proposed_navigation",
            "operation": "navigation_303",
            "status_code": response.status_code,
            "latency_ms": (time.perf_counter_ns() - started_ns) / 1_000_000,
        })
    return samples


def _summarize(samples: list[dict], elapsed: float) -> dict:
    by_operation = {}
    for name in sorted({row["operation"] for row in samples}):
        subset = [row for row in samples if row["operation"] == name]
        successes = [row for row in subset if row["status_code"] in (200, 201, 303)]
        errors = [row for row in subset if row not in successes]
        by_operation[name] = {
            "attempted": len(subset),
            "completed": len(successes),
            "errors": len(errors),
            "throughput_per_second": len(subset) / elapsed if elapsed else None,
            "success_latency": _latency_summary(successes),
            "error_latency": _latency_summary(errors, successful_only=False),
        }
    return {"elapsed_seconds": elapsed, "operations": by_operation}


def _system_metadata() -> dict:
    memory_bytes = None
    try:
        output = subprocess.run(
            ["sysctl", "-n", "hw.memsize"], check=True, capture_output=True, text=True
        ).stdout.strip()
        memory_bytes = int(output)
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError):
        try:
            memory_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        except (AttributeError, OSError, ValueError):
            pass
    return {
        "os": platform.platform(),
        "cpu_architecture": platform.machine(),
        "cpu_count": os.cpu_count(),
        "memory_bytes": memory_bytes,
        "python": platform.python_version(),
        "fastapi": importlib.metadata.version("fastapi"),
        "sqlalchemy": importlib.metadata.version("sqlalchemy"),
        "psycopg": importlib.metadata.version("psycopg"),
        "timer": "time.perf_counter_ns",
        "timer_resolution_seconds": time.get_clock_info("perf_counter").resolution,
    }


def test_run_local_adapter_benchmark(database, current_authority):
    if "PULSEGRID_SHORT_LINKS_BENCH_OUTPUT" not in os.environ:
        pytest.skip("Run through experiments/phase4/short_links/run.py")
    level = os.environ.get("PULSEGRID_SHORT_LINKS_BENCH_LEVEL", "low")
    seed = int(os.environ.get("PULSEGRID_SHORT_LINKS_BENCH_SEED", "404"))
    output_path = Path(os.environ["PULSEGRID_SHORT_LINKS_BENCH_OUTPUT"])
    warmup_seconds = float(os.environ.get("PULSEGRID_SHORT_LINKS_BENCH_WARMUP", "5"))
    duration_seconds = float(os.environ.get("PULSEGRID_SHORT_LINKS_BENCH_DURATION", "30"))
    if level not in LEVELS or duration_seconds <= 0 or warmup_seconds < 0:
        raise ValueError("Invalid short-link benchmark settings")
    size, clients = LEVELS[level]
    started_at = datetime.now(timezone.utc)

    async def work(db):
        await _install_test_table(db)
        rows = await _seed_dataset(db, size, seed)
        ports = ShortLinksTestPorts(db)
        app = _make_app(db, ports, with_checkin=True)
        async with db.session_factory() as session:
            pg_version = (await session.execute(text("SELECT version()"))).scalar_one()

        sample_rows = []
        trials = []
        navigation_started = time.perf_counter()
        nav_samples = await _navigation_samples(app, rows[0]["_alias_for_test_only"])
        navigation_elapsed = time.perf_counter() - navigation_started
        sample_rows.extend(nav_samples)
        for trial in range(3):
            base_index = trial * size
            before_collisions = sum(
                value for name, _labels, value in ports.observer.counters
                if name == "pulsegrid_short_link_collisions_total"
            )
            order = ("baseline", "proposed") if trial % 2 == 0 else ("proposed", "baseline")
            trial_samples = {}
            for mode in order:
                await _drive(
                    app=app, ports=ports, rows=rows, base_index=base_index, size=size,
                    clients=clients, mode=mode, seed=seed, trial=trial,
                    duration_seconds=warmup_seconds, record=False,
                )
                measured, elapsed = await _drive(
                    app=app, ports=ports, rows=rows, base_index=base_index, size=size,
                    clients=clients, mode=mode, seed=seed, trial=trial,
                    duration_seconds=duration_seconds, record=True,
                )
                sample_rows.extend(measured)
                trial_samples[mode] = _summarize(measured, elapsed)
            after_collisions = sum(
                value for name, _labels, value in ports.observer.counters
                if name == "pulsegrid_short_link_collisions_total"
            )
            trials.append({
                "trial": trial + 1,
                "execution_order": list(order),
                "baseline": trial_samples["baseline"],
                "proposed": trial_samples["proposed"],
                "collisions": after_collisions - before_collisions,
            })
        output_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path = output_path.with_suffix(".samples.csv")
        with raw_path.open("w", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["trial", "mode", "operation", "status_code", "latency_ms"],
            )
            writer.writeheader()
            writer.writerows(sample_rows)
        report = {
            "benchmark": "phase4_short_links_local_adapter",
            "seed": seed,
            "level": level,
            "dataset_alias_count_per_trial": size,
            "total_fixture_alias_count": size * 3,
            "total_fixture_future_appointments": size * 3,
            "clients": clients,
            "read_create_mix": {"reads_percent": 90, "creates_percent": 10},
            "warmup_seconds_per_mode_per_trial": warmup_seconds,
            "measurement_seconds_per_mode_per_trial": duration_seconds,
            "repeats": 3,
            "started_at_utc": started_at.isoformat().replace("+00:00", "Z"),
            "finished_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "environment": {**_system_metadata(), "postgresql": pg_version.splitlines()[0]},
            "baseline": "existing authenticated Phase 3 workflow GET route",
            "proposed": "short-link authenticated JSON resolution and creation routes",
            "navigation_303": _summarize(nav_samples, navigation_elapsed),
            "trials": trials,
            "collisions_observed": sum(trial["collisions"] for trial in trials),
            "raw_samples_file": str(raw_path),
            "limitations": [
                "Coordinator route mounting and migration 0010 are not in this Agent 5 checkout.",
                "The local port adapter uses synthetic in-process principals and direct route calls, not JWT, ASGI network, Traefik or production middleware.",
                "Creation effects use a no-op test stage_effect port; integrated audit/outbox transaction cost is not measured.",
                "The baseline and proposed paths use the same disposable PostgreSQL and synthetic owner rows; no unauthenticated or raw QR path is measured.",
            ],
        }
        output_path.write_text(json.dumps(report, indent=2) + "\n")

    run(database, work)
