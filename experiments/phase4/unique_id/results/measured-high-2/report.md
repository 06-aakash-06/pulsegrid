# Measured unique ID comparison

Measured trials (see summary.csv seed/repeat), 5-second warmup per mode. Pipeline includes allocation and one PostgreSQL INSERT; generation includes ownership check/reservation for Snowflake. All counts are measured.

- csprng: IDs/s [17941]; pipeline p95 us [3481.0]; observed collisions 0 across 1000000 measured IDs.
- sequence: IDs/s [13557]; pipeline p95 us [3514.0]; observed collisions 0 across 1000000 measured IDs.
- snowflake: IDs/s [10793]; pipeline p95 us [4288.5]; observed collisions 0 across 1000000 measured IDs.

No global uniqueness claim across legacy IDs or independent owner databases with conflicting worker assignments. PostgreSQL 16 and hospital integration remain coordinator gates.
