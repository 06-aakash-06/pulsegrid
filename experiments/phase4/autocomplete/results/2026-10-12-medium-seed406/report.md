# Autocomplete benchmark: medium

Dataset seed: `406`. Generated owner catalogs contain 10,000 entries each; the Doctor catalog includes active-doctor and specialty kinds, while the Pharmacy catalog contains active-medicine names only.

## Results

| Owner | Algorithm | Clients | Average ms | P95 ms | Lookups/s | Samples |
|---|---|---:|---:|---:|---:|---:|
| doctor | trie | 1 | 0.0028 | 0.0046 | 335146.4 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0023 | 0.0031 | 404042.1 | 100000 |
| doctor | python_scan_secondary | 1 | 1.2228 | 2.6290 | 817.4 | 1000 |
| doctor | trie | 1 | 0.0029 | 0.0051 | 319464.6 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0026 | 0.0041 | 355850.9 | 100000 |
| doctor | trie | 8 | 0.0121 | 0.0047 | 325468.8 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0084 | 0.0031 | 390168.4 | 100000 |
| doctor | trie | 8 | 0.0165 | 0.0051 | 310973.8 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0093 | 0.0041 | 345739.4 | 100000 |
| doctor | trie | 32 | 0.0092 | 0.0047 | 319267.5 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0072 | 0.0031 | 383720.7 | 100000 |
| doctor | trie | 32 | 0.0101 | 0.0051 | 302643.2 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0108 | 0.0040 | 338698.4 | 100000 |
| doctor | trie | 1 | 0.0028 | 0.0047 | 333922.9 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0023 | 0.0031 | 403966.3 | 100000 |
| doctor | python_scan_secondary | 1 | 1.2179 | 2.6162 | 820.6 | 1000 |
| doctor | trie | 1 | 0.0029 | 0.0050 | 321042.5 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0026 | 0.0041 | 355594.9 | 100000 |
| doctor | trie | 8 | 0.0106 | 0.0046 | 324689.2 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0079 | 0.0031 | 392311.5 | 100000 |
| doctor | trie | 8 | 0.0106 | 0.0051 | 310420.9 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0101 | 0.0041 | 344855.4 | 100000 |
| doctor | trie | 32 | 0.0105 | 0.0046 | 318598.1 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0068 | 0.0031 | 384573.0 | 100000 |
| doctor | trie | 32 | 0.0093 | 0.0051 | 301054.8 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0096 | 0.0041 | 338653.3 | 100000 |
| doctor | trie | 1 | 0.0033 | 0.0048 | 279031.4 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0023 | 0.0031 | 398530.3 | 100000 |
| doctor | python_scan_secondary | 1 | 1.2554 | 2.6744 | 795.7 | 1000 |
| doctor | trie | 1 | 0.0029 | 0.0051 | 313184.2 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0027 | 0.0042 | 343023.7 | 100000 |
| doctor | trie | 8 | 0.0091 | 0.0047 | 322524.1 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0091 | 0.0031 | 387454.1 | 100000 |
| doctor | trie | 8 | 0.0105 | 0.0051 | 310176.9 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0092 | 0.0041 | 339217.7 | 100000 |
| doctor | trie | 32 | 0.0082 | 0.0047 | 319324.3 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0072 | 0.0031 | 382550.4 | 100000 |
| doctor | trie | 32 | 0.0084 | 0.0051 | 291477.9 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0108 | 0.0041 | 315522.5 | 100000 |
| pharmacy | trie | 1 | 0.0024 | 0.0039 | 391428.4 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0025 | 0.0032 | 374407.6 | 100000 |
| pharmacy | python_scan_secondary | 1 | 1.0422 | 1.4099 | 958.9 | 1000 |
| pharmacy | trie | 1 | 0.0026 | 0.0043 | 363261.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0030 | 0.0043 | 316063.1 | 100000 |
| pharmacy | trie | 8 | 0.0110 | 0.0039 | 382333.0 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0093 | 0.0032 | 363300.9 | 100000 |
| pharmacy | trie | 8 | 0.0106 | 0.0044 | 347367.0 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0126 | 0.0043 | 300597.2 | 100000 |
| pharmacy | trie | 32 | 0.0108 | 0.0040 | 356209.1 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0065 | 0.0032 | 355830.9 | 100000 |
| pharmacy | trie | 32 | 0.0088 | 0.0044 | 341409.4 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0118 | 0.0043 | 301447.6 | 100000 |
| pharmacy | trie | 1 | 0.0023 | 0.0039 | 392569.2 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0025 | 0.0033 | 366905.5 | 100000 |
| pharmacy | python_scan_secondary | 1 | 1.0661 | 1.4540 | 937.5 | 1000 |
| pharmacy | trie | 1 | 0.0044 | 0.0045 | 210068.6 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0031 | 0.0044 | 304093.6 | 100000 |
| pharmacy | trie | 8 | 0.0081 | 0.0039 | 377488.5 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0106 | 0.0032 | 365686.0 | 100000 |
| pharmacy | trie | 8 | 0.0082 | 0.0043 | 352602.8 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0147 | 0.0043 | 308104.0 | 100000 |
| pharmacy | trie | 32 | 0.0050 | 0.0039 | 371854.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0069 | 0.0032 | 358922.7 | 100000 |
| pharmacy | trie | 32 | 0.0080 | 0.0044 | 343880.4 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0128 | 0.0043 | 289721.2 | 100000 |
| pharmacy | trie | 1 | 0.0024 | 0.0039 | 391778.8 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0025 | 0.0032 | 376785.6 | 100000 |
| pharmacy | python_scan_secondary | 1 | 1.0472 | 1.4393 | 954.3 | 1000 |
| pharmacy | trie | 1 | 0.0026 | 0.0043 | 361327.8 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0030 | 0.0044 | 312617.6 | 100000 |
| pharmacy | trie | 8 | 0.0066 | 0.0039 | 381284.9 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0104 | 0.0032 | 367412.6 | 100000 |
| pharmacy | trie | 8 | 0.0118 | 0.0043 | 350041.6 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0141 | 0.0043 | 307563.4 | 100000 |
| pharmacy | trie | 32 | 0.0101 | 0.0039 | 372980.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0098 | 0.0034 | 323453.9 | 100000 |
| pharmacy | trie | 32 | 0.0110 | 0.0085 | 266291.7 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0123 | 0.0043 | 300992.2 | 100000 |

