#!/usr/bin/env python3
"""Reproducible synthetic prefix-search comparison for Phase 4.7."""

from __future__ import annotations

import argparse
import bisect
import csv
import gc
import hashlib
import heapq
import json
import math
import os
import platform
import random
from functools import lru_cache
import resource
import statistics
import sys
import subprocess
import time
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "components/autocomplete/src"))

from pulsegrid_autocomplete import (  # noqa: E402
    DEFAULT_INDEX_LIMITS,
    IndexLimits,
    IndexTooLarge,
    Suggestion,
    build_snapshot,
    normalize_label,
    normalize_prefix,
)

LEVEL_ENTRIES = {"low": 1_000, "medium": 10_000, "high": 100_000}
CLIENT_COUNTS = (1, 8, 32)
RESULT_LIMITS = (10, 20)
STRENGTHS = ("250 mg", "500 mg", "750 mg", "1 g")
FIRST_NAMES = (
    "Aanya", "Aarav", "Aditya", "Anika", "Arjun", "Diya", "Ishaan", "Kabir",
    "Kavya", "Meera", "Mira", "Neha", "Nikhil", "Riya", "Saanvi", "Vihaan",
)
LAST_NAMES = (
    "Banerjee", "Bose", "Chatterjee", "Das", "Gupta", "Iyer", "Kapoor", "Khan",
    "Menon", "Mukherjee", "Nair", "Patel", "Rao", "Reddy", "Shah", "Sharma",
    "Singh", "Srinivasan", "Verma", "Yadav",
)
SPECIALTIES = (
    "Cardiology", "Dermatology", "Endocrinology", "Family Medicine", "Gastroenterology",
    "General Surgery", "Geriatrics", "Hematology", "Internal Medicine", "Nephrology",
    "Neurology", "Obstetrics and Gynecology", "Oncology", "Ophthalmology", "Orthopedics",
    "Otolaryngology", "Pediatrics", "Physical Medicine", "Psychiatry", "Pulmonology",
    "Radiology", "Rheumatology", "Urology", "Vascular Surgery", "Anesthesiology",
    "Emergency Medicine", "Infectious Disease", "Medical Genetics", "Neurosurgery",
    "Pathology", "Plastic Surgery", "Preventive Medicine",
)
MEDICINES = (
    "Acetaminophen", "Amoxicillin", "Amlodipine", "Atorvastatin", "Azithromycin",
    "Cetirizine", "Doxycycline", "Ibuprofen", "Losartan", "Metformin", "Omeprazole",
    "Paracetamol", "Pantoprazole", "Prednisone", "Sertraline", "Simvastatin",
    "Tramadol", "Vitamin D3", "Warfarin", "Levothyroxine", "Lisinopril", "Montelukast",
)


@dataclass(frozen=True)
class Workload:
    name: str
    prefix: str
    kinds: tuple[str, ...]


