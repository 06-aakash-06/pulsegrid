# Autocomplete benchmark: low

Dataset seed: `405`. Generated owner catalogs contain 1,000 entries each; the Doctor catalog includes active-doctor and specialty kinds, while the Pharmacy catalog contains active-medicine names only.

## Results

| Owner | Algorithm | Clients | Average ms | P95 ms | Lookups/s | Samples |
|---|---|---:|---:|---:|---:|---:|
| doctor | trie | 1 | 0.0123 | 0.0096 | 74104.8 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0095 | 0.0054 | 90125.9 | 100000 |
| doctor | python_scan_secondary | 1 | 0.4907 | 0.5559 | 2035.3 | 10000 |
| doctor | trie | 1 | 0.0139 | 0.0066 | 69058.9 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0091 | 0.0074 | 99797.2 | 100000 |
| doctor | trie | 8 | 0.0128 | 0.0047 | 303044.6 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0075 | 0.0038 | 380141.2 | 100000 |
| doctor | trie | 8 | 0.0129 | 0.0095 | 240712.5 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0166 | 0.0076 | 272650.0 | 100000 |
| doctor | trie | 32 | 0.0141 | 0.0085 | 250027.7 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0087 | 0.0035 | 371710.8 | 100000 |
| doctor | trie | 32 | 0.0163 | 0.0104 | 230553.4 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0125 | 0.0071 | 322715.4 | 100000 |
| doctor | trie | 1 | 0.0112 | 0.0084 | 86004.0 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0079 | 0.0053 | 112849.6 | 100000 |
| doctor | python_scan_secondary | 1 | 0.5354 | 0.5590 | 1865.2 | 10000 |
| doctor | trie | 1 | 0.0131 | 0.0103 | 70046.1 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0094 | 0.0075 | 89923.1 | 100000 |
| doctor | trie | 8 | 0.0184 | 0.0084 | 247633.5 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0086 | 0.0052 | 371560.2 | 100000 |
| doctor | trie | 8 | 0.0162 | 0.0070 | 253021.1 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0229 | 0.0077 | 256598.4 | 100000 |
| doctor | trie | 32 | 0.0110 | 0.0085 | 228453.3 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0101 | 0.0053 | 336165.6 | 100000 |
| doctor | trie | 32 | 0.0132 | 0.0103 | 212952.4 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0111 | 0.0075 | 291664.2 | 100000 |
| doctor | trie | 1 | 0.0101 | 0.0080 | 88405.8 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0101 | 0.0053 | 94507.9 | 100000 |
| doctor | python_scan_secondary | 1 | 0.4893 | 0.5590 | 2030.9 | 10000 |
| doctor | trie | 1 | 0.0133 | 0.0104 | 69843.1 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0087 | 0.0073 | 101688.2 | 100000 |
| doctor | trie | 8 | 0.0197 | 0.0072 | 270336.6 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0081 | 0.0032 | 399450.6 | 100000 |
| doctor | trie | 8 | 0.0131 | 0.0090 | 254091.9 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0139 | 0.0073 | 319247.7 | 100000 |
| doctor | trie | 32 | 0.0147 | 0.0097 | 203942.4 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0092 | 0.0035 | 374068.6 | 100000 |
| doctor | trie | 32 | 0.0110 | 0.0092 | 229838.6 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0148 | 0.0075 | 283259.6 | 100000 |
| pharmacy | trie | 1 | 0.0091 | 0.0087 | 96015.1 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0084 | 0.0053 | 104763.5 | 100000 |
| pharmacy | python_scan_secondary | 1 | 0.4309 | 0.3260 | 2313.4 | 10000 |
| pharmacy | trie | 1 | 0.0109 | 0.0096 | 79345.2 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0117 | 0.0076 | 78916.5 | 100000 |
| pharmacy | trie | 8 | 0.0134 | 0.0085 | 297695.9 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0106 | 0.0053 | 328923.6 | 100000 |
| pharmacy | trie | 8 | 0.0103 | 0.0094 | 287465.5 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0206 | 0.0073 | 294980.9 | 100000 |
| pharmacy | trie | 32 | 0.0127 | 0.0086 | 282600.4 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0113 | 0.0053 | 308569.9 | 100000 |
| pharmacy | trie | 32 | 0.0070 | 0.0082 | 293467.2 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0124 | 0.0074 | 280976.2 | 100000 |
| pharmacy | trie | 1 | 0.0093 | 0.0074 | 99708.7 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0088 | 0.0053 | 110200.9 | 100000 |
| pharmacy | python_scan_secondary | 1 | 0.4306 | 0.3097 | 2319.6 | 10000 |
| pharmacy | trie | 1 | 0.0102 | 0.0097 | 94279.5 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0103 | 0.0075 | 91415.6 | 100000 |
| pharmacy | trie | 8 | 0.0092 | 0.0072 | 328209.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0130 | 0.0052 | 336884.9 | 100000 |
| pharmacy | trie | 8 | 0.0165 | 0.0096 | 261385.1 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0206 | 0.0076 | 226449.0 | 100000 |
| pharmacy | trie | 32 | 0.0108 | 0.0088 | 219800.2 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0084 | 0.0053 | 332906.6 | 100000 |
| pharmacy | trie | 32 | 0.0114 | 0.0097 | 245876.9 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0172 | 0.0074 | 274118.4 | 100000 |
| pharmacy | trie | 1 | 0.0109 | 0.0085 | 80641.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0086 | 0.0033 | 101614.6 | 100000 |
| pharmacy | python_scan_secondary | 1 | 0.4145 | 0.3218 | 2407.5 | 10000 |
| pharmacy | trie | 1 | 0.0129 | 0.0097 | 74693.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0120 | 0.0075 | 75908.2 | 100000 |
| pharmacy | trie | 8 | 0.0112 | 0.0086 | 287810.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0148 | 0.0052 | 337040.1 | 100000 |
| pharmacy | trie | 8 | 0.0090 | 0.0080 | 288128.7 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0184 | 0.0075 | 260197.7 | 100000 |
| pharmacy | trie | 32 | 0.0152 | 0.0088 | 254089.0 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0129 | 0.0053 | 313184.1 | 100000 |
| pharmacy | trie | 32 | 0.0162 | 0.0096 | 251672.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0116 | 0.0075 | 258896.1 | 100000 |

