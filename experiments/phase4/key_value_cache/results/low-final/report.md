# Measured key-value cache adapter benchmark

Level low; 3 trials with seeds 404..406; 5s warmup and 30s measurement per scenario.

| Scenario | Mean ms | p95 ms | Reads/s | Hit ratio | DB queries/read |
|---|---:|---:|---:|---:|---:|
| uncached | 1.527 | 1.791 | 673.2 | n/a | 1.000 |
| cold | 2.277 | 2.898 | 352.5 | 0.0 | 2.000 |
| warm | 0.630 | 0.848 | 1571.7 | 0.9997879154206698 | 1.000 |
| invalidation | 0.656 | 0.888 | 1511.9 | 0.9869923717976983 | 1.013 |
| redis_failure | 0.650 | 0.824 | 1522.4 | 0.9997808667450677 | 1.001 |

p95 is nearest-rank per trial; displayed values average the three trial summaries, not pooled percentiles. Full trial variation, counts and failure denominators are in summary.csv.

Adapter/owner PostgreSQL benchmark; authenticated HTTP and fresh wire reconstruction remain coordinator work.
Test-only DDL, no production migration.
Cold explicitly deletes selected key before each read; throughput includes deletion, read latency excludes preparation; concurrent readers may repopulate.
Invalidation uses atomic DB revision mutation; no shared mutation hooks mounted.
Redis failure pauses both owned nodes for 2 seconds and restores; results include recovery.
No real consistent ring or HA claim.
No OS/container resource limits imposed.

Unindexed diagnostic fixture: only primary-key indexes; existing Doctor secondary read indexes omitted. Not the frozen authenticated owner endpoint baseline.
