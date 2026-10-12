# Measured unique ID comparison

Measured trials (see summary.csv seed/repeat), 5-second warmup per mode. Pipeline includes allocation and one PostgreSQL INSERT; generation includes ownership check/reservation for Snowflake. All counts are measured.

- csprng: IDs/s [17322]; pipeline p95 us [3913.6]; observed collisions 0 across 1000000 measured IDs.
- sequence: IDs/s [13658]; pipeline p95 us [3002.6]; observed collisions 0 across 1000000 measured IDs.
- snowflake: IDs/s [5485]; pipeline p95 us [18667.2]; observed collisions 0 across 1000000 measured IDs.

No global uniqueness claim across legacy IDs or independent owner databases with conflicting worker assignments. PostgreSQL 16 and hospital integration remain coordinator gates.
