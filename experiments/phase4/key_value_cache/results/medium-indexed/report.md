# Measured key-value cache adapter benchmark

Level medium; 3 trials with seeds 404..406; 0.2s warmup and 3s measurement per scenario.

| Scenario | Mean ms | p95 ms | Reads/s | Hit ratio | DB queries/read |
|---|---:|---:|---:|---:|---:|
| uncached | 6.600 | 8.682 | 1210.9 | n/a | 1.000 |
| cold | 10.022 | 12.320 | 615.6 | 0.028622862286228623 | 1.971 |
| warm | 3.389 | 4.184 | 2357.5 | 1.0 | 1.000 |
| invalidation | 3.464 | 4.224 | 2305.7 | 0.9870442614265761 | 1.013 |
| redis_failure | 9.364 | 61.350 | 853.9 | 1.0 | 1.101 |

p95 is nearest-rank per trial; displayed values average the three trial summaries, not pooled percentiles. Full trial variation, counts and failure denominators are in summary.csv.

Adapter/owner PostgreSQL benchmark; authenticated HTTP and fresh wire reconstruction remain coordinator work.
Test-only DDL, no production migration.
Cold explicitly deletes selected key before each read; throughput includes deletion, read latency excludes preparation; concurrent readers may repopulate.
Invalidation uses atomic DB revision mutation; no shared mutation hooks mounted.
Redis failure pauses both owned nodes for 2 seconds and restores; results include recovery.
No real consistent ring or HA claim.
No OS/container resource limits imposed.

Existing Doctor query-relevant secondary indexes included (see manifest). This short sensitivity run is not frozen-duration HTTP acceptance.
