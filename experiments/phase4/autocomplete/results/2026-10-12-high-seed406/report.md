# Autocomplete benchmark: high

Dataset seed: `406`. Generated owner catalogs contain 100,000 entries each; the Doctor catalog includes active-doctor and specialty kinds, while the Pharmacy catalog contains active-medicine names only.

## Results

| Owner | Algorithm | Clients | Average ms | P95 ms | Lookups/s | Samples |
|---|---|---:|---:|---:|---:|---:|
| doctor | trie | 1 | 0.0029 | 0.0047 | 325268.6 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0026 | 0.0035 | 354067.8 | 100000 |
| doctor | python_scan_secondary | 1 | 13.7535 | 28.4868 | 72.7 | 100 |
| doctor | trie | 1 | 0.0029 | 0.0051 | 318020.0 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0029 | 0.0044 | 323169.6 | 100000 |
| doctor | trie | 8 | 0.0116 | 0.0046 | 315020.7 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0085 | 0.0034 | 336045.5 | 100000 |
| doctor | trie | 8 | 0.0137 | 0.0051 | 293551.4 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0129 | 0.0043 | 294753.0 | 100000 |
| doctor | trie | 32 | 0.0075 | 0.0046 | 318154.2 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0069 | 0.0033 | 330230.1 | 100000 |
| doctor | trie | 32 | 0.0087 | 0.0050 | 293916.0 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0088 | 0.0043 | 290541.8 | 100000 |
| doctor | trie | 1 | 0.0028 | 0.0047 | 331946.4 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0026 | 0.0035 | 355125.0 | 100000 |
| doctor | python_scan_secondary | 1 | 13.5516 | 28.0775 | 73.8 | 100 |
| doctor | trie | 1 | 0.0030 | 0.0051 | 312908.2 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0029 | 0.0044 | 315279.4 | 100000 |
| doctor | trie | 8 | 0.0102 | 0.0047 | 317412.1 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0082 | 0.0034 | 344183.7 | 100000 |
| doctor | trie | 8 | 0.0088 | 0.0051 | 300952.1 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0116 | 0.0044 | 303287.4 | 100000 |
| doctor | trie | 32 | 0.0106 | 0.0047 | 305709.7 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0105 | 0.0035 | 329627.8 | 100000 |
| doctor | trie | 32 | 0.0085 | 0.0051 | 301908.7 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0088 | 0.0044 | 303006.8 | 100000 |
| doctor | trie | 1 | 0.0028 | 0.0047 | 328379.1 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0026 | 0.0035 | 355394.8 | 100000 |
| doctor | python_scan_secondary | 1 | 13.3252 | 27.9740 | 75.0 | 100 |
| doctor | trie | 1 | 0.0029 | 0.0051 | 317778.6 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0029 | 0.0044 | 321830.4 | 100000 |
| doctor | trie | 8 | 0.0118 | 0.0046 | 311846.2 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0074 | 0.0034 | 340870.9 | 100000 |
| doctor | trie | 8 | 0.0100 | 0.0051 | 305543.2 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0140 | 0.0044 | 308484.5 | 100000 |
| doctor | trie | 32 | 0.0075 | 0.0046 | 307577.4 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0147 | 0.0066 | 240186.1 | 100000 |
| doctor | trie | 32 | 0.0104 | 0.0051 | 300577.4 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0105 | 0.0044 | 292599.9 | 100000 |
| pharmacy | trie | 1 | 0.0023 | 0.0039 | 395758.2 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0027 | 0.0035 | 344480.3 | 100000 |
| pharmacy | python_scan_secondary | 1 | 22.6651 | 32.5926 | 44.1 | 100 |
| pharmacy | trie | 1 | 0.0049 | 0.0081 | 189105.4 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0060 | 0.0085 | 157007.0 | 100000 |
| pharmacy | trie | 8 | 0.0229 | 0.0091 | 163544.8 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0353 | 0.0080 | 142676.7 | 100000 |
| pharmacy | trie | 8 | 0.0248 | 0.0081 | 179516.1 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0347 | 0.0085 | 149750.7 | 100000 |
| pharmacy | trie | 32 | 0.0104 | 0.0063 | 227252.4 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0180 | 0.0055 | 199253.6 | 100000 |
| pharmacy | trie | 32 | 0.0204 | 0.0069 | 201272.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0228 | 0.0073 | 164706.2 | 100000 |
| pharmacy | trie | 1 | 0.0023 | 0.0039 | 392944.6 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0027 | 0.0035 | 346694.0 | 100000 |
| pharmacy | python_scan_secondary | 1 | 17.9123 | 23.9970 | 55.8 | 100 |
| pharmacy | trie | 1 | 0.0041 | 0.0069 | 219426.4 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0051 | 0.0073 | 180902.4 | 100000 |
| pharmacy | trie | 8 | 0.0178 | 0.0062 | 230273.5 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0172 | 0.0055 | 211389.3 | 100000 |
| pharmacy | trie | 8 | 0.0180 | 0.0060 | 238212.1 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0281 | 0.0063 | 199333.1 | 100000 |
| pharmacy | trie | 32 | 0.0114 | 0.0062 | 232665.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0165 | 0.0056 | 189219.0 | 100000 |
| pharmacy | trie | 32 | 0.0141 | 0.0069 | 201942.2 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0302 | 0.0073 | 171725.9 | 100000 |
| pharmacy | trie | 1 | 0.0023 | 0.0038 | 395603.5 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0027 | 0.0035 | 338698.4 | 100000 |
| pharmacy | python_scan_secondary | 1 | 17.5144 | 22.8845 | 57.1 | 100 |
| pharmacy | trie | 1 | 0.0035 | 0.0060 | 258463.8 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0044 | 0.0063 | 211481.4 | 100000 |
| pharmacy | trie | 8 | 0.0106 | 0.0061 | 258254.4 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0191 | 0.0055 | 203780.2 | 100000 |
| pharmacy | trie | 8 | 0.0168 | 0.0069 | 206560.6 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0303 | 0.0073 | 174058.5 | 100000 |
| pharmacy | trie | 32 | 0.0143 | 0.0063 | 222381.6 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0252 | 0.0055 | 198020.4 | 100000 |
| pharmacy | trie | 32 | 0.0187 | 0.0069 | 200386.4 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0286 | 0.0070 | 183232.8 | 100000 |

