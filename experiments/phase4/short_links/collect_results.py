#!/usr/bin/env python3
"""Package short-link benchmark JSON and raw samples into bounded artifacts."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
GENERATOR = ROOT / "services/appointment/tests/phase4_short_links/test_benchmark.py"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_reports(values: list[str]) -> dict[str, tuple[Path, dict]]:
    reports = {}
    for value in values:
        level, separator, path_text = value.partition("=")
        if not separator or level not in {"low", "medium", "high"}:
            raise ValueError("Each report must use LEVEL=PATH for low, medium, or high")
        path = Path(path_text).expanduser().resolve()
        report = json.loads(path.read_text())
        if report.get("level") != level or report.get("benchmark") != "phase4_short_links_local_adapter":
            raise ValueError(f"Report identity mismatch: {path}")
        if level in reports:
            raise ValueError(f"Duplicate level: {level}")
        reports[level] = (path, report)
    if set(reports) != {"low", "medium", "high"}:
        raise ValueError("Package requires low, medium, and high reports")
    seeds = {report[1]["seed"] for report in reports.values()}
    if len(seeds) != 1:
        raise ValueError("All reports must use the same seed")
    return reports


def _operation_rows(level: str, report: dict) -> list[dict]:
    rows = []
    for trial in report["trials"]:
        for mode in ("baseline", "proposed"):
            for operation, values in trial[mode]["operations"].items():
                latency = values["success_latency"]
                error_latency = values["error_latency"]
                rows.append({
                    "level": level,
                    "seed": report["seed"],
                    "dataset_aliases_per_trial": report["dataset_alias_count_per_trial"],
                    "clients": report["clients"],
                    "trial": trial["trial"],
                    "mode": mode,
                    "operation": operation,
                    "attempted": values["attempted"],
                    "completed": values["completed"],
                    "errors": values["errors"],
                    "throughput_per_second": values["throughput_per_second"],
                    "p50_ms": latency["p50_ms"],
                    "p95_ms": latency["p95_ms"],
                    "p99_ms": latency["p99_ms"],
                    "min_ms": latency["min_ms"],
                    "max_ms": latency["max_ms"],
                    "error_p50_ms": error_latency["p50_ms"],
                    "error_p95_ms": error_latency["p95_ms"],
                    "error_p99_ms": error_latency["p99_ms"],
                    "error_min_ms": error_latency["min_ms"],
                    "error_max_ms": error_latency["max_ms"],
                    "collisions": trial["collisions"],
                })
    navigation = report["navigation_303"]["operations"]["navigation_303"]
    latency = navigation["success_latency"]
    rows.append({
        "level": level,
        "seed": report["seed"],
        "dataset_aliases_per_trial": report["dataset_alias_count_per_trial"],
        "clients": report["clients"],
        "trial": 0,
        "mode": "proposed_navigation",
        "operation": "navigation_303",
        "attempted": navigation["attempted"],
        "completed": navigation["completed"],
        "errors": navigation["errors"],
        "throughput_per_second": navigation["throughput_per_second"],
        "p50_ms": latency["p50_ms"],
        "p95_ms": latency["p95_ms"],
        "p99_ms": latency["p99_ms"],
        "min_ms": latency["min_ms"],
        "max_ms": latency["max_ms"],
        "error_p50_ms": None,
        "error_p95_ms": None,
        "error_p99_ms": None,
        "error_min_ms": None,
        "error_max_ms": None,
        "collisions": 0,
    })
    return rows


def _metric(report: dict, mode: str, operation: str, trial_index: int, key: str):
    return report["trials"][trial_index][mode]["operations"][operation]["success_latency"][key]


def _latency_svg(reports: dict[str, tuple[Path, dict]]) -> str:
    entries = []
    for level in ("low", "medium", "high"):
        report = reports[level][1]
        for trial_index, trial in enumerate(report["trials"]):
            for mode, operation, label, color in (
                ("baseline", "baseline_workflow_lookup", "baseline", "#52718f"),
                ("proposed", "proposed_authenticated_resolution", "alias resolve", "#178a70"),
                ("proposed", "proposed_creation", "create", "#d08b28"),
            ):
                latency = trial[mode]["operations"][operation]["success_latency"]
                if latency["p95_ms"] is not None:
                    entries.append((f"{level} / trial {trial['trial']} / {label}", latency["p50_ms"], latency["p95_ms"], color))
    width, left, right, top, row_height = 1000, 280, 40, 55, 22
    height = 100 + len(entries) * row_height
    chart_width = width - left - right
    maximum = max(entry[2] for entry in entries) or 1
    scale = chart_width / maximum
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="24" y="28" font-family="sans-serif" font-size="18" font-weight="bold">Short-link adapter latency by trial (p50 marker, p95 bar)</text>',
        '<text x="24" y="48" font-family="sans-serif" font-size="12" fill="#555">Milliseconds; local direct-call adapter, PostgreSQL-backed</text>',
    ]
    for index, (label, p50, p95, color) in enumerate(entries):
        y = top + index * row_height
        parts.extend([
            f'<text x="{left - 10}" y="{y + 13}" text-anchor="end" font-family="sans-serif" font-size="11">{label}</text>',
            f'<rect x="{left}" y="{y}" width="{max(1, p95 * scale):.2f}" height="14" rx="3" fill="{color}" opacity="0.55"/>',
            f'<line x1="{left + p50 * scale:.2f}" y1="{y - 1}" x2="{left + p50 * scale:.2f}" y2="{y + 15}" stroke="{color}" stroke-width="3"/>',
            f'<text x="{left + p95 * scale + 6:.2f}" y="{y + 12}" font-family="sans-serif" font-size="10" fill="#333">{p95:.2f}</text>',
        ])
    axis_y = top + len(entries) * row_height
    for tick in range(0, int(maximum) + 1, max(1, int(maximum / 5))):
        x = left + tick * scale
        parts.append(f'<line x1="{x:.2f}" y1="{top - 5}" x2="{x:.2f}" y2="{axis_y}" stroke="#e3e7ea"/>')
        parts.append(f'<text x="{x:.2f}" y="{axis_y + 16}" text-anchor="middle" font-family="sans-serif" font-size="10" fill="#555">{tick}</text>')
    parts.extend([
        f'<line x1="{left}" y1="{axis_y}" x2="{width - right}" y2="{axis_y}" stroke="#777"/>',
        f'<text x="{left + chart_width / 2:.2f}" y="{height - 8}" text-anchor="middle" font-family="sans-serif" font-size="11">Latency (ms)</text>',
        '</svg>',
    ])
    return "\n".join(parts) + "\n"


def _report_markdown(reports: dict[str, tuple[Path, dict]], diagnostic_types: dict[str, int] | None = None) -> str:
    first = next(iter(reports.values()))[1]
    environment = first["environment"]
    seed = first["seed"]
    sensitivity_seeds = sorted({404, 405, 406} - {seed})
    high_errors = []
    for trial in reports["high"][1]["trials"]:
        proposed = trial["proposed"]["operations"]
        high_errors.append(sum(operation["errors"] for operation in proposed.values()))
    lines = [
        "# Phase 4.5 short-link benchmark",
        "",
        f"Seed: `{first['seed']}`. Each level contains three independent 30-second measured trials per mode, with a 5-second warmup per mode. The baseline/proposed order alternates.",
        "",
        "## Workloads and results",
        "",
        "The baseline is the existing authenticated Phase 3 workflow GET. Proposed traffic is authenticated JSON alias resolution and creation at a 90/10 mix. The separate navigation result is a static, shape-checked 303 and performs no database read.",
        "",
        "| Level | Trial | Baseline workflow p50/p95 ms | Alias resolve p50/p95 ms | Create p50/p95 ms | Baseline / resolve / create ops/s | Collisions | Errors |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for level in ("low", "medium", "high"):
        report = reports[level][1]
        for trial in report["trials"]:
            baseline = trial["baseline"]["operations"]["baseline_workflow_lookup"]
            proposed = trial["proposed"]["operations"]
            resolve = proposed["proposed_authenticated_resolution"]
            create = proposed["proposed_creation"]
            fmt = lambda op: f"{op['success_latency']['p50_ms']:.2f}/{op['success_latency']['p95_ms']:.2f}"
            throughput = f"{baseline['throughput_per_second']:.1f} / {resolve['throughput_per_second']:.1f} / {create['throughput_per_second']:.1f}"
            errors = baseline["errors"] + resolve["errors"] + create["errors"]
            lines.append(f"| {level} ({report['dataset_alias_count_per_trial']:,}, {report['clients']} clients) | {trial['trial']} | {fmt(baseline)} | {fmt(resolve)} | {fmt(create)} | {throughput} | {trial['collisions']} | {errors} |")
    lines.extend([
        "",
        "## Environment and limits",
        "",
        f"- {environment['os']}; {environment['cpu_count']} CPUs; {environment['memory_bytes'] // (1024 * 1024 * 1024)} GiB RAM.",
        f"- Python {environment['python']}; FastAPI {environment['fastapi']}; SQLAlchemy {environment['sqlalchemy']}; psycopg {environment['psycopg']}; {environment['postgresql']}.",
        "- Timing uses `perf_counter_ns`; measured calls use the same local PostgreSQL fixture and synthetic Appointment owner rows.",
        "- Alias resolution latency includes the feature's direct route adapter, PostgreSQL digest/booking/hold reads, authorization adapter and audit read. Creation includes its repository writes and test command adapter.",
        "- The test `stage_effect` is a no-op. Calls use in-process principals and direct route invocation; JWT middleware, ASGI/network, Traefik, coordinator migration 0010, production lock/effect adapters, and integrated audit/outbox write cost are not measured.",
        "- Throughput is not a like-for-like ratio: the baseline workload is 100% workflow GET, while proposed traffic is a 90/10 resolution/create mix. Compare per-operation latency and report throughput alongside that mix.",
        "- `summary.csv` separates successful latency percentiles from failed-operation percentiles; errors are not omitted from the raw samples.",
        "- Random-alias collisions were zero in measured trials. Forced digest/unique-index collisions and retry bounds are covered by correctness tests.",
        f"- Other distribution-sensitivity seeds not included in this per-seed artifact: {', '.join(map(str, sensitivity_seeds))}.",
        "",
        "## Navigation sample",
        "",
        "Each level measured 1,000 static 303 responses. Per-level p50/p95/p99 and sample counts are in `summary.csv`.",
        "",
        "See `manifest.json` for generation command, environment, input-spec and output SHA-256 values. Raw samples are gzip-compressed under `raw_samples/` locally and ignored by Git.",
        "",
    ])
    if diagnostic_types:
        diagnostic_count = sum(diagnostic_types.values())
        lines.insert(lines.index(f"- Other distribution-sensitivity seeds not included in this per-seed artifact: {', '.join(map(str, sensitivity_seeds))}."),
                     f"- High-load measured proposed-operation errors were {', '.join(map(str, high_errors))} across trials. A separate same-seed diagnostic run classified {diagnostic_count} exceptions as {', '.join(f'`{name}`={count}' for name, count in sorted(diagnostic_types.items()))}. The test fixture has a 20-connection pool, no overflow and a 2-second pool-acquisition timeout. This is consistent with pool pressure at 32 clients, but the diagnostic captured exception classes rather than the exception module, so the exact timeout source is not confirmed.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--diagnostic-samples", type=Path)
    parser.add_argument("reports", nargs="+", help="LEVEL=benchmark.json for low, medium, and high")
    args = parser.parse_args()
    reports = load_reports(args.reports)
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / "raw_samples"
    raw_dir.mkdir(exist_ok=True)
    csv_path = output_dir / "summary.csv"
    rows = []
    report_hashes = {}
    raw_hashes = {}
    for level, (path, report) in reports.items():
        rows.extend(_operation_rows(level, report))
        report_hashes[level] = sha256(path)
        source_samples = Path(report["raw_samples_file"]).expanduser().resolve()
        target_samples = raw_dir / f"{level}.samples.csv.gz"
        with source_samples.open("rb") as source, gzip.open(target_samples, "wb", compresslevel=6) as target:
            shutil.copyfileobj(source, target)
        raw_hashes[level] = {
            "source_csv_sha256": sha256(source_samples),
            "local_gzip_sha256": sha256(target_samples),
            "sample_count": sum(row["attempted"] for row in rows if row["level"] == level),
        }
    fieldnames = list(rows[0])
    with csv_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    report_path = output_dir / "report.md"
    diagnostic_types = {}
    diagnostic_manifest = None
    if args.diagnostic_samples is not None:
        diagnostic_path = args.diagnostic_samples.expanduser().resolve()
        with diagnostic_path.open(newline="") as stream:
            for row in csv.DictReader(stream):
                if row.get("status_code") == "0" and row.get("error_type"):
                    diagnostic_types[row["error_type"]] = diagnostic_types.get(row["error_type"], 0) + 1
        diagnostic_copy = raw_dir / "high-diagnostic.samples.csv.gz"
        with diagnostic_path.open("rb") as source, gzip.open(diagnostic_copy, "wb", compresslevel=6) as target:
            shutil.copyfileobj(source, target)
        diagnostic_manifest = {
            "source_csv_sha256": sha256(diagnostic_path),
            "local_gzip_sha256": sha256(diagnostic_copy),
            "error_type_counts": diagnostic_types,
        }
    report_path.write_text(_report_markdown(reports, diagnostic_types or None))
    svg_path = output_dir / "latency.svg"
    svg_path.write_text(_latency_svg(reports))

    fixture_generator_sha256 = sha256(GENERATOR)
    fixture_specs = {}
    for level, (_path, report) in reports.items():
        spec = {
            "seed": report["seed"],
            "level": level,
            "dataset_alias_count_per_trial": report["dataset_alias_count_per_trial"],
            "total_fixture_alias_count": report["total_fixture_alias_count"],
            "clients": report["clients"],
            "read_create_mix": report["read_create_mix"],
            "generator_sha256": fixture_generator_sha256,
        }
        canonical = json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()
        fixture_specs[level] = {**spec, "fixture_spec_sha256": hashlib.sha256(canonical).hexdigest()}
    output_hashes = {path.name: sha256(path) for path in (csv_path, report_path, svg_path)}
    manifest = {
        "benchmark": "phase4_short_links_local_adapter",
        "run_id": f"seed-{next(iter(reports.values()))[1]['seed']}",
        "packaged_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "generation_command": "python experiments/phase4/short_links/run.py --seed SEED --level LEVEL --output PATH",
        "collection_command": "python experiments/phase4/short_links/collect_results.py --output-dir DIR low=PATH medium=PATH high=PATH",
        "environment": next(iter(reports.values()))[1]["environment"],
        "fixture_specs": fixture_specs,
        "source_report_sha256": report_hashes,
        "raw_samples": raw_hashes,
        "diagnostic_samples": diagnostic_manifest,
        "committed_output_sha256": output_hashes,
        "limitations": next(iter(reports.values()))[1]["limitations"],
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"Packaged summary: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
