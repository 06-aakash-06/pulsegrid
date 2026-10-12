# low measured CPU-only run

Keys: 10,000; seeds 404–406. Three trials; 100,000 timed calls per timing case, 10,000 warmup calls.

No Redis, DB or hospital API integration measured. Latency surrounds complete locate including SHA256. Throughput includes timers, loop scheduling and thread pool creation; serialization/network/DB are not part of this pure algorithm. Closed-loop threads share immutable snapshots; GIL scheduling can raise tail latency and does not establish parallel CPU scaling. No fixed arrival target applies.

| Algorithm/vnodes | 3→4 remap range % | one-reader throughput range /s | one-reader p95 range ns |
|---|---:|---:|---:|
| modulo/0 | 74.750–75.130 | 1148129–1189262 | 792–834 |
| ring/32 | 22.580–22.780 | 996481–1032176 | 917–959 |
| ring/128 | 24.900–25.410 | 949383–967202 | 1000–1041 |
| ring/512 | 25.920–26.180 | 901952–919397 | 1083–1125 |

distribution.csv reports per-node key and hot-access counts/shares, max/mean and population coefficient of variation; movement.csv uses changed logical owner/total. build.csv estimates retained ring allocation (excludes allocator overhead/build peak and snapshot metadata), with process peak RSS separately in manifest. Raw datasets/traces/timing samples are ignored within this exclusive experiment path; their hashes/sizes allow regeneration and verification. Timing hashes vary on reruns. Charts show every trial, not a selected best run. Uniform key balance does not guarantee hot-access balance.

ring/32 compared to modulo (same-seed one-reader trials):
- Seed 404: throughput baseline/proposed=1.152, proposed−baseline=-157086/s; mean latency baseline/proposed=0.860, proposed−baseline=120.5ns.
- Seed 405: throughput baseline/proposed=1.137, proposed−baseline=-141414/s; mean latency baseline/proposed=0.859, proposed−baseline=121.4ns.
- Seed 406: throughput baseline/proposed=1.152, proposed−baseline=-151648/s; mean latency baseline/proposed=0.845, proposed−baseline=139.1ns.

ring/128 compared to modulo (same-seed one-reader trials):
- Seed 404: throughput baseline/proposed=1.230, proposed−baseline=-222059/s; mean latency baseline/proposed=0.805, proposed−baseline=179.2ns.
- Seed 405: throughput baseline/proposed=1.234, proposed−baseline=-221918/s; mean latency baseline/proposed=0.789, proposed−baseline=197.5ns.
- Seed 406: throughput baseline/proposed=1.206, proposed−baseline=-196336/s; mean latency baseline/proposed=0.807, proposed−baseline=180.6ns.

ring/512 compared to modulo (same-seed one-reader trials):
- Seed 404: throughput baseline/proposed=1.294, proposed−baseline=-269865/s; mean latency baseline/proposed=0.761, proposed−baseline=232.8ns.
- Seed 405: throughput baseline/proposed=1.299, proposed−baseline=-269349/s; mean latency baseline/proposed=0.742, proposed−baseline=257.5ns.
- Seed 406: throughput baseline/proposed=1.252, proposed−baseline=-230880/s; mean latency baseline/proposed=0.772, proposed−baseline=223.1ns.
