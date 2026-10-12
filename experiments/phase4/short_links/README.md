# Short-link benchmark

This driver runs against a fresh, disposable local PostgreSQL cluster created
by the Appointment test fixture. It applies the current Appointment migrations,
adds only the owned `short_links` test table, seeds future synthetic bookings,
and removes the entire temporary database and cluster during fixture cleanup.
It does not touch the Compose database.

From the repository root, with the Appointment test dependencies available:

```sh
python experiments/phase4/short_links/run.py --seed 404 --level low --output /tmp/pulsegrid-short-links-low.json
```

Levels map to the frozen workloads: low is 1,000 aliases and 1 client, medium
is 10,000 aliases and 8 clients, and high is 50,000 aliases and 32 clients.
Each run seeds three equal datasets so the three 30-second trials use separate
rows. Warmup defaults to 5 seconds per mode and each trial alternates execution
order between the baseline and proposed adapter. Proposed traffic uses a 90/10
JSON-resolution/create mix. The runner also measures 1,000 static 303 responses.
Override durations only for a smoke run; report the chosen values.

The report JSON contains the environment, sample counts, attempted and completed
throughput, success/error p50/p95/p99, observed collision count and limitations.
A sibling `.samples.csv` holds status and latency only; it contains no IDs,
aliases, QR secrets or patient values. Repeat with seeds 405 and 406 to examine
fixture-distribution sensitivity. The report records the PostgreSQL version
reported by the disposable test cluster.

Package all three fixed-seed reports into the bounded results required by the
benchmark plan:

```sh
python experiments/phase4/short_links/collect_results.py \
  --output-dir experiments/phase4/short_links/results/seed-404 \
  low=/tmp/pulsegrid-short-links-low-404-fixed.json \
  medium=/tmp/pulsegrid-short-links-medium-404-fixed.json \
  high=/tmp/pulsegrid-short-links-high-404-fixed.json
```

This writes `manifest.json`, `summary.csv`, `report.md` and `latency.svg`.
Compressed raw samples are stored under the ignored `raw_samples/` directory.
For an optional failure-classification rerun, pass its `.samples.csv` path with
`--diagnostic-samples`; the collector reports only exception class counts.

## Interpretation

The baseline invokes the existing authenticated Phase 3 workflow GET route. The
proposed path invokes the owned authenticated JSON resolver and creation route.
Both use the same disposable PostgreSQL version and synthetic Appointment-owned rows. The fixture uses
in-process principals and direct route calls, and its test `stage_effect` port
does not write integration outbox effects. These results measure the component
adapter and repository behavior; they do not measure JWT middleware, ASGI/network,
Traefik, coordinator migration 0010, production locks, or integrated audit/outbox
cost. The coordinator must repeat this comparison after route mounting and its
real lock/effect ports are wired.
