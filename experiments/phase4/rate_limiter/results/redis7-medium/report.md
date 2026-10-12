# medium component decisions

Measured three trials, seeds 404–406, 2 processes and 32 clients; 5s warmup and 30s measurement each backend/trial. See summary.csv for every outcome and latency including rejections. Baseline has no distributed quota guarantee. Redis adds network latency; no throughput superiority or production capacity claim. Rejection denominator accepted+limited; unavailable separate. Throughput completed/measurement_seconds. Latency percentiles use nearest rank. Queue delay is separate.

- baseline seed 404: 5984 completed, 4439 accepted, 1545 limited, 0 unavailable; 199.47/s; p95 0.038 ms.
- redis seed 404: 5984 completed, 3728 accepted, 2256 limited, 0 unavailable; 199.47/s; p95 6.725 ms.
- redis seed 405: 5984 completed, 3722 accepted, 2262 limited, 0 unavailable; 199.47/s; p95 7.592 ms.
- baseline seed 405: 5984 completed, 4507 accepted, 1477 limited, 0 unavailable; 199.47/s; p95 0.031 ms.
- baseline seed 406: 5984 completed, 4556 accepted, 1428 limited, 0 unavailable; 199.47/s; p95 0.034 ms.
- redis seed 406: 5984 completed, 3798 accepted, 2186 limited, 0 unavailable; 199.47/s; p95 7.722 ms.

Burst: [{"backend": "baseline", "attempted": 160, "accepted": 120, "theoretical_shared_bound": 60.06825874996139, "excess_shared_admissions": 60, "p95_ms": 0.006583999493159354, "queue_p95_ms": 6.3129159971140325}, {"backend": "redis", "attempted": 160, "accepted": 60, "theoretical_shared_bound": 60.3345404099673, "excess_shared_admissions": 0, "p95_ms": 6.870292010717094, "queue_p95_ms": 28.82991598744411}]

Disposable Redis cleanup passed. Hospital mounting/gateway/browser acceptance remains coordinator work.
