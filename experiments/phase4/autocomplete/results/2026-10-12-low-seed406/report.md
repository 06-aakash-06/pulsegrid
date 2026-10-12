# Autocomplete benchmark: low

Dataset seed: `406`. Generated owner catalogs contain 1,000 entries each; the Doctor catalog includes active-doctor and specialty kinds, while the Pharmacy catalog contains active-medicine names only.

## Results

| Owner | Algorithm | Clients | Average ms | P95 ms | Lookups/s | Samples |
|---|---|---:|---:|---:|---:|---:|
| doctor | trie | 1 | 0.0028 | 0.0046 | 333926.0 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0020 | 0.0028 | 455427.7 | 100000 |
| doctor | python_scan_secondary | 1 | 0.1187 | 0.2571 | 8398.7 | 10000 |
| doctor | trie | 1 | 0.0029 | 0.0051 | 316538.6 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0024 | 0.0038 | 389240.0 | 100000 |
| doctor | trie | 8 | 0.0099 | 0.0047 | 314768.6 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0062 | 0.0028 | 440064.0 | 100000 |
| doctor | trie | 8 | 0.0123 | 0.0052 | 282372.4 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0090 | 0.0038 | 380661.6 | 100000 |
| doctor | trie | 32 | 0.0071 | 0.0046 | 323197.8 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0054 | 0.0028 | 410643.0 | 100000 |
| doctor | trie | 32 | 0.0096 | 0.0051 | 292553.9 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0087 | 0.0038 | 362237.3 | 100000 |
| doctor | trie | 1 | 0.0028 | 0.0046 | 333306.3 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0020 | 0.0029 | 450947.2 | 100000 |
| doctor | python_scan_secondary | 1 | 0.1190 | 0.2582 | 8377.1 | 10000 |
| doctor | trie | 1 | 0.0029 | 0.0050 | 321297.4 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0024 | 0.0038 | 393491.8 | 100000 |
| doctor | trie | 8 | 0.0075 | 0.0047 | 326758.7 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0056 | 0.0029 | 431091.2 | 100000 |
| doctor | trie | 8 | 0.0142 | 0.0071 | 254515.6 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0084 | 0.0038 | 379077.6 | 100000 |
| doctor | trie | 32 | 0.0077 | 0.0046 | 318324.7 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0059 | 0.0028 | 426041.4 | 100000 |
| doctor | trie | 32 | 0.0102 | 0.0050 | 304450.4 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0057 | 0.0039 | 365545.3 | 100000 |
| doctor | trie | 1 | 0.0030 | 0.0047 | 311794.5 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0020 | 0.0029 | 456562.1 | 100000 |
| doctor | python_scan_secondary | 1 | 0.1193 | 0.2584 | 8355.3 | 10000 |
| doctor | trie | 1 | 0.0029 | 0.0052 | 318267.9 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0023 | 0.0038 | 396768.3 | 100000 |
| doctor | trie | 8 | 0.0125 | 0.0047 | 325969.2 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0073 | 0.0028 | 432739.6 | 100000 |
| doctor | trie | 8 | 0.0111 | 0.0051 | 306282.7 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0073 | 0.0038 | 377119.9 | 100000 |
| doctor | trie | 32 | 0.0081 | 0.0046 | 315525.3 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0060 | 0.0028 | 417186.0 | 100000 |
| doctor | trie | 32 | 0.0104 | 0.0050 | 302249.6 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0084 | 0.0038 | 368689.0 | 100000 |
| pharmacy | trie | 1 | 0.0024 | 0.0040 | 389180.2 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0021 | 0.0028 | 430547.9 | 100000 |
| pharmacy | python_scan_secondary | 1 | 0.0975 | 0.1411 | 10223.4 | 10000 |
| pharmacy | trie | 1 | 0.0025 | 0.0043 | 366054.9 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0027 | 0.0038 | 352514.2 | 100000 |
| pharmacy | trie | 8 | 0.0096 | 0.0039 | 379154.9 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0069 | 0.0028 | 418410.3 | 100000 |
| pharmacy | trie | 8 | 0.0094 | 0.0043 | 327048.1 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0124 | 0.0037 | 345095.8 | 100000 |
| pharmacy | trie | 32 | 0.0081 | 0.0039 | 364233.9 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0060 | 0.0028 | 406718.9 | 100000 |
| pharmacy | trie | 32 | 0.0084 | 0.0043 | 342196.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0102 | 0.0038 | 335450.4 | 100000 |
| pharmacy | trie | 1 | 0.0024 | 0.0039 | 390865.9 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0022 | 0.0028 | 427529.9 | 100000 |
| pharmacy | python_scan_secondary | 1 | 0.0970 | 0.1395 | 10280.9 | 10000 |
| pharmacy | trie | 1 | 0.0026 | 0.0043 | 362079.4 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0026 | 0.0038 | 355495.3 | 100000 |
| pharmacy | trie | 8 | 0.0086 | 0.0039 | 380196.6 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0062 | 0.0028 | 418574.2 | 100000 |
| pharmacy | trie | 8 | 0.0103 | 0.0043 | 352056.9 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0127 | 0.0037 | 347027.6 | 100000 |
| pharmacy | trie | 32 | 0.0069 | 0.0039 | 375042.5 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0058 | 0.0028 | 407221.5 | 100000 |
| pharmacy | trie | 32 | 0.0075 | 0.0043 | 339755.5 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0106 | 0.0037 | 337481.3 | 100000 |
| pharmacy | trie | 1 | 0.0024 | 0.0039 | 393183.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0022 | 0.0028 | 425905.8 | 100000 |
| pharmacy | python_scan_secondary | 1 | 0.0997 | 0.1412 | 10000.7 | 10000 |
| pharmacy | trie | 1 | 0.0026 | 0.0043 | 361631.7 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0026 | 0.0038 | 354382.5 | 100000 |
| pharmacy | trie | 8 | 0.0076 | 0.0039 | 379033.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0101 | 0.0028 | 419082.2 | 100000 |
| pharmacy | trie | 8 | 0.0089 | 0.0043 | 352686.9 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0089 | 0.0037 | 345601.9 | 100000 |
| pharmacy | trie | 32 | 0.0054 | 0.0039 | 374144.6 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0059 | 0.0028 | 408035.4 | 100000 |
| pharmacy | trie | 32 | 0.0071 | 0.0043 | 344427.1 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0094 | 0.0038 | 309009.2 | 100000 |

