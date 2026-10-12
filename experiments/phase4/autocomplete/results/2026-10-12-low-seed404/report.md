# Autocomplete benchmark: low

Dataset seed: `404`. Generated owner catalogs contain 1,000 entries each; the Doctor catalog includes active-doctor and specialty kinds, while the Pharmacy catalog contains active-medicine names only.

## Results

| Owner | Algorithm | Clients | Average ms | P95 ms | Lookups/s | Samples |
|---|---|---:|---:|---:|---:|---:|
| doctor | trie | 1 | 0.0029 | 0.0047 | 325638.1 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0022 | 0.0032 | 407948.5 | 100000 |
| doctor | python_scan_secondary | 1 | 0.1173 | 0.2520 | 8497.7 | 10000 |
| doctor | trie | 1 | 0.0030 | 0.0051 | 316687.5 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0024 | 0.0039 | 391231.6 | 100000 |
| doctor | trie | 8 | 0.0147 | 0.0047 | 324000.8 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0090 | 0.0029 | 441722.1 | 100000 |
| doctor | trie | 8 | 0.0147 | 0.0052 | 215055.4 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0105 | 0.0040 | 331835.6 | 100000 |
| doctor | trie | 32 | 0.0135 | 0.0048 | 282091.3 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0081 | 0.0029 | 421774.8 | 100000 |
| doctor | trie | 32 | 0.0127 | 0.0052 | 275495.9 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0088 | 0.0040 | 316030.2 | 100000 |
| doctor | trie | 1 | 0.0029 | 0.0047 | 326203.3 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0022 | 0.0029 | 422475.6 | 100000 |
| doctor | python_scan_secondary | 1 | 0.1182 | 0.2525 | 8434.1 | 10000 |
| doctor | trie | 1 | 0.0030 | 0.0051 | 307056.5 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0024 | 0.0038 | 390294.5 | 100000 |
| doctor | trie | 8 | 0.0087 | 0.0047 | 321351.6 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0071 | 0.0029 | 417210.6 | 100000 |
| doctor | trie | 8 | 0.0140 | 0.0052 | 301257.4 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0114 | 0.0039 | 335360.3 | 100000 |
| doctor | trie | 32 | 0.0134 | 0.0048 | 282958.3 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0059 | 0.0029 | 427676.7 | 100000 |
| doctor | trie | 32 | 0.0109 | 0.0051 | 287797.5 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0121 | 0.0039 | 360427.0 | 100000 |
| doctor | trie | 1 | 0.0028 | 0.0047 | 334114.4 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0020 | 0.0029 | 454642.4 | 100000 |
| doctor | python_scan_secondary | 1 | 0.1182 | 0.2523 | 8435.1 | 10000 |
| doctor | trie | 1 | 0.0030 | 0.0051 | 316466.3 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0024 | 0.0038 | 392516.7 | 100000 |
| doctor | trie | 8 | 0.0121 | 0.0047 | 324370.7 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0089 | 0.0029 | 439344.3 | 100000 |
| doctor | trie | 8 | 0.0124 | 0.0051 | 300083.5 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0098 | 0.0039 | 354463.3 | 100000 |
| doctor | trie | 32 | 0.0085 | 0.0047 | 321343.6 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0077 | 0.0030 | 382379.2 | 100000 |
| doctor | trie | 32 | 0.0117 | 0.0052 | 274339.4 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0081 | 0.0039 | 350990.1 | 100000 |
| pharmacy | trie | 1 | 0.0025 | 0.0040 | 371501.2 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0022 | 0.0028 | 422109.1 | 100000 |
| pharmacy | python_scan_secondary | 1 | 0.1071 | 0.1625 | 9305.8 | 10000 |
| pharmacy | trie | 1 | 0.0027 | 0.0044 | 346874.6 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0027 | 0.0039 | 344204.3 | 100000 |
| pharmacy | trie | 8 | 0.0137 | 0.0040 | 356366.5 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0112 | 0.0028 | 412777.3 | 100000 |
| pharmacy | trie | 8 | 0.0129 | 0.0044 | 342546.8 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0123 | 0.0041 | 306527.9 | 100000 |
| pharmacy | trie | 32 | 0.0075 | 0.0040 | 355700.0 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0056 | 0.0028 | 404342.2 | 100000 |
| pharmacy | trie | 32 | 0.0089 | 0.0044 | 329743.2 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0116 | 0.0039 | 317380.8 | 100000 |
| pharmacy | trie | 1 | 0.0024 | 0.0040 | 391554.1 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0022 | 0.0029 | 411847.3 | 100000 |
| pharmacy | python_scan_secondary | 1 | 0.1059 | 0.1628 | 9414.2 | 10000 |
| pharmacy | trie | 1 | 0.0026 | 0.0043 | 360146.4 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0028 | 0.0038 | 333190.0 | 100000 |
| pharmacy | trie | 8 | 0.0082 | 0.0039 | 382713.7 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0133 | 0.0031 | 372658.1 | 100000 |
| pharmacy | trie | 8 | 0.0099 | 0.0046 | 306989.8 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0117 | 0.0038 | 341706.3 | 100000 |
| pharmacy | trie | 32 | 0.0108 | 0.0040 | 355700.6 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0070 | 0.0029 | 374152.0 | 100000 |
| pharmacy | trie | 32 | 0.0104 | 0.0044 | 333555.1 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0079 | 0.0039 | 305089.0 | 100000 |
| pharmacy | trie | 1 | 0.0024 | 0.0040 | 383379.2 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0022 | 0.0028 | 425511.6 | 100000 |
| pharmacy | python_scan_secondary | 1 | 0.1018 | 0.1431 | 9790.4 | 10000 |
| pharmacy | trie | 1 | 0.0026 | 0.0044 | 358601.8 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0028 | 0.0039 | 328089.3 | 100000 |
| pharmacy | trie | 8 | 0.0104 | 0.0040 | 335818.9 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0067 | 0.0028 | 415611.0 | 100000 |
| pharmacy | trie | 8 | 0.0099 | 0.0044 | 343845.1 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0136 | 0.0039 | 319790.5 | 100000 |
| pharmacy | trie | 32 | 0.0086 | 0.0040 | 352532.0 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0061 | 0.0028 | 398318.8 | 100000 |
| pharmacy | trie | 32 | 0.0093 | 0.0044 | 310819.4 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0100 | 0.0038 | 324108.5 | 100000 |

