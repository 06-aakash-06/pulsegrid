# Measured key-value cache adapter benchmark

Level high; 3 trials with seeds 404..406; 0.2s warmup and 3s measurement per scenario.

| Scenario | Mean ms | p95 ms | Reads/s | Hit ratio | DB queries/read |
|---|---:|---:|---:|---:|---:|
| uncached | 59.857 | 92.768 | 532.4 | n/a | 1.000 |
| cold | 54.097 | 84.066 | 467.0 | 0.2338879775017577 | 1.766 |
| warm | 13.314 | 14.854 | 2399.0 | 0.9995843724023276 | 1.000 |
| invalidation | 15.019 | 16.703 | 2126.5 | 0.9672173867722937 | 1.033 |
| redis_failure | 33.584 | 123.027 | 951.2 | 0.9981284192340916 | 1.192 |

p95 is nearest-rank per trial; displayed values average the three trial summaries, not pooled percentiles. Full trial variation, counts and failure denominators are in summary.csv.

Adapter/owner PostgreSQL benchmark; authenticated HTTP and fresh wire reconstruction remain coordinator work.
Test-only DDL, no production migration.
Cold explicitly deletes selected key before each read; throughput includes deletion, read latency excludes preparation; concurrent readers may repopulate.
Invalidation uses atomic DB revision mutation; no shared mutation hooks mounted.
Redis failure pauses both owned nodes for 2 seconds and restores; results include recovery.
No real consistent ring or HA claim.
No OS/container resource limits imposed.

Existing Doctor query-relevant secondary indexes included (see manifest). This short sensitivity run is not frozen-duration HTTP acceptance.
