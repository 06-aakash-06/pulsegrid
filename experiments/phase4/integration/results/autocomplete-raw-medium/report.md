# Autocomplete benchmark: medium

Dataset seed: `404`. Generated owner catalogs contain 10,000 entries each; the Doctor catalog includes active-doctor and specialty kinds, while the Pharmacy catalog contains active-medicine names only.

## Results

| Owner | Algorithm | Clients | Average ms | P95 ms | Lookups/s | Samples |
|---|---|---:|---:|---:|---:|---:|
| doctor | trie | 1 | 0.0025 | 0.0043 | 367959.4 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0022 | 0.0032 | 421894.1 | 100000 |
| doctor | python_scan_secondary | 1 | 1.5194 | 3.0832 | 657.8 | 1000 |
| doctor | trie | 1 | 0.0028 | 0.0049 | 337227.1 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0027 | 0.0047 | 343197.2 | 100000 |
| doctor | trie | 8 | 0.0091 | 0.0043 | 355766.8 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0098 | 0.0032 | 401994.6 | 100000 |
| doctor | trie | 8 | 0.0106 | 0.0048 | 332970.9 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0100 | 0.0048 | 332524.2 | 100000 |
| doctor | trie | 32 | 0.0067 | 0.0043 | 343911.7 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0067 | 0.0032 | 396809.7 | 100000 |
| doctor | trie | 32 | 0.0087 | 0.0050 | 326091.9 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0072 | 0.0047 | 329463.6 | 100000 |
| doctor | trie | 1 | 0.0025 | 0.0043 | 366285.5 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0022 | 0.0032 | 423438.6 | 100000 |
| doctor | python_scan_secondary | 1 | 1.7024 | 3.2207 | 587.1 | 1000 |
| doctor | trie | 1 | 0.0027 | 0.0048 | 347020.4 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0027 | 0.0046 | 350249.5 | 100000 |
| doctor | trie | 8 | 0.0073 | 0.0043 | 356010.5 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0067 | 0.0032 | 419170.9 | 100000 |
| doctor | trie | 8 | 0.0094 | 0.0049 | 331936.4 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0094 | 0.0047 | 341721.0 | 100000 |
| doctor | trie | 32 | 0.0078 | 0.0043 | 344081.1 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0059 | 0.0040 | 352024.5 | 100000 |
| doctor | trie | 32 | 0.0090 | 0.0049 | 326247.3 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0100 | 0.0047 | 330367.7 | 100000 |
| doctor | trie | 1 | 0.0025 | 0.0043 | 363752.8 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0022 | 0.0032 | 417394.0 | 100000 |
| doctor | python_scan_secondary | 1 | 1.5349 | 3.2095 | 651.1 | 1000 |
| doctor | trie | 1 | 0.0027 | 0.0048 | 345368.3 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0027 | 0.0047 | 344528.8 | 100000 |
| doctor | trie | 8 | 0.0106 | 0.0043 | 347833.2 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0067 | 0.0032 | 397043.9 | 100000 |
| doctor | trie | 8 | 0.0105 | 0.0048 | 327464.8 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0100 | 0.0046 | 329172.8 | 100000 |
| doctor | trie | 32 | 0.0077 | 0.0043 | 341886.2 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0074 | 0.0032 | 390979.0 | 100000 |
| doctor | trie | 32 | 0.0077 | 0.0049 | 326003.9 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0079 | 0.0047 | 326244.1 | 100000 |
| pharmacy | trie | 1 | 0.0021 | 0.0035 | 427815.9 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0024 | 0.0033 | 376511.3 | 100000 |
| pharmacy | python_scan_secondary | 1 | 1.2760 | 1.7274 | 783.2 | 1000 |
| pharmacy | trie | 1 | 0.0024 | 0.0040 | 383725.4 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0033 | 0.0051 | 289321.9 | 100000 |
| pharmacy | trie | 8 | 0.0068 | 0.0036 | 397181.8 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0091 | 0.0034 | 367059.8 | 100000 |
| pharmacy | trie | 8 | 0.0095 | 0.0041 | 364976.5 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0120 | 0.0050 | 281011.2 | 100000 |
| pharmacy | trie | 32 | 0.0050 | 0.0036 | 396269.1 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0070 | 0.0033 | 348348.4 | 100000 |
| pharmacy | trie | 32 | 0.0067 | 0.0040 | 336659.6 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0088 | 0.0051 | 275589.2 | 100000 |
| pharmacy | trie | 1 | 0.0022 | 0.0036 | 422602.1 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0024 | 0.0033 | 377830.4 | 100000 |
| pharmacy | python_scan_secondary | 1 | 1.2829 | 1.7520 | 779.0 | 1000 |
| pharmacy | trie | 1 | 0.0024 | 0.0041 | 378398.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0032 | 0.0049 | 291714.3 | 100000 |
| pharmacy | trie | 8 | 0.0068 | 0.0037 | 400730.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0082 | 0.0034 | 360494.3 | 100000 |
| pharmacy | trie | 8 | 0.0079 | 0.0041 | 364533.1 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0136 | 0.0051 | 277779.9 | 100000 |
| pharmacy | trie | 32 | 0.0051 | 0.0036 | 391980.5 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0076 | 0.0035 | 354872.3 | 100000 |
| pharmacy | trie | 32 | 0.0058 | 0.0040 | 357278.4 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0093 | 0.0050 | 274649.5 | 100000 |
| pharmacy | trie | 1 | 0.0022 | 0.0037 | 416519.9 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0025 | 0.0034 | 374691.1 | 100000 |
| pharmacy | python_scan_secondary | 1 | 1.2932 | 1.7813 | 772.8 | 1000 |
| pharmacy | trie | 1 | 0.0024 | 0.0040 | 382332.1 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0032 | 0.0050 | 286367.5 | 100000 |
| pharmacy | trie | 8 | 0.0088 | 0.0036 | 394803.9 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0081 | 0.0034 | 362876.4 | 100000 |
| pharmacy | trie | 8 | 0.0074 | 0.0043 | 349704.0 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0124 | 0.0051 | 278725.9 | 100000 |
| pharmacy | trie | 32 | 0.0062 | 0.0037 | 393661.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0077 | 0.0035 | 350700.4 | 100000 |
| pharmacy | trie | 32 | 0.0081 | 0.0040 | 361050.0 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0123 | 0.0050 | 271648.9 | 100000 |