def generate_catalogs(count: int, seed: int) -> dict[str, tuple[Suggestion, ...]]:
    rng = random.Random(seed)
    doctor_specialty_count = min(len(SPECIALTIES), max(10, count // 32))
    doctor_count = count - doctor_specialty_count
    doctors: list[Suggestion] = []
    for index in range(1, doctor_count + 1):
        first = FIRST_NAMES[(index - 1) % len(FIRST_NAMES)]
        last = LAST_NAMES[((index - 1) // len(FIRST_NAMES)) % len(LAST_NAMES)]
        suffix = rng.randrange(0, 1_000)
        doctors.append(
            Suggestion(
                str(index),
                "doctor",
                f"Dr. {first} {last} {suffix:03d}-{index:06d}",
            )
        )
    specialties = tuple(
        Suggestion(
            str(index),
            "specialty",
            SPECIALTIES[index - 1] + (f" {index:02d}" if count > len(SPECIALTIES) else ""),
        )
        for index in range(1, doctor_specialty_count + 1)
    )
    medicines: list[Suggestion] = []
    for index in range(1, count + 1):
        name = MEDICINES[(index - 1) % len(MEDICINES)]
        strength = STRENGTHS[((index - 1) // len(MEDICINES)) % len(STRENGTHS)]
        form = "tablet" if index % 4 else "capsule"
        medicines.append(
            Suggestion(
                str(index),
                "medicine",
                f"{name} {strength} {form} {index:06d}",
            )
        )
    return {
        "doctor": tuple(doctors) + specialties,
        "pharmacy": tuple(medicines),
    }


def workloads(owner: str) -> tuple[Workload, ...]:
    kinds = ("doctor", "specialty") if owner == "doctor" else ("medicine",)
    if owner == "doctor":
        return (
            Workload("hot_doctor_1", "d", ("doctor", "specialty")),
            Workload("hot_doctor_3", "dr.", ("doctor", "specialty")),
            Workload("hot_doctor_8", "dr. aany", ("doctor", "specialty")),
            Workload("hot_specialty_1", "c", ("doctor", "specialty")),
            Workload("hot_specialty_3", "car", ("doctor", "specialty")),
            Workload("hot_specialty_8", "cardiolo", ("doctor", "specialty")),
            Workload("missing_1", "q", ("doctor", "specialty")),
            Workload("missing_3", "qzx", ("doctor", "specialty")),
            Workload("missing_8", "qzxvbnm", ("doctor", "specialty")),
        )
    hot = ("a", "amo", "amoxicil")
    missing = ("q", "qzx", "qzxvbnmz")
    return tuple(
        Workload(f"{kind}_{length}", prefix, ("medicine",))
        for kind, prefixes in (("hot", hot), ("missing", missing))
        for length, prefix in zip((1, 3, 8), prefixes)
    )


def sorted_index(entries: Sequence[Suggestion]):
    return sorted(
        ((normalize_label(item.label), item.kind, int(item.id), item) for item in entries),
        key=lambda row: row[:3],
    )


def sorted_prefix_search(index, prefix: str, limit: int, kinds: Sequence[str]):
    normalized = normalize_prefix(prefix)
    target = (normalized, "", -1)
    position = bisect.bisect_left(index, target, key=lambda row: row[:3])
    result = []
    allowed = set(kinds)
    while position < len(index) and index[position][0].startswith(normalized):
        entry = index[position][3]
        if entry.kind in allowed:
            result.append(entry)
            if len(result) == limit:
                break
        position += 1
    return tuple(result)


def scan_prefix_search(entries, prefix: str, limit: int, kinds: Sequence[str]):
    normalized = normalize_prefix(prefix)
    allowed = set(kinds)
    # The generated owner catalogs have one row per (kind,id). Cache each
    # normalized display label, while retaining the scan's O(n) row visits.
    return tuple(
        heapq.nsmallest(
            limit,
            (
                entry
                for entry in entries
                if entry.kind in allowed
                and _cached_normalize(entry.label).startswith(normalized)
            ),
            key=_cached_order,
        )
    )


@lru_cache(maxsize=250_000)
def _cached_normalize(label: str) -> str:
    return normalize_label(label)


def _cached_order(entry: Suggestion) -> tuple[str, str, int]:
    return _cached_normalize(entry.label), entry.kind, int(entry.id)


def query_digest(catalogs: dict[str, tuple[Suggestion, ...]]) -> str:
    canonical = {
        owner: [
            {"id": entry.id, "kind": entry.kind, "label": entry.label}
            for entry in entries
        ]
        for owner, entries in catalogs.items()
    }
    return hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _measure_calls(search, trace, clients: int, result_limit: int):
    if clients == 1:
        assignments = (range(len(trace)),)
    else:
        assignments = tuple(range(worker, len(trace), clients) for worker in range(clients))

    def worker(indices):
        samples: list[int] = []
        by_workload: dict[str, list[int]] = {}
        for index in indices:
            name, prefix, kinds = trace[index]
            before = time.perf_counter_ns()
            search(prefix, result_limit, kinds)
            elapsed = time.perf_counter_ns() - before
            samples.append(elapsed)
            by_workload.setdefault(name, []).append(elapsed)
        return samples, by_workload

    started = time.perf_counter()
    if clients == 1:
        worker_samples = [worker(assignments[0])]
    else:
        with ThreadPoolExecutor(max_workers=clients) as pool:
            worker_samples = list(pool.map(worker, assignments))
    wall_seconds = time.perf_counter() - started
    samples = [value for worker_result, _ in worker_samples for value in worker_result]
    by_workload: dict[str, list[int]] = {}
    for _, worker_groups in worker_samples:
        for name, values in worker_groups.items():
            by_workload.setdefault(name, []).extend(values)
    return samples, by_workload, wall_seconds


def percentile(samples: Sequence[int], p: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    return ordered[max(0, math.ceil(p * len(ordered)) - 1)] / 1_000_000


def summarize_samples(samples: Sequence[int], wall_seconds: float) -> dict[str, float | int]:
    return {
        "sample_count": len(samples),
        "average_latency_ms": statistics.fmean(samples) / 1_000_000 if samples else 0.0,
        "min_latency_ms": min(samples) / 1_000_000 if samples else 0.0,
        "p50_latency_ms": percentile(samples, 0.50),
        "p95_latency_ms": percentile(samples, 0.95),
        "p99_latency_ms": percentile(samples, 0.99),
        "max_latency_ms": max(samples) / 1_000_000 if samples else 0.0,
        "lookup_throughput_per_second": len(samples) / wall_seconds if wall_seconds else 0.0,
    }


def rss_bytes() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == "darwin" else value * 1024)


def approximate_sorted_index_bytes(index) -> int:
    seen: set[int] = set()
    total = 0

    def add(value: object) -> None:
        nonlocal total
        if id(value) not in seen:
            seen.add(id(value))
            total += sys.getsizeof(value)

    add(index)
    for row in index:
        add(row)
        for value in row:
            add(value)
            if isinstance(value, Suggestion):
                add(value.id)
                add(value.kind)
                add(value.label)
    return total


def _warm(search, query_set, result_limit: int) -> None:
    for index in range(1_000):
        _, prefix, kinds = query_set[index % len(query_set)]
        search(prefix, result_limit, kinds)


def run_level(level: str, seed: int, trials: int, operations: int):
    count = LEVEL_ENTRIES[level]
    catalogs = generate_catalogs(count, seed)
    data_hash = query_digest(catalogs)
    all_queries: dict[str, tuple[Workload, ...]] = {
        owner: workloads(owner) for owner in catalogs
    }
    correctness_rows = []

    summary_rows: list[dict[str, object]] = []
    workload_rows: list[dict[str, object]] = []
    build_rows: list[dict[str, object]] = []
    default_cap_rows: list[dict[str, object]] = []
    high_water_before = rss_bytes()
    python_peaks: dict[str, int] = {}
    for owner, entries in catalogs.items():
        query_set = all_queries[owner]
        query_set_values = tuple((q.name, q.prefix, q.kinds) for q in query_set)

        try:
            default_probe = build_snapshot(1, entries, DEFAULT_INDEX_LIMITS)
            default_cap_rows.append(
                {
                    "owner": owner,
                    "accepted": True,
                    "reason": "within_default_limit",
                    "entries": default_probe.entries,
                    "estimated_bytes": default_probe.estimated_bytes,
                }
            )
            del default_probe
        except IndexTooLarge as error:
            default_cap_rows.append(
                {
                    "owner": owner,
                    "accepted": False,
                    "reason": error.reason,
                    "entries": error.entries,
                    "estimated_bytes": error.estimated_bytes,
                }
            )

        oracle_by_query = {
            (query.name, query.prefix, query.kinds): scan_prefix_search(
                entries, query.prefix, 20, query.kinds
            )
            for query in query_set
        }
        for trial in range(trials):
            print(
                f"benchmark level={level} owner={owner} trial={trial + 1}/{trials}",
                flush=True,
            )
            trial_seed = seed + trial
            rng = random.Random(trial_seed + (0 if owner == "doctor" else 100_000))
            trace_workloads = [query_set[index % len(query_set)] for index in range(operations)]
            rng.shuffle(trace_workloads)
            trace = tuple((q.name, q.prefix, q.kinds) for q in trace_workloads)

            build_started = time.perf_counter()
            sorted_baseline = sorted_index(entries)
            baseline_build_seconds = time.perf_counter() - build_started
            baseline_bytes = approximate_sorted_index_bytes(sorted_baseline)

            rss_before_trie = rss_bytes()
            build_started = time.perf_counter()
            trie_snapshot = build_snapshot(
                1,
                entries,
                IndexLimits(max_entries=100_000, max_estimated_bytes=512 * 1024 * 1024),
            )
            trie_build_seconds = time.perf_counter() - build_started
            trie_rss_after = rss_bytes()
            trie_estimated_bytes = trie_snapshot.estimated_bytes

            def trie_search(prefix, limit, kinds):
                return trie_snapshot.trie.search(prefix, limit=limit, kinds=kinds)

            def baseline_search(prefix, limit, kinds):
                return sorted_prefix_search(sorted_baseline, prefix, limit, kinds)

            def scan_search(prefix, limit, kinds):
                return scan_prefix_search(entries, prefix, limit, kinds)

            # Prove exact top-K output for every workload and result limit against
            # the independent full string-scan oracle before timing any algorithm.
            exact_checks = 0
            total_checks = 0
            for query in query_set:
                for limit in RESULT_LIMITS:
                    key = (query.name, query.prefix, query.kinds)
                    oracle = oracle_by_query[key]
                    if limit != 20:
                        oracle = scan_prefix_search(entries, query.prefix, limit, query.kinds)
                    trie_exact = trie_search(query.prefix, limit, query.kinds) == oracle
                    baseline_exact = baseline_search(query.prefix, limit, query.kinds) == oracle
                    exact_checks += int(trie_exact) + int(baseline_exact)
                    total_checks += 2
                    if trial == 0:
                        for algorithm, exact in (
                            ("trie", trie_exact),
                            ("sorted_prefix_baseline", baseline_exact),
                        ):
                            correctness_rows.append(
                                {
                                    "owner": owner,
                                    "workload": query.name,
                                    "prefix_length": len(normalize_prefix(query.prefix)),
                                    "result_limit": limit,
                                    "algorithm": algorithm,
                                    "expected_count": len(oracle),
                                    "exact_ordered_top_k": exact,
                                }
                            )
            all_exact = exact_checks == total_checks
            accuracy_percent = 100.0 * exact_checks / total_checks if total_checks else 0.0
            if not all_exact:
                raise RuntimeError(f"exact result correctness failed for {owner} at {level}")

            build_rows.append(
                {
                    "level": level,
                    "owner": owner,
                    "trial": trial + 1,
                    "seed": seed,
                    "entries": len(entries),
                    "trie_nodes": trie_snapshot.nodes,
                    "trie_estimated_bytes": trie_estimated_bytes,
                    "trie_build_seconds": trie_build_seconds,
                    "sorted_baseline_estimated_bytes": baseline_bytes,
                    "sorted_baseline_build_seconds": baseline_build_seconds,
                    "tracemalloc_peak_bytes": "measured_separately",
                    "process_peak_rss_before_trie_bytes": rss_before_trie,
                    "process_peak_rss_after_trie_bytes": trie_rss_after,
                }
            )

            scan_operations = max(100, min(operations, 10_000_000 // len(entries)))
            scan_trace = tuple(
                (q.name, q.prefix, q.kinds)
                for q in (query_set[index % len(query_set)] for index in range(scan_operations))
            )
            for clients in CLIENT_COUNTS:
                for result_limit in RESULT_LIMITS:
                    _warm(trie_search, query_set_values, result_limit)
                    trie_samples, trie_by_workload, trie_wall = _measure_calls(
                        trie_search, trace, clients, result_limit
                    )
                    _warm(baseline_search, query_set_values, result_limit)
                    baseline_samples, baseline_by_workload, baseline_wall = _measure_calls(
                        baseline_search, trace, clients, result_limit
                    )

                    measured = [
                        ("trie", trie_samples, trie_by_workload, trie_wall, trie_build_seconds, trie_estimated_bytes),
                        ("sorted_prefix_baseline", baseline_samples, baseline_by_workload, baseline_wall, baseline_build_seconds, baseline_bytes),
                    ]
                    if clients == 1 and result_limit == RESULT_LIMITS[0]:
                        _warm(scan_search, query_set_values, result_limit)
                        scan_samples, scan_by_workload, scan_wall = _measure_calls(
                            scan_search, scan_trace, clients, result_limit
                        )
                        measured.append(
                            ("python_scan_secondary", scan_samples, scan_by_workload, scan_wall, 0.0, "")
                        )

                    for algorithm, samples, groups, wall, build_seconds, memory_bytes in measured:
                        summary_rows.append(
                            {
                                "level": level,
                                "owner": owner,
                                "trial": trial + 1,
                                "seed": seed,
                                "clients": clients,
                                "algorithm": algorithm,
                                "result_limit": result_limit,
                                "entries": len(entries),
                                "index_nodes": trie_snapshot.nodes if algorithm == "trie" else "",
                                "index_estimated_bytes": memory_bytes,
                                "index_construction_seconds": build_seconds,
                                "result_correctness_exact": all_exact,
                            "result_accuracy_percent": accuracy_percent,
                                "scan_sample_cap": scan_operations if algorithm == "python_scan_secondary" else "",
                                **summarize_samples(samples, wall),
                            }
                        )
                        for query in query_set:
                            rows = groups.get(query.name, [])
                            group = summarize_samples(rows, wall)
                            workload_rows.append(
                                {
                                    "level": level,
                                    "owner": owner,
                                    "trial": trial + 1,
                                    "seed": seed,
                                    "clients": clients,
                                    "algorithm": algorithm,
                                    "result_limit": result_limit,
                                    "workload": query.name,
                                    "prefix_length": len(normalize_prefix(query.prefix)),
                                    "sampled_queries": len(rows),
                                    **group,
                                }
                            )
            del trie_snapshot, sorted_baseline

        # Trace allocations in a separate build so tracing does not distort the
        # lookup latency or normal construction-time measurements.
        gc.collect()
        tracemalloc.start()
        tracemalloc.reset_peak()
        traced_snapshot = build_snapshot(
            1,
            entries,
            IndexLimits(max_entries=100_000, max_estimated_bytes=512 * 1024 * 1024),
        )
        _, python_peaks[owner] = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        del traced_snapshot
        for row in build_rows:
            if row["owner"] == owner:
                row["tracemalloc_peak_bytes"] = python_peaks[owner]
        gc.collect()

    memory_summary = {
        "process_peak_rss_before_run_bytes": high_water_before,
        "process_peak_rss_after_run_bytes": rss_bytes(),
        "tracemalloc_peak_bytes_by_owner": python_peaks,
    }
    return {
        "catalogs": catalogs,
        "data_hash": data_hash,
        "summary_rows": summary_rows,
        "workload_rows": workload_rows,
        "build_rows": build_rows,
        "default_cap_rows": default_cap_rows,
        "correctness_rows": correctness_rows,
        "memory_summary": memory_summary,
    }


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_svg(path: Path, rows: list[dict[str, object]]) -> None:
    grouped_values: dict[tuple[str, int], list[float]] = {}
    for row in rows:
        if str(row["algorithm"]) not in {"trie", "sorted_prefix_baseline"}:
            continue
        grouped_values.setdefault((str(row["algorithm"]), int(row["clients"])), []).append(
            float(row["p95_latency_ms"])
        )
    groups = {
        key: {"p95": statistics.fmean(values)}
        for key, values in grouped_values.items()
    }
    width, height = 980, 420
    left, top, chart_width, chart_height = 230, 50, 690, 310
    max_value = max((values["p95"] for values in groups.values()), default=1.0) or 1.0
    colors = {"trie": "#1d4ed8", "sorted_prefix_baseline": "#d97706"}
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="28" y="28" font-family="Arial" font-size="18" font-weight="bold">Autocomplete P95 CPU lookup latency</text>',
    ]
    values = list(groups.items())
    row_height = chart_height / max(1, len(values))
    for index, ((algorithm, clients), stats) in enumerate(values):
        y = top + index * row_height
        label = f"{algorithm}, {clients} clients"
        bar_width = chart_width * stats["p95"] / max_value
        lines.append(
            f'<text x="{left - 12}" y="{y + 18:.1f}" text-anchor="end" font-family="Arial" font-size="12">{label}</text>'
        )
        lines.append(
            f'<rect x="{left}" y="{y + 2:.1f}" width="{bar_width:.2f}" height="22" fill="{colors.get(algorithm, "#64748b")}"/>'
        )
        lines.append(
            f'<text x="{left + bar_width + 6:.2f}" y="{y + 18:.1f}" font-family="Arial" font-size="12">{stats["p95"]:.4f} ms</text>'
        )
    lines.append(
        f'<text x="{left}" y="{height - 20}" font-family="Arial" font-size="12">P95 by algorithm and concurrent closed-loop clients · trie and sorted baseline</text>'
    )
    lines.append("</svg>")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_report(path: Path, result: dict[str, object], level: str, seed: int) -> None:
    summary_rows = result["summary_rows"]
    build_rows = result["build_rows"]
    default_cap_rows = result["default_cap_rows"]
    assert isinstance(summary_rows, list)
    assert isinstance(build_rows, list)
    assert isinstance(default_cap_rows, list)
    outcomes = []
    for row in summary_rows:
        outcomes.append(
            f"| {row['owner']} | {row['algorithm']} | {row['clients']} | "
            f"{row['average_latency_ms']:.4f} | {row['p95_latency_ms']:.4f} | "
            f"{row['lookup_throughput_per_second']:.1f} | {row['sample_count']} |"
        )
    caps = ", ".join(
        f"{row['owner']}={'within limit' if row['accepted'] else row['reason']}"
        for row in default_cap_rows
    )
    text = [
        f"# Autocomplete benchmark: {level}",
        "",
        f"Dataset seed: `{seed}`. Generated owner catalogs contain {LEVEL_ENTRIES[level]:,} entries each; "
        "the Doctor catalog includes active-doctor and specialty kinds, while the Pharmacy catalog contains active-medicine names only.",
        "",
        "## Results",
        "",
        "| Owner | Algorithm | Clients | Average ms | P95 ms | Lookups/s | Samples |",
        "|---|---|---:|---:|---:|---:|---:|",
        *outcomes,
        "",
        "## Index construction and memory",
        "",
        "See `build.csv` for trie nodes, estimated retained object bytes, sorted-baseline estimated bytes, "
        "construction time, separately traced build-allocation peak, and observed process peak RSS. Trie bytes are an approximate "
        "Python object-size estimate; RSS and tracemalloc are separate measurements.",
        "",
        f"Default 64 MiB index-cap preflight: {caps}. The timed high-cap trie uses a recorded 512 MiB experimental cap so 100k-entry cases can be measured; the deployed default remains 64 MiB.",
        "",
        "## Correctness and scope",
        "",
        "Trie and sorted-prefix outputs were checked for exact ordered top-K equality against the independent full string-scan oracle for each generated hot and missing prefix, at limits 10 and 20. `correctness.csv` contains the per-prefix oracle counts.",
        "",
        "The primary baseline is an in-memory sorted string-prefix range that models the ordering behavior of a PostgreSQL prefix index. The full Python string scan is the correctness oracle and is also measured as a bounded secondary CPU baseline; its operation cap is reported because its O(n) cost grows with catalog size. This is a CPU-only algorithm benchmark: it does not include authenticated HTTP, PostgreSQL revision reads, selected-ID validation, or network latency, because the coordinator owns route mounting and migration integration.",
        "",
        "Measurements use `perf_counter_ns`, 1,000 warmup calls per owner/algorithm/client/result-limit configuration, and closed-loop thread clients. Trie and sorted baseline each receive at least 100,000 timed operations per trial for limits 10 and 20. Tracemalloc runs in a separate build pass and is disabled during timed lookups. Throughput is completed lookups divided by wall time. P95 uses nearest-rank `ceil(0.95*n)-1`; no endpoint or service-level speedup is claimed.",
        "",
        f"Catalog SHA256: `{result['data_hash']}`.",
    ]
    path.write_text("\n".join(text) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=404)
    parser.add_argument("--level", choices=tuple(LEVEL_ENTRIES), required=True)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--operations", type=int, default=100_000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.trials < 1 or args.operations < 100_000:
        parser.error("trials must be positive and operations must be at least 100000")

    command = " ".join(sys.argv)
    started_utc = datetime.now(timezone.utc)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    result = run_level(args.level, args.seed, args.trials, args.operations)
    write_csv(output / "summary.csv", result["summary_rows"])
    write_csv(output / "workload.csv", result["workload_rows"])
    write_csv(output / "build.csv", result["build_rows"])
    write_csv(output / "default_cap.csv", result["default_cap_rows"])
    write_csv(output / "correctness.csv", result["correctness_rows"])
    write_svg(output / "latency.svg", result["summary_rows"])
    write_report(output / "report.md", result, args.level, args.seed)

    tracked_outputs = (
        "summary.csv",
        "workload.csv",
        "build.csv",
        "default_cap.csv",
        "correctness.csv",
        "latency.svg",
        "report.md",
    )
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    component_source_hashes = {
        name: hashlib.sha256(
            (ROOT / "components/autocomplete/src/pulsegrid_autocomplete" / name).read_bytes()
        ).hexdigest()
        for name in ("trie.py", "lifecycle.py", "metrics.py")
    }
    baseline_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    output_hashes = {
        name: hashlib.sha256((output / name).read_bytes()).hexdigest()
        for name in tracked_outputs
    }
    manifest = {
        "component": "autocomplete",
        "run_started_utc": started_utc.isoformat().replace("+00:00", "Z"),
        "run_finished_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "command": command,
        "level": args.level,
        "dataset_seed": args.seed,
        "baseline_commit": baseline_commit,
        "component_base_commit": "45273ea7fd1ea53e335942b6c38f2d81d38856ee",
        "component_source_script_sha256": script_hash,
        "component_source_sha256": component_source_hashes,
        "baseline_algorithm": "sorted normalized-label prefix range with identical rank and limit",
        "trial_count": args.trials,
        "operations_per_configuration_per_trial": args.operations,
        "clients": list(CLIENT_COUNTS),
        "result_limits_timed": list(RESULT_LIMITS),
        "result_limits_correctness": list(RESULT_LIMITS),
        "entry_count_per_owner": LEVEL_ENTRIES[args.level],
        "catalog_sha256": result["data_hash"],
        "script_sha256": script_hash,
        "python": sys.version,
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "cpu_model": platform.processor() or platform.uname().processor or "unavailable",
        "cpu_count": os.cpu_count(),
        "memory_total_bytes": (
            os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
            if hasattr(os, "sysconf") and "SC_PHYS_PAGES" in os.sysconf_names
            else None
        ),
        "default_index_limits": asdict(DEFAULT_INDEX_LIMITS),
        "timed_trie_limits": {"max_entries": 100_000, "max_estimated_bytes": 512 * 1024 * 1024},
        "normalization": "Unicode NFKC, casefold, strip, collapse whitespace",
        "timer": "time.perf_counter_ns",
        "timer_resolution_seconds": time.get_clock_info("perf_counter").resolution,
        "p95_method": "nearest-rank ceil(0.95*n)-1",
        "topology": "one process with closed-loop ThreadPoolExecutor clients; CPU-only",
        "memory_summary": result["memory_summary"],
        "output_sha256": output_hashes,
        "raw_samples_or_datasets_retained": False,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"Wrote {args.level} autocomplete benchmark to {output}; "
        f"catalog_sha256={result['data_hash']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
