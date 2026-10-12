# Measured key-value cache adapter benchmark

Level low; 3 trials with seeds 404..406; 0.2s warmup and 3s measurement per scenario.

| Scenario | Mean ms | p95 ms | Reads/s | Hit ratio | DB queries/read |
|---|---:|---:|---:|---:|---:|
| uncached | 1.543 | 1.909 | 644.4 | n/a | 1.000 |
| cold | 2.412 | 3.023 | 329.5 | 0.0 | 2.000 |
| warm | 0.652 | 0.852 | 1516.8 | 1.0 | 1.000 |
| invalidation | 0.674 | 0.909 | 1465.5 | 0.9886294724075197 | 1.011 |
| redis_failure | 1.974 | 1.007 | 504.5 | 1.0 | 1.024 |

p95 is nearest-rank per trial; displayed values average the three trial summaries, not pooled percentiles. Full trial variation, counts and failure denominators are in summary.csv.

Adapter/owner PostgreSQL benchmark; authenticated HTTP and fresh wire reconstruction remain coordinator work.
Test-only DDL, no production migration.
Cold explicitly deletes selected key before each read; throughput includes deletion, read latency excludes preparation; concurrent readers may repopulate.
Invalidation uses atomic DB revision mutation; no shared mutation hooks mounted.
Redis failure pauses both owned nodes for 2 seconds and restores; results include recovery.
No real consistent ring or HA claim.
No OS/container resource limits imposed.

Existing Doctor query-relevant secondary indexes included (see manifest). This short sensitivity run is not frozen-duration HTTP acceptance.
