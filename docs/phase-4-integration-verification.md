# Phase 4 integration and verification

Status: IN PROGRESS. No Phase 4 completion claim. Synthetic-only, local main; no push.

## Checkpoint A: source integration

Main started clean at `45273ea7fd1ea53e335942b6c38f2d81d38856ee`, descending from supplied Phase 3 baseline. All source objects exist; none was integrated. All changed paths respect ownership. Eight source branches and all nine original worktrees retained.

| Original | Integrated |
|---|---|
| `705dd7e80028f17562fb647c54ffb71549f5d5f3` | `f12222fd0cc9751134f0191171dabdb01e62b70e` |
| `17287d1ecb70d93dc09b1f97f5e958a2d165b013` | `d962dc4276e4085305c5adf9c535c9eb1f1cc678` |
| `ff61546a4d0a78bca68e123ddd89433c4bb195a4` | `516ad3852aa2286887b8a668ded58db6b14dcda2` |
| `a0875a2c5a80549a581e3ad9c7ebf73b12b110a1` | `c5b8f6ea90623543bd5c612e5cde723505b1b679` |
| `e8bb1e633f4279be9efd2a382d5aea3445fa3bbc` | `fa071ff8c1a8ba3170700fe2ae1ae0aaf5d44e20` |
| `a7775a9083933547fea2a53fc60bf3babc17505e` | `17652b1da56aa3838efca963bebbe84f501d6ab3` |
| `1fb5b1e4ad7965d25f3ac3bd55d0743ed28597cf` | `e95e814aa4ed723435760338983b7cbbaeef8e55` |
| `d58ef2fb9b1d4a566c5f6a014656a8c7d2a083c0` | `3262f078f3d07a57e66a8c2dcbee0505f128f281` |
| `c528b9d92076c82f249f2d10bad2e06085dfa5b0` | `8c3059a7a9822a67420bc3592340de74546c668e` |
| `69c81ee55d1776bb9453abe723ff6bc240c51551` | `7a677306651a58c4f1b564ca46374013793fec3a` |

Rate limiter tip is a benchmark/handoff commit, not the complete implementation patch. Its prerequisite commits c0cbae1c53a755d335116c09b9e5bd1a62f78feb, 4d379612d06d9bdc99a4d11ad7fd4389f25736fb and 87bd594a397562a7217ec8dfcf815f6fae8ec1e0 were included by restoring the entire reviewed owned tree at 705dd7e into its cherry-pick. Initial modify/delete conflicts were resolved this way, retaining all functionality. Original-to-integrated owned trees are identical. All remaining ordered picks were conflict-free. Both Agent 5/6 commits imported in ancestry order.

Frozen contracts, plan, ownership, benchmark plan, preparation and Phase 3 verification, eight handoffs and principal source seams reviewed. Ring provides locate(bytes) and epoch directly; no cache port amendment needed. Imported components do not mount production routes by themselves.

Fresh checks: compileall components/services/experiments passed; editable installation of all seven services and five independent technical packages passed. Component suite with owned disposable PostgreSQL and Redis: **148 passed**, no skips. Initial invocation lacked ID_TEST_DSN and had ten setup failures; rerun with owned cluster resolves them. Frontend typecheck, **126 tests**, production build pass; 896.57 kB initial main JS bundle warning remains under investigation.

Initial full backend run: 584 passed, two async test-runner configuration failures, 52 skipped; isolated Records run separately **77 passed**. Two failures are unmarked async Doctor cache tests requiring asyncio_mode=auto; full rerun is in progress. Records skips in broad run are replaced by its mandatory isolated runner, not excluded. Benchmark harness skip is intentional and must execute through its workload runner. These counts are provisional, not final regression acceptance.

## Remaining checkpoints

B–M remain in progress: final migration grants/preflight tests; private Redis/fixture topology; rate admission activation; ring cache endpoint parity/churn; deployment worker IDs; alias lifecycle/security/pool investigation; Billing ingestion/auth/leases; trie memory/fallback endpoint evidence; mounted frontend/browser; cross-component benchmarks and full HTTP/security regressions. Persistent application volumes have not been reset. Existing stack remains preserved.

Final main SHA, Git status and completion verdict will be recorded after verification. Current verdict: **PARTIAL source integration; activation and acceptance unfinished**.

## Activation checkpoint (in progress)

Forward Doctor/Pharmacy revision migrations applied. Appointment `0010` followed by `0011_phase4_alias_parent_guard`; Billing `0005` followed by narrow corrective `0006` provider-lock grant, `0007` SQL null-safe worker audit, `0008` source parent guard and `0009` explicit provenance FK delete semantics. Corrective revisions preserve applied history; no applied migration is rewritten. `0009` deployment verification remains pending at this entry.

