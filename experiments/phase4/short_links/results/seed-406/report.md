# Phase 4.5 short-link benchmark

Seed: `406`. Each level contains three independent 30-second measured trials per mode, with a 5-second warmup per mode. The baseline/proposed order alternates.

## Workloads and results

The baseline is the existing authenticated Phase 3 workflow GET. Proposed traffic is authenticated JSON alias resolution and creation at a 90/10 mix. The separate navigation result is a static, shape-checked 303 and performs no database read.

| Level | Trial | Baseline workflow p50/p95 ms | Alias resolve p50/p95 ms | Create p50/p95 ms | Baseline / resolve / create ops/s | Collisions | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| low (1,000, 1 clients) | 1 | 1.11/1.42 | 2.09/2.97 | 4.17/5.77 | 853.5 / 357.9 / 41.4 | 0 | 0 |
| low (1,000, 1 clients) | 2 | 1.11/1.45 | 2.10/2.91 | 4.17/5.65 | 846.9 / 362.9 / 40.0 | 0 | 0 |
| low (1,000, 1 clients) | 3 | 1.12/1.42 | 2.35/3.01 | 4.62/5.81 | 846.8 / 345.7 / 38.1 | 0 | 0 |
| medium (10,000, 8 clients) | 1 | 5.98/6.63 | 13.04/15.21 | 22.06/24.70 | 1322.6 / 512.2 / 55.9 | 0 | 0 |
| medium (10,000, 8 clients) | 2 | 6.07/6.74 | 13.08/15.47 | 22.02/24.84 | 1302.7 / 506.2 / 57.2 | 0 | 0 |
| medium (10,000, 8 clients) | 3 | 6.10/6.80 | 13.04/15.31 | 21.99/24.83 | 1297.2 / 503.2 / 59.6 | 0 | 0 |
| high (50,000, 32 clients) | 1 | 21.37/29.60 | 55.93/2024.85 | 60.95/2009.78 | 1417.7 / 95.5 / 10.7 | 0 | 155 |
| high (50,000, 32 clients) | 2 | 21.49/29.76 | 55.78/2001.91 | 61.19/127.66 | 1405.0 / 81.6 / 8.8 | 0 | 274 |
| high (50,000, 32 clients) | 3 | 21.70/31.72 | 54.93/2011.78 | 60.77/118.09 | 1376.6 / 101.2 / 10.5 | 0 | 182 |

## Environment and limits

- macOS-26.6.2-arm64-arm-64bit-Mach-O; 12 CPUs; 16 GiB RAM.
- Python 3.14.7; FastAPI 0.143.0; SQLAlchemy 2.0.54; psycopg 3.3.6; PostgreSQL 14.17 (Homebrew) on aarch64-apple-darwin24.2.0, compiled by Apple clang version 16.0.0 (clang-1600.0.26.6), 64-bit.
- Timing uses `perf_counter_ns`; measured calls use the same local PostgreSQL fixture and synthetic Appointment owner rows.
- Alias resolution latency includes the feature's direct route adapter, PostgreSQL digest/booking/hold reads, authorization adapter and audit read. Creation includes its repository writes and test command adapter.
- The test `stage_effect` is a no-op. Calls use in-process principals and direct route invocation; JWT middleware, ASGI/network, Traefik, coordinator migration 0010, production lock/effect adapters, and integrated audit/outbox write cost are not measured.
- Throughput is not a like-for-like ratio: the baseline workload is 100% workflow GET, while proposed traffic is a 90/10 resolution/create mix. Compare per-operation latency and report throughput alongside that mix.
- `summary.csv` separates successful latency percentiles from failed-operation percentiles; errors are not omitted from the raw samples.
- Random-alias collisions were zero in measured trials. Forced digest/unique-index collisions and retry bounds are covered by correctness tests.
- Other distribution-sensitivity seeds not included in this per-seed artifact: 404, 405.

## Navigation sample

Each level measured 1,000 static 303 responses. Per-level p50/p95/p99 and sample counts are in `summary.csv`.

See `manifest.json` for generation command, environment, input-spec and output SHA-256 values. Raw samples are gzip-compressed under `raw_samples/` locally and ignored by Git.
