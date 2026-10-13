#!/usr/bin/env python3
"""Bounded authenticated HTTP load helpers for the Phase 8 evaluation."""

from __future__ import annotations

import argparse
import asyncio
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random
import stat
import time
from typing import Any, Awaitable, Callable, Iterable, Mapping, Sequence

import httpx


ORIGIN = "http://127.0.0.1:5173"
REQUEST_TIMEOUT_SECONDS = 5.0
SAMPLE_FIELDS = (
    "run_id",
    "scenario",
    "trial",
    "level",
    "replicas",
    "worker",
    "sequence",
    "endpoint",
    "started_utc",
    "started_monotonic_s",
    "latency_ms",
    "status_code",
    "classification",
    "response_bytes",
)


@dataclass(frozen=True)
class RequestSpec:
    name: str
    path: str
    params: Mapping[str, str] | None = None


def classify_status(status_code: int) -> str:
    if 200 <= status_code < 300:
        return "success"
    if status_code == 429:
        return "admission_rejected"
    if status_code == 409:
        return "business_conflict"
    if status_code == 404:
        return "missing_resource"
    if 400 <= status_code < 500:
        return "client_error"
    if 500 <= status_code < 600:
        return "server_error"
    return "other_status"


def classify_exception(error: BaseException) -> str:
    if isinstance(error, httpx.TimeoutException):
        return "timeout"
    if isinstance(error, (httpx.ConnectError, httpx.NetworkError, httpx.RemoteProtocolError)):
        return "connection_failure"
    if isinstance(error, httpx.RequestError):
        return "request_failure"
    return "client_exception"


def percentile(values: Iterable[float], fraction: float) -> float | None:
    """Nearest-rank percentile, using the Phase 4 benchmark convention."""
    if not 0 < fraction <= 1:
        raise ValueError("fraction must be in (0, 1]")
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def statistics(values: Iterable[float]) -> dict[str, float | int | None]:
    observed = [float(value) for value in values]
    if not observed:
        return {
            "samples": 0,
            "mean": None,
            "median": None,
            "p95": None,
            "p99": None,
            "min": None,
            "max": None,
        }
    return {
        "samples": len(observed),
        "mean": sum(observed) / len(observed),
        "median": percentile(observed, 0.50),
        "p95": percentile(observed, 0.95),
        "p99": percentile(observed, 0.99),
        "min": min(observed),
        "max": max(observed),
    }


def summarize_samples(
    samples: Sequence[Mapping[str, Any]],
    measurement_seconds: float,
) -> dict[str, Any]:
    if measurement_seconds <= 0:
        raise ValueError("measurement_seconds must be positive")
    counts: dict[str, int] = {}
    http_latencies: list[float] = []
    success_latencies: list[float] = []
    latency_by_class: dict[str, list[float]] = {}
    for sample in samples:
        classification = str(sample["classification"])
        counts[classification] = counts.get(classification, 0) + 1
        latency_by_class.setdefault(classification, []).append(float(sample["latency_ms"]))
        if sample.get("status_code") is not None:
            http_latencies.append(float(sample["latency_ms"]))
            if classification == "success":
                success_latencies.append(float(sample["latency_ms"]))

    attempted = len(samples)
    rejected = counts.get("admission_rejected", 0)
    responses = len(http_latencies)
    admitted = responses - rejected
    successful = counts.get("success", 0)
    admission_denominator = admitted + rejected
    return {
        "attempted": attempted,
        "completed_http_responses": responses,
        "successful": successful,
        "admitted_http_responses": admitted,
        "http_4xx": sum(
            1
            for sample in samples
            if sample.get("status_code") is not None
            and 400 <= int(sample["status_code"]) < 500
        ),
        "http_409": counts.get("business_conflict", 0),
        "http_404": counts.get("missing_resource", 0),
        "http_429": rejected,
        "http_5xx": sum(
            1
            for sample in samples
            if sample.get("status_code") is not None
            and 500 <= int(sample["status_code"]) < 600
        ),
        "timeouts": counts.get("timeout", 0),
        "connection_failures": counts.get("connection_failure", 0),
        "request_failures": counts.get("request_failure", 0),
        "other_exceptions": counts.get("client_exception", 0),
        "attempted_rps": attempted / measurement_seconds,
        "admitted_rps": admitted / measurement_seconds,
        "successful_rps": successful / measurement_seconds,
        "rejection_percent": (
            100.0 * rejected / admission_denominator
            if admission_denominator
            else None
        ),
        "all_attempt_latency_ms": statistics(
            float(sample["latency_ms"]) for sample in samples
        ),
        "all_http_latency_ms": statistics(http_latencies),
        "success_latency_ms": statistics(success_latencies),
        "latency_by_class_ms": {
            name: statistics(values) for name, values in sorted(latency_by_class.items())
        },
        "classification_counts": dict(sorted(counts.items())),
        "measurement_seconds": measurement_seconds,
    }


