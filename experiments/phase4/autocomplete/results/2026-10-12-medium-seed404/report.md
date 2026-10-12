# Autocomplete benchmark: medium

Dataset seed: `404`. Generated owner catalogs contain 10,000 entries each; the Doctor catalog includes active-doctor and specialty kinds, while the Pharmacy catalog contains active-medicine names only.

## Results

| Owner | Algorithm | Clients | Average ms | P95 ms | Lookups/s | Samples |
|---|---|---:|---:|---:|---:|---:|
| doctor | trie | 1 | 0.0032 | 0.0048 | 291835.4 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0023 | 0.0031 | 398992.5 | 100000 |
| doctor | python_scan_secondary | 1 | 1.2183 | 2.6043 | 820.5 | 1000 |
| doctor | trie | 1 | 0.0029 | 0.0051 | 318211.9 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0026 | 0.0041 | 353425.8 | 100000 |
| doctor | trie | 8 | 0.0141 | 0.0047 | 322611.8 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0086 | 0.0031 | 395482.1 | 100000 |
| doctor | trie | 8 | 0.0164 | 0.0051 | 309503.3 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0122 | 0.0041 | 336198.5 | 100000 |
| doctor | trie | 32 | 0.0075 | 0.0047 | 318886.2 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0070 | 0.0031 | 386293.6 | 100000 |
| doctor | trie | 32 | 0.0087 | 0.0051 | 305462.8 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0082 | 0.0040 | 343183.7 | 100000 |
| doctor | trie | 1 | 0.0028 | 0.0047 | 328182.6 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0023 | 0.0031 | 399242.2 | 100000 |
| doctor | python_scan_secondary | 1 | 1.2346 | 2.6302 | 809.5 | 1000 |
| doctor | trie | 1 | 0.0029 | 0.0051 | 319850.7 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0026 | 0.0041 | 357216.3 | 100000 |
| doctor | trie | 8 | 0.0152 | 0.0048 | 294274.9 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0066 | 0.0031 | 397745.4 | 100000 |
| doctor | trie | 8 | 0.0128 | 0.0051 | 312425.1 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0169 | 0.0041 | 349731.1 | 100000 |
| doctor | trie | 32 | 0.0092 | 0.0047 | 322781.1 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0066 | 0.0030 | 392303.8 | 100000 |
| doctor | trie | 32 | 0.0110 | 0.0051 | 308325.5 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0092 | 0.0041 | 345131.6 | 100000 |
| doctor | trie | 1 | 0.0029 | 0.0047 | 324678.4 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0024 | 0.0031 | 385749.5 | 100000 |
| doctor | python_scan_secondary | 1 | 1.2205 | 2.6208 | 819.0 | 1000 |
| doctor | trie | 1 | 0.0029 | 0.0050 | 320049.9 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0026 | 0.0041 | 357356.3 | 100000 |
| doctor | trie | 8 | 0.0090 | 0.0047 | 322346.1 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0130 | 0.0031 | 362932.2 | 100000 |
| doctor | trie | 8 | 0.0147 | 0.0051 | 309508.6 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0115 | 0.0041 | 349132.1 | 100000 |
| doctor | trie | 32 | 0.0088 | 0.0047 | 313484.9 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0090 | 0.0031 | 379099.5 | 100000 |
| doctor | trie | 32 | 0.0153 | 0.0051 | 291175.5 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0084 | 0.0041 | 340466.1 | 100000 |
| pharmacy | trie | 1 | 0.0024 | 0.0039 | 392727.7 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0027 | 0.0034 | 346699.9 | 100000 |
| pharmacy | python_scan_secondary | 1 | 1.0447 | 1.4021 | 956.8 | 1000 |
| pharmacy | trie | 1 | 0.0026 | 0.0044 | 354387.4 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0032 | 0.0044 | 296399.9 | 100000 |
| pharmacy | trie | 8 | 0.0102 | 0.0040 | 376279.9 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0098 | 0.0032 | 365265.9 | 100000 |
| pharmacy | trie | 8 | 0.0141 | 0.0043 | 346846.5 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0135 | 0.0043 | 302852.6 | 100000 |
| pharmacy | trie | 32 | 0.0080 | 0.0040 | 371395.9 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0086 | 0.0032 | 365154.0 | 100000 |
| pharmacy | trie | 32 | 0.0110 | 0.0044 | 344401.8 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0095 | 0.0043 | 304628.9 | 100000 |
| pharmacy | trie | 1 | 0.0024 | 0.0040 | 389294.1 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0025 | 0.0032 | 376873.2 | 100000 |
| pharmacy | python_scan_secondary | 1 | 1.2192 | 2.2408 | 819.6 | 1000 |
| pharmacy | trie | 1 | 0.0033 | 0.0092 | 280489.2 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0034 | 0.0083 | 271959.4 | 100000 |
| pharmacy | trie | 8 | 0.0165 | 0.0088 | 282256.0 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0103 | 0.0063 | 289031.2 | 100000 |
| pharmacy | trie | 8 | 0.0119 | 0.0087 | 281456.8 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0226 | 0.0088 | 223126.4 | 100000 |
| pharmacy | trie | 32 | 0.0123 | 0.0088 | 263848.1 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0178 | 0.0063 | 278373.7 | 100000 |
| pharmacy | trie | 32 | 0.0127 | 0.0099 | 234433.9 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0256 | 0.0088 | 192901.9 | 100000 |
| pharmacy | trie | 1 | 0.0028 | 0.0073 | 323235.5 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0027 | 0.0034 | 340539.7 | 100000 |
| pharmacy | python_scan_secondary | 1 | 1.2661 | 2.4405 | 789.2 | 1000 |
| pharmacy | trie | 1 | 0.0028 | 0.0044 | 327649.0 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0038 | 0.0085 | 244362.2 | 100000 |
| pharmacy | trie | 8 | 0.0105 | 0.0076 | 312264.5 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0188 | 0.0062 | 283582.8 | 100000 |
| pharmacy | trie | 8 | 0.0128 | 0.0098 | 245983.2 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0158 | 0.0088 | 230122.8 | 100000 |
| pharmacy | trie | 32 | 0.0099 | 0.0088 | 284091.9 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0146 | 0.0062 | 232879.1 | 100000 |
| pharmacy | trie | 32 | 0.0121 | 0.0097 | 257774.0 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0176 | 0.0088 | 226218.7 | 100000 |

