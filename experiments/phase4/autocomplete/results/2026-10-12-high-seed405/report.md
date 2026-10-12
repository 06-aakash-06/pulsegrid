# Autocomplete benchmark: high

Dataset seed: `405`. Generated owner catalogs contain 100,000 entries each; the Doctor catalog includes active-doctor and specialty kinds, while the Pharmacy catalog contains active-medicine names only.

## Results

| Owner | Algorithm | Clients | Average ms | P95 ms | Lookups/s | Samples |
|---|---|---:|---:|---:|---:|---:|
| doctor | trie | 1 | 0.0028 | 0.0047 | 327360.7 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0026 | 0.0034 | 356890.6 | 100000 |
| doctor | python_scan_secondary | 1 | 13.1744 | 27.5402 | 75.9 | 100 |
| doctor | trie | 1 | 0.0030 | 0.0052 | 306451.7 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0029 | 0.0044 | 316082.2 | 100000 |
| doctor | trie | 8 | 0.0145 | 0.0047 | 309256.0 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0088 | 0.0034 | 345823.2 | 100000 |
| doctor | trie | 8 | 0.0166 | 0.0053 | 272048.6 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0145 | 0.0045 | 297724.4 | 100000 |
| doctor | trie | 32 | 0.0103 | 0.0047 | 314911.3 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0087 | 0.0034 | 335779.6 | 100000 |
| doctor | trie | 32 | 0.0094 | 0.0051 | 297329.6 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0132 | 0.0044 | 302986.2 | 100000 |
| doctor | trie | 1 | 0.0028 | 0.0047 | 327219.3 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0026 | 0.0034 | 359603.1 | 100000 |
| doctor | python_scan_secondary | 1 | 14.0596 | 28.4934 | 71.1 | 100 |
| doctor | trie | 1 | 0.0029 | 0.0051 | 314788.0 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0029 | 0.0044 | 315948.4 | 100000 |
| doctor | trie | 8 | 0.0105 | 0.0047 | 319956.6 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0088 | 0.0034 | 347674.9 | 100000 |
| doctor | trie | 8 | 0.0129 | 0.0051 | 301306.7 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0149 | 0.0045 | 294457.6 | 100000 |
| doctor | trie | 32 | 0.0085 | 0.0047 | 316689.5 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0130 | 0.0043 | 315037.7 | 100000 |
| doctor | trie | 32 | 0.0097 | 0.0051 | 300846.1 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0092 | 0.0044 | 305975.4 | 100000 |
| doctor | trie | 1 | 0.0028 | 0.0047 | 328868.4 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0026 | 0.0034 | 357355.9 | 100000 |
| doctor | python_scan_secondary | 1 | 13.2531 | 28.1460 | 75.4 | 100 |
| doctor | trie | 1 | 0.0032 | 0.0052 | 287517.3 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0030 | 0.0044 | 313734.6 | 100000 |
| doctor | trie | 8 | 0.0113 | 0.0047 | 318855.9 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0118 | 0.0034 | 340192.8 | 100000 |
| doctor | trie | 8 | 0.0132 | 0.0053 | 274457.5 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0112 | 0.0044 | 302194.8 | 100000 |
| doctor | trie | 32 | 0.0127 | 0.0047 | 297783.8 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0110 | 0.0035 | 328970.3 | 100000 |
| doctor | trie | 32 | 0.0114 | 0.0052 | 282152.3 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0109 | 0.0045 | 281781.1 | 100000 |
| pharmacy | trie | 1 | 0.0024 | 0.0040 | 386769.4 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0027 | 0.0035 | 340516.4 | 100000 |
| pharmacy | python_scan_secondary | 1 | 12.0150 | 16.0734 | 83.2 | 100 |
| pharmacy | trie | 1 | 0.0026 | 0.0043 | 359402.8 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0032 | 0.0046 | 289771.0 | 100000 |
| pharmacy | trie | 8 | 0.0092 | 0.0040 | 370071.7 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0127 | 0.0035 | 330053.2 | 100000 |
| pharmacy | trie | 8 | 0.0104 | 0.0044 | 344119.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0144 | 0.0046 | 281764.3 | 100000 |
| pharmacy | trie | 32 | 0.0069 | 0.0040 | 363566.8 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0131 | 0.0039 | 300698.3 | 100000 |
| pharmacy | trie | 32 | 0.0077 | 0.0044 | 337810.1 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0134 | 0.0046 | 277907.4 | 100000 |
| pharmacy | trie | 1 | 0.0024 | 0.0040 | 383867.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0030 | 0.0041 | 308155.5 | 100000 |
| pharmacy | python_scan_secondary | 1 | 11.8458 | 15.9924 | 84.4 | 100 |
| pharmacy | trie | 1 | 0.0026 | 0.0044 | 355062.7 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0033 | 0.0046 | 287458.3 | 100000 |
| pharmacy | trie | 8 | 0.0086 | 0.0040 | 367411.1 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0102 | 0.0036 | 330077.6 | 100000 |
| pharmacy | trie | 8 | 0.0127 | 0.0044 | 344280.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0171 | 0.0047 | 279684.9 | 100000 |
| pharmacy | trie | 32 | 0.0081 | 0.0042 | 339024.4 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0093 | 0.0036 | 324514.6 | 100000 |
| pharmacy | trie | 32 | 0.0096 | 0.0045 | 335853.5 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0118 | 0.0046 | 274834.2 | 100000 |
| pharmacy | trie | 1 | 0.0024 | 0.0039 | 384863.1 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0027 | 0.0035 | 343929.5 | 100000 |
| pharmacy | python_scan_secondary | 1 | 13.4586 | 18.2739 | 74.3 | 100 |
| pharmacy | trie | 1 | 0.0026 | 0.0044 | 354665.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0034 | 0.0047 | 276404.7 | 100000 |
| pharmacy | trie | 8 | 0.0073 | 0.0040 | 363646.1 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0118 | 0.0035 | 321519.8 | 100000 |
| pharmacy | trie | 8 | 0.0096 | 0.0045 | 318330.7 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0156 | 0.0047 | 276404.7 | 100000 |
| pharmacy | trie | 32 | 0.0081 | 0.0040 | 338981.7 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0091 | 0.0036 | 300066.8 | 100000 |
| pharmacy | trie | 32 | 0.0073 | 0.0045 | 331801.5 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0128 | 0.0047 | 272505.7 | 100000 |