## Index construction and memory

See `build.csv` for trie nodes, estimated retained object bytes, sorted-baseline estimated bytes, construction time, separately traced build-allocation peak, and observed process peak RSS. Trie bytes are an approximate Python object-size estimate; RSS and tracemalloc are separate measurements.

Default 64 MiB index-cap preflight: doctor=memory_limit_exceeded, pharmacy=memory_limit_exceeded. The timed high-cap trie uses a recorded 512 MiB experimental cap so 100k-entry cases can be measured; the deployed default remains 64 MiB.

## Correctness and scope

Trie and sorted-prefix outputs were checked for exact ordered top-K equality against the independent full string-scan oracle for each generated hot and missing prefix, at limits 10 and 20. `correctness.csv` contains the per-prefix oracle counts.

The primary baseline is an in-memory sorted string-prefix range that models the ordering behavior of a PostgreSQL prefix index. The full Python string scan is the correctness oracle and is also measured as a bounded secondary CPU baseline; its operation cap is reported because its O(n) cost grows with catalog size. This is a CPU-only algorithm benchmark: it does not include authenticated HTTP, PostgreSQL revision reads, selected-ID validation, or network latency, because the coordinator owns route mounting and migration integration.

Measurements use `perf_counter_ns`, 1,000 warmup calls per owner/algorithm/client/result-limit configuration, and closed-loop thread clients. Trie and sorted baseline each receive at least 100,000 timed operations per trial for limits 10 and 20. Tracemalloc runs in a separate build pass and is disabled during timed lookups. Throughput is completed lookups divided by wall time. P95 uses nearest-rank `ceil(0.95*n)-1`; no endpoint or service-level speedup is claimed.

Catalog SHA256: `fd438ae617fe9af4a98a8b02683e33b5e5b8e2be60ba2df76c7379349ebdc9a1`.