## Index construction and memory

See `build.csv` for trie nodes, estimated retained object bytes, sorted-baseline estimated bytes, construction time, separately traced build-allocation peak, and observed process peak RSS. Trie bytes are an approximate Python object-size estimate; RSS and tracemalloc are separate measurements.

Default 64 MiB index-cap preflight: doctor=within limit, pharmacy=within limit. The timed high-cap trie uses a recorded 512 MiB experimental cap so 100k-entry cases can be measured; the deployed default remains 64 MiB.

## Correctness and scope

Trie and sorted-prefix outputs were checked for exact ordered top-K equality against the independent full string-scan oracle for each generated hot and missing prefix, at limits 10 and 20. `correctness.csv` contains the per-prefix oracle counts.

The primary baseline is an in-memory sorted string-prefix range that models the ordering behavior of a PostgreSQL prefix index. The full Python string scan is the correctness oracle and is also measured as a bounded secondary CPU baseline; its operation cap is reported because its O(n) cost grows with catalog size. This is a CPU-only algorithm benchmark: it does not include authenticated HTTP, PostgreSQL revision reads, selected-ID validation, or network latency, because the coordinator owns route mounting and migration integration.

Measurements use `perf_counter_ns`, 1,000 warmup calls per owner/algorithm/client/result-limit configuration, and closed-loop thread clients. Trie and sorted baseline each receive at least 100,000 timed operations per trial for limits 10 and 20. Tracemalloc runs in a separate build pass and is disabled during timed lookups. Throughput is completed lookups divided by wall time. P95 uses nearest-rank `ceil(0.95*n)-1`; no endpoint or service-level speedup is claimed.

Catalog SHA256: `2ec99d896c487edd4662a57d56eb37d1d6eb997d3e715028652fe8647df5bb7f`.
