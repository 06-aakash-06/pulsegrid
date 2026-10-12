# Measured key-value cache adapter benchmark

Level medium; 3 trials with seeds 404..406; 5.0s warmup and 30.0s measurement per scenario.

| Scenario | Mean ms | p95 ms | Reads/s | Hit ratio | DB queries/read |
|---|---:|---:|---:|---:|---:|
| uncached | 4.484 | 6.444 | 1946.4 | n/a | 1.000 |
| cold | 8.342 | 12.012 | 728.2 | 0.0028982854353529807 | 1.997 |
| warm | 3.053 | 3.803 | 2616.2 | 0.9997621808020453 | 1.000 |
| invalidation | 3.435 | 5.197 | 2336.0 | 0.985821506030973 | 1.014 |
| redis_failure | 3.425 | 4.204 | 2335.6 | 0.9997278365873573 | 1.004 |

p95 is nearest-rank per trial; displayed values average the three trial summaries, not pooled percentiles. Full trial variation, counts and failure denominators are in summary.csv.

Adapter/owner PostgreSQL benchmark; authenticated HTTP and fresh wire reconstruction remain coordinator work.
Test-only DDL, no production migration.
Cold explicitly deletes selected key before each read; throughput includes deletion, read latency excludes preparation; concurrent readers may repopulate.
Invalidation uses atomic DB revision mutation; no shared mutation hooks mounted.
Redis failure pauses both owned nodes for 2 seconds and restores; results include recovery.
Actual HashRing placement is used; no replication/HA claim.
No OS/container resource limits imposed.

Coordinator rerun: actual production HashRing placement, existing Doctor query indexes, full5s warmup/30s x3. This remains a storage adapter benchmark; authenticated endpoint samples are separate.
