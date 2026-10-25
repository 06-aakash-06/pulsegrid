# System Design Lab — three-minute presenter script

Open `/system-design` in `npm run dev:mock`. Use synthetic data. The eight cards cover the seven implemented components plus database isolation. Browser results are illustrative and vary by device; they are separate from measured lab figures.

Presenter allocation below is provisional: `UI_SIMULATION_SPEC.md` and its section 11/team split were not present in the supplied workspace. Presenter numbers are placeholders, not invented team names or a claim about the unavailable design document. Replace the assignments with that document's exact team split when it becomes available.

## Presenter 1 — cache placement and reads (0:00–0:45)

“PulseGrid connects seven hospital services. This lab shows the algorithms behind them, and every measured figure links to our verification report.

First, add a Redis node. The browser really hashes ten thousand keys with SHA-256 and compares clockwise placement against modulo. In our million-key lab run, adding a fourth node moved 25.43–25.50 percent with the ring, versus about 75 percent with modulo. This reduces movement; it does not replicate data.

Read the directory cache twice: miss, then hit. At high load, warm p95 was 15.836 milliseconds versus 36.418 uncached, with 2,535 versus 1,755 reads per second. The database stays authoritative.”

Actions: Add node; Read directory twice. Sources: [Phase 4 component measurements](phase-4-integration-verification.md#4-component-measurements).

## Presenter 2 — admission and identifiers (0:45–1:30)

“Fire a burst. The browser counts actual accepted and rejected requests. In the lab, shared Redis admitted sixty of 160, while separate in-memory limiters admitted 120 against the same shared budget. Redis coordination cost 6.725–7.722 milliseconds at p95.

Surge Mode preserves class A's finite budget, gives B sixty percent and C fifteen percent, with the implemented small-bucket floor. It is manually controlled; a rejected request does not automatically activate it.

Now generate ten thousand Snowflake IDs and inspect their bits. The lab generated 4.5 million without collisions, at roughly ten thousand IDs per second at medium load. Random IDs were faster. Snowflake adds ordering and assigned worker identity.”

Actions: Fire burst; toggle Surge Mode and fire again; Generate 10,000 IDs. Sources: [Phase 4](phase-4-integration-verification.md#4-component-measurements), [Phase 6 budgets](phase-6-integration-verification.md#surge-mode-and-operation-classes).

## Presenter 3 — links and autocomplete (1:30–2:15)

“Appointment links use 128 random bits encoded into twenty-two Base62 characters, stored only as SHA-256 hashes. Randomness resists guessing, while ownership, expiry and workflow checks still control access. There are no custom aliases or Redis link cache. The adapter benchmark measured resolution p95 of 118–129 milliseconds at thirty-two clients; authenticated high-concurrency endpoint performance remains partially verified.

Type a prefix and race the trie against a linear scan. Both run here. Our lab's sorted-prefix baseline and trie were both around 0.0025 milliseconds, so we claim no general speedup. At one hundred thousand entries the trie exceeded its 64 MiB budget and safely fell back to the owner database.”

Actions: Generate random token; type a generated prefix; Race trie vs linear scan. Source: [Phase 4](phase-4-integration-verification.md#4-component-measurements). Real-service buttons use current sign-in permissions; dev mock responses are labelled and unavailable routes remain explicit.

## Presenter 4 — provenance and ownership (2:15–3:00)

“Fetch the synthetic insurance fixture twice, then introduce a same-revision conflict. We validate, deduplicate by version and content hash, quarantine conflicts, and block conflicting estimates. Publishing a newer revision recovers. Our synthetic crawler measured 52.38 pages per second with perfect extraction and rule accuracy on evaluated data, but seven of three hundred requested pages failed. That is crawler throughput with fake persistence, not hospital capacity.

Finally, try the illustrated cross-database join. It is blocked by the ownership design: seven private databases, no shared tables or sharding. A payment commits with its outbox; RabbitMQ delivers it; Appointment deduplicates it in an inbox and acknowledges after commit. Delivery is at least once, and reconciliation uses owner APIs.”

Actions: Fetch fixture twice; Try revision conflict; Publish next revision; Try cross-database join. Sources: [Phase 4 crawler](phase-4-integration-verification.md#synthetic-insurance-crawler), [Phase 6 recovery evidence](phase-6-integration-verification.md#live-failure-recovery-and-workflow-results). The separate replica-scaling figure comes from [Phase 8.2](phase-8-2-scalability-finalization.md#7-replica-scaling); scaling replicas is not sharding.
