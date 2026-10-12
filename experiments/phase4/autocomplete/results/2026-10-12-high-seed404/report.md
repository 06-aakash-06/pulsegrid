# Autocomplete benchmark: high

Dataset seed: `404`. Generated owner catalogs contain 100,000 entries each; the Doctor catalog includes active-doctor and specialty kinds, while the Pharmacy catalog contains active-medicine names only.

## Results

| Owner | Algorithm | Clients | Average ms | P95 ms | Lookups/s | Samples |
|---|---|---:|---:|---:|---:|---:|
| doctor | trie | 1 | 0.0035 | 0.0083 | 264193.2 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0030 | 0.0044 | 306839.3 | 100000 |
| doctor | python_scan_secondary | 1 | 17.6561 | 42.0750 | 56.6 | 100 |
| doctor | trie | 1 | 0.0040 | 0.0097 | 224073.4 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0040 | 0.0086 | 229192.8 | 100000 |
| doctor | trie | 8 | 0.0178 | 0.0083 | 250963.7 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0213 | 0.0064 | 267814.5 | 100000 |
| doctor | trie | 8 | 0.0193 | 0.0107 | 213732.3 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0181 | 0.0087 | 233771.4 | 100000 |
| doctor | trie | 32 | 0.0250 | 0.0102 | 163223.1 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0199 | 0.0066 | 191989.4 | 100000 |
| doctor | trie | 32 | 0.0168 | 0.0099 | 226910.3 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0166 | 0.0088 | 222144.8 | 100000 |
| doctor | trie | 1 | 0.0039 | 0.0065 | 236926.3 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0040 | 0.0064 | 228933.9 | 100000 |
| doctor | python_scan_secondary | 1 | 13.1922 | 27.4661 | 75.7 | 100 |
| doctor | trie | 1 | 0.0030 | 0.0051 | 305158.7 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0029 | 0.0044 | 317104.8 | 100000 |
| doctor | trie | 8 | 0.0142 | 0.0047 | 319258.9 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0105 | 0.0034 | 343865.8 | 100000 |
| doctor | trie | 8 | 0.0097 | 0.0051 | 305960.9 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0154 | 0.0045 | 302565.6 | 100000 |
| doctor | trie | 32 | 0.0106 | 0.0047 | 310987.4 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0083 | 0.0035 | 336204.2 | 100000 |
| doctor | trie | 32 | 0.0097 | 0.0052 | 293103.5 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0099 | 0.0045 | 297630.3 | 100000 |
| doctor | trie | 1 | 0.0030 | 0.0047 | 308958.6 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0026 | 0.0034 | 355775.6 | 100000 |
| doctor | python_scan_secondary | 1 | 13.3192 | 26.9112 | 75.0 | 100 |
| doctor | trie | 1 | 0.0030 | 0.0051 | 306227.1 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0030 | 0.0045 | 306362.0 | 100000 |
| doctor | trie | 8 | 0.0108 | 0.0047 | 319219.2 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0132 | 0.0035 | 320193.6 | 100000 |
| doctor | trie | 8 | 0.0126 | 0.0052 | 285537.2 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0118 | 0.0044 | 298411.0 | 100000 |
| doctor | trie | 32 | 0.0071 | 0.0047 | 315896.4 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0081 | 0.0035 | 318936.6 | 100000 |
| doctor | trie | 32 | 0.0136 | 0.0051 | 288321.8 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0169 | 0.0045 | 283612.7 | 100000 |
| pharmacy | trie | 1 | 0.0025 | 0.0040 | 372768.5 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0028 | 0.0035 | 331296.3 | 100000 |
| pharmacy | python_scan_secondary | 1 | 15.2156 | 22.6099 | 65.7 | 100 |
| pharmacy | trie | 1 | 0.0026 | 0.0043 | 348704.5 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0033 | 0.0046 | 288217.6 | 100000 |
| pharmacy | trie | 8 | 0.0079 | 0.0040 | 368242.5 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0103 | 0.0035 | 324452.5 | 100000 |
| pharmacy | trie | 8 | 0.0131 | 0.0045 | 315288.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0182 | 0.0046 | 267124.8 | 100000 |
| pharmacy | trie | 32 | 0.0079 | 0.0040 | 355085.4 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0126 | 0.0036 | 306476.9 | 100000 |
| pharmacy | trie | 32 | 0.0120 | 0.0045 | 306898.1 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0131 | 0.0047 | 248752.5 | 100000 |
| pharmacy | trie | 1 | 0.0026 | 0.0040 | 355143.5 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0034 | 0.0037 | 272673.7 | 100000 |
| pharmacy | python_scan_secondary | 1 | 16.9709 | 22.7112 | 58.9 | 100 |
| pharmacy | trie | 1 | 0.0028 | 0.0044 | 322085.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0034 | 0.0047 | 274813.5 | 100000 |
| pharmacy | trie | 8 | 0.0124 | 0.0065 | 303146.2 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0159 | 0.0041 | 287480.2 | 100000 |
| pharmacy | trie | 8 | 0.0106 | 0.0047 | 294418.0 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0184 | 0.0050 | 253608.2 | 100000 |
| pharmacy | trie | 32 | 0.0103 | 0.0040 | 323550.2 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0148 | 0.0066 | 259596.4 | 100000 |
| pharmacy | trie | 32 | 0.0140 | 0.0045 | 301561.6 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0173 | 0.0047 | 251279.0 | 100000 |
| pharmacy | trie | 1 | 0.0024 | 0.0039 | 386710.0 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0028 | 0.0036 | 337035.7 | 100000 |
| pharmacy | python_scan_secondary | 1 | 13.5783 | 17.5855 | 73.6 | 100 |
| pharmacy | trie | 1 | 0.0026 | 0.0043 | 360813.4 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0033 | 0.0046 | 288000.6 | 100000 |
| pharmacy | trie | 8 | 0.0085 | 0.0040 | 367049.5 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0111 | 0.0035 | 321964.2 | 100000 |
| pharmacy | trie | 8 | 0.0091 | 0.0045 | 298441.9 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0165 | 0.0046 | 265235.6 | 100000 |
| pharmacy | trie | 32 | 0.0094 | 0.0040 | 350703.2 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0111 | 0.0036 | 312793.4 | 100000 |
| pharmacy | trie | 32 | 0.0074 | 0.0044 | 336930.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0121 | 0.0046 | 275146.1 | 100000 |

