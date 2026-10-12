# PulseGrid unique IDs

Independent technical library, no service mounts, entity models or migrations.
Default layout: 41 UTC-millisecond bits since 2026-01-01, 10 worker bits,
12 sequence bits. Positive signed BIGINT, return Python int; serialize as decimal
string at owner boundary. Configure epoch/bit allocation only for a fresh ID
namespace, never change them for an existing entity family. PostgreSQL worker
store supports worker 0..1023; production uses the frozen 41/10/12 layout.

```python
from pulsegrid_unique_id import Config, Generator, PostgresWorkerStore, worker_identity

generator = Generator(Config(worker_identity(2, explicit_process_replica)),
                      PostgresWorkerStore(owner_dsn), observer=observer)
await generator.start()
allocate_id = generator.next_id  # inject into short-link/insurance ports
new_id = await allocate_id()    # BEFORE the business transaction and locks
# On shutdown: await generator.close()
```

DSN must be the consuming owner's database and runtime credentials. Existing
`id_worker_state(worker_id, reserved_through_ms)` is reused; no migration needed
for Appointment/Billing. Dedicated session advisory lock `(74104,worker_id)`
blocks duplicates in the same database. Reservation atomically advances the
committed absolute-UTC high watermark; restarts skip the whole old range, even
if business INSERT rolled back. Default 100 ms ranges, maximum 1000 ms, 2000 ms
allocation deadline including queue wait/I/O/real-clock waiting. Overflow waits
for real time; any backward wall-clock movement poisons the generator. Close
and explicit restart required; store errors never cause silent reconnect.

Each OS process needs a unique explicit worker assignment: service codes 0..6
and replica codes 0..127, including rolling deployments and multiple web workers.
No default replica, DNS hash, PID or random worker assignment. PostgreSQL locks
are local to each database: infrastructure MUST ensure identical worker codes
are never allocated in independent owner databases/clusters. Deployment must
pin service code to owner, keep replicas disjoint during rollout, forbid arbitrary
worker overrides and provision one extra dedicated connection/process. Loss of
ownership blocks output. Disjoint committed ranges fence an old session's late
output after replacement. Do not reset/truncate worker state in deployment.
A database restore to older high watermarks requires a new worker namespace or
waiting past all ranges previously allocated; restoration safety is operational.

`IdUnavailable` is fail-closed; safe reason strings include worker_conflict,
clock_rollback, invalid_timestamp, ownership_lost, deadline_exceeded,
store_unavailable and not_owned. Configuration/decode errors are ValueError.
Await next_id from one event loop; concurrency serialized per generator. Do not
fork/reuse a live connection or generator; create/start after fork. Metrics are
best-effort and cannot change output. Collision counts belong to the owner's PK
insert/retry handler; the generator cannot see entity insert outcomes.

Coordinator rollout: shadow first, then enable only new short-link and insurance
run/rule/estimate entities with their PK and stable business uniqueness. Keep all
legacy IDs/URLs/allocators unchanged; never infer format from bits. Mixed legacy
tables require a PK backstop and at most three fresh allocations after WHOLE
command rollback on specifically identified PK collision, never retry arbitrary
integrity errors. No global monotonic ordering across workers or uniqueness
promise against legacy random IDs. An ID grants no access.

Test command (dedicated disposable test DB only):
`PYTHONPATH=components/unique_id ID_TEST_DSN=... python -m pytest -q components/unique_id/tests`.
