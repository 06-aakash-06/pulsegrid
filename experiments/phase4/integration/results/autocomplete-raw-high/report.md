# Autocomplete benchmark: high

Dataset seed: `404`. Generated owner catalogs contain 100,000 entries each; the Doctor catalog includes active-doctor and specialty kinds, while the Pharmacy catalog contains active-medicine names only.

## Results

| Owner | Algorithm | Clients | Average ms | P95 ms | Lookups/s | Samples |
|---|---|---:|---:|---:|---:|---:|
| doctor | trie | 1 | 0.0026 | 0.0044 | 354588.7 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0025 | 0.0035 | 370701.5 | 100000 |
| doctor | python_scan_secondary | 1 | 17.8495 | 34.3763 | 56.0 | 100 |
| doctor | trie | 1 | 0.0028 | 0.0048 | 333631.2 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0030 | 0.0050 | 310967.1 | 100000 |
| doctor | trie | 8 | 0.0071 | 0.0044 | 342954.9 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0098 | 0.0035 | 353572.1 | 100000 |
| doctor | trie | 8 | 0.0093 | 0.0050 | 330658.3 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0089 | 0.0050 | 302944.7 | 100000 |
| doctor | trie | 32 | 0.0064 | 0.0045 | 341103.2 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0059 | 0.0036 | 349463.3 | 100000 |
| doctor | trie | 32 | 0.0068 | 0.0048 | 318832.0 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0090 | 0.0049 | 296864.5 | 100000 |
| doctor | trie | 1 | 0.0025 | 0.0044 | 361288.3 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0025 | 0.0036 | 362057.7 | 100000 |
| doctor | python_scan_secondary | 1 | 17.6234 | 33.3071 | 56.7 | 100 |
| doctor | trie | 1 | 0.0027 | 0.0049 | 324406.7 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0030 | 0.0050 | 310102.2 | 100000 |
| doctor | trie | 8 | 0.0094 | 0.0044 | 351026.5 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0105 | 0.0035 | 353225.6 | 100000 |
| doctor | trie | 8 | 0.0084 | 0.0048 | 329413.5 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0110 | 0.0049 | 299263.5 | 100000 |
| doctor | trie | 32 | 0.0075 | 0.0043 | 329310.2 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0078 | 0.0035 | 350949.8 | 100000 |
| doctor | trie | 32 | 0.0074 | 0.0048 | 313982.1 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0071 | 0.0051 | 296752.1 | 100000 |
| doctor | trie | 1 | 0.0025 | 0.0043 | 362758.1 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0025 | 0.0035 | 370960.0 | 100000 |
| doctor | python_scan_secondary | 1 | 17.5473 | 33.3701 | 57.0 | 100 |
| doctor | trie | 1 | 0.0027 | 0.0048 | 340177.0 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0030 | 0.0050 | 312332.1 | 100000 |
| doctor | trie | 8 | 0.0083 | 0.0043 | 341890.1 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0083 | 0.0035 | 350670.9 | 100000 |
| doctor | trie | 8 | 0.0090 | 0.0048 | 324085.4 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0147 | 0.0050 | 302907.4 | 100000 |
| doctor | trie | 32 | 0.0060 | 0.0044 | 309575.8 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0079 | 0.0035 | 348153.1 | 100000 |
| doctor | trie | 32 | 0.0084 | 0.0048 | 316746.9 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0089 | 0.0050 | 295524.3 | 100000 |
| pharmacy | trie | 1 | 0.0022 | 0.0036 | 419659.4 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0027 | 0.0036 | 342724.4 | 100000 |
| pharmacy | python_scan_secondary | 1 | 17.2157 | 21.7708 | 58.1 | 100 |
| pharmacy | trie | 1 | 0.0024 | 0.0041 | 382351.0 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0035 | 0.0054 | 268144.6 | 100000 |
| pharmacy | trie | 8 | 0.0112 | 0.0036 | 391337.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0117 | 0.0036 | 327482.7 | 100000 |
| pharmacy | trie | 8 | 0.0066 | 0.0042 | 363724.5 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0205 | 0.0063 | 230164.2 | 100000 |
| pharmacy | trie | 32 | 0.0062 | 0.0037 | 336570.9 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0067 | 0.0036 | 321403.9 | 100000 |
| pharmacy | trie | 32 | 0.0070 | 0.0042 | 352171.1 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0102 | 0.0053 | 255407.9 | 100000 |
| pharmacy | trie | 1 | 0.0022 | 0.0037 | 417297.4 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0027 | 0.0036 | 342933.7 | 100000 |
| pharmacy | python_scan_secondary | 1 | 16.9513 | 21.7389 | 59.0 | 100 |
| pharmacy | trie | 1 | 0.0028 | 0.0041 | 312233.1 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0036 | 0.0055 | 260024.9 | 100000 |
| pharmacy | trie | 8 | 0.0068 | 0.0036 | 392804.2 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0115 | 0.0036 | 324287.1 | 100000 |
| pharmacy | trie | 8 | 0.0081 | 0.0042 | 360786.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0119 | 0.0053 | 258367.9 | 100000 |
| pharmacy | trie | 32 | 0.0053 | 0.0036 | 392228.2 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0090 | 0.0036 | 327597.9 | 100000 |
| pharmacy | trie | 32 | 0.0059 | 0.0041 | 351460.8 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0111 | 0.0052 | 255617.5 | 100000 |
| pharmacy | trie | 1 | 0.0022 | 0.0036 | 415994.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0027 | 0.0037 | 342061.9 | 100000 |
| pharmacy | python_scan_secondary | 1 | 16.9659 | 22.1851 | 58.9 | 100 |
| pharmacy | trie | 1 | 0.0026 | 0.0041 | 347297.9 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0036 | 0.0054 | 265698.3 | 100000 |
| pharmacy | trie | 8 | 0.0076 | 0.0037 | 394719.6 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0106 | 0.0037 | 328604.8 | 100000 |
| pharmacy | trie | 8 | 0.0088 | 0.0041 | 351488.8 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0136 | 0.0053 | 261885.4 | 100000 |
| pharmacy | trie | 32 | 0.0069 | 0.0036 | 382779.9 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0093 | 0.0036 | 320456.5 | 100000 |
| pharmacy | trie | 32 | 0.0061 | 0.0041 | 346707.2 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0114 | 0.0052 | 251528.0 | 100000 |