def workload_specs(doctor_id: str) -> dict[str, RequestSpec]:
    """Only GET routes with no business mutation are available to the runner."""
    specs = {
        "directory": RequestSpec(
            "directory", "/api/v1/doctors", {"q": "Synthetic", "limit": "20"}
        ),
        "autocomplete": RequestSpec(
            "autocomplete",
            "/api/v1/doctors/autocomplete",
            {"prefix": "synthetic"},
        ),
        "profile": RequestSpec("profile", f"/api/v1/doctors/{doctor_id}"),
    }
    if any(not spec.path.startswith("/api/v1/doctors") for spec in specs.values()):
        raise ValueError("workload path escaped the Doctor read-only allowlist")
    return specs


def mixed_endpoint(index: int, worker: int, seed: int) -> str:
    """A deterministic 5:3:2 mix of directory, autocomplete and profile reads."""
    slot = (index + worker + seed) % 10
    if slot < 5:
        return "directory"
    if slot < 8:
        return "autocomplete"
    return "profile"


def load_private_fixture(path: Path) -> tuple[dict[str, Any], str]:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise ValueError("private fixture permissions must be 0600")
    state = json.loads(path.read_text())
    patient = state.get("actors", {}).get("patient")
    doctor = state.get("resources", {}).get("doctor")
    if not isinstance(patient, dict) or not patient.get("email") or not patient.get("password"):
        raise ValueError("fixture must contain the existing synthetic patient actor")
    if not isinstance(doctor, dict) or not str(doctor.get("id", "")).isdecimal():
        raise ValueError("fixture must contain an existing synthetic Doctor ID")
    return state, str(doctor["id"])


class AuthenticatedActor:
    """Login/logout wrapper; bearer tokens remain in memory only."""

    def __init__(self, base_url: str, actor_data: Mapping[str, str]):
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Origin": ORIGIN},
            timeout=REQUEST_TIMEOUT_SECONDS,
            trust_env=False,
        )
        self.actor_data = actor_data
        self.access_token: str | None = None
        self.csrf_token: str | None = None

    def login(self) -> str:
        csrf_response = self.client.get("/api/v1/auth/csrf")
        csrf_response.raise_for_status()
        self.csrf_token = str(csrf_response.json()["csrf_token"])
        response = self.client.post(
            "/api/v1/auth/login",
            json={
                "email": self.actor_data["email"],
                "password": self.actor_data["password"],
            },
            headers={"X-CSRF-Token": self.csrf_token},
        )
        response.raise_for_status()
        token = response.json().get("access_token")
        if not isinstance(token, str) or not token:
            raise RuntimeError("authenticated login did not return an access token")
        self.access_token = token
        self.client.headers["Authorization"] = f"Bearer {token}"
        return token

    def logout(self) -> None:
        if self.csrf_token is None:
            return
        try:
            response = self.client.post(
                "/api/v1/auth/logout",
                headers={"X-CSRF-Token": self.csrf_token},
            )
            if response.status_code not in (200, 204):
                raise RuntimeError(f"synthetic actor logout returned HTTP {response.status_code}")
        finally:
            self.client.close()


