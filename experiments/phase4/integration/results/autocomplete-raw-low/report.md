# Autocomplete benchmark: low

Dataset seed: `404`. Generated owner catalogs contain 1,000 entries each; the Doctor catalog includes active-doctor and specialty kinds, while the Pharmacy catalog contains active-medicine names only.

## Results

| Owner | Algorithm | Clients | Average ms | P95 ms | Lookups/s | Samples |
|---|---|---:|---:|---:|---:|---:|
| doctor | trie | 1 | 0.0025 | 0.0043 | 377675.8 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0020 | 0.0030 | 467591.1 | 100000 |
| doctor | python_scan_secondary | 1 | 0.1435 | 0.2904 | 6950.5 | 10000 |
| doctor | trie | 1 | 0.0027 | 0.0048 | 353048.2 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0024 | 0.0044 | 383977.1 | 100000 |
| doctor | trie | 8 | 0.0089 | 0.0043 | 363271.7 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0059 | 0.0029 | 472596.5 | 100000 |
| doctor | trie | 8 | 0.0086 | 0.0048 | 337982.1 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0113 | 0.0045 | 381930.5 | 100000 |
| doctor | trie | 32 | 0.0057 | 0.0044 | 349134.7 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0046 | 0.0030 | 439251.2 | 100000 |
| doctor | trie | 32 | 0.0077 | 0.0047 | 331380.6 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0095 | 0.0044 | 364840.2 | 100000 |
| doctor | trie | 1 | 0.0025 | 0.0043 | 378692.6 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0019 | 0.0029 | 481052.0 | 100000 |
| doctor | python_scan_secondary | 1 | 0.1437 | 0.2910 | 6937.0 | 10000 |
| doctor | trie | 1 | 0.0027 | 0.0049 | 346514.9 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0025 | 0.0045 | 384034.0 | 100000 |
| doctor | trie | 8 | 0.0083 | 0.0043 | 362127.7 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0063 | 0.0029 | 471662.9 | 100000 |
| doctor | trie | 8 | 0.0091 | 0.0047 | 342176.7 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0077 | 0.0044 | 382520.4 | 100000 |
| doctor | trie | 32 | 0.0060 | 0.0043 | 348610.5 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0052 | 0.0030 | 443285.0 | 100000 |
| doctor | trie | 32 | 0.0066 | 0.0047 | 329440.4 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0056 | 0.0045 | 357988.2 | 100000 |
| doctor | trie | 1 | 0.0026 | 0.0045 | 364478.8 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0020 | 0.0030 | 466650.4 | 100000 |
| doctor | python_scan_secondary | 1 | 0.1521 | 0.2965 | 6556.5 | 10000 |
| doctor | trie | 1 | 0.0027 | 0.0049 | 346255.8 | 100000 |
| doctor | sorted_prefix_baseline | 1 | 0.0025 | 0.0046 | 369872.6 | 100000 |
| doctor | trie | 8 | 0.0067 | 0.0045 | 325319.5 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0104 | 0.0030 | 461501.5 | 100000 |
| doctor | trie | 8 | 0.0121 | 0.0049 | 333556.9 | 100000 |
| doctor | sorted_prefix_baseline | 8 | 0.0100 | 0.0046 | 369622.3 | 100000 |
| doctor | trie | 32 | 0.0073 | 0.0044 | 349688.8 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0039 | 0.0030 | 431511.3 | 100000 |
| doctor | trie | 32 | 0.0092 | 0.0048 | 327257.8 | 100000 |
| doctor | sorted_prefix_baseline | 32 | 0.0075 | 0.0044 | 355218.9 | 100000 |
| pharmacy | trie | 1 | 0.0022 | 0.0037 | 426176.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0021 | 0.0029 | 438304.8 | 100000 |
| pharmacy | python_scan_secondary | 1 | 0.1226 | 0.1672 | 8137.2 | 10000 |
| pharmacy | trie | 1 | 0.0024 | 0.0042 | 381013.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0029 | 0.0046 | 323506.2 | 100000 |
| pharmacy | trie | 8 | 0.0066 | 0.0035 | 413649.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0063 | 0.0030 | 428264.8 | 100000 |
| pharmacy | trie | 8 | 0.0072 | 0.0040 | 380088.4 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0109 | 0.0045 | 322151.4 | 100000 |
| pharmacy | trie | 32 | 0.0060 | 0.0035 | 398603.4 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0057 | 0.0030 | 405576.4 | 100000 |
| pharmacy | trie | 32 | 0.0055 | 0.0042 | 360259.7 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0073 | 0.0047 | 301765.4 | 100000 |
| pharmacy | trie | 1 | 0.0021 | 0.0036 | 438494.4 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0021 | 0.0030 | 437603.9 | 100000 |
| pharmacy | python_scan_secondary | 1 | 0.1197 | 0.1632 | 8328.5 | 10000 |
| pharmacy | trie | 1 | 0.0024 | 0.0040 | 389676.2 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0029 | 0.0045 | 326388.2 | 100000 |
| pharmacy | trie | 8 | 0.0070 | 0.0035 | 413037.2 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0071 | 0.0030 | 424091.7 | 100000 |
| pharmacy | trie | 8 | 0.0084 | 0.0040 | 372818.2 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0104 | 0.0046 | 314852.9 | 100000 |
| pharmacy | trie | 32 | 0.0045 | 0.0035 | 396229.2 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0055 | 0.0030 | 401971.8 | 100000 |
| pharmacy | trie | 32 | 0.0053 | 0.0042 | 355044.6 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0092 | 0.0044 | 305493.6 | 100000 |
| pharmacy | trie | 1 | 0.0021 | 0.0035 | 434532.2 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0021 | 0.0030 | 435132.8 | 100000 |
| pharmacy | python_scan_secondary | 1 | 0.1211 | 0.1656 | 8232.5 | 10000 |
| pharmacy | trie | 1 | 0.0024 | 0.0041 | 391639.0 | 100000 |
| pharmacy | sorted_prefix_baseline | 1 | 0.0029 | 0.0045 | 323009.4 | 100000 |
| pharmacy | trie | 8 | 0.0074 | 0.0036 | 415223.5 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0082 | 0.0030 | 424796.5 | 100000 |
| pharmacy | trie | 8 | 0.0090 | 0.0041 | 376788.9 | 100000 |
| pharmacy | sorted_prefix_baseline | 8 | 0.0094 | 0.0045 | 316911.3 | 100000 |
| pharmacy | trie | 32 | 0.0051 | 0.0035 | 401233.3 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0061 | 0.0030 | 404473.0 | 100000 |
| pharmacy | trie | 32 | 0.0062 | 0.0042 | 363072.4 | 100000 |
| pharmacy | sorted_prefix_baseline | 32 | 0.0100 | 0.0044 | 306632.5 | 100000 |

