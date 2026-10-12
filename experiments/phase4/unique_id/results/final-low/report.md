> Preliminary, superseded by the combined authoritative comparison.

# Measured unique ID comparison

Measured trials (see summary.csv seed/repeat), 5-second warmup per mode. Pipeline includes allocation and one PostgreSQL INSERT; generation includes ownership check/reservation for Snowflake. All counts are measured.

- csprng: IDs/s [13758, 16796, 14688]; pipeline p95 us [113.3, 90.8, 111.5]; observed collisions 0 across 300000 measured IDs.
- sequence: IDs/s [8908, 7673, 9470]; pipeline p95 us [171.4, 230.1, 161.8]; observed collisions 0 across 300000 measured IDs.
- snowflake: IDs/s [5818, 6094, 6002]; pipeline p95 us [262.7, 249.6, 255.1]; observed collisions 0 across 300000 measured IDs.

No global uniqueness claim across legacy IDs or independent owner databases with conflicting worker assignments. PostgreSQL 16 and hospital integration remain coordinator gates.