async def run_fixed_window(
    client: httpx.AsyncClient,
    specs: Mapping[str, RequestSpec],
    *,
    concurrency: int,
    window_seconds: float,
    scenario: str,
    run_id: str,
    trial: int,
    level: str,
    replicas: int,
    seed: int,
    capture_samples: bool = True,
) -> list[dict[str, Any]]:
    if concurrency < 1 or window_seconds <= 0:
        raise ValueError("concurrency and window_seconds must be positive")
    if scenario not in ("mixed_read", "profile_read", "autocomplete_burst"):
        raise ValueError("scenario is not in the fixed Phase 8 read-only workload set")
    if scenario == "autocomplete_burst":
        concurrency = min(concurrency, 64)

    loop = asyncio.get_running_loop()
    stop_at = loop.time() + window_seconds
    samples: list[dict[str, Any]] = []

    async def worker(worker_id: int) -> None:
        sequence = 0
        while loop.time() < stop_at:
            if scenario == "profile_read":
                endpoint = "profile"
            elif scenario == "autocomplete_burst":
                endpoint = "autocomplete"
            else:
                endpoint = mixed_endpoint(sequence, worker_id, seed)
            spec = specs[endpoint]
            started = time.perf_counter_ns()
            started_monotonic_s = loop.time()
            started_utc = datetime.now(timezone.utc).isoformat()
            status_code: int | None = None
            response_bytes: int | None = None
            classification: str
            try:
                response = await client.get(spec.path, params=spec.params)
                status_code = response.status_code
                response_bytes = len(response.content)
                classification = classify_status(status_code)
            except asyncio.CancelledError:
                raise
            except BaseException as error:
                classification = classify_exception(error)
            elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
            if capture_samples:
                samples.append(
                    {
                        "run_id": run_id,
                        "scenario": scenario,
                        "trial": trial,
                        "level": level,
                        "replicas": replicas,
                        "worker": worker_id,
                        "sequence": sequence,
                        "endpoint": endpoint,
                        "started_utc": started_utc,
                        "started_monotonic_s": started_monotonic_s,
                        "latency_ms": elapsed_ms,
                        "status_code": status_code,
                        "classification": classification,
                        "response_bytes": response_bytes,
                    }
                )
            sequence += 1

    tasks = [asyncio.create_task(worker(index)) for index in range(concurrency)]
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    return samples


async def run_burst(
    client: httpx.AsyncClient,
    spec: RequestSpec,
    *,
    count: int,
    run_id: str,
    scenario: str,
    level: str,
    replicas: int,
) -> list[dict[str, Any]]:
    if count < 1 or count > 64:
        raise ValueError("burst count must be in 1..64")

    async def one(index: int) -> dict[str, Any]:
        started = time.perf_counter_ns()
        started_monotonic_s = asyncio.get_running_loop().time()
        started_utc = datetime.now(timezone.utc).isoformat()
        status_code: int | None = None
        response_bytes: int | None = None
        classification = "client_exception"
        try:
            response = await client.get(spec.path, params=spec.params)
            status_code = response.status_code
            response_bytes = len(response.content)
            classification = classify_status(status_code)
        except asyncio.CancelledError:
            raise
        except BaseException as error:
            classification = classify_exception(error)
        return {
            "run_id": run_id,
            "scenario": scenario,
            "trial": 1,
            "level": level,
            "replicas": replicas,
            "worker": index,
            "sequence": 0,
            "endpoint": spec.name,
            "started_utc": started_utc,
            "started_monotonic_s": started_monotonic_s,
            "latency_ms": (time.perf_counter_ns() - started) / 1_000_000,
            "status_code": status_code,
            "classification": classification,
            "response_bytes": response_bytes,
        }

    tasks = [asyncio.create_task(one(index)) for index in range(count)]
    try:
        return await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def warm_up(
    client: httpx.AsyncClient,
    specs: Mapping[str, RequestSpec],
    *,
    concurrency: int,
    seconds: float,
    scenario: str,
    seed: int,
) -> dict[str, int]:
    samples = await run_fixed_window(
        client,
        specs,
        concurrency=concurrency,
        window_seconds=seconds,
        scenario=scenario,
        run_id="warmup",
        trial=0,
        level="warmup",
        replicas=0,
        seed=seed,
        capture_samples=True,
    )
    return {
        "attempted": len(samples),
        "success": sum(sample["classification"] == "success" for sample in samples),
        "http_429": sum(sample["classification"] == "admission_rejected" for sample in samples),
    }


