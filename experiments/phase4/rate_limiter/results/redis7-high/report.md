# high component decisions

Measured three trials, seeds 404–406, 4 processes and 128 clients; 5s warmup and 30s measurement each backend/trial. See summary.csv for every outcome and latency including rejections. Baseline has no distributed quota guarantee. Redis adds network latency; no throughput superiority or production capacity claim. Rejection denominator accepted+limited; unavailable separate. Throughput completed/measurement_seconds. Latency percentiles use nearest rank. Queue delay is separate.

- baseline seed 404: 23936 completed, 15086 accepted, 8850 limited, 0 unavailable; 797.87/s; p95 0.028 ms.
- redis seed 404: 23936 completed, 9151 accepted, 14785 limited, 0 unavailable; 797.87/s; p95 16.580 ms.
- redis seed 405: 23936 completed, 9101 accepted, 14835 limited, 0 unavailable; 797.87/s; p95 17.294 ms.
- baseline seed 405: 23936 completed, 15019 accepted, 8917 limited, 0 unavailable; 797.87/s; p95 0.023 ms.
- baseline seed 406: 23936 completed, 15087 accepted, 8849 limited, 0 unavailable; 797.87/s; p95 0.023 ms.
- redis seed 406: 23936 completed, 9065 accepted, 14871 limited, 0 unavailable; 797.87/s; p95 16.073 ms.

Burst: [{"backend": "baseline", "attempted": 160, "accepted": 160, "theoretical_shared_bound": 60.076172499975655, "excess_shared_admissions": 100, "p95_ms": 0.006416987162083387, "queue_p95_ms": 7.080459006829187}, {"backend": "redis", "attempted": 160, "accepted": 60, "theoretical_shared_bound": 60.289223750005476, "excess_shared_admissions": 0, "p95_ms": 5.602582998108119, "queue_p95_ms": 26.819041988346726}]

Disposable Redis cleanup passed. Hospital mounting/gateway/browser acceptance remains coordinator work.
