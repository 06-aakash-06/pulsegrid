# Measured key-value cache adapter benchmark

Level high; 3 trials with seeds 404..406; 5s warmup and 30s measurement per scenario.

| Scenario | Mean ms | p95 ms | Reads/s | Hit ratio | DB queries/read |
|---|---:|---:|---:|---:|---:|
| uncached | 1032.664 | 1222.687 | 30.8 | n/a | 1.000 |
| cold | 892.212 | 1186.218 | 35.4 | 0.1007105344454742 | 1.899 |
| warm | 14.622 | 18.670 | 2191.7 | 0.9992195062616884 | 1.001 |
| invalidation | 456.455 | 1215.246 | 69.7 | 0.5816358508304607 | 1.418 |
| redis_failure | 15.622 | 17.083 | 2047.3 | 0.9990928695198726 | 1.002 |

p95 is nearest-rank per trial; displayed values average the three trial summaries, not pooled percentiles. Full trial variation, counts and failure denominators are in summary.csv.

Adapter/owner PostgreSQL benchmark; authenticated HTTP and fresh wire reconstruction remain coordinator work.
Test-only DDL, no production migration.
Cold explicitly deletes selected key before each read; throughput includes deletion, read latency excludes preparation; concurrent readers may repopulate.
Invalidation uses atomic DB revision mutation; no shared mutation hooks mounted.
Redis failure pauses both owned nodes for 2 seconds and restores; results include recovery.
No real consistent ring or HA claim.
No OS/container resource limits imposed.

Unindexed diagnostic fixture: only primary-key indexes; existing Doctor secondary read indexes omitted. Not the frozen authenticated owner endpoint baseline.
