# Synthetic insurance crawler benchmark

This report uses only generated synthetic provider pages served on loopback. The persistence adapter is a disposable in-memory contract fake; PostgreSQL migration, locks, and production networking were not exercised.

## Trial results

| Level | Delay | Global slots | Seeds | Pages/s mean ± SD | Duration p50/p95/p99 (s) | Field accuracy | Duplicate % | Failure % | Retried pages | Rule P/R |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| high | 20 ms | 1 | 404,405,406 | 18.539 ± 0.149 | 15.733/15.953/15.953 | 100.00% | 10.24% | 2.33% | 45 | 100.00%/100.00% |
| high | 20 ms | 4 | 404,405,406 | 51.548 ± 0.641 | 5.657/5.765/5.765 | 100.00% | 10.24% | 2.33% | 45 | 100.00%/100.00% |
| high | 20 ms | 8 | 404,405,406 | 52.376 ± 0.109 | 5.596/5.605/5.605 | 100.00% | 10.24% | 2.33% | 45 | 100.00%/100.00% |
| high | 100 ms | 1 | 404,405,406 | 7.240 ± 0.032 | 40.374/40.674/40.674 | 100.00% | 10.24% | 2.33% | 45 | 100.00%/100.00% |
| high | 100 ms | 4 | 404,405,406 | 23.794 ± 4.038 | 11.224/15.315/15.315 | 100.00% | 10.24% | 2.33% | 45 | 100.00%/100.00% |
| low | 20 ms | 1 | 404,405,406 | 28.089 ± 0.285 | 0.358/0.358/0.358 | 100.00% | 10.00% | 0.00% | 3 | 100.00%/100.00% |
| low | 20 ms | 4 | 404,405,406 | 57.101 ± 0.371 | 0.176/0.176/0.176 | 100.00% | 10.00% | 0.00% | 3 | 100.00%/100.00% |
| low | 20 ms | 8 | 404,405,406 | 55.802 ± 0.112 | 0.179/0.180/0.180 | 100.00% | 10.00% | 0.00% | 3 | 100.00%/100.00% |
| medium | 20 ms | 1 | 404,405,406 | 20.089 ± 0.007 | 4.878/4.880/4.880 | 100.00% | 10.20% | 2.00% | 15 | 100.00%/100.00% |
| medium | 20 ms | 4 | 404,405,406 | 56.726 ± 0.031 | 1.727/1.729/1.729 | 100.00% | 10.20% | 2.00% | 15 | 100.00%/100.00% |
| medium | 20 ms | 8 | 404,405,406 | 57.077 ± 0.237 | 1.714/1.725/1.725 | 100.00% | 10.20% | 2.00% | 15 | 100.00%/100.00% |

## Sequential versus bounded concurrency

Speedup is the paired seed ratio of sequential duration divided by the bounded run duration. Duration difference is sequential minus bounded. No threshold is treated as an acceptance target.

| Level | Delay | Compared slots | Paired duration speedup mean ± SD | Duration saved seconds mean ± SD | Throughput delta pages/s mean ± SD |
|---|---:|---:|---:|---:|---:|
| high | 20 ms | 1 → 4 | 2.781 ± 0.052× | 10.121 ± 0.182 | 33.010 ± 0.746 |
| high | 20 ms | 1 → 8 | 2.825 ± 0.018× | 10.211 ± 0.119 | 33.838 ± 0.091 |
| high | 100 ms | 1 → 4 | 3.285 ± 0.545× | 27.888 ± 2.190 | 16.554 ± 4.006 |
| low | 20 ms | 1 → 4 | 2.033 ± 0.008× | 0.181 ± 0.003 | 29.013 ± 0.112 |
| low | 20 ms | 1 → 8 | 1.987 ± 0.019× | 0.177 ± 0.003 | 27.714 ± 0.269 |
| medium | 20 ms | 1 → 4 | 2.824 ± 0.002× | 3.151 ± 0.002 | 36.637 ± 0.032 |
| medium | 20 ms | 1 → 8 | 2.841 ± 0.013× | 3.161 ± 0.009 | 36.988 ± 0.242 |

## Interpretation limits

- Concurrency 8 is an experiment setting; the deployment default remains 4, and per-host concurrency remains 2.
- Invalid pages are reported as rejected and excluded from field accuracy. Timed-out pages have no extracted field denominator and remain in the failure denominator.
- Duplicate percentage is duplicate content pages divided by successfully processed unique URLs. Failure percentage is failed unique page requests divided by attempted unique page requests. HTTP retries do not inflate either denominator.
- Fixture delay, loopback server behavior, Python scheduling, and in-memory repository timings are local measurements. They do not establish production crawl capacity or PostgreSQL transaction performance.
