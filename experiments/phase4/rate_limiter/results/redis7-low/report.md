# low component decisions

Measured three trials, seeds 404–406, 1 processes and 8 clients; 5s warmup and 30s measurement each backend/trial. See summary.csv for every outcome and latency including rejections. Baseline has no distributed quota guarantee. Redis adds network latency; no throughput superiority or production capacity claim. Rejection denominator accepted+limited; unavailable separate. Throughput completed/measurement_seconds. Latency percentiles use nearest rank. Queue delay is separate.

- baseline seed 404: 1496 completed, 1150 accepted, 346 limited, 0 unavailable; 49.87/s; p95 0.034 ms.
- redis seed 404: 1496 completed, 1150 accepted, 346 limited, 0 unavailable; 49.87/s; p95 5.644 ms.
- redis seed 405: 1496 completed, 1229 accepted, 267 limited, 0 unavailable; 49.87/s; p95 4.307 ms.
- baseline seed 405: 1496 completed, 1229 accepted, 267 limited, 0 unavailable; 49.87/s; p95 0.034 ms.
- baseline seed 406: 1496 completed, 1226 accepted, 270 limited, 0 unavailable; 49.87/s; p95 0.035 ms.
- redis seed 406: 1496 completed, 1226 accepted, 270 limited, 0 unavailable; 49.87/s; p95 3.244 ms.

Burst: [{"backend": "baseline", "attempted": 160, "accepted": 60, "theoretical_shared_bound": 60.06829915997514, "excess_shared_admissions": 0, "p95_ms": 0.0056249991757795215, "queue_p95_ms": 6.364000000758097}, {"backend": "redis", "attempted": 160, "accepted": 60, "theoretical_shared_bound": 60.34454792003089, "excess_shared_admissions": 0, "p95_ms": 6.98333399486728, "queue_p95_ms": 30.312334005429875}]

Disposable Redis cleanup passed. Hospital mounting/gateway/browser acceptance remains coordinator work.
