# Measured key-value cache adapter benchmark

Level low; 3 trials with seeds 404..406; 5.0s warmup and 30.0s measurement per scenario.

| Scenario | Mean ms | p95 ms | Reads/s | Hit ratio | DB queries/read |
|---|---:|---:|---:|---:|---:|
| uncached | 1.397 | 1.761 | 712.2 | n/a | 1.000 |
| cold | 2.393 | 3.067 | 320.6 | 0.0 | 2.000 |
| warm | 0.686 | 1.010 | 1442.4 | 0.9997689072393658 | 1.000 |
| invalidation | 0.722 | 1.109 | 1369.7 | 0.9856417411619645 | 1.014 |
| redis_failure | 0.722 | 0.949 | 1372.5 | 0.9997569393806816 | 1.001 |

p95 is nearest-rank per trial; displayed values average the three trial summaries, not pooled percentiles. Full trial variation, counts and failure denominators are in summary.csv.

Adapter/owner PostgreSQL benchmark; authenticated HTTP and fresh wire reconstruction remain coordinator work.
Test-only DDL, no production migration.
Cold explicitly deletes selected key before each read; throughput includes deletion, read latency excludes preparation; concurrent readers may repopulate.
Invalidation uses atomic DB revision mutation; no shared mutation hooks mounted.
Redis failure pauses both owned nodes for 2 seconds and restores; results include recovery.
Actual ring placement; no replication/HA.
No OS/container resource limits imposed.

Coordinator rerun: actual production HashRing placement, existing Doctor query indexes, full5s warmup/30s x3. This remains a storage adapter benchmark; authenticated endpoint samples are separate.
