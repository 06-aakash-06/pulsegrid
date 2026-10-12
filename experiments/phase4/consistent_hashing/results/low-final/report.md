# low measured CPU-only run

Keys: 10,000; seeds 404–406. Three trials; 100,000 timed calls per timing case, 10,000 warmup calls.

No Redis, DB or hospital API integration measured. Latency surrounds complete locate including SHA256. Throughput includes timers, loop scheduling and thread pool creation; serialization/network/DB are not part of this pure algorithm. Closed-loop threads share immutable snapshots; GIL scheduling can raise tail latency and does not establish parallel CPU scaling. No fixed arrival target applies.

| Algorithm/vnodes | 3→4 remap range % | one-reader throughput range /s | one-reader p95 range ns |
|---|---:|---:|---:|
| modulo/0 | 74.750–75.130 | 1163867–1189484 | 833–875 |
| ring/32 | 22.580–22.780 | 1045681–1053986 | 958–959 |
| ring/128 | 24.900–25.410 | 996850–1000131 | 1000–1042 |
| ring/512 | 25.920–26.180 | 931863–945653 | 1042–1084 |

distribution.csv reports per-node key and hot-access counts/shares, max/mean and population coefficient of variation; movement.csv uses changed logical owner/total. build.csv estimates retained ring allocation (excludes allocator overhead/build peak and snapshot metadata), with process peak RSS separately in manifest. Raw datasets/traces/timing samples are ignored within this exclusive experiment path; their hashes/sizes allow regeneration and verification. Timing hashes vary on reruns. Charts show every trial, not a selected best run. Uniform key balance does not guarantee hot-access balance.

ring/32 compared to modulo (same-seed one-reader trials):
- Seed 404: throughput baseline/proposed=1.117, proposed−baseline=-123147/s; mean latency baseline/proposed=0.884, proposed−baseline=97.5ns.
- Seed 405: throughput baseline/proposed=1.138, proposed−baseline=-143803/s; mean latency baseline/proposed=0.856, proposed−baseline=122.3ns.
- Seed 406: throughput baseline/proposed=1.106, proposed−baseline=-111313/s; mean latency baseline/proposed=0.881, proposed−baseline=100.7ns.

ring/128 compared to modulo (same-seed one-reader trials):
- Seed 404: throughput baseline/proposed=1.178, proposed−baseline=-177783/s; mean latency baseline/proposed=0.838, proposed−baseline=144.7ns.
- Seed 405: throughput baseline/proposed=1.189, proposed−baseline=-189353/s; mean latency baseline/proposed=0.820, proposed−baseline=160.0ns.
- Seed 406: throughput baseline/proposed=1.168, proposed−baseline=-167017/s; mean latency baseline/proposed=0.836, proposed−baseline=146.5ns.

ring/512 compared to modulo (same-seed one-reader trials):
- Seed 404: throughput baseline/proposed=1.246, proposed−baseline=-232310/s; mean latency baseline/proposed=0.791, proposed−baseline=197.5ns.
- Seed 405: throughput baseline/proposed=1.258, proposed−baseline=-243830/s; mean latency baseline/proposed=0.769, proposed−baseline=219.1ns.
- Seed 406: throughput baseline/proposed=1.249, proposed−baseline=-232003/s; mean latency baseline/proposed=0.778, proposed−baseline=212.8ns.
