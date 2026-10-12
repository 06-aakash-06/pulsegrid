# Measured unique ID comparison

Measured trials (see summary.csv seed/repeat), 5-second warmup per mode. Pipeline includes allocation and one PostgreSQL INSERT; generation includes ownership check/reservation for Snowflake. All counts are measured.

- csprng: IDs/s [27370]; pipeline p95 us [1379.5]; observed collisions 0 across 1000000 measured IDs.
- sequence: IDs/s [13552]; pipeline p95 us [3453.1]; observed collisions 0 across 1000000 measured IDs.
- snowflake: IDs/s [10172]; pipeline p95 us [6083.0]; observed collisions 0 across 1000000 measured IDs.

No global uniqueness claim across legacy IDs or independent owner databases with conflicting worker assignments. PostgreSQL 16 and hospital integration remain coordinator gates.
