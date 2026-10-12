# Measured key-value cache adapter benchmark

Level low; 3 trials with seeds 404..406; 0.2s warmup and 3.0s measurement per scenario.

| Scenario | Mean ms | p95 ms | Reads/s | Hit ratio | DB queries/read |
|---|---:|---:|---:|---:|---:|
| uncached | 2.084 | 2.440 | 479.1 | n/a | 1.000 |
| cold | 2.682 | 3.055 | 307.8 | 0.0 | 2.000 |
| warm | 0.675 | 0.904 | 1474.7 | 1.0 | 1.000 |
| invalidation | 0.649 | 0.811 | 1528.8 | 0.9890996293873991 | 1.011 |
| redis_failure | 1.859 | 0.775 | 538.2 | 1.0 | 1.012 |

p95 is nearest-rank per trial; displayed values average the three trial summaries, not pooled percentiles. Full trial variation, counts and failure denominators are in summary.csv.

Adapter/owner PostgreSQL benchmark; authenticated HTTP and fresh wire reconstruction remain coordinator work.
Test-only DDL, no production migration.
Cold explicitly deletes selected key before each read; throughput includes deletion, read latency excludes preparation; concurrent readers may repopulate.
Invalidation uses atomic DB revision mutation; no shared mutation hooks mounted.
Redis failure pauses both owned nodes for 2 seconds and restores; results include recovery.
No real consistent ring or HA claim.
No OS/container resource limits imposed.
