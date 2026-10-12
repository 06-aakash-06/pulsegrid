# Autocomplete synthetic benchmark

`run.py` compares the immutable radix trie with a sorted string-prefix range
(the CPU model of an indexed PostgreSQL prefix query) and a bounded full Python
scan. The scan is the correctness oracle and is also timed as a secondary
baseline with its sample cap disclosed. The primary trie and sorted-baseline
measurements each run at least 100,000 timed lookups per configuration/trial.

Catalog levels contain 1,000, 10,000, or 100,000 entries **per owner**. Doctor
fixtures contain active doctor names plus a specialty vocabulary; Pharmacy
fixtures contain active medicine names only. The generator uses synthetic
labels, deterministic seed input, top-K limits 10 and 20, hot and missing
prefixes of normalized lengths 1, 3, and 8, and owner-specific kinds. Client
counts are 1, 8, and 32. Each operation times the complete pure lookup,
including normalization and top-K result construction. The script also records
trie node count, approximate Python object bytes, sorted-baseline estimated
bytes, build time, tracemalloc peak, process peak RSS, and exact ordered top-K
correctness against the full scan.

Default index admission is checked at 100,000 entries/64 MiB. Timed high-level
search uses a 512 MiB experimental memory cap so the trie comparison remains
observable if the default cap rejects a catalog; both caps are recorded. The
configured default is not changed by the benchmark.

Run the fixed-seed low, medium, and high levels separately from the repository
root. Each run uses three measured trials (seeded operation-order repeats) and
three client counts. Repeat with seeds 405 and 406 for distribution sensitivity.

```sh
python experiments/phase4/autocomplete/run.py --seed 404 --level low --output experiments/phase4/autocomplete/results/low-seed404
python experiments/phase4/autocomplete/run.py --seed 404 --level medium --output experiments/phase4/autocomplete/results/medium-seed404
python experiments/phase4/autocomplete/run.py --seed 404 --level high --output experiments/phase4/autocomplete/results/high-seed404
```

Each run emits `manifest.json`, `summary.csv`, `workload.csv`, `build.csv`,
`default_cap.csv`, `correctness.csv`, `report.md`, and `latency.svg`. The manifest
records the command, baseline and base commits, runtime/hardware, caps,
dataset/script/output SHA256 values, and whether exact correctness passed. No synthetic catalog or per-query raw
latency sample is retained. P95 uses nearest-rank `ceil(0.95*n)-1`; throughput
is completed lookups divided by measured wall time.

This is a CPU-only algorithm experiment. It does not measure authenticated HTTP,
PostgreSQL revision reads, selected-ID revalidation, DB fallback, or network
latency. Agent 7 cannot mount shared routes or create the coordinator-owned
Doctor/Pharmacy revision migrations. The integration benchmark must compare the
live existing PostgreSQL prefix baseline and mounted endpoint against the trie,
including revision and selected-ID validation overhead.