## Index construction and memory

See `build.csv` for trie nodes, estimated retained object bytes, sorted-baseline estimated bytes, construction time, separately traced build-allocation peak, and observed process peak RSS. Trie bytes are an approximate Python object-size estimate; RSS and tracemalloc are separate measurements.

Default 64 MiB index-cap preflight: doctor=memory_limit_exceeded, pharmacy=memory_limit_exceeded. The timed high-cap trie uses a recorded 512 MiB experimental cap so 100k-entry cases can be measured; the deployed default remains 64 MiB.

## Correctness and scope

Trie and sorted-prefix outputs were checked for exact ordered top-K equality against the independent full string-scan oracle for each generated hot and missing prefix, at limits 10 and 20. `correctness.csv` contains the per-prefix oracle counts.

The primary baseline is an in-memory sorted string-prefix range that models the ordering behavior of a PostgreSQL prefix index. The full Python string scan is the correctness oracle and is also measured as a bounded secondary CPU baseline; its operation cap is reported because its O(n) cost grows with catalog size. This is a CPU-only algorithm benchmark: it does not include authenticated HTTP, PostgreSQL revision reads, selected-ID validation, or network latency, because the coordinator owns route mounting and migration integration.

Measurements use `perf_counter_ns`, 1,000 warmup calls per owner/algorithm/client/result-limit configuration, and closed-loop thread clients. Trie and sorted baseline each receive at least 100,000 timed operations per trial for limits 10 and 20. Tracemalloc runs in a separate build pass and is disabled during timed lookups. Throughput is completed lookups divided by wall time. P95 uses nearest-rank `ceil(0.95*n)-1`; no endpoint or service-level speedup is claimed.

Catalog SHA256: `9aa31b5f002409bbee98e2d7e49ad58e42881711902ddd07d440b989328d8b26`.
