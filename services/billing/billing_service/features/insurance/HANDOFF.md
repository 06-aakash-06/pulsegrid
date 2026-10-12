# Agent 6 insurance crawler handoff

Base: `45273ea7fd1ea53e335942b6c38f2d81d38856ee`

Exclusive source/test/experiment prefixes: `services/billing/billing_service/features/insurance/`, `services/billing/tests/phase4_insurance/`, and `experiments/phase4/insurance_crawler/`.

## Exports

- `crawl(provider_id, fetcher, repository, observer) -> CrawlOutcome`
- `extract(html, source_id) -> tuple[PolicyRule, ...]`
- `validate(rule) -> PolicyRule`
- `estimate(invoice_snapshot, rule, now) -> EstimateResult`; `calculate_estimate(...)` exposes the arithmetic-only helper
- `build_estimate_result(...) -> dict` with the frozen `EstimateResult` fields
- `export_validated_policy(...) -> ValidatedPolicyExport`, the Billing ingestion boundary; its factory verifies the canonical policy hash and carries provider, source path/version, run, and observation time provenance
- `register_routes(app, ports)`, `register_tables(metadata)`, `schema_spec()`, and `worker_tick(ports)`
- `AllowlistedFetcher` and `SourceConfig` for explicitly seeded synthetic provider fixtures
- `SQLAlchemyInsuranceRepository` for the coordinator's Billing session, ID, and transactional audit/outbox adapters

The route module is intentionally not mounted by this change. Production mounting,
configuration, auth wiring, worker lifespan, shared router changes, and database
migrations remain coordinator-owned. Import `register_routes` in Billing's
coordinator adapter and mount it only after the forward migration is applied.

## Synthetic fixtures and source networking

Seed three provider rows in Billing's `insurance_providers` table with synthetic
slugs and internal fixture URLs. Never expose `allowlisted_url` in a public or
operator response. Configure one `SourceConfig` per provider using its exact
provider ID, stable source ID, fixture base URL, and approved private fixture IPs.
The crawler refuses providers or sources absent from that in-process registry.

The integration fixture hosts should be reachable only from the Billing worker on
the isolated synthetic backend network. A local test can bind loopback and inject
the resolver. Disable external DNS/proxies for worker requests; map each fixture
hostname to its approved private address. Do not add a public insurer proxy or
allow arbitrary URLs. Each request and redirect re-resolves, checks the complete
answer set against approved fixture IPs, and connects to a pinned address. Keep
host ports unpublished in shared Compose configuration.

Policy pages use inert HTML containing a
`<script type="application/json" data-pulsegrid-insurance-policy>` element. The
script body is parsed as JSON and never executed. Index pages may link to relative
paths under their configured source path. Do not put patient identifiers,
clinical data, query tokens, or real insurer content in fixtures.

## Billing migration and runtime adapter

Review `schema_spec()` and the frozen contract before preparing `0005_phase4_insurance`.
Preflight all dormant provider/run/rule/estimate rows and stop for manual review
if a policy mapping, source revision, or effective-to date cannot be proven. Keep
Billing's single Alembic head and existing `(provider_id, revision)` storage
uniqueness. Add the frozen run counters, worker lease and fencing columns, active
provider run uniqueness, immutable source policy revision uniqueness, `effective_to`,
`policy_code`, `content_hash`, estimate snapshot/provenance fields, and the
`insurance_source_versions` feature table. Grant runtime updates only for run
lease/state/counts. Accepted rules are append-only. Do not reset dormant data.

Construct `SQLAlchemyInsuranceRepository` from Billing's existing `read_session`,
the injected ID allocator, a bounded configured worker ID, and an adapter callback
that writes Billing audit and outbox rows using the existing transaction. Use the
exact adapter port names from the component contract: `authorize`, `allocate_id`,
`command`, `read_session`, `claim_runs(session, now, limit)`, `read_invoice`, and
the common observer. The run claim transaction is short and commits before any
HTTP fetch. `commit_run` persists page hashes, rule revisions, counts, completion,
audit and outbox data in one Billing transaction after checking the fencing
version. A stale finalizer writes nothing.

Mount `register_routes(app, ports)` only after the coordinator supplies current
Billing authorization, request metadata, If-Match/idempotency, bounded owner-local
invoice snapshots, and safe response handling. The existing Billing API router,
production app lifespan, and migration were not modified by Agent 6.

## Estimate ingestion boundary

Only persisted, validated `ValidatedPolicyExport` values may reach estimate code.
The coordinator adapter reads the invoice snapshot from Billing's own database
after checking invoice scope, current version, balance, and current local
charge-code membership. It resolves one explicitly chosen active `policy_code`;
it does not search patient plans. Exact integer estimate output is stored in
`insurance_estimates` with invoice version and source run/rule provenance. Creating
or reading an estimate never changes invoice totals, payment rows, charges, or
journey discharge state. Stale source data may yield a stale-labeled simulated
estimate; it does not trigger a blocking crawl.

## Verification and benchmark

Run the owned tests without installing dependencies:

```sh
PYTHONPATH=services/billing python3 -m unittest discover -s services/billing/tests/phase4_insurance -v
```

Run the reproducible whole-batch sequential/concurrent benchmark using the command
in `experiments/phase4/insurance_crawler/README.md`. The benchmark records all
three seeds and levels, plus the 100 ms sensitivity. Its repository is an in-memory
contract fake, so it does not verify PostgreSQL migration locks, active-run
uniqueness, Alembic grants, Billing auth/idempotency, or live API mounting. Those
are coordinator integration gates.