## Index construction and memory

See `build.csv` for trie nodes, estimated retained object bytes, sorted-baseline estimated bytes, construction time, separately traced build-allocation peak, and observed process peak RSS. Trie bytes are an approximate Python object-size estimate; RSS and tracemalloc are separate measurements.

Default 64 MiB index-cap preflight: doctor=within limit, pharmacy=within limit. The timed high-cap trie uses a recorded 512 MiB experimental cap so 100k-entry cases can be measured; the deployed default remains 64 MiB.

## Correctness and scope

Trie and sorted-prefix outputs were checked for exact ordered top-K equality against the independent full string-scan oracle for each generated hot and missing prefix, at limits 10 and 20. `correctness.csv` contains the per-prefix oracle counts.

The primary baseline is an in-memory sorted string-prefix range that models the ordering behavior of a PostgreSQL prefix index. The full Python string scan is the correctness oracle and is also measured as a bounded secondary CPU baseline; its operation cap is reported because its O(n) cost grows with catalog size. This is a CPU-only algorithm benchmark: it does not include authenticated HTTP, PostgreSQL revision reads, selected-ID validation, or network latency, because the coordinator owns route mounting and migration integration.

Measurements use `perf_counter_ns`, 1,000 warmup calls per owner/algorithm/client/result-limit configuration, and closed-loop thread clients. Trie and sorted baseline each receive at least 100,000 timed operations per trial for limits 10 and 20. Tracemalloc runs in a separate build pass and is disabled during timed lookups. Throughput is completed lookups divided by wall time. P95 uses nearest-rank `ceil(0.95*n)-1`; no endpoint or service-level speedup is claimed.

Catalog SHA256: `73c39c75ff6fbb415410fef0a50866df525a1a0c5bbde89a80295c6d419a3ff2`.