def write_samples(path: Path, samples: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=SAMPLE_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(samples)


def run_self_test() -> None:
    """Small local checks for accounting, latency, concurrency and cancellation."""
    import unittest

    class HarnessTests(unittest.IsolatedAsyncioTestCase):
        async def test_fixed_window_bounds_concurrency_and_records_latencies(self):
            active = 0
            maximum = 0

            async def handler(request: httpx.Request) -> httpx.Response:
                nonlocal active, maximum
                active += 1
                maximum = max(maximum, active)
                await asyncio.sleep(0.004)
                active -= 1
                return httpx.Response(200, json={"synthetic": True})

            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                samples = await run_fixed_window(
                    client,
                    {"profile": RequestSpec("profile", "/api/v1/doctors/1")},
                    concurrency=3,
                    window_seconds=0.05,
                    scenario="profile_read",
                    run_id="self-test",
                    trial=1,
                    level="test",
                    replicas=1,
                    seed=1,
                )
            self.assertGreater(len(samples), 3)
            self.assertLessEqual(maximum, 3)
            self.assertTrue(all(sample["latency_ms"] >= 0 for sample in samples))

        async def test_cancelled_window_cleans_up_workers(self):
            active = 0

            async def handler(request: httpx.Request) -> httpx.Response:
                nonlocal active
                active += 1
                try:
                    await asyncio.sleep(0.05)
                    return httpx.Response(200)
                finally:
                    active -= 1

            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                task = asyncio.create_task(
                    run_fixed_window(
                        client,
                        {"profile": RequestSpec("profile", "/api/v1/doctors/1")},
                        concurrency=2,
                        window_seconds=1.0,
                        scenario="profile_read",
                        run_id="self-test",
                        trial=1,
                        level="test",
                        replicas=1,
                        seed=1,
                    )
                )
                await asyncio.sleep(0.01)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                await asyncio.sleep(0)
            self.assertEqual(active, 0)

        def test_classification_and_percentiles(self):
            self.assertEqual(classify_status(200), "success")
            self.assertEqual(classify_status(409), "business_conflict")
            self.assertEqual(classify_status(404), "missing_resource")
            self.assertEqual(classify_status(429), "admission_rejected")
            self.assertEqual(classify_status(503), "server_error")
            self.assertEqual(classify_exception(httpx.ReadTimeout("timeout")), "timeout")
            self.assertEqual(percentile([4, 1, 3, 2], 0.50), 2.0)
            self.assertEqual(percentile([4, 1, 3, 2], 0.95), 4.0)

        def test_accounting_keeps_expected_categories_separate(self):
            samples = [
                {"classification": "success", "status_code": 200, "latency_ms": 10},
                {"classification": "admission_rejected", "status_code": 429, "latency_ms": 2},
                {"classification": "business_conflict", "status_code": 409, "latency_ms": 3},
                {"classification": "missing_resource", "status_code": 404, "latency_ms": 4},
                {"classification": "server_error", "status_code": 503, "latency_ms": 8},
                {"classification": "timeout", "status_code": None, "latency_ms": 20},
            ]
            result = summarize_samples(samples, 2.0)
            self.assertEqual(result["attempted"], 6)
            self.assertEqual(result["admitted_http_responses"], 4)
            self.assertEqual(result["successful"], 1)
            self.assertEqual(result["http_4xx"], 3)
            self.assertEqual(result["http_409"], 1)
            self.assertEqual(result["http_404"], 1)
            self.assertEqual(result["http_429"], 1)
            self.assertEqual(result["http_5xx"], 1)
            self.assertEqual(result["timeouts"], 1)
            self.assertEqual(result["attempted_rps"], 3.0)

        def test_workload_mix_is_fixed_and_read_only(self):
            names = [mixed_endpoint(index, 0, 0) for index in range(10)]
            self.assertEqual(names.count("directory"), 5)
            self.assertEqual(names.count("autocomplete"), 3)
            self.assertEqual(names.count("profile"), 2)
            specs = workload_specs("123")
            self.assertEqual(set(specs), {"directory", "autocomplete", "profile"})
            self.assertTrue(all(spec.path.startswith("/api/v1/doctors") for spec in specs.values()))

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(HarnessTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="run offline harness checks")
    args = parser.parse_args()
    if args.self_test:
        run_self_test()
        return
    parser.error("use experiments/phase8/run_matrix.py for the fixed live experiment plan")


if __name__ == "__main__":
    main()
