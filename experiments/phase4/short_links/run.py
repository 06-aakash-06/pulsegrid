#!/usr/bin/env python3
"""Run the isolated PostgreSQL short-link adapter benchmark."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
SERVICE_ROOT = ROOT / "services" / "appointment"
TEST_FILE = SERVICE_ROOT / "tests" / "phase4_short_links" / "test_benchmark.py"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=404)
    parser.add_argument("--level", choices=("low", "medium", "high"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--warmup-seconds", type=float, default=5.0)
    parser.add_argument("--duration-seconds", type=float, default=30.0)
    args = parser.parse_args()
    if args.warmup_seconds < 0 or args.duration_seconds <= 0:
        parser.error("warmup must be nonnegative and duration must be positive")

    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment.update({
        "PULSEGRID_SHORT_LINKS_BENCH_LEVEL": args.level,
        "PULSEGRID_SHORT_LINKS_BENCH_SEED": str(args.seed),
        "PULSEGRID_SHORT_LINKS_BENCH_OUTPUT": str(output_path),
        "PULSEGRID_SHORT_LINKS_BENCH_WARMUP": str(args.warmup_seconds),
        "PULSEGRID_SHORT_LINKS_BENCH_DURATION": str(args.duration_seconds),
    })
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        str(TEST_FILE),
    ]
    result = subprocess.run(command, cwd=SERVICE_ROOT, env=environment, check=False)
    if result.returncode == 0:
        print(f"Benchmark report: {output_path}")
        print(f"Raw samples: {output_path.with_suffix('.samples.csv')}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
