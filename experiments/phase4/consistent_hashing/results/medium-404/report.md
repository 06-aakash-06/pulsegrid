# medium measured CPU-only run

Keys: 100,000; seeds 404–406. Three trials; 100,000 timed calls per timing case, 10,000 warmup calls.

No Redis, DB or hospital API integration measured. Latency surrounds complete locate including SHA256. Throughput includes timers, loop scheduling and thread pool creation; serialization/network/DB are not part of this pure algorithm. Closed-loop threads share immutable snapshots; GIL scheduling can raise tail latency and does not establish parallel CPU scaling. No fixed arrival target applies.

| Algorithm/vnodes | 3→4 remap range % | one-reader throughput range /s | one-reader p95 range ns |
|---|---:|---:|---:|
| modulo/0 | 74.886–75.063 | 1081634–1150877 | 834–834 |
| ring/32 | 22.707–22.813 | 898766–1003279 | 959–1083 |
| ring/128 | 25.234–25.640 | 583105–893537 | 1083–1167 |
| ring/512 | 25.816–25.984 | 784822–902708 | 1084–1708 |

distribution.csv reports per-node key and hot-access counts/shares, max/mean and population coefficient of variation; movement.csv uses changed logical owner/total. build.csv estimates retained ring allocation (excludes allocator overhead/build peak and snapshot metadata), with process peak RSS separately in manifest. Raw datasets/traces/timing samples are ignored within this exclusive experiment path; their hashes/sizes allow regeneration and verification. Timing hashes vary on reruns. Charts show every trial, not a selected best run. Uniform key balance does not guarantee hot-access balance.

ring/32 compared to modulo (same-seed one-reader trials):
- Seed 404: throughput baseline/proposed=1.139, proposed−baseline=-139849/s; mean latency baseline/proposed=0.875, proposed−baseline=110.0ns.
- Seed 405: throughput baseline/proposed=1.203, proposed−baseline=-182867/s; mean latency baseline/proposed=0.814, proposed−baseline=180.0ns.
- Seed 406: throughput baseline/proposed=1.245, proposed−baseline=-226337/s; mean latency baseline/proposed=0.795, proposed−baseline=193.9ns.

ring/128 compared to modulo (same-seed one-reader trials):
- Seed 404: throughput baseline/proposed=1.960, proposed−baseline=-560023/s; mean latency baseline/proposed=0.500, proposed−baseline=771.3ns.
- Seed 405: throughput baseline/proposed=1.251, proposed−baseline=-216901/s; mean latency baseline/proposed=0.774, proposed−baseline=231.0ns.
- Seed 406: throughput baseline/proposed=1.288, proposed−baseline=-257341/s; mean latency baseline/proposed=0.761, proposed−baseline=237.0ns.

ring/512 compared to modulo (same-seed one-reader trials):
- Seed 404: throughput baseline/proposed=1.457, proposed−baseline=-358306/s; mean latency baseline/proposed=0.682, proposed−baseline=358.9ns.
- Seed 405: throughput baseline/proposed=1.221, proposed−baseline=-195970/s; mean latency baseline/proposed=0.785, proposed−baseline=216.4ns.
- Seed 406: throughput baseline/proposed=1.275, proposed−baseline=-248169/s; mean latency baseline/proposed=0.763, proposed−baseline=234.6ns.