## Index construction and memory

See `build.csv` for trie nodes, estimated retained object bytes, sorted-baseline estimated bytes, construction time, separately traced build-allocation peak, and observed process peak RSS. Trie bytes are an approximate Python object-size estimate; RSS and tracemalloc are separate measurements.

Default 64 MiB index-cap preflight: doctor=within limit, pharmacy=within limit. The timed high-cap trie uses a recorded 512 MiB experimental cap so 100k-entry cases can be measured; the deployed default remains 64 MiB.

## Correctness and scope

Trie and sorted-prefix outputs were checked for exact ordered top-K equality against the independent full string-scan oracle for each generated hot and missing prefix, at limits 10 and 20. `correctness.csv` contains the per-prefix oracle counts.

The primary baseline is an in-memory sorted string-prefix range that models the ordering behavior of a PostgreSQL prefix index. The full Python string scan is the correctness oracle and is also measured as a bounded secondary CPU baseline; its operation cap is reported because its O(n) cost grows with catalog size. This is a CPU-only algorithm benchmark: it does not include authenticated HTTP, PostgreSQL revision reads, selected-ID validation, or network latency, because the coordinator owns route mounting and migration integration.

Measurements use `perf_counter_ns`, 1,000 warmup calls per owner/algorithm/client/result-limit configuration, and closed-loop thread clients. Trie and sorted baseline each receive at least 100,000 timed operations per trial for limits 10 and 20. Tracemalloc runs in a separate build pass and is disabled during timed lookups. Throughput is completed lookups divided by wall time. P95 uses nearest-rank `ceil(0.95*n)-1`; no endpoint or service-level speedup is claimed.

Catalog SHA256: `cfed79bb8af0a2915d8b8a95842d1a50d1d26000d6b4b8d2e7dc2541c498a021`.