Initial live Billing preflight: providers/runs/rules/estimates all zero. Seeded three explicit `phase4-synthetic-4101..4103` providers on isolated fixture hosts. All pre-existing invoice/payment rows retained. Worker IDs Appointment256 and Billing640 are required and validated against service/replica allocation; dedicated PostgreSQL sessions reserve durable ranges before alias/run/rule/estimate business locks. Accepted insurance rules remain append-only. A provider row lock needs UPDATE privilege in PostgreSQL: the corrective grant permits only its version column, not fixture URL or slug changes. Immutable rule FOR UPDATE was removed under the already-held provider lock instead of widening rule permissions.

Opt-in `compose.phase4.yaml` mounts reviewed packages using explicit root Docker COPY allowlists, dedicated authenticated admission Redis, two independently sharded cache Redis nodes and three isolated fixture servers. Redis/fixtures have no published ports. Doctor has two processes behind an opt-in Traefik file config; all other owners retain one. Redis bootstrap copies ACL files and then uses the pinned image's own entrypoint to preserve privilege dropping and AOF-directory ownership. No persistent volumes reset. Secret/config initialization writes ignored files only; keys retained on rerun. All seven APIs stay PostgreSQL-ready during cache/admission degradation. Admission HMAC/policy state is shared across replicas; fallback remains conservative/approximate.

Activated: pre-auth source and verified user/internal admission; current-authority staff command quotas; isolated Emergency staff/authenticated partitions; Doctor revision-aware cache using actual immutable ring; Doctor/Pharmacy trie background refresh and DB fallback; Appointment digest-only alias routes and canonical lifecycle hooks; Billing bounded fixture crawler and idempotent estimates; all seven requested frontend exports. Retry-After is preserved structurally in ApiError. Provider-list optional version is an additive v1 amendment for per-provider If-Match. Hospital pages and QR libraries are split into production chunks (initial304kB, hospital146kB, decoder454kB, encoder25kB); typecheck126 tests/build pass and Vite size warning is removed.

Fresh service regression before the latest provenance model/constraint additions: broad run **587 passed,52 skipped** plus isolated Records **77 passed**. Deduplicated service total **638 passed** (26 Records pure tests appear in both runs); component tests148 and integration configuration tests4 are separate layers. The one benchmark harness skip requires its workload runner; broad Records storage skips are actually rerun by its isolated runner. Final full regression still pending.

Real Traefik workflow checks have passed Doctor/medicine trie suggestions, empty suggestions, directory cache parity, booking, Snowflake alias creation, authorized JSON resolution, wrong-patient404, static303, sanitized token replay409, explicit QR check-in and cancellation alias invalidation. The initial workflow script exposed test assumptions (first QR issuance preserves version; reissue increments it) and an overlapping restart502; corrected/repeated affected paths. Live crawler/estimate verification passes fixture extraction/ingestion, provenance, authorization and byte-equal paid invoice/payment history before/after estimate. Its initial worker failure was immutable-rule FOR UPDATE permission, corrected without granting rule UPDATE. Policy update/conflict verification remains pending.

Real gateway admission burst from eight legitimate container sources across two Doctor replicas:100 attempted,64 admitted,36 limited,zero transport/server errors;1.156s wall,86.49 attempted/s and55.36 successful/s;mean35.65ms,p95(all outcomes)112.39ms. Admitted count stays within capacity60+elapsed*10. Rejections have rate_limited and Retry-After. Spoofed forwarded headers cannot expand principal capacity. Emergency submission still reaches its normal422 business validation after search overload. This is a bounded burst, not a production throughput/SLO claim.

Disposable real cache/ring experiment:10,000 keys, initial physical counts5341/4659; third node3608/3536/2856. Add moves28.56% vs modulo67.31%; epoch namespace miss, real TTL expiration and delete pass. One-node removal and refill tested. No replication or HA claim.

### Short-link pool investigation

Equivalent seed404 high workload:50,000 aliases/trial,150,000 future appointments,32 clients,5s warmup/30s x3 per mode. Before:476 resolution exceptions and47 creation exceptions; resolution p95 about2015–2020ms. Resolver held a checked-out connection while authorize opened another owner session, creating pool-acquisition deadlock at saturation. Fix releases lookup session before scope authorization and re-reads/validates link/workflow/expiry afterwards. No timeout increase or auth bypass. Actual one-connection/eight-request regression passes, no checked-out connection remains. Six retained short-link tests pass.

