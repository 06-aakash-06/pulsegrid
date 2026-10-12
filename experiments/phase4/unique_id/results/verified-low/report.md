# Measured unique ID comparison

Measured trials (see summary.csv seed/repeat), 5-second warmup per mode. Pipeline includes allocation and one PostgreSQL INSERT; generation includes ownership check/reservation for Snowflake. All counts are measured.

- csprng: IDs/s [12438, 6045, 6274]; pipeline p95 us [121.6, 167.9, 164.9]; observed collisions 0 across 300000 measured IDs.
- sequence: IDs/s [7836, 5173, 3271]; pipeline p95 us [209.1, 245.8, 306.5]; observed collisions 0 across 300000 measured IDs.
- snowflake: IDs/s [3199, 5587, 2806]; pipeline p95 us [346.8, 296.7, 363.8]; observed collisions 0 across 300000 measured IDs.

No global uniqueness claim across legacy IDs or independent owner databases with conflicting worker assignments. PostgreSQL 16 and hospital integration remain coordinator gates.
