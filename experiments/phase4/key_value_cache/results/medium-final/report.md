# Measured key-value cache adapter benchmark

Level medium; 3 trials with seeds 404..406; 5s warmup and 30s measurement per scenario.

| Scenario | Mean ms | p95 ms | Reads/s | Hit ratio | DB queries/read |
|---|---:|---:|---:|---:|---:|
| uncached | 41.376 | 49.694 | 193.3 | n/a | 1.000 |
| cold | 33.866 | 49.045 | 218.5 | 0.13612804878048781 | 1.864 |
| warm | 3.325 | 4.031 | 2402.8 | 0.9996901948997757 | 1.000 |
| invalidation | 3.845 | 4.381 | 2077.7 | 0.9816475495307612 | 1.018 |
| redis_failure | 3.664 | 4.428 | 2179.7 | 0.999657339831943 | 1.004 |

p95 is nearest-rank per trial; displayed values average the three trial summaries, not pooled percentiles. Full trial variation, counts and failure denominators are in summary.csv.

Adapter/owner PostgreSQL benchmark; authenticated HTTP and fresh wire reconstruction remain coordinator work.
Test-only DDL, no production migration.
Cold explicitly deletes selected key before each read; throughput includes deletion, read latency excludes preparation; concurrent readers may repopulate.
Invalidation uses atomic DB revision mutation; no shared mutation hooks mounted.
Redis failure pauses both owned nodes for 2 seconds and restores; results include recovery.
No real consistent ring or HA claim.
No OS/container resource limits imposed.

Unindexed diagnostic fixture: only primary-key indexes; existing Doctor secondary read indexes omitted. Not the frozen authenticated owner endpoint baseline.