## Index construction and memory

See `build.csv` for trie nodes, estimated retained object bytes, sorted-baseline estimated bytes, construction time, separately traced build-allocation peak, and observed process peak RSS. Trie bytes are an approximate Python object-size estimate; RSS and tracemalloc are separate measurements.

Default 64 MiB index-cap preflight: doctor=within limit, pharmacy=within limit. The timed high-cap trie uses a recorded 512 MiB experimental cap so 100k-entry cases can be measured; the deployed default remains 64 MiB.

## Correctness and scope

Trie and sorted-prefix outputs were checked for exact ordered top-K equality against the independent full string-scan oracle for each generated hot and missing prefix, at limits 10 and 20. `correctness.csv` contains the per-prefix oracle counts.

The primary baseline is an in-memory sorted string-prefix range that models the ordering behavior of a PostgreSQL prefix index. The full Python string scan is the correctness oracle and is also measured as a bounded secondary CPU baseline; its operation cap is reported because its O(n) cost grows with catalog size. This is a CPU-only algorithm benchmark: it does not include authenticated HTTP, PostgreSQL revision reads, selected-ID validation, or network latency, because the coordinator owns route mounting and migration integration.

Measurements use `perf_counter_ns`, 1,000 warmup calls per owner/algorithm/client/result-limit configuration, and closed-loop thread clients. Trie and sorted baseline each receive at least 100,000 timed operations per trial for limits 10 and 20. Tracemalloc runs in a separate build pass and is disabled during timed lookups. Throughput is completed lookups divided by wall time. P95 uses nearest-rank `ceil(0.95*n)-1`; no endpoint or service-level speedup is claimed.

Catalog SHA256: `2ec99d896c487edd4662a57d56eb37d1d6eb997d3e715028652fe8647df5bb7f`.
