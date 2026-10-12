# Phase 4.5 short-link benchmark

Seed: `405`. Each level contains three independent 30-second measured trials per mode, with a 5-second warmup per mode. The baseline/proposed order alternates.

## Workloads and results

The baseline is the existing authenticated Phase 3 workflow GET. Proposed traffic is authenticated JSON alias resolution and creation at a 90/10 mix. The separate navigation result is a static, shape-checked 303 and performs no database read.

| Level | Trial | Baseline workflow p50/p95 ms | Alias resolve p50/p95 ms | Create p50/p95 ms | Baseline / resolve / create ops/s | Collisions | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| low (1,000, 1 clients) | 1 | 1.07/1.41 | 2.03/2.88 | 3.99/5.56 | 879.2 / 373.3 / 41.3 | 0 | 0 |
| low (1,000, 1 clients) | 2 | 1.09/1.39 | 2.02/2.82 | 3.99/5.53 | 871.3 / 377.8 / 42.4 | 0 | 0 |
| low (1,000, 1 clients) | 3 | 1.09/1.41 | 2.00/2.64 | 3.95/5.08 | 874.2 / 391.5 / 43.9 | 0 | 0 |
| medium (10,000, 8 clients) | 1 | 5.78/6.42 | 12.52/14.51 | 21.10/23.70 | 1364.9 / 532.9 / 58.3 | 0 | 0 |
| medium (10,000, 8 clients) | 2 | 5.85/6.51 | 12.52/14.56 | 21.18/23.75 | 1343.3 / 532.5 / 59.0 | 0 | 0 |
| medium (10,000, 8 clients) | 3 | 5.86/6.52 | 13.51/18.32 | 22.73/29.97 | 1347.0 / 469.5 / 53.6 | 0 | 0 |
| high (50,000, 32 clients) | 1 | 24.49/36.86 | 59.27/2022.99 | 66.81/223.40 | 1214.7 / 76.1 / 8.0 | 0 | 192 |
| high (50,000, 32 clients) | 2 | 23.85/31.73 | 58.95/2019.90 | 63.41/2010.00 | 1279.4 / 79.7 / 8.6 | 0 | 172 |
| high (50,000, 32 clients) | 3 | 23.82/32.05 | 58.86/2007.77 | 65.91/127.99 | 1274.8 / 79.5 / 8.3 | 0 | 269 |

## Environment and limits

- macOS-26.6.2-arm64-arm-64bit-Mach-O; 12 CPUs; 16 GiB RAM.
- Python 3.14.7; FastAPI 0.143.0; SQLAlchemy 2.0.54; psycopg 3.3.6; PostgreSQL 14.17 (Homebrew) on aarch64-apple-darwin24.2.0, compiled by Apple clang version 16.0.0 (clang-1600.0.26.6), 64-bit.
- Timing uses `perf_counter_ns`; measured calls use the same local PostgreSQL fixture and synthetic Appointment owner rows.
- Alias resolution latency includes the feature's direct route adapter, PostgreSQL digest/booking/hold reads, authorization adapter and audit read. Creation includes its repository writes and test command adapter.
- The test `stage_effect` is a no-op. Calls use in-process principals and direct route invocation; JWT middleware, ASGI/network, Traefik, coordinator migration 0010, production lock/effect adapters, and integrated audit/outbox write cost are not measured.
- Throughput is not a like-for-like ratio: the baseline workload is 100% workflow GET, while proposed traffic is a 90/10 resolution/create mix. Compare per-operation latency and report throughput alongside that mix.
- `summary.csv` separates successful latency percentiles from failed-operation percentiles; errors are not omitted from the raw samples.
- Random-alias collisions were zero in measured trials. Forced digest/unique-index collisions and retry bounds are covered by correctness tests.
- Other distribution-sensitivity seeds not included in this per-seed artifact: 404, 406.

## Navigation sample

Each level measured 1,000 static 303 responses. Per-level p50/p95/p99 and sample counts are in `summary.csv`.

See `manifest.json` for generation command, environment, input-spec and output SHA-256 values. Raw samples are gzip-compressed under `raw_samples/` locally and ignored by Git.
