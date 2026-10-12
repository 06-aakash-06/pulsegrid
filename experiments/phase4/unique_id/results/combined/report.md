# Final measured comparison

Three trials per mode/level. Closed-loop single-process asyncio, real loopback PostgreSQL 14. Pipeline includes allocator and INSERT; allocation latency includes ownership/committed range checks. No hospital endpoints mounted.

| Level | Mode | IDs/s range | Pipeline p95 us range | Generation p95 us range | Measured IDs | Collisions |
|---|---|---|---|---|---|---|
| low | csprng | 6045.5–12438.0 | 121.6–167.9 | 4.5–4.7 | 300000 | 0 |
| low | sequence | 3270.6–7835.8 | 209.1–306.5 | 105.1–142.6 | 300000 | 0 |
| low | snowflake | 2805.5–5586.8 | 296.7–363.8 | 173.8–200.7 | 300000 | 0 |
| medium | csprng | 16501.1–22085.6 | 453.2–621.2 | 2.7–3.1 | 1200000 | 0 |
| medium | sequence | 7703.2–14488.8 | 649.8–1411.2 | 329.8–662.7 | 1200000 | 0 |
| medium | snowflake | 10449.0–10849.3 | 881.7–977.5 | 558.3–621.9 | 1200000 | 0 |
| high | csprng | 17322.1–27369.5 | 1379.5–3913.6 | 2.2–4.1 | 3000000 | 0 |
| high | sequence | 13552.4–13658.4 | 3002.6–3514.0 | 1512.0–1717.0 | 3000000 | 0 |
| high | snowflake | 5485.4–10792.5 | 4288.5–18667.2 | 2664.8–7639.3 | 3000000 | 0 |

low: mean CSPRNG/Snowflake throughput ratio 2.136; absolute mean difference 4388.8 IDs/s.

medium: mean CSPRNG/Snowflake throughput ratio 1.806; absolute mean difference 8560.2 IDs/s.

high: mean CSPRNG/Snowflake throughput ratio 2.368; absolute mean difference 12060.8 IDs/s.

Zero observed collisions is finite evidence, not a guarantee against legacy IDs or duplicate assignments across independent databases. Allocators use per-client temporary PK tables plus a whole-trial uniqueness set; sequence baseline is technical nextval, not Records API. PostgreSQL 16, multi-process performance and coordinator hospital integration remain unexecuted.
