> Preliminary, superseded by the combined authoritative comparison.

# Measured unique ID comparison

Measured trials (see summary.csv seed/repeat), 5-second warmup per mode. Pipeline includes allocation and one PostgreSQL INSERT; generation includes ownership check/reservation for Snowflake. All counts are measured.

- csprng: IDs/s [18900, 15396, 14836]; pipeline p95 us [82.6, 94.0, 99.6]; observed collisions 0 across 300000 measured IDs.
- sequence: IDs/s [9078, 9349, 8974]; pipeline p95 us [177.7, 159.5, 164.7]; observed collisions 0 across 300000 measured IDs.
- snowflake: IDs/s [6092, 5867, 5701]; pipeline p95 us [226.5, 234.5, 236.0]; observed collisions 0 across 300000 measured IDs.

No global uniqueness claim across legacy IDs or independent owner databases with conflicting worker assignments. PostgreSQL 16 and hospital integration remain coordinator gates.
