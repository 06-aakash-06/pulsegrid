> Preliminary, superseded by the combined authoritative comparison.

# Measured unique ID comparison

Measured trials (see summary.csv seed/repeat), 5-second warmup per mode. Pipeline includes allocation and one PostgreSQL INSERT; generation includes ownership check/reservation for Snowflake. All counts are measured.

- csprng: IDs/s [26928, 26881, 26407]; pipeline p95 us [364.0, 368.4, 375.5]; observed collisions 0 across 1200000 measured IDs.
- sequence: IDs/s [14207, 13960, 14002]; pipeline p95 us [675.2, 692.9, 683.9]; observed collisions 0 across 1200000 measured IDs.
- snowflake: IDs/s [10850, 10780, 10934]; pipeline p95 us [929.1, 930.1, 895.2]; observed collisions 0 across 1200000 measured IDs.

No global uniqueness claim across legacy IDs or independent owner databases with conflicting worker assignments. PostgreSQL 16 and hospital integration remain coordinator gates.
