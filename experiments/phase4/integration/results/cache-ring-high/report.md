# Measured key-value cache adapter benchmark

Level high; 3 trials with seeds 404..406; 5.0s warmup and 30.0s measurement per scenario.

| Scenario | Mean ms | p95 ms | Reads/s | Hit ratio | DB queries/read |
|---|---:|---:|---:|---:|---:|
| uncached | 25.565 | 36.418 | 1754.9 | n/a | 1.000 |
| cold | 30.405 | 49.833 | 784.2 | 0.03329415263478396 | 1.967 |
| warm | 12.619 | 15.836 | 2535.1 | 0.9994522900846978 | 1.001 |
| invalidation | 13.168 | 25.802 | 2429.0 | 0.9677410506103415 | 1.032 |
| redis_failure | 13.575 | 23.304 | 2361.6 | 0.9994146508606536 | 1.012 |

p95 is nearest-rank per trial; displayed values average the three trial summaries, not pooled percentiles. Full trial variation, counts and failure denominators are in summary.csv.

Adapter/owner PostgreSQL benchmark; authenticated HTTP and fresh wire reconstruction remain coordinator work.
Test-only DDL, no production migration.
Cold explicitly deletes selected key before each read; throughput includes deletion, read latency excludes preparation; concurrent readers may repopulate.
Invalidation uses atomic DB revision mutation; no shared mutation hooks mounted.
Redis failure pauses both owned nodes for 2 seconds and restores; results include recovery.
Actual HashRing placement is used; no replication/HA claim.
No OS/container resource limits imposed.

Coordinator rerun: actual production HashRing placement, existing Doctor query indexes, full5s warmup/30s x3. This remains a storage adapter benchmark; authenticated endpoint samples are separate.