After:32,935 successful resolutions and3,745 creations,zero errors across three trials. Resolution mean76.98–81.65ms,p95118.03–128.89ms,354.50–377.63 successful/s; creation mean71.89–76.15ms,p95104.81–115.57ms,39.84–44.30 successful/s. Baseline workflow remains faster (1055–1082/s,p9543.11–50.40ms). These are adapter/PostgreSQL measurements with fake principal/effect ports, not authenticated gateway capacity. Raw status samples cannot individually classify every pre-fix exception; diagnostic mechanism is reproduced by source/pool behavior and regression, with exact exception classification still pending. Before workload completed and saved evidence but shared scratch-parent cleanup failed because a second disposable suite was active; its cluster stopped, parent cleanup now ignores only nonempty/missing parent. After workload and cleanup pass. Preserved raw hashes/config and all18 comparison rows under experiments/phase4/integration/results; raw compressed samples stay in ignored artifacts/phase4/short-links.

Remaining: final schema/isolation/audit verification, final regression, endpoint cache/outage/topology and index fallback measurements, remaining low/medium short-link reruns, browser role/landing/feedback coverage, extraction updates/conflicts and resource/performance evidence. Current verdict remains **PARTIAL**; no Phase4 completion claim.

### Continued verification checkpoint

Final service suites after claim-order repair: broad **588 passed,52 skipped**; isolated Records **77 passed**; 26 duplicate Records pure cases means **639 distinct service tests passed**. Frontend typecheck,126 tests and production build pass (304.15kB initial chunk; no size warning). Real trie endpoint forced-memory fallback/recovery passes both owners with identical suggestions at1024-byte temporary budget; normal64MiB budget restored. Real synthetic same-revision content conflict is quarantined, new estimate409, configured source restored, subsequent refresh complete/revision2 and invoice unchanged. Agent pool diagnostic rerun recorded240 exceptions, all TimeoutError; low/medium proposed workload reruns have zero errors. Retained five raw sample sets and45 comparison rows.

All17 current containers healthy after lighter fixture HTTP health probe (socket instead of costly urllib import) and5s process deadline under0.1CPU. No API/request timeout increased. A fresh hospital regression fixture is now running independently of old recorded successful groups. Private credentials and aliases stay ignored.

### Activation verification and measured refinements

Fresh hospital fixture completed all10 real gateway groups: booking/schedules,
QR single-use, queue, prescription fulfillment, invoice/payment/discharge,
concurrent waitlist offer acceptance, durable offer expiry/FIFO successor, owner
outage recovery and gateway auth/isolation. Expected429 during the separate
admission outage interrupted polling; bounded Retry-After handling resumed the
same fixture without replaying completed business effects. Real Emergency
submission/ownership/triage/claim/processing/resolution also passes. Spoofed20
forwarding headers cannot expand authentication source quota. Real admission
Redis outage triggers conservative local429 and recovers after restart.

All36 ID correctness cases pass on disposable PostgreSQL16.15 matching the
retained image, in addition to the PostgreSQL14 component suite. Temporary
container/tmpfs removed; no persistent volume touched.

Autocomplete investigation found5s polling rebuilt an unchanged index.
Revision-first background polling now skips unchanged snapshots and unchanged
oversized catalogs; explicit refresh API behavior and64MiB cap retained. Three
new lifecycle cases pass; live16s interval observes zero unnecessary rebuilds.
Complete component suite now151 passes. Live Doctor/Pharmacy forced-budget
fallback/recovery passes with health-waited rollouts. Frontend now129 tests,
typecheck/build pass, after fixed literal short-link login return and safe
Retry-After text on identity errors. Browser verified booking, alias creation,
authenticated landing, fragment clearing, navigation and anonymous-to-login
handoff. Real expiry is currently awaiting the ordinary wall-clock deadline.

Full-duration indexed real-ring cache low/medium runs pass with zero errors;
high remains running. Authenticated5-doctor directory comparison5s/30s x3 shows
warm-cache overhead relative to the simpler baseline. This revealed N+1 fresh
wire reconstruction; batching preserves current PostgreSQL fields/order in one
query (actual PostgreSQL test passes). Duplicate cached source IDs are rejected.
A fresh equivalent endpoint comparison of the batching fix is running; no
endpoint speedup is claimed. Actual storage-adapter benefits are a separate layer.

Estimate effects now identify insurance_estimate/estimate_id/version1, with
source-run provenance retained. Early local unpublished run-keyed effects are
preserved as history, not rewritten. Contract amendment records this before any
consumer exists; broker business workflows remain deferred. Final effect/schema,
regression and documentation verification remain pending.
