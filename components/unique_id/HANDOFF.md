# Phase 4.4 integration handoff

Branch `phase4/unique-id`; base `45273ea7fd1ea53e335942b6c38f2d81d38856ee`.
Final SHA is the commit containing this file (reported after commit).
Changes confined to `components/unique_id/**` and
`experiments/phase4/unique_id/**`. No entrypoints, entity primary keys, existing
migrations, models, service packages, root configuration or contracts changed.

Exports: Config, Reservation, WorkerStore protocol, Generator,
PostgresWorkerStore, IdUnavailable, worker_identity, EPOCH_MS.
Generator start/next_id/close are async; decode/health synchronous.
Inject the bound next_id as `async allocate_id() -> int` into Agent 5/6 ports.
No routes or mounting order introduced. Package is independently versioned
0.1.0, psycopg[binary] pinned 3.2.10. requirements-test.txt records test pins.
Wheel builds; consuming images/pinned installation are coordinator work.

Schema: existing owner id_worker_state, same worker_id PK and absolute UTC
reserved_through_ms, no DDL/migration shipped by runtime. All test DDL resides
in owned tests/experiments and uses disposable storage. PostgreSQL transaction
UPSERT takes row lock and commits independently of business transaction. Lock
(74104,worker_id) held on dedicated session; before each ID SELECT verifies the
current session actually owns the lock. Generator never reconnects. Reservations
fence late old-process output against replacement ranges; must persist across
business rollback, process crash and restart. Database restore to stale state
is an operational safety boundary, not automatically fenced.

Worker safety: map Patient0, Doctor1, Appointment2, Records3, Pharmacy4, Billing5,
Emergency6; replica0..127; service7 rejected in the frozen 10-bit configuration.
Every process, including web workers and overlapping deployments, needs a unique
explicit assignment. Duplicate same-DB process fails at start. Locks are not
cross-database: coordinator MUST bind service codes to owners and prevent
same worker IDs across independent clusters/DSNs; do not promise global locks.
Extra connection per generator must be included in PostgreSQL connection budget.
Epoch/bit allocation immutable for adopted entities; default frozen 41/10/12.
Alternative positive bit allocations totaling63 are isolated experimental
namespaces only. Zero slot at epoch/worker0 is skipped to keep positive wire IDs.

Activate shadow first. Allocate before business locks/transaction, then only
adopt for new short-link and insurance run/rule/estimate entities with PK/business
uniqueness. Existing ID allocators, IDs, URLs, audit and outbox remain intact.
Never inspect ID bits for runtime format dispatch. For mixed tables retry only
specific PK collision after full command rollback, at most3 allocations;
existing unrelated integrity errors are not retryable. Owner insert outcome
must supply collision metrics: allocator cannot observe domain DB writes.
No Redis/random fallback for these new entities on ID failure. Only configured
new commands fail; existing service readiness stays owner-DB-authoritative.

Executed checks and measured comparisons are recorded in the owned experiment
results and final report. Correctness covers deterministic bit boundaries,
5000 same-ms requests, parallel tasks, 1/100/10000ms rollback, invalid timestamps,
restart after reservation/issuance/rolled-back insert, cancelled/expired calls,
real advisory conflict/unlock/session loss, 16 workers, four separate OS process
workers, and bounded PK-only whole-command retry. No legacy table mutated.

Limits: local PostgreSQL14, not deployment16; multi-process correctness measured,
performance is one asyncio process; no mounted hospital endpoint, final migration,
Docker image, live seven-owner regression, gateway or browser validation.
These remain coordinator gates. Raw benchmark data stays ignored inside the
owned experiment prefix to honor the task's exclusive paths, overriding the
plan's root raw-artifact location. Preliminary results retained; verified-low, verified-medium and measured-high-1/2/3 folders
and combined summary are authoritative. No merge or push.

## Final verification

- `PYTHONPATH=components/unique_id ID_TEST_DSN=<disposable correctness DSN>
  /tmp/pulsegrid-id-venv/bin/pytest -q components/unique_id/tests`: **36 passed**.
  Includes actual killed-process recovery at reservation-only, issued-ID and
  rolled-back-business stages; original legacy service code is unchanged.
- `/tmp/pulsegrid-id-venv/bin/pip wheel --no-deps components/unique_id
  -w /tmp/pulsegrid-id-wheels`: **pass** (independent wheel builds).
- Uniform run.py CLI: seeds404/405/406, low100k / medium400k / high1m IDs per
  mode/trial, three trials for CSPRNG, owner sequence and Snowflake. Authoritative
  results: verified-low, verified-medium, measured-high-1/2/3. **27 rows pass**;
  **4.5m Snowflake allocations/persisted inserts, zero observed collisions,
  zero rejected allocations, zero observed overflow waits**. Forced overflow is
  exercised separately in deterministic tests. Per-worker counters and committed
  reservation counts exclude warmup. Restart wait is not measured by throughput
  trials (CSV null), but deterministic PostgreSQL timeline measures101ms.
- summarize.py: all raw SHA256 hashes and counts pass. Five authoritative
  component-source hashes match the final library sources. Combined report has
  baseline ratios and p50/p95/p99 raw summaries, min/max, counts and throughput.
- plot.py: six matplotlib SVGs rendered; throughput PNG visually inspected.
  SVG XML parsing passes. Individual latency plots not separately image-inspected.
