#!/usr/bin/env python3
"""Validate retained finite benchmark evidence against raw hashes and counts."""
import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OWNED = Path(__file__).resolve().parent


def read_csv(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def main():
    runs = sorted((OWNED / "results").iterdir())
    assert runs, "no measured runs"
    for output in runs:
        manifest = json.loads((output / "manifest.json").read_text())
        for name, expected in manifest["output_sha256"].items():
            assert hashlib.sha256((output / name).read_bytes()).hexdigest() == expected, name
        for name, expected in manifest["raw_sha256"].items():
            path = ROOT / name
            assert path.resolve().is_relative_to(OWNED / "artifacts"), name
            assert path.stat().st_size == expected["bytes"], name
            assert hashlib.sha256(path.read_bytes()).hexdigest() == expected["sha256"], name
        summary = read_csv(output / "summary.csv")
        assert len(summary) == 36
        assert {int(r["seed"]) for r in summary} == set(manifest["seeds"])
        for row in summary:
            assert int(row["attempted"]) == int(row["completed"]) == 100000
            assert int(row["errors"]) == 0
            samples = sorted(json.loads((OWNED / "artifacts" / output.name / f"latency-{row['seed']}-{row['algorithm']}-{row['vnodes']}-{row['readers']}.json").read_text()))
            assert len(samples) == 100000
            for p in (50, 95, 99):
                assert int(row[f"p{p}_ns"]) == samples[math.ceil(p / 100 * len(samples)) - 1]
            assert math.isclose(float(row["average_ns"]), sum(samples) / len(samples))
            assert math.isclose(float(row["throughput"]), len(samples) / float(row["elapsed_seconds"]))
        distribution = read_csv(output / "distribution.csv")
        groups = {}
        for row in distribution:
            key = tuple(row[n] for n in ("seed", "algorithm", "vnodes", "nodes", "workload"))
            groups.setdefault(key, []).append(row)
        assert len(groups) == 96
        for rows in groups.values():
            total = int(rows[0]["total"])
            assert len(rows) == int(rows[0]["nodes"])
            assert sum(int(r["count"]) for r in rows) == total
            assert math.isclose(sum(float(r["share"]) for r in rows), 1.0)
            counts = [int(r["count"]) for r in rows]
            mean = total / len(rows)
            cv = math.sqrt(sum((c-mean)**2 for c in counts) / len(rows)) / mean
            assert math.isclose(float(rows[0]["max_mean"]), max(counts)/mean)
            assert math.isclose(float(rows[0]["cv"]), cv)
        movement = read_csv(output / "movement.csv")
        assert len(movement) == 36
        for row in movement:
            assert math.isclose(float(row["percent"]), 100 * int(row["changed_keys"]) / int(row["total"]))
        assert len(read_csv(output / "build.csv")) == 48
        print(f"{output.name}: hashes, 36 timing cases, 96 distribution groups, 36 transitions, 48 builds PASS")


if __name__ == "__main__":
    main()