## Index construction and memory

See `build.csv` for trie nodes, estimated retained object bytes, sorted-baseline estimated bytes, construction time, separately traced build-allocation peak, and observed process peak RSS. Trie bytes are an approximate Python object-size estimate; RSS and tracemalloc are separate measurements.

Default 64 MiB index-cap preflight: doctor=memory_limit_exceeded, pharmacy=memory_limit_exceeded. The timed high-cap trie uses a recorded 512 MiB experimental cap so 100k-entry cases can be measured; the deployed default remains 64 MiB.

## Correctness and scope

Trie and sorted-prefix outputs were checked for exact ordered top-K equality against the independent full string-scan oracle for each generated hot and missing prefix, at limits 10 and 20. `correctness.csv` contains the per-prefix oracle counts.

The primary baseline is an in-memory sorted string-prefix range that models the ordering behavior of a PostgreSQL prefix index. The full Python string scan is the correctness oracle and is also measured as a bounded secondary CPU baseline; its operation cap is reported because its O(n) cost grows with catalog size. This is a CPU-only algorithm benchmark: it does not include authenticated HTTP, PostgreSQL revision reads, selected-ID validation, or network latency, because the coordinator owns route mounting and migration integration.

Measurements use `perf_counter_ns`, 1,000 warmup calls per owner/algorithm/client/result-limit configuration, and closed-loop thread clients. Trie and sorted baseline each receive at least 100,000 timed operations per trial for limits 10 and 20. Tracemalloc runs in a separate build pass and is disabled during timed lookups. Throughput is completed lookups divided by wall time. P95 uses nearest-rank `ceil(0.95*n)-1`; no endpoint or service-level speedup is claimed.

Catalog SHA256: `cba2cb94593cbe0cf8b38bb67a87140894acba9ce574439dbfa9b94ebc89548a`.