## Index construction and memory

See `build.csv` for trie nodes, estimated retained object bytes, sorted-baseline estimated bytes, construction time, separately traced build-allocation peak, and observed process peak RSS. Trie bytes are an approximate Python object-size estimate; RSS and tracemalloc are separate measurements.

Default 64 MiB index-cap preflight: doctor=within limit, pharmacy=within limit. The timed high-cap trie uses a recorded 512 MiB experimental cap so 100k-entry cases can be measured; the deployed default remains 64 MiB.

## Correctness and scope

Trie and sorted-prefix outputs were checked for exact ordered top-K equality against the independent full string-scan oracle for each generated hot and missing prefix, at limits 10 and 20. `correctness.csv` contains the per-prefix oracle counts.

The primary baseline is an in-memory sorted string-prefix range that models the ordering behavior of a PostgreSQL prefix index. The full Python string scan is the correctness oracle and is also measured as a bounded secondary CPU baseline; its operation cap is reported because its O(n) cost grows with catalog size. This is a CPU-only algorithm benchmark: it does not include authenticated HTTP, PostgreSQL revision reads, selected-ID validation, or network latency, because the coordinator owns route mounting and migration integration.

Measurements use `perf_counter_ns`, 1,000 warmup calls per owner/algorithm/client/result-limit configuration, and closed-loop thread clients. Trie and sorted baseline each receive at least 100,000 timed operations per trial for limits 10 and 20. Tracemalloc runs in a separate build pass and is disabled during timed lookups. Throughput is completed lookups divided by wall time. P95 uses nearest-rank `ceil(0.95*n)-1`; no endpoint or service-level speedup is claimed.

Catalog SHA256: `73c39c75ff6fbb415410fef0a50866df525a1a0c5bbde89a80295c6d419a3ff2`.