## Index construction and memory

See `build.csv` for trie nodes, estimated retained object bytes, sorted-baseline estimated bytes, construction time, separately traced build-allocation peak, and observed process peak RSS. Trie bytes are an approximate Python object-size estimate; RSS and tracemalloc are separate measurements.

Default 64 MiB index-cap preflight: doctor=within limit, pharmacy=within limit. The timed high-cap trie uses a recorded 512 MiB experimental cap so 100k-entry cases can be measured; the deployed default remains 64 MiB.

## Correctness and scope

Trie and sorted-prefix outputs were checked for exact ordered top-K equality against the independent full string-scan oracle for each generated hot and missing prefix, at limits 10 and 20. `correctness.csv` contains the per-prefix oracle counts.

The primary baseline is an in-memory sorted string-prefix range that models the ordering behavior of a PostgreSQL prefix index. The full Python string scan is the correctness oracle and is also measured as a bounded secondary CPU baseline; its operation cap is reported because its O(n) cost grows with catalog size. This is a CPU-only algorithm benchmark: it does not include authenticated HTTP, PostgreSQL revision reads, selected-ID validation, or network latency, because the coordinator owns route mounting and migration integration.

Measurements use `perf_counter_ns`, 1,000 warmup calls per owner/algorithm/client/result-limit configuration, and closed-loop thread clients. Trie and sorted baseline each receive at least 100,000 timed operations per trial for limits 10 and 20. Tracemalloc runs in a separate build pass and is disabled during timed lookups. Throughput is completed lookups divided by wall time. P95 uses nearest-rank `ceil(0.95*n)-1`; no endpoint or service-level speedup is claimed.

Catalog SHA256: `8150b9eb3ac5fab3eaa343befe4fda02bb08df870531eef9b581b25f7cc12120`.