## Index construction and memory

See `build.csv` for trie nodes, estimated retained object bytes, sorted-baseline estimated bytes, construction time, separately traced build-allocation peak, and observed process peak RSS. Trie bytes are an approximate Python object-size estimate; RSS and tracemalloc are separate measurements.

Default 64 MiB index-cap preflight: doctor=memory_limit_exceeded, pharmacy=memory_limit_exceeded. The timed high-cap trie uses a recorded 512 MiB experimental cap so 100k-entry cases can be measured; the deployed default remains 64 MiB.

## Correctness and scope

Trie and sorted-prefix outputs were checked for exact ordered top-K equality against the independent full string-scan oracle for each generated hot and missing prefix, at limits 10 and 20. `correctness.csv` contains the per-prefix oracle counts.

The primary baseline is an in-memory sorted string-prefix range that models the ordering behavior of a PostgreSQL prefix index. The full Python string scan is the correctness oracle and is also measured as a bounded secondary CPU baseline; its operation cap is reported because its O(n) cost grows with catalog size. This is a CPU-only algorithm benchmark: it does not include authenticated HTTP, PostgreSQL revision reads, selected-ID validation, or network latency, because the coordinator owns route mounting and migration integration.

Measurements use `perf_counter_ns`, 1,000 warmup calls per owner/algorithm/client/result-limit configuration, and closed-loop thread clients. Trie and sorted baseline each receive at least 100,000 timed operations per trial for limits 10 and 20. Tracemalloc runs in a separate build pass and is disabled during timed lookups. Throughput is completed lookups divided by wall time. P95 uses nearest-rank `ceil(0.95*n)-1`; no endpoint or service-level speedup is claimed.

Catalog SHA256: `cba2cb94593cbe0cf8b38bb67a87140894acba9ce574439dbfa9b94ebc89548a`.
