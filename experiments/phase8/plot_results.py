#!/usr/bin/env python3
"""Generate Phase 8 plots from retained Phase 4 CSV and Phase 8 JSON/CSV evidence."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import statistics
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN = "phase8-20261013-run1"
LEVELS = ("low", "medium", "high")
LEVEL_CLIENTS = {"low": 8, "medium": 32, "high": 128}
COLORS = {
    "baseline": "#0072B2",
    "redis": "#D55E00",
    "warm": "#009E73",
    "uncached": "#CC79A7",
    "accepted": "#009E73",
    "rejected": "#D55E00",
    "blue": "#0072B2",
    "orange": "#E69F00",
    "purple": "#6F4E7C",
    "gray": "#595959",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def med(values: Iterable[float]) -> float:
    result = statistics.median([float(value) for value in values])
    return float(result)


def save(fig: plt.Figure, path: Path, title: str, footnote: str | None = None) -> None:
    fig.suptitle(title, fontsize=14, fontweight="semibold")
    if footnote:
        fig.text(0.5, 0.012, footnote, ha="center", va="bottom", fontsize=7.5, color=COLORS["gray"])
    fig.tight_layout(rect=(0, 0.075 if footnote else 0, 1, 0.96))
    fig.savefig(path, format="svg", bbox_inches="tight", metadata={"Title": title})
    fig.savefig(path.with_suffix(".png"), format="png", dpi=180, bbox_inches="tight", metadata={"Title": title})
    plt.close(fig)


def normalize_svg_whitespace(output: Path) -> None:
    for path in output.glob("*.svg"):
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text("\n".join(line.rstrip() for line in lines) + "\n", encoding="utf-8")


def load_rate_limiter_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for level in LEVELS:
        path = ROOT / f"experiments/phase4/rate_limiter/results/redis7-{level}/summary.csv"
        rows.extend(read_csv(path))
    return rows


def plot_limiter_throughput(output: Path, rows: list[dict[str, str]]) -> None:
    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    for backend in ("baseline", "redis"):
        xs: list[int] = []
        ys: list[float] = []
        for level in LEVELS:
            group = [row for row in rows if row["level"] == level and row["backend"] == backend]
            xs.append(LEVEL_CLIENTS[level])
            ys.append(med(float(row["accepted"]) / 30.0 for row in group))
        ax.plot(
            xs,
            ys,
            marker="o",
            linewidth=2,
            markersize=6,
            color=COLORS[backend],
            label=f"{backend}: admitted decisions/s",
        )
    ax.set_xscale("log", base=2)
    ax.set_xticks([8, 32, 128], ["8", "32", "128"])
    ax.set_xlabel("Concurrent clients (Phase 4 component benchmark)")
    ax.set_ylabel("Admitted decisions per second")
    ax.grid(True, alpha=0.25)
    ax.legend(frameon=False)
    save(
        fig,
        output / "01_phase4_admission_throughput.svg",
        "Phase 4 limiter throughput under increasing offered load",
        "Phase 4 component limiter; 30-second trials and three seeds per level, not hospital API throughput.",
    )


def plot_latency(output: Path, limiter_rows: list[dict[str, str]], run_dir: Path) -> None:
    phase8 = read_json(run_dir / "summaries/l1-c4-t1.json")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.0, 4.8), gridspec_kw={"width_ratios": [1.25, 1]})
    for backend, color in (("baseline", COLORS["baseline"]), ("redis", COLORS["redis"])):
        p50 = [
            med(float(row["admission_p50_ms"]) for row in limiter_rows if row["level"] == level and row["backend"] == backend)
            for level in LEVELS
        ]
        p95 = [
            med(float(row["admission_p95_ms"]) for row in limiter_rows if row["level"] == level and row["backend"] == backend)
            for level in LEVELS
        ]
        xs = [LEVEL_CLIENTS[level] for level in LEVELS]
        ax1.plot(xs, p50, marker="o", color=color, linestyle="--", label=f"{backend} p50")
        ax1.plot(xs, p95, marker="s", color=color, linewidth=2, label=f"{backend} p95")
    ax1.set_xscale("log", base=2)
    ax1.set_yscale("log")
    ax1.set_xticks([8, 32, 128], ["8", "32", "128"])
    ax1.set_ylim(0.005, 30)
    ax1.set_xlabel("Concurrent clients")
    ax1.set_ylabel("Admission decision latency (ms)")
    ax1.set_title("Phase 4 component calls")
    ax1.grid(True, alpha=0.25)
    ax1.legend(frameon=False, fontsize=8, ncol=2)

    latency_groups = (
        ("All HTTP\n(including 429)", phase8["all_http_latency_ms"]),
        ("Successful\n2xx only", phase8["success_latency_ms"]),
    )
    x = [0, 1]
    means = [float(item["mean"]) for _, item in latency_groups]
    p95s = [float(item["p95"]) for _, item in latency_groups]
    width = 0.34
    ax2.bar([v - width / 2 for v in x], means, width, color=COLORS["blue"], label="Mean")
    ax2.bar([v + width / 2 for v in x], p95s, width, color=COLORS["orange"], label="P95")
    ax2.set_xticks(x, [label for label, _ in latency_groups])
    ax2.set_ylabel("HTTP response latency (ms)")
    ax2.set_title("Phase 8: one C=4 mixed-read trial")
    ax2.grid(axis="y", alpha=0.25)
    ax2.legend(frameon=False)
    for container in (ax2.containers[0], ax2.containers[1]):
        ax2.bar_label(container, fmt="%.1f", padding=2, fontsize=8)
    save(
        fig,
        output / "02_latency_by_condition.svg",
        "Latency evidence by measurement boundary",
        "Phase 8 has one C=4 condition; 99.18% of responses were HTTP 429. No HTTP latency trend was measured.",
    )


def plot_rejections(output: Path, rows: list[dict[str, str]], run_dir: Path) -> None:
    phase8 = read_json(run_dir / "summaries/l1-c4-t1.json")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.6, 4.7), gridspec_kw={"width_ratios": [1.35, 1]})
    for backend, color in (("baseline", COLORS["baseline"]), ("redis", COLORS["redis"])):
        values = [
            med(float(row["rejection_percent"]) for row in rows if row["level"] == level and row["backend"] == backend)
            for level in LEVELS
        ]
        ax1.plot([LEVEL_CLIENTS[level] for level in LEVELS], values, marker="o", linewidth=2, color=color, label=backend)
    ax1.set_xscale("log", base=2)
    ax1.set_xticks([8, 32, 128], ["8", "32", "128"])
    ax1.set_ylim(0, 100)
    ax1.set_xlabel("Concurrent clients (Phase 4 component run)")
    ax1.set_ylabel("Admission-limited decisions (%)")
    ax1.set_title("Historical limiter outcomes")
    ax1.grid(True, alpha=0.25)
    ax1.legend(frameon=False)

    accepted = int(phase8["classification_counts"].get("success", 0))
    rejected = int(phase8["classification_counts"].get("admission_rejected", 0))
    ax2.bar(["Phase 8\nC=4"], [100 * rejected / (accepted + rejected)], color=COLORS["rejected"], label="HTTP 429")
    ax2.bar(
        ["Phase 8\nC=4"],
        [100 * accepted / (accepted + rejected)],
        bottom=[100 * rejected / (accepted + rejected)],
        color=COLORS["accepted"],
        label="HTTP 2xx",
    )
    ax2.set_ylim(0, 100)
    ax2.set_ylabel("Share of HTTP responses (%)")
    ax2.set_title("One authenticated HTTP trial")
    ax2.text(
        0.5,
        0.77,
        f"{rejected:,} HTTP 429\n{accepted} HTTP 2xx",
        transform=ax2.transAxes,
        ha="center",
        fontsize=9,
        color="white",
        fontweight="bold",
    )
    save(
        fig,
        output / "03_admission_outcomes.svg",
        "Admission behavior under increasing offered traffic",
        "Phase 4 component and Phase 8 authenticated HTTP use different workloads; do not join the series.",
    )


def plot_cache(output: Path) -> None:
    cases = (("low", "low-final"), ("medium", "medium-final"), ("high", "high-final"))
    summary: dict[str, dict[str, dict[str, float]]] = {}
    for level, directory in cases:
        rows = read_csv(ROOT / f"experiments/phase4/key_value_cache/results/{directory}/summary.csv")
        summary[level] = {}
        for scenario in ("uncached", "warm"):
            group = [row for row in rows if row["scenario"] == scenario]
            summary[level][scenario] = {
                "mean_ms": med(float(row["mean_ms"]) for row in group),
                "p95_ms": med(float(row["p95_ms"]) for row in group),
            }
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.0, 4.7))
    levels = list(LEVELS)
    x = list(range(len(levels)))
    width = 0.34
    for scenario, offset, color in (("uncached", -width / 2, COLORS["uncached"]), ("warm", width / 2, COLORS["warm"])):
        ax1.bar([i + offset for i in x], [summary[l][scenario]["mean_ms"] for l in levels], width, color=color, label=scenario)
        ax2.bar([i + offset for i in x], [summary[l][scenario]["p95_ms"] for l in levels], width, color=color, label=scenario)
    for ax, field, label in ((ax1, "mean_ms", "Median of trial means (ms)"), (ax2, "p95_ms", "Median of trial P95s (ms)")):
        ax.set_yscale("log")
        ax.set_xticks(x, ["1k rows", "10k rows", "50k rows"])
        ax.set_ylabel(label)
        ax.grid(axis="y", alpha=0.25)
        ax.legend(frameon=False)
    ax1.set_title("Mean latency")
    ax2.set_title("Tail latency")
    save(
        fig,
        output / "05_cache_warm_vs_uncached.svg",
        "Warm cache-aside comparison by synthetic catalog size",
        "Phase 4.3 PostgreSQL/Redis projection adapter; synthetic catalog, not authenticated HTTP.",
    )


def plot_hash_movement(output: Path) -> None:
    rows = read_csv(ROOT / "experiments/phase4/consistent_hashing/results/high-404/movement.csv")
    rows = [row for row in rows if row["transition"] == "3->4"]
    groups: list[tuple[str, str, list[float]]] = []
    for algorithm, vnodes in (("modulo", 0), ("ring", 32), ("ring", 128), ("ring", 512)):
        values = [float(row["percent"]) for row in rows if row["algorithm"] == algorithm and int(row["vnodes"]) == vnodes]
        groups.append((algorithm, str(vnodes) if algorithm == "ring" else "0", values))
    labels = ["Modulo", "Ring\n32 vnodes", "Ring\n128 vnodes", "Ring\n512 vnodes"]
    values = [med(group[2]) for group in groups]
    lower = [values - min(group[2]) for values, group in zip([med(item[2]) for item in groups], groups)]
    upper = [max(group[2]) - values for values, group in zip([med(item[2]) for item in groups], groups)]
    fig, ax = plt.subplots(figsize=(8.6, 4.8))
    bars = ax.bar(labels, values, color=[COLORS["gray"], COLORS["blue"], COLORS["orange"], COLORS["purple"]])
    ax.errorbar(range(len(values)), values, yerr=[lower, upper], fmt="none", ecolor="#222222", capsize=4)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2, f"{value:.2f}%", ha="center", fontsize=9)
    ax.set_ylim(0, 90)
    ax.set_ylabel("Keys moved after adding node 4 (%)")
    ax.set_title("One million synthetic keys; three seeds")
    ax.grid(axis="y", alpha=0.25)
    save(
        fig,
        output / "06_hash_remapping.svg",
        "Consistent hashing versus modulo remapping",
        "Ring movement is lower; lookup was slower than modulo. Placement does not replicate data.",
    )


def plot_surge(output: Path, historical: dict[str, Any]) -> None:
    data = historical["surge"]["class_c_autocomplete_burst"]
    accepted, rejected = data["accepted_2xx"], data["rejected_429"]
    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    ax.bar(["Phase 6\nSURGE"], [accepted], color=COLORS["accepted"], label="Accepted 2xx")
    ax.bar(["Phase 6\nSURGE"], [rejected], bottom=[accepted], color=COLORS["rejected"], label="Rejected 429")
    ax.text(0, accepted / 2, str(accepted), ha="center", va="center", color="white", fontweight="bold")
    ax.text(0, accepted + rejected / 2, str(rejected), ha="center", va="center", color="white", fontweight="bold")
    ax.set_ylim(0, data["attempted"] + 3)
    ax.set_ylabel("Authenticated Doctor autocomplete requests")
    ax.set_title("Class C burst: 20 concurrent requests")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.2)
    save(
        fig,
        output / "07_surge_observed_admission.svg",
        "Historical Surge Mode evidence; NORMAL comparator unavailable",
        "A separate Class A Emergency workflow was admitted and completed; no same-workload NORMAL or Class B sample exists.",
    )


def plot_fault_timeline(output: Path, historical: dict[str, Any]) -> None:
    rabbit = historical["faults"]["rabbitmq_billing_appointment"]
    records = historical["faults"]["records_circuit_breaker"]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11.0, 6.0), gridspec_kw={"height_ratios": [1, 1]})

    broker_events = (
        (0, "Outbox row\ncreated", COLORS["blue"]),
        (8, "Published\non attempt 2", COLORS["orange"]),
        (10, "Appointment inbox\nprocessed once", COLORS["accepted"]),
    )
    ax1.hlines(0, 0, 10, color="#777777", linewidth=2)
    for seconds, label, color in broker_events:
        ax1.scatter([seconds], [0], color=color, s=80, zorder=3)
        ax1.annotate(label, (seconds, 0), xytext=(seconds, 0.28 if seconds != 8 else -0.4), ha="center", va="center", fontsize=9, arrowprops={"arrowstyle": "-", "color": color})
    ax1.set_xlim(-1, 11)
    ax1.set_ylim(-0.7, 0.65)
    ax1.set_yticks([])
    ax1.set_xticks([0, 2, 4, 6, 8, 10])
    ax1.set_xlabel("Seconds from Billing outbox creation (Phase 6, 2026-10-12)")
    ax1.set_title("RabbitMQ outage and resumed delivery")
    ax1.grid(axis="x", alpha=0.2)
    ax1.text(0.99, 0.91, f"{rabbit['matching_inbox_rows_after_recovery']} matching inbox row", transform=ax1.transAxes, ha="right", fontsize=8, color=COLORS["gray"])

    recovery_seconds = records["seconds_from_records_restart_to_reconciliation_success"]
    ax2.hlines(0, 0, recovery_seconds, color="#777777", linewidth=2)
    ax2.scatter([0, recovery_seconds], [0, 0], color=[COLORS["orange"], COLORS["accepted"]], s=80, zorder=3)
    ax2.annotate("Records service restarted", (0, 0), xytext=(0, 0.3), ha="left", fontsize=9, arrowprops={"arrowstyle": "-", "color": COLORS["orange"]})
    ax2.annotate("Reconciliation succeeded; breaker closed", (recovery_seconds, 0), xytext=(recovery_seconds, -0.35), ha="right", fontsize=9, arrowprops={"arrowstyle": "-", "color": COLORS["accepted"]})
    ax2.set_xlim(-0.5, recovery_seconds + 0.5)
    ax2.set_ylim(-0.65, 0.65)
    ax2.set_yticks([])
    ax2.set_xticks([0, 2, 4, 6])
    ax2.set_xlabel("Seconds from Records service restart (separate Phase 6 scenario)")
    ax2.set_title(f"Records breaker: 3 logical failures opened it; OPEN request returned in {records['open_request_latency_ms']} ms")
    ax2.grid(axis="x", alpha=0.2)
    save(fig, output / "08_fault_recovery_timeline.svg", "Recorded Phase 6 fault and recovery sequences")


def plot_resources(output: Path, run_dir: Path) -> None:
    l1 = read_json(run_dir / "summaries/l1-c4-t1.json")
    resources = l1["resource_summary"]
    names = [name.replace("pulsegrid-", "").replace("-1", "") for name in resources]
    memory = [float(resources[name]["memory_percent_max"]) for name in resources]
    cpu = [float(resources[name]["cpu_percent_max"]) for name in resources]
    order = sorted(range(len(names)), key=lambda i: memory[i], reverse=True)
    names = [names[i] for i in order]
    memory = [memory[i] for i in order]
    cpu = [cpu[i] for i in order]
    tempo = read_csv(run_dir / "tempo/stability_samples.csv")
    elapsed = [float(row["elapsed_seconds"]) for row in tempo]
    tempo_memory = [float(row["memory_percent"]) for row in tempo]

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12.0, 10.0), gridspec_kw={"height_ratios": [1.1, 0.9, 1.0]})
    y = list(range(len(names)))
    ax1.barh(y, memory, color=[COLORS["orange"] if value >= 90 else COLORS["blue"] for value in memory])
    ax1.axvline(90, color=COLORS["rejected"], linestyle="--", linewidth=1.5, label="90% stop threshold")
    ax1.set_yticks(y, names)
    ax1.invert_yaxis()
    ax1.set_xlim(0, 105)
    ax1.set_xlabel("Peak of sampled container memory limit (%)")
    ax1.set_title("Phase 8 C=4 trial: 16 Docker stats samples per container")
    ax1.grid(axis="x", alpha=0.2)
    ax1.legend(frameon=False, loc="lower right")

    ax2.barh(y, cpu, color=COLORS["purple"])
    ax2.set_yticks(y, names)
    ax2.invert_yaxis()
    ax2.set_xlabel("Peak Docker stats CPU (%)")
    ax2.set_title("CPU peak during the same single trial")
    ax2.grid(axis="x", alpha=0.2)

    ax3.plot(elapsed, tempo_memory, marker="o", markersize=3, linewidth=1.5, color=COLORS["blue"])
    ax3.axhline(90, color=COLORS["rejected"], linestyle="--", linewidth=1.5, label="90% load stop threshold")
    ax3.set_ylim(0, 100)
    ax3.set_xlabel("Elapsed seconds in 120-second idle observation (effective sample interval ~3.18 s)")
    ax3.set_ylabel("Tempo memory limit used (%)")
    ax3.set_title("Tempo idle stability observation; restart count increased by one")
    ax3.grid(True, alpha=0.2)
    ax3.legend(frameon=False)
    save(
        fig,
        output / "09_phase8_resources.svg",
        "Measured local container resource use",
        "Docker-reported CPU and memory for local capped containers; not host capacity or cloud sizing.",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=DEFAULT_RUN)
    args = parser.parse_args()
    run_dir = ROOT / "experiments/phase8/results" / args.run_id
    output = run_dir / "graphs"
    output.mkdir(parents=True, exist_ok=True)

    limiter_rows = load_rate_limiter_rows()
    historical = read_json(run_dir / "summaries/historical_phase6.json")
    plot_limiter_throughput(output, limiter_rows)
    plot_latency(output, limiter_rows, run_dir)
    plot_rejections(output, limiter_rows, run_dir)
    plot_cache(output)
    plot_hash_movement(output)
    plot_surge(output, historical)
    plot_fault_timeline(output, historical)
    plot_resources(output, run_dir)
    normalize_svg_whitespace(output)

    manifest = {
        "run_id": args.run_id,
        "generated_from": [
            "experiments/phase4/rate_limiter/results/redis7-{low,medium,high}/summary.csv",
            "experiments/phase4/key_value_cache/results/{low,medium,high}-final/summary.csv",
            "experiments/phase4/consistent_hashing/results/high-404/movement.csv",
            f"experiments/phase8/results/{args.run_id}/summaries/l1-c4-t1.json",
            f"experiments/phase8/results/{args.run_id}/tempo/stability_samples.csv",
            f"experiments/phase8/results/{args.run_id}/summaries/historical_phase6.json",
        ],
        "graphs": {
            "1": {"file": "01_phase4_admission_throughput.svg", "status": "generated", "scope": "Phase 4 rate-limiter component; not hospital HTTP throughput"},
            "2": {"file": "02_latency_by_condition.svg", "status": "generated", "scope": "Phase 4 admission component plus one Phase 8 C=4 HTTP trial; no HTTP concurrency curve"},
            "3": {"file": "03_admission_outcomes.svg", "status": "generated", "scope": "Phase 4 component outcomes plus one distinct Phase 8 HTTP outcome"},
            "4": {"file": None, "status": "not_generated", "reason": "The one-upstream/two-upstream scaling matrix did not run after the memory guardrail stopped L1."},
            "5": {"file": "05_cache_warm_vs_uncached.svg", "status": "generated", "scope": "Phase 4.3 PostgreSQL/Redis adapter trials; not authenticated HTTP"},
            "6": {"file": "06_hash_remapping.svg", "status": "generated", "scope": "One million synthetic keys, three seeds, node transition 3 to 4"},
            "7": {"file": "07_surge_observed_admission.svg", "status": "generated_with_gap", "scope": "Historical Class C SURGE burst only; same-workload NORMAL and Class B samples absent"},
            "8": {"file": "08_fault_recovery_timeline.svg", "status": "generated", "scope": "Historical Phase 6 RabbitMQ and Records recovery sequences"},
            "9": {"file": "09_phase8_resources.svg", "status": "generated", "scope": "One Phase 8 HTTP trial plus 120-second idle Tempo window"},
        },
        "historical_phase6_source_is_summary_transcription": True,
        "horizontal_scaling_efficiency": None,
    }
    (output / "plot_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest["graphs"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
