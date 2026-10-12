# high measured CPU-only run

Keys: 1,000,000; seeds 404–406. Three trials; 100,000 timed calls per timing case, 10,000 warmup calls.

No Redis, DB or hospital API integration measured. Latency surrounds complete locate including SHA256. Throughput includes timers, loop scheduling and thread pool creation; serialization/network/DB are not part of this pure algorithm. Closed-loop threads share immutable snapshots; GIL scheduling can raise tail latency and does not establish parallel CPU scaling. No fixed arrival target applies.

| Algorithm/vnodes | 3→4 remap range % | one-reader throughput range /s | one-reader p95 range ns |
|---|---:|---:|---:|
| modulo/0 | 74.971–75.118 | 1163992–1185503 | 792–833 |
| ring/32 | 22.821–22.831 | 1020834–1028470 | 958–958 |
| ring/128 | 25.426–25.502 | 970847–984384 | 1000–1000 |
| ring/512 | 25.773–25.893 | 897231–941928 | 1041–1167 |

distribution.csv reports per-node key and hot-access counts/shares, max/mean and population coefficient of variation; movement.csv uses changed logical owner/total. build.csv estimates retained ring allocation (excludes allocator overhead/build peak and snapshot metadata), with process peak RSS separately in manifest. Raw datasets/traces/timing samples are ignored within this exclusive experiment path; their hashes/sizes allow regeneration and verification. Timing hashes vary on reruns. Charts show every trial, not a selected best run. Uniform key balance does not guarantee hot-access balance.

ring/32 compared to modulo (same-seed one-reader trials):
- Seed 404: throughput baseline/proposed=1.156, proposed−baseline=-160028/s; mean latency baseline/proposed=0.861, proposed−baseline=120.6ns.
- Seed 405: throughput baseline/proposed=1.140, proposed−baseline=-143158/s; mean latency baseline/proposed=0.860, proposed−baseline=122.0ns.
- Seed 406: throughput baseline/proposed=1.134, proposed−baseline=-137835/s; mean latency baseline/proposed=0.864, proposed−baseline=117.0ns.

ring/128 compared to modulo (same-seed one-reader trials):
- Seed 404: throughput baseline/proposed=1.221, proposed−baseline=-214656/s; mean latency baseline/proposed=0.820, proposed−baseline=163.3ns.
- Seed 405: throughput baseline/proposed=1.184, proposed−baseline=-180752/s; mean latency baseline/proposed=0.831, proposed−baseline=151.5ns.
- Seed 406: throughput baseline/proposed=1.185, proposed−baseline=-181921/s; mean latency baseline/proposed=0.825, proposed−baseline=158.0ns.

ring/512 compared to modulo (same-seed one-reader trials):
- Seed 404: throughput baseline/proposed=1.259, proposed−baseline=-243575/s; mean latency baseline/proposed=0.783, proposed−baseline=206.3ns.
- Seed 405: throughput baseline/proposed=1.279, proposed−baseline=-253598/s; mean latency baseline/proposed=0.762, proposed−baseline=233.5ns.
- Seed 406: throughput baseline/proposed=1.300, proposed−baseline=-269073/s; mean latency baseline/proposed=0.748, proposed−baseline=251.0ns.
