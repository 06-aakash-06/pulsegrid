# Synthetic insurance crawler benchmark

This experiment compares sequential crawling (one global in-flight request) with
the same parser, allowlist, validation, retry policy, and repository contract at
global concurrency 4 and 8. The per-host cap is 2. Three synthetic provider hosts
are served by an in-process HTTP fixture bound to loopback; DNS is injected to
`127.0.0.1`, environmental proxies are disabled, and no external URL is fetched.
The deployment default remains global concurrency 4. Concurrency 8 is a bounded
experiment setting from the frozen plan.

## Reproduce

Use Python 3.12 or later and the Billing service's pinned HTTPX dependency. From
the repository root:

```sh
PYTHONPATH=services/billing python3 experiments/phase4/insurance_crawler/run.py \
  --seed 404 --level all \
  --output experiments/phase4/insurance_crawler/results/insurance-crawler-20261012
```

The default distribution repeats use seeds 405 and 406. The `all` level executes
10, 100, and 300 total pages, plus a 100 ms per-response sensitivity at the high
level. A single level can be selected with `--level low|medium|high`. The
`--include-100ms-sensitivity` option adds the sensitivity run to a single-level
invocation. Each bounded trial runs all three providers concurrently; each
single-slot baseline runs the providers sequentially. Every provider stays at or
below 100 pages, and each trial resets the in-memory Billing sink and HTTP
fixture. Execution order alternates across trials.

## Fixture truth and measurements

The seeded generator creates policy JSON inside inert `application/json` script
elements, index pages with bounded relative links, 10% duplicate content, 5%
transient 503 responses, 5% malformed or timed-out pages, and a same-revision
conflict. All generated bodies stay in memory and are discarded after a trial.
`summary.csv` records each seed, delay, and concurrency setting. `fixture_confusion.csv`
records fixture classes, `latency.svg` plots whole-batch duration and throughput,
`report.md` provides paired sequential-versus-concurrent ratios and absolute
differences, and `manifest.json` stores input/output hashes and runtime details.

Field accuracy compares extracted fields on successfully retrieved valid,
duplicate, and conflicting pages with generated truth. Invalid pages count as
correct rejections and are reported separately; timeout pages remain in the
failure denominator. Duplicate percentage is duplicate content pages over
successfully processed URLs. Failure percentage is failed unique page requests
over attempted unique page requests. Retry attempts do not inflate those
denominators.

The runner uses a disposable in-memory repository fake to measure crawler and
loopback HTTP behavior. It does not measure PostgreSQL locks, the coordinator's
Alembic migration, live Billing APIs, or deployment networking. Those require
the integration steps in the insurance module's `HANDOFF.md`.
