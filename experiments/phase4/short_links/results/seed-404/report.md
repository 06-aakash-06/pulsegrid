# Phase 4.5 short-link benchmark

Seed: `404`. Each level contains three independent 30-second measured trials per mode, with a 5-second warmup per mode. The baseline/proposed order alternates.

## Workloads and results

The baseline is the existing authenticated Phase 3 workflow GET. Proposed traffic is authenticated JSON alias resolution and creation at a 90/10 mix. The separate navigation result is a static, shape-checked 303 and performs no database read.

| Level | Trial | Baseline workflow p50/p95 ms | Alias resolve p50/p95 ms | Create p50/p95 ms | Baseline / resolve / create ops/s | Collisions | Errors |
|---|---:|---:|---:|---:|---:|---:|---:|
| low (1,000, 1 clients) | 1 | 1.18/1.72 | 2.51/3.61 | 4.90/7.01 | 765.9 / 314.7 / 34.7 | 0 | 0 |
| low (1,000, 1 clients) | 2 | 1.20/1.71 | 2.47/3.51 | 4.86/6.75 | 759.8 / 321.8 / 34.6 | 0 | 0 |
| low (1,000, 1 clients) | 3 | 1.17/1.58 | 2.18/3.05 | 4.44/5.80 | 793.4 / 352.2 / 39.7 | 0 | 0 |
| medium (10,000, 8 clients) | 1 | 6.01/7.12 | 13.06/15.23 | 22.11/24.88 | 1295.7 / 507.5 / 55.3 | 0 | 0 |
| medium (10,000, 8 clients) | 2 | 6.11/7.06 | 13.31/16.88 | 22.41/27.69 | 1285.2 / 481.1 / 55.2 | 0 | 0 |
| medium (10,000, 8 clients) | 3 | 6.01/6.81 | 13.78/80.64 | 23.27/141.49 | 1309.8 / 268.9 / 28.8 | 0 | 0 |
| high (50,000, 32 clients) | 1 | 22.67/33.01 | 58.02/1989.01 | 64.75/125.20 | 1330.3 / 116.3 / 12.9 | 0 | 184 |
| high (50,000, 32 clients) | 2 | 23.63/35.71 | 56.50/119.63 | 64.61/125.73 | 1256.3 / 174.8 / 20.3 | 0 | 143 |
| high (50,000, 32 clients) | 3 | 23.10/34.75 | 56.96/123.02 | 64.61/114.32 | 1289.7 / 132.6 / 16.3 | 0 | 192 |

## Environment and limits

- macOS-26.6.2-arm64-arm-64bit-Mach-O; 12 CPUs; 16 GiB RAM.
- Python 3.14.7; FastAPI 0.143.0; SQLAlchemy 2.0.54; psycopg 3.3.6; PostgreSQL 14.17 (Homebrew) on aarch64-apple-darwin24.2.0, compiled by Apple clang version 16.0.0 (clang-1600.0.26.6), 64-bit.
- Timing uses `perf_counter_ns`; measured calls use the same local PostgreSQL fixture and synthetic Appointment owner rows.
- Alias resolution latency includes the feature's direct route adapter, PostgreSQL digest/booking/hold reads, authorization adapter and audit read. Creation includes its repository writes and test command adapter.
- The test `stage_effect` is a no-op. Calls use in-process principals and direct route invocation; JWT middleware, ASGI/network, Traefik, coordinator migration 0010, production lock/effect adapters, and integrated audit/outbox write cost are not measured.
- Throughput is not a like-for-like ratio: the baseline workload is 100% workflow GET, while proposed traffic is a 90/10 resolution/create mix. Compare per-operation latency and report throughput alongside that mix.
- `summary.csv` separates successful latency percentiles from failed-operation percentiles; errors are not omitted from the raw samples.
- Random-alias collisions were zero in measured trials. Forced digest/unique-index collisions and retry bounds are covered by correctness tests.
- High-load measured proposed-operation errors were 184, 143, 192 across trials. A separate same-seed diagnostic run classified 488 exceptions as `TimeoutError`=488. The test fixture has a 20-connection pool, no overflow and a 2-second pool-acquisition timeout. This is consistent with pool pressure at 32 clients, but the diagnostic captured exception classes rather than the exception module, so the exact timeout source is not confirmed.
- Seeds 405 and 406 are distribution-sensitivity repeats and were not run in this artifact.

## Navigation sample

Each level measured 1,000 static 303 responses. Per-level p50/p95/p99 and sample counts are in `summary.csv`.

See `manifest.json` for generation command, environment, input-spec and output SHA-256 values. Raw samples are gzip-compressed under `raw_samples/` locally and ignored by Git.
