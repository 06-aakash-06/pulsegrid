> Preliminary, superseded by the combined authoritative comparison.

# Measured unique ID comparison

Three trials, seeds 404/405/406, 5-second warmup per mode. Pipeline includes allocation and one PostgreSQL INSERT; generation includes ownership check/reservation for Snowflake. All counts are measured.

- csprng: IDs/s [18957, 19824, 19159]; pipeline p95 us [82.9, 73.9, 79.8]; observed collisions 0 across 300000 measured IDs.
- sequence: IDs/s [11134, 9521, 9905]; pipeline p95 us [135.2, 161.3, 158.0]; observed collisions 0 across 300000 measured IDs.
- snowflake: IDs/s [5875, 5235, 5612]; pipeline p95 us [259.0, 292.4, 267.8]; observed collisions 0 across 300000 measured IDs.

No global uniqueness claim across legacy IDs or independent owner databases with conflicting worker assignments. PostgreSQL 16 and hospital integration remain coordinator gates.
