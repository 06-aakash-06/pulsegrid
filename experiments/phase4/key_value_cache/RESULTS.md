# Phase 4.3 measured evidence

All rows measure the unmounted Doctor projection adapter plus real owner PostgreSQL/Redis, not authenticated HTTP or final owner wire reconstruction. Placement is a two-node modulo harness, not Agent2 ring.

Full diagnostic:5s warmup/30s measurement, primary-key-only fixture. Indexed sensitivity:0.2s/3s, existing Doctor query secondary indexes. Each uses three trials (seeds404/405/406). Neither completes the frozen integrated endpoint gate.

## Full-duration unindexed diagnostics

| Level | Scenario | Mean ms | p95 ms | Reads/s | Hit ratio |
|---|---|---:|---:|---:|---:|
| low | uncached | 1.527 | 1.791 | 673.2 | n/a |
| low | cold | 2.277 | 2.898 | 352.5 | 0.00% |
| low | warm | 0.630 | 0.848 | 1571.7 | 99.98% |
| low | invalidation | 0.656 | 0.888 | 1511.9 | 98.70% |
| low | redis_failure | 0.650 | 0.824 | 1522.4 | 99.98% |
| medium | uncached | 41.376 | 49.694 | 193.3 | n/a |
| medium | cold | 33.866 | 49.045 | 218.5 | 13.61% |
| medium | warm | 3.325 | 4.031 | 2402.8 | 99.97% |
| medium | invalidation | 3.845 | 4.381 | 2077.7 | 98.16% |
| medium | redis_failure | 3.664 | 4.428 | 2179.7 | 99.97% |
| high | uncached | 1032.664 | 1222.687 | 30.8 | n/a |
| high | cold | 892.212 | 1186.218 | 35.4 | 10.07% |
| high | warm | 14.622 | 18.670 | 2191.7 | 99.92% |
| high | invalidation | 456.455 | 1215.246 | 69.7 | 58.16% |
| high | redis_failure | 15.622 | 17.083 | 2047.3 | 99.91% |

## Short existing-index sensitivity

| Level | Scenario | Mean ms | p95 ms | Reads/s | Hit ratio |
|---|---|---:|---:|---:|---:|
| low | uncached | 1.543 | 1.909 | 644.4 | n/a |
| low | cold | 2.412 | 3.023 | 329.5 | 0.00% |
| low | warm | 0.652 | 0.852 | 1516.8 | 100.00% |
| low | invalidation | 0.674 | 0.909 | 1465.5 | 98.86% |
| low | redis_failure | 1.974 | 1.007 | 504.5 | 100.00% |
| medium | uncached | 6.600 | 8.682 | 1210.9 | n/a |
| medium | cold | 10.022 | 12.320 | 615.6 | 2.86% |
| medium | warm | 3.389 | 4.184 | 2357.5 | 100.00% |
| medium | invalidation | 3.464 | 4.224 | 2305.7 | 98.70% |
| medium | redis_failure | 9.364 | 61.350 | 853.9 | 100.00% |
| high | uncached | 59.857 | 92.768 | 532.4 | n/a |
| high | cold | 54.097 | 84.066 | 467.0 | 23.39% |
| high | warm | 13.314 | 14.854 | 2399.0 | 99.96% |
| high | invalidation | 15.019 | 16.703 | 2126.5 | 96.72% |
| high | redis_failure | 33.584 | 123.027 | 951.2 | 99.81% |

1,702,317 successful measured reads across90 final/sensitivity trials; zero measured read errors. Owned storage cleanup and post-outage Redis recovery checks passed. Superseded low smoke is excluded.

Tables average trial means/p95/throughput; hit ratio pools hit/miss counts. p95 is nearest-rank per trial, not a pooled percentile. Each source/hash/raw count and complete per-trial variation is retained. comparisons.csv gives ratios and absolute latency/query deltas matched by trial.

Every cache request still reads a PostgreSQL revision. Warm caching avoids expensive projection SQL but does not reduce total SQL query count versus the one-statement baseline; misses add a projection read. Redis failures are excluded from hit/(hit+miss) and recorded separately, including their p95/p99 latency.

Cold preparation deletes a key before each read; concurrent repopulation can yield hits. Cold throughput includes preparation, but latency/application DB counts exclude its extra revision read/delete. The hot-query share is50/80/95 percent over a ten-key working set, not an exact repeated-key probability. Two cache objects share one adapter process.

No real ring, authenticated endpoint, final Alembic revision triggers, fresh wire fields, Compose ACL/networking, browser or full hospital regressions were verified. These are coordinator-only integration gates; Phase4 acceptance remains incomplete. The initial final low cold trial overlapped roughly5s of local test activity.
