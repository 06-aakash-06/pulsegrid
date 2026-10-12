# Measured unique ID comparison

Measured trials (see summary.csv seed/repeat), 5-second warmup per mode. Pipeline includes allocation and one PostgreSQL INSERT; generation includes ownership check/reservation for Snowflake. All counts are measured.

- csprng: IDs/s [22086, 18959, 16501]; pipeline p95 us [487.1, 453.2, 621.2]; observed collisions 0 across 1200000 measured IDs.
- sequence: IDs/s [7703, 13192, 14489]; pipeline p95 us [1411.2, 841.0, 649.8]; observed collisions 0 across 1200000 measured IDs.
- snowflake: IDs/s [10449, 10567, 10849]; pipeline p95 us [933.8, 977.5, 881.7]; observed collisions 0 across 1200000 measured IDs.

No global uniqueness claim across legacy IDs or independent owner databases with conflicting worker assignments. PostgreSQL 16 and hospital integration remain coordinator gates.