## Index construction and memory

See `build.csv` for trie nodes, estimated retained object bytes, sorted-baseline estimated bytes, construction time, separately traced build-allocation peak, and observed process peak RSS. Trie bytes are an approximate Python object-size estimate; RSS and tracemalloc are separate measurements.

Default 64 MiB index-cap preflight: doctor=within limit, pharmacy=within limit. The timed high-cap trie uses a recorded 512 MiB experimental cap so 100k-entry cases can be measured; the deployed default remains 64 MiB.

## Correctness and scope

Trie and sorted-prefix outputs were checked for exact ordered top-K equality against the independent full string-scan oracle for each generated hot and missing prefix, at limits 10 and 20. `correctness.csv` contains the per-prefix oracle counts.

The primary baseline is an in-memory sorted string-prefix range that models the ordering behavior of a PostgreSQL prefix index. The full Python string scan is the correctness oracle and is also measured as a bounded secondary CPU baseline; its operation cap is reported because its O(n) cost grows with catalog size. This is a CPU-only algorithm benchmark: it does not include authenticated HTTP, PostgreSQL revision reads, selected-ID validation, or network latency, because the coordinator owns route mounting and migration integration.

Measurements use `perf_counter_ns`, 1,000 warmup calls per owner/algorithm/client/result-limit configuration, and closed-loop thread clients. Trie and sorted baseline each receive at least 100,000 timed operations per trial for limits 10 and 20. Tracemalloc runs in a separate build pass and is disabled during timed lookups. Throughput is completed lookups divided by wall time. P95 uses nearest-rank `ceil(0.95*n)-1`; no endpoint or service-level speedup is claimed.

Catalog SHA256: `997af72534927796ae04bbba524799a1ace6fb4a70a904b05d2cb1941c995606`.
