# Autocomplete benchmark: medium

Dataset seed: `405`. Generated owner catalogs contain 10,000 entries each; the Doctor catalog includes active-doctor and specialty kinds, while the Pharmacy catalog contains active-medicine names only.

## Results

| Owner | Algorithm | Clients | Average ms | P95 ms | Lookups/s | Samples |
|---|---|---:|---:|---:|---:|---:|
| doctor | trie | 1 | 0.0112 | 0.0093 | 84374.8 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0105 | 0.0059 | 90478.8 | 100000 |
| doctor | python_scan_secondary | 1 | 5.0053 | 27.2204 | 199.7 | 1000 |
| doctor | trie | 1 | 0.0130 | 0.0093 | 72265.5 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0082 | 0.0046 | 106033.9 | 100000 |
| doctor | trie | 8 | 0.0236 | 0.0103 | 172310.0 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0139 | 0.0041 | 340201.5 | 100000 |
| doctor | trie | 8 | 0.0146 | 0.0095 | 235161.5 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0214 | 0.0079 | 276477.5 | 100000 |
| doctor | trie | 32 | 0.0151 | 0.0097 | 218038.8 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0100 | 0.0059 | 281125.4 | 100000 |
| doctor | trie | 32 | 0.0157 | 0.0095 | 231743.6 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0156 | 0.0081 | 253689.8 | 100000 |
| doctor | trie | 1 | 0.0122 | 0.0089 | 76713.2 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0081 | 0.0057 | 113220.1 | 100000 |
| doctor | python_scan_secondary | 1 | 4.3539 | 27.3429 | 229.6 | 1000 |
| doctor | trie | 1 | 0.0116 | 0.0083 | 83764.9 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0078 | 0.0078 | 117931.5 | 100000 |
| doctor | trie | 8 | 0.0171 | 0.0106 | 196817.2 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0241 | 0.0060 | 246097.0 | 100000 |
| doctor | trie | 8 | 0.0125 | 0.0052 | 285344.9 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0113 | 0.0041 | 346047.2 | 100000 |
| doctor | trie | 32 | 0.0094 | 0.0047 | 320256.7 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0086 | 0.0031 | 376891.6 | 100000 |
| doctor | trie | 32 | 0.0122 | 0.0051 | 303145.8 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0087 | 0.0041 | 330231.7 | 100000 |
| doctor | trie | 1 | 0.0028 | 0.0047 | 331659.9 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0023 | 0.0031 | 399424.0 | 100000 |
| doctor | python_scan_secondary | 1 | 1.2281 | 2.6440 | 813.8 | 1000 |
| doctor | trie | 1 | 0.0029 | 0.0051 | 320085.1 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0026 | 0.0041 | 351273.3 | 100000 |
| doctor | trie | 8 | 0.0112 | 0.0047 | 324783.9 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0084 | 0.0031 | 391299.0 | 100000 |
| doctor | trie | 8 | 0.0123 | 0.0051 | 310285.2 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0095 | 0.0041 | 345511.3 | 100000 |
| doctor | trie | 32 | 0.0072 | 0.0047 | 319015.3 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0063 | 0.0031 | 379843.5 | 100000 |
| doctor | trie | 32 | 0.0094 | 0.0051 | 304208.7 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0082 | 0.0041 | 334963.5 | 100000 |
| pharmacy | trie | 1 | 0.0025 | 0.0040 | 364512.7 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0025 | 0.0032 | 368795.3 | 100000 |
| pharmacy | python_scan_secondary | 1 | 1.0549 | 1.4195 | 947.4 | 1000 |
| pharmacy | trie | 1 | 0.0030 | 0.0045 | 304442.9 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0031 | 0.0043 | 300725.3 | 100000 |
| pharmacy | trie | 8 | 0.0097 | 0.0070 | 296819.7 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0103 | 0.0032 | 364856.6 | 100000 |
| pharmacy | trie | 8 | 0.0090 | 0.0043 | 345091.4 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0126 | 0.0043 | 301310.2 | 100000 |
| pharmacy | trie | 32 | 0.0114 | 0.0040 | 321523.9 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0100 | 0.0037 | 302121.6 | 100000 |
| pharmacy | trie | 32 | 0.0098 | 0.0044 | 335192.6 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0097 | 0.0043 | 295277.9 | 100000 |
| pharmacy | trie | 1 | 0.0024 | 0.0040 | 378294.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0025 | 0.0032 | 366850.1 | 100000 |
| pharmacy | python_scan_secondary | 1 | 1.0469 | 1.4325 | 954.6 | 1000 |
| pharmacy | trie | 1 | 0.0026 | 0.0044 | 356629.4 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0030 | 0.0043 | 310497.5 | 100000 |
| pharmacy | trie | 8 | 0.0102 | 0.0040 | 369035.2 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0127 | 0.0032 | 364774.0 | 100000 |
| pharmacy | trie | 8 | 0.0104 | 0.0044 | 346938.9 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0154 | 0.0043 | 299022.6 | 100000 |
| pharmacy | trie | 32 | 0.0061 | 0.0040 | 354517.5 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0081 | 0.0033 | 334626.2 | 100000 |
| pharmacy | trie | 32 | 0.0101 | 0.0045 | 294212.5 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0170 | 0.0085 | 211972.8 | 100000 |
| pharmacy | trie | 1 | 0.0028 | 0.0042 | 333532.9 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0026 | 0.0033 | 357028.0 | 100000 |
| pharmacy | python_scan_secondary | 1 | 1.1693 | 1.4699 | 854.7 | 1000 |
| pharmacy | trie | 1 | 0.0081 | 0.0096 | 113593.6 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0068 | 0.0084 | 130514.9 | 100000 |
| pharmacy | trie | 8 | 0.0088 | 0.0040 | 372998.0 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0126 | 0.0032 | 358366.1 | 100000 |
| pharmacy | trie | 8 | 0.0163 | 0.0045 | 295266.0 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0141 | 0.0043 | 299555.3 | 100000 |
| pharmacy | trie | 32 | 0.0077 | 0.0040 | 367825.2 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0091 | 0.0033 | 326613.8 | 100000 |
| pharmacy | trie | 32 | 0.0094 | 0.0044 | 325777.6 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0117 | 0.0043 | 291259.3 | 100000 |