- py_compile passes. Initial staged whitespace check flagged generated CSV CRLF
  and SVG trailing spaces; these were normalized and the final check passes. Git scope/branch/base and staged
  whitespace are checked before commit; final SHA/status reported after commit.
- Disposable loopback PostgreSQL cluster stopped successfully. Dedicated sessions
  and temporary entity tables closed by runner finally blocks. Synthetic worker
  state/raw history retained locally; no shared/development fixture writes.

Performance has substantial trial variation. Pipeline Snowflake ranges:
low2806–5587 IDs/s, medium10449–10849, high5485–10793. Pipeline p95 ranges:
low0.297–0.364ms, medium0.882–0.978ms, high4.288–18.667ms. Mean baseline CSPRNG
is respectively2.136/1.806/2.368 times faster; no superiority or capacity SLO
claim. The owner sequence is separately labeled in every comparison.

Skipped: PostgreSQL16, mounted hospital/API/browser/regression acceptance,
service-role grants/final migrations/images, multi-process performance, clinical
or HA validation. Test-only DDL uses the disposable cluster owner. These are
coordinator integration gates, not proved by library tests.

## Changed paths

- components/unique_id/.gitignore
- components/unique_id/HANDOFF.md
- components/unique_id/README.md
- components/unique_id/pulsegrid_unique_id/__init__.py
- components/unique_id/pulsegrid_unique_id/postgres.py
- components/unique_id/pyproject.toml
- components/unique_id/requirements-test.txt
- components/unique_id/tests/test_generator.py
- experiments/phase4/unique_id/.gitignore
- experiments/phase4/unique_id/README.md
- experiments/phase4/unique_id/fixture.py
- experiments/phase4/unique_id/plot.py
- experiments/phase4/unique_id/requirements-plot.txt
- experiments/phase4/unique_id/results/boundaries/report.md
- experiments/phase4/unique_id/results/boundaries/timeline.json
- experiments/phase4/unique_id/results/boundaries/timeline.svg
- experiments/phase4/unique_id/results/combined/report.md
- experiments/phase4/unique_id/results/combined/summary.csv
- experiments/phase4/unique_id/results/combined/throughput.svg
- experiments/phase4/unique_id/results/final-low/latency.svg
- experiments/phase4/unique_id/results/final-low/manifest.json
- experiments/phase4/unique_id/results/final-low/partial.json
- experiments/phase4/unique_id/results/final-low/report.md
- experiments/phase4/unique_id/results/final-low/summary.csv
- experiments/phase4/unique_id/results/low/latency.svg
- experiments/phase4/unique_id/results/low/manifest.json
- experiments/phase4/unique_id/results/low/report.md
- experiments/phase4/unique_id/results/low/summary.csv
- experiments/phase4/unique_id/results/measured-high-1/latency.svg
- experiments/phase4/unique_id/results/measured-high-1/manifest.json
- experiments/phase4/unique_id/results/measured-high-1/partial.json
- experiments/phase4/unique_id/results/measured-high-1/report.md
- experiments/phase4/unique_id/results/measured-high-1/summary.csv
- experiments/phase4/unique_id/results/measured-high-2/latency.svg
- experiments/phase4/unique_id/results/measured-high-2/manifest.json
- experiments/phase4/unique_id/results/measured-high-2/partial.json
- experiments/phase4/unique_id/results/measured-high-2/report.md
- experiments/phase4/unique_id/results/measured-high-2/summary.csv
- experiments/phase4/unique_id/results/measured-high-3/latency.svg
- experiments/phase4/unique_id/results/measured-high-3/manifest.json
- experiments/phase4/unique_id/results/measured-high-3/partial.json
- experiments/phase4/unique_id/results/measured-high-3/report.md
- experiments/phase4/unique_id/results/measured-high-3/summary.csv
- experiments/phase4/unique_id/results/measured-low/latency.svg
- experiments/phase4/unique_id/results/measured-low/manifest.json
- experiments/phase4/unique_id/results/measured-low/partial.json
- experiments/phase4/unique_id/results/measured-low/report.md
- experiments/phase4/unique_id/results/measured-low/summary.csv
- experiments/phase4/unique_id/results/measured-medium/latency.svg
- experiments/phase4/unique_id/results/measured-medium/manifest.json
- experiments/phase4/unique_id/results/measured-medium/partial.json
- experiments/phase4/unique_id/results/measured-medium/report.md
- experiments/phase4/unique_id/results/measured-medium/summary.csv
- experiments/phase4/unique_id/results/verified-low/latency.svg
- experiments/phase4/unique_id/results/verified-low/manifest.json
- experiments/phase4/unique_id/results/verified-low/partial.json
- experiments/phase4/unique_id/results/verified-low/report.md
- experiments/phase4/unique_id/results/verified-low/summary.csv
- experiments/phase4/unique_id/results/verified-medium/latency.svg
- experiments/phase4/unique_id/results/verified-medium/manifest.json
- experiments/phase4/unique_id/results/verified-medium/partial.json
- experiments/phase4/unique_id/results/verified-medium/report.md
- experiments/phase4/unique_id/results/verified-medium/summary.csv
- experiments/phase4/unique_id/run.py
- experiments/phase4/unique_id/summarize.py
- experiments/phase4/unique_id/timeline.py