## Index construction and memory

See `build.csv` for trie nodes, estimated retained object bytes, sorted-baseline estimated bytes, construction time, separately traced build-allocation peak, and observed process peak RSS. Trie bytes are an approximate Python object-size estimate; RSS and tracemalloc are separate measurements.

Default 64 MiB index-cap preflight: doctor=within limit, pharmacy=within limit. The timed high-cap trie uses a recorded 512 MiB experimental cap so 100k-entry cases can be measured; the deployed default remains 64 MiB.

## Correctness and scope

Trie and sorted-prefix outputs were checked for exact ordered top-K equality against the independent full string-scan oracle for each generated hot and missing prefix, at limits 10 and 20. `correctness.csv` contains the per-prefix oracle counts.

The primary baseline is an in-memory sorted string-prefix range that models the ordering behavior of a PostgreSQL prefix index. The full Python string scan is the correctness oracle and is also measured as a bounded secondary CPU baseline; its operation cap is reported because its O(n) cost grows with catalog size. This is a CPU-only algorithm benchmark: it does not include authenticated HTTP, PostgreSQL revision reads, selected-ID validation, or network latency, because the coordinator owns route mounting and migration integration.

Measurements use `perf_counter_ns`, 1,000 warmup calls per owner/algorithm/client/result-limit configuration, and closed-loop thread clients. Trie and sorted baseline each receive at least 100,000 timed operations per trial for limits 10 and 20. Tracemalloc runs in a separate build pass and is disabled during timed lookups. Throughput is completed lookups divided by wall time. P95 uses nearest-rank `ceil(0.95*n)-1`; no endpoint or service-level speedup is claimed.

Catalog SHA256: `d99a1e686d27e1e9d12c014a3d633a2a690951e8a34ea4a816977574405fa200`.
