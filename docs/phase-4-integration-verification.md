# Phase 4 integration and verification

Verification date: 2026-10-12. Data is synthetic. Work was integrated on local main; nothing was pushed and no persistent application database was reset.

**Verdict: PARTIAL.** All seven components are mounted in the hospital application and their core correctness paths were exercised. The authenticated short-link load matrix stopped partway, and full-catalog autocomplete fallback latency was not measured. These are recorded below; Phase 4 is not marked fully complete.

## 1. Source integration and Git

The integration started from Phase 4.0 commit 45273ea7fd1ea53e335942b6c38f2d81d38856ee, descending from Phase 3 commit 340909aade79b23a3ffb99ade8d9863bd0a6b928. Main was clean before cherry-picks. All supplied objects existed, none was already integrated, ordered Agent 5 and Agent 6 commits were picked in ancestry order, and the owned source trees were compared to their agent handoffs. The Agent 1 branch tip was a benchmark/handoff commit, so its reviewed owned tree and three prerequisite limiter commits were restored into its integration commit after modify/delete conflicts.

| Agent | Original commit | Integrated commit |
|---|---|---|
| Distributed rate limiter | 705dd7e80028f17562fb647c54ffb71549f5d5f3 | f12222fd0cc9751134f0191171dabdb01e62b70e |
| Consistent hashing | 17287d1ecb70d93dc09b1f97f5e958a2d165b013 | d962dc4276e4085305c5adf9c535c9eb1f1cc678 |
| Key-value cache | ff61546a4d0a78bca68e123ddd89433c4bb195a4 | 516ad3852aa2286887b8a668ded58db6b14dcda2 |
| Unique ID generator | a0875a2c5a80549a581e3ad9c7ebf73b12b110a1 | c5b8f6ea90623543bd5c612e5cde723505b1b679 |
| URL shortener implementation | e8bb1e633f4279be9efd2a382d5aea3445fa3bbc | fa071ff8c1a8ba3170700fe2ae1ae0aaf5d44e20 |
| URL shortener benchmark | a7775a9083933547fea2a53fc60bf3babc17505e | 17652b1da56aa3838efca963bebbe84f501d6ab3 |
| Insurance crawler implementation | 1fb5b1e4ad7965d25f3ac3bd55d0743ed28597cf | e95e814aa4ed723435760338983b7cbbaeef8e55 |
| Insurance crawler benchmark | d58ef2fb9b1d4a566c5f6a014656a8c7d2a083c0 | 3262f078f3d07a57e66a8c2dcbee0505f128f281 |
| Autocomplete | c528b9d92076c82f249f2d10bad2e06085dfa5b0 | 8c3059a7a9822a67420bc3592340de74546c668e |
| Frontend | 69c81ee55d1776bb9453abe723ff6bc240c51551 | 7a677306651a58c4f1b564ca46374013793fec3a |

Integration commits before this finalization were 30afef2, 6325e53, f810719, 804dd52 and dd401cd. The final local-main SHA is the commit that contains this report; because a commit cannot store its own object ID, the exact SHA is reported with the final task result and is available from git rev-parse HEAD. Source branches and agent worktrees remain intact.

## 2. Database and infrastructure

Live services have exactly these migration heads:

| Owner | Head |
|---|---|
| Patient | 0005_waitlist_eligibility |
| Doctor | 0005_phase4_directory_revision |
| Appointment | 0011_phase4_alias_parent_guard |
| Records | 0005_phase3_workflow |
| Pharmacy | 0005_phase4_catalog_revision |
| Billing | 0009_phase4_provenance_fks |
| Emergency | 0003_emergency_workflow |

Disposable forward-migration checks passed for Doctor, Pharmacy, Appointment and Billing. Their forward-only history safely refused downgrade and retained the expected head. Existing IDs, patient records, appointments, stock, invoices and payments were retained. Doctor and Pharmacy revision tracking uses additive owner migrations. Appointment aliases and Billing provenance use additive schema changes. The contract amendment for per-provider If-Match/version is optional and additive within v1.

The final Phase 4 Compose deployment has 17 healthy containers: seven API owners, a second Doctor replica, PostgreSQL, RabbitMQ, Traefik, one dedicated admission Redis, two cache Redis nodes and three synthetic fixture providers. Redis and fixtures have no published ports. Admission, cache and provider traffic use private networks; fixture hosts are allowlisted and pinned. Admission Redis credentials are distinct from cache credentials. Redis restart and credential failure/recovery paths passed. The APIs remain database authoritative; cache and limiter failure paths do not grant business authority.

PostgreSQL owner isolation was checked for all fourteen database roles: each was denied CONNECT to the six other owner databases. Traefik checks verified authentication, health routes, private service leaves and reserved short-link routing. The service packages built and installed; the final seven API images built successfully.

## 3. Activated component interfaces

| Component | Hospital integration |
|---|---|
| Distributed rate limiter | Admission middleware in all seven APIs covers authentication, registration, search, appointment and owner-command categories. Emergency has isolated admission partitions. HTTP admission counters include owner, policy and outcome. |
| Consistent hashing | The production cache placement port calls the HashRing to select one of two private Redis nodes. Placement changes advance the cache namespace epoch. |
| Key-value cache | Doctor directory reads use the Redis cache through the ring, validate owner revision and fall back to the Doctor database. Clinical, payment and reservation authority stays in PostgreSQL. |
| Distributed IDs | Durable PostgreSQL worker reservations are configured for approved new alias, run, rule and estimate identities. Existing entity primary keys and URLs are unchanged. Appointment and Billing workers use distinct deployment identities. |
| Short links | Appointment owns authenticated create/resolve/revoke routes and lifecycle invalidation. Aliases store only a digest, use the approved same-origin landing route, and do not contain QR secrets. |
| Synthetic insurance crawler | Billing starts bounded asynchronous refresh jobs against only the three isolated fixture providers. Ingestion validates versions, deduplicates pages and records source provenance before estimate creation. |
| Autocomplete | Doctor exposes authorized doctor-name and specialty suggestions; Pharmacy exposes authorized medicine-name suggestions. Revision-aware background indexes fall back to their owner databases. |

The existing QR credential remains the single-use check-in authority. Short-link navigation still requires the patient session and Appointment ownership authorization. The frontend mounts DoctorAutocomplete, MedicineAutocomplete, AppointmentShortLinkPanel, ShortLinkLanding, InsuranceEstimatePanel, InsuranceRefreshPanel and AdmissionFeedback in the existing hospital pages.

## 4. Component measurements

All numbers below are observed measurements from retained synthetic workloads. CPU-only algorithm timing, Redis/PostgreSQL adapter timing and authenticated HTTP timing are separate layers. They are not interchangeable capacity claims. Benchmark scripts, configurations, summaries and manifests are under experiments/phase4; detailed raw tables are linked by their paths below. Raw compressed sample files remain in the ignored artifacts/phase4 directories with hashes in their manifests.

### Distributed rate limiter

The component benchmark used three 30-second trials, seeds 404–406, two processes and 32 clients. Baseline and Redis completed about 199.47 decisions/s. Baseline p95 decision latency was 0.031–0.038 ms; Redis p95 was 6.725–7.722 ms. Across matched bursts, the in-process baseline admitted 120/160 where a shared budget was about 60; Redis admitted 60/160. This measures the cost of coordination and shared quota enforcement, not a speedup.

The final real Traefik run attempted 100 authenticated Doctor searches over eight legitimate container sources and two Doctor replicas: 63 admitted, 37 returned 429, zero transport/server errors, 124.28 attempts/s and 78.30 admitted requests/s. Mean latency across both outcomes was 28.69 ms and p95 was 135.07 ms. Per-replica HTTP counter deltas were 31 accepted/19 limited and 32 accepted/18 limited, matching the response totals. Rejections returned rate_limited and Retry-After. Spoofed forwarded addresses did not expand a principal quota; Emergency continued to its own 422 business validation after search overload.

A bad admission credential on one temporary replica produced 503 while its peer returned 200; restoring the credential returned the failed replica to 200. With admission Redis stopped, a 20-request check exercised the documented conservative per-process divided quota (14 returned 200, six 429) and returned to 200 after Redis recovery. That fallback is approximate across processes and is not described as globally coordinated.

Evidence: experiments/phase4/rate_limiter/results, experiments/phase4/integration/results/admission-http.json, admission-config-failure-http.json, admission-outage-http.json and proxy-http.json.

### Consistent hashing and key-value cache

The pure hashing benchmark used one million synthetic keys and seeds 404–406. Modulo remapped 74.97–75.12% of keys on a three-to-four-node change. Ring/32 moved 22.82–22.83%; ring/128 moved 25.43–25.50%. Ring/128 single-reader throughput was 970,847–984,384 lookups/s at 958–1,000 ns p95; modulo was 1,163,992–1,185,503/s at 792–833 ns p95. The ring improved movement and cost some placement latency. It does not replicate data or make Redis highly available.

The real two-node cache topology test placed 10,000 keys 5,341/4,659. Adding a third node moved 28.56% with the ring and 67.31% with modulo; resulting counts were 3,608/3,536/2,856. Epoch invalidation, TTL, delete, node removal, database fallback and refill passed.

The indexed cache adapter benchmark ran three 30-second trials per level with one, eight and 32 clients. Each trial had zero errors. Means below average the three trial summaries:

| Level | State | Mean ms | p95 ms | Reads/s | Hit ratio |
|---|---|---:|---:|---:|---:|
| Low | Uncached | 1.397 | 1.761 | 712.2 | n/a |
| Low | Cold | 2.393 | 3.067 | 320.6 | 0 |
| Low | Warm | 0.686 | 1.010 | 1,442.4 | 0.9998 |
| Low | Redis unavailable | 0.722 | 0.949 | 1,372.5 | 0.9998 |
| Medium | Uncached | 4.484 | 6.444 | 1,946.4 | n/a |
| Medium | Cold | 8.342 | 12.012 | 728.2 | 0.0029 |
| Medium | Warm | 3.053 | 3.803 | 2,616.2 | 0.9998 |
| Medium | Redis unavailable | 3.425 | 4.204 | 2,335.6 | 0.9997 |
| High | Uncached | 25.565 | 36.418 | 1,754.9 | n/a |
| High | Cold | 30.405 | 49.833 | 784.2 | 0.0333 |
| High | Warm | 12.619 | 15.836 | 2,535.1 | 0.9995 |
| High | Redis unavailable | 13.575 | 23.304 | 2,361.6 | 0.9994 |

The separate authenticated Doctor endpoint comparison used the live five-doctor directory, three paced 30-second trials per condition, one client and zero errors. After batching cache projection into one owner query, mean/p95 were 11.18/20.57 ms uncached, 23.49/61.82 ms cold and 23.44/44.37 ms warm. This small catalog did not benefit from the cache; no endpoint speedup is claimed. Before batching, means were 18.57/45.37/27.14 ms and average p95 was 56.95/205.75/70.95 ms for uncached/cold/warm. No OS or container resource cap was imposed for the adapter benchmark; Redis and PostgreSQL RSS was not captured there.

Evidence: experiments/phase4/consistent_hashing/results, experiments/phase4/integration/results/cache-topology.json, cache-ring-{low,medium,high}, cache-endpoint-before-batch.json and cache-endpoint-full.json.

### Distributed IDs

The generator benchmark compared CSPRNG, owner sequence and Snowflake pipelines using loopback PostgreSQL 14, three trials at each level and 4.5 million total Snowflake allocations/inserts. It observed zero collisions, rejected allocations or overflow waits. All 36 correctness tests passed on the PostgreSQL 16 deployment version as well. Tested cases include sequence progression/overflow, rollback/restart, worker conflict and multiple processes.

Snowflake throughput was 2,806–5,587 IDs/s low, 10,449–10,849 medium and 5,485–10,793 high. Pipeline p95 was 0.297–0.364 ms, 0.882–0.978 ms and 4.288–18.667 ms respectively. CSPRNG was 2.136x, 1.806x and 2.368x faster on mean throughput at those levels. The baseline is faster; Snowflake was selected for the additive distributed-ID properties, not to claim a performance win. Restart reservation recovery measured 101 ms in a separate PostgreSQL timeline. Worker uniqueness relies on an explicitly allocated deployment/process identity; PostgreSQL locks do not coordinate independent databases.

Evidence: components/unique_id/HANDOFF.md and experiments/phase4/unique_id/results.

### Appointment short links

The original 50,000-alias, 150,000-future-appointment, 32-client adapter workload had 476 resolution exceptions and 47 creation exceptions across three trials; resolution p95 was about 2.015–2.020 s. Investigation found the resolver kept one database connection while authorization opened another owner session, exhausting the pool under concurrency. Releasing the lookup connection before authorization and then re-reading the workflow, ownership and expiry fixed the reproduced pool contention without raising timeouts. The equivalent adapter workload then completed 32,935 resolutions and 3,745 creations with zero errors. Resolution mean was 76.98–81.65 ms, p95 118.03–128.89 ms and throughput 354.50–377.63/s. Creation mean was 71.89–76.15 ms, p95 104.81–115.57 ms and throughput 39.84–44.30/s. The baseline workflow read remained faster at 1,055–1,082/s and 43.11–50.40 ms p95. The pre-fix raw error file did not classify every exception; a separate diagnostic recorded 240 TimeoutError events.

Low and medium adapter runs also had zero errors: low resolution averaged 4.80 ms and 213.86/s, creation 7.67 ms and 22.70/s; medium resolution averaged 42.78 ms and 223.03/s, creation 56.91 ms and 24.80/s. These adapter runs used PostgreSQL with fake authorization/effect ports, not gateway requests.

The actual authenticated gateway matrix was started with temporary clients. Its saved partial result includes all low one-client trials and the first medium baseline trial. At medium resolution, link churn produced a mix of 200, stale-alias 404 and admission 429 responses; the harness aborted before recording that trial. It did not track replacement aliases. No high-concurrency authenticated endpoint result is claimed. The real UI flow, ownership checks, expiry, cancellation/rescheduling invalidation and safe same-origin login return did pass independently. This performance acceptance remains PARTIAL.

Evidence: experiments/phase4/integration/results/short-links-before-after.csv, short-links-manifest.json, short-links-http.json and alias-real-expiry.json; the partial gateway harness is experiments/phase4/integration/short_links_http.py.

### Synthetic insurance crawler

The crawler benchmark used generated loopback provider pages and a fake persistence port, so its page throughput is crawler measurement rather than PostgreSQL or hospital HTTP capacity. It ran three seeds at one, four and eight global slots with at most two per host. For 20 ms fixture delay, low/medium/high throughput ranged from 27.93 to 57.25 pages/s; high at eight slots averaged 52.38 pages/s with p95 duration 5.605 s over 300 expected pages. High processed 293 pages, recorded seven request failures and rejected eight invalid pages; field accuracy and rule precision/recall were each 100%. The measured synthetic duplicate rate was about 10.24%. Medium processed 98 of 100 pages with two failures and 100% extraction/rule correctness. Low processed all ten pages without failures. A 100 ms high-delay run ranged from 7.20 pages/s sequential to 26.15 pages/s at four slots.

The integrated Billing refresh fetched the isolated fixtures, validated and deduplicated their records, and produced versioned estimates with source-run provenance. A same-revision content conflict was quarantined; the estimate was rejected with 409, the configured fixture recovered at revision 2, arbitrary URL input returned 422, and the existing invoice remained unchanged. Two real estimate commands produced distinct insurance_estimate effect identities. Staff browser refresh completed against the three synthetic providers. No real insurers or patient coverage records were used.

Evidence: experiments/phase4/insurance_crawler/results/phase4-insurance-20261012 and experiments/phase4/integration/results/insurance-conflict-http.json and estimate-effects-http.json.

### Autocomplete

The completed raw benchmark used seed 404, 100,000 lookups per timed configuration, 1/8/32 closed-loop clients and three trial repetitions. Results are CPU-only; the route measurements below are separately authenticated HTTP samples. The table reports the one-client, top-10 lookup results averaged across the three trials. The baseline is sorted-prefix lookup.

| Owner catalog | Entries | Trie mean/p95 ms | Trie lookups/s | Baseline mean/p95 ms | Baseline lookups/s | Trie estimate | Mean build |
|---|---:|---:|---:|---:|---:|---:|---:|
| Doctor low | 1,000 | 0.0025/0.0044 | 373,616 | 0.0020/0.0030 | 471,765 | 1.26 MiB | 0.049 s |
| Pharmacy low | 1,000 | 0.0021/0.0036 | 433,068 | 0.0021/0.0030 | 437,014 | 1.13 MiB | 0.056 s |
| Doctor medium | 10,000 | 0.0025/0.0043 | 365,999 | 0.0022/0.0032 | 420,909 | 11.90 MiB | 0.912 s |
| Pharmacy medium | 10,000 | 0.0022/0.0036 | 422,313 | 0.0025/0.0034 | 376,344 | 11.02 MiB | 0.796 s |
| Doctor high | 100,000 | 0.0025/0.0044 | 359,545 | 0.0025/0.0035 | 367,906 | 123.03 MiB | 17.118 s |
| Pharmacy high | 100,000 | 0.0022/0.0036 | 417,650 | 0.0027/0.0036 | 342,573 | 114.51 MiB | 11.756 s |

The configured index budget remains 64 MiB. At 100,000 entries, the estimated trie sizes exceeded it and default-cap checks correctly denied both indexes; measured tracemalloc peaks were about 240.79 MiB for Doctor and 233.56 MiB for Pharmacy. The benchmark used a 512 MiB cap only for a separately labeled algorithm diagnostic. Production keeps the 64 MiB cap and falls back to the owner database. Medium catalogs fit; build and query correctness were exact. At the live deployment, Doctor has seven indexed entries and Pharmacy four. A forced 1 KiB fallback/recovery check preserved exact results for those catalogs; unchanged revisions caused zero rebuilds during a 16-second observation.

Authenticated route checks returned zero errors in 12 paced samples per condition. Doctor trie mean/p95 was 12.82/31.69 ms versus database 14.49/21.27 ms in one condition; Pharmacy trie was 10.68/17.34 ms versus database 9.64/20.33 ms. A second Doctor sample included a 181.90 ms p95 tail; the second Pharmacy trie p95 was 22.73 ms. These are small samples and do not establish saturation behavior or a general latency win. Full-catalog database-fallback route latency was not measured.

Raw workload, build, correctness, cap and summary evidence is in experiments/phase4/integration/results/autocomplete-raw-{low,medium,high}; authenticated HTTP samples are in autocomplete-http.json.

## 5. Cross-component and browser verification

| Scenario | Result |
|---|---|
| Doctor search → limiter → autocomplete → ring-placed directory cache → results | PASS. Authenticated search and suggestions returned authorized Doctor records. Cache and owner database projections matched. |
| Remove a cache node → topology epoch changes → fallback and recovery | PASS. The 10,000-key topology run verified remapping, namespace misses, node removal, owner fallback and refill. Cache placement alone is not replication. |
| Book appointment → additive ID/alias → secure resolution → QR check-in | PASS. Real gateway and browser flows created a booking and alias, redirected to the same-origin landing, required the patient session, and retained the independent single-use QR check-in path. |
| Reschedule/cancel → alias invalidation → check-in protection | PASS. Reschedule invalidated the old alias and it returned 404; QR authorization remained separate. Real wall-clock alias expiry also returned 404. |
| Fixture policy update → crawl → Billing validation → estimate | PASS. The fixture update became a versioned estimate; conflict and arbitrary-URL rejection passed. Invoice/payment history remained byte-equal. |
| High volume → shared limiter → isolated Emergency → metrics | PASS for the bounded burst. Two Doctor replicas shared the observed bucket; Emergency retained its own partition and service validation. This is not a capacity SLO. |
| Redis or owner outage → safe fallback → recovery | PASS for exercised cases. Admission Redis used the documented approximate local quota; cache Redis loss fell back to PostgreSQL; a Billing owner outage recovered without duplicate business effects. |

Real-browser patient checks covered login, keyboard Doctor suggestion and selection, appointment booking, alias creation/resolution, fragment clearing, navigation, anonymous landing-to-login return, medicine keyboard selection, empty suggestions, insurance estimate display and billing history. The browser showed the staff provider list and completed a fixture refresh. A deliberately exhausted login quota displayed the measured Retry-After wait. Existing staff consultation, pharmacy, emergency and journey workflows were exercised through the Phase 3 regression gateway groups. Physical camera scanning was not available and was not claimed; QR single-use behavior was verified at the service/API level.

## 6. Regression, migration, HTTP and security results

The final broad backend run passed 590 tests and skipped 52. The isolated Records PostgreSQL runner passed 77; 26 pure Records cases overlap the broad run, giving 641 distinct service tests. The component suite passed 151 tests. Phase 4 integration configuration tests passed four. Frontend typecheck passed, all 129 frontend tests passed and the production build passed. Thirty-six Snowflake correctness tests also passed against PostgreSQL 16.15; they repeat component correctness and are not added to the service total. The broad-run skips are documented isolated Records cases and the dedicated benchmark harness entry, not suppressed failures.

A fresh service regression completed ten real Traefik workflow groups, including scheduling, booking, QR single use, queue actions, prescription fulfillment, pharmacy stock, invoice/payment/discharge, competing waitlist acceptance, offer expiry/FIFO successor and Billing outage recovery. Emergency ownership, triage, claim, processing and resolution passed. Migration checks used disposable databases. No persistent database volume was reset. The final API image build passed for all seven owners and current Compose health reports all 17 containers healthy.

Security checks confirmed same-owner authorization for short aliases, wrong-patient 404, revoked/expired alias 404, safe same-origin landing, no QR secret in aliases, and no unrestricted redirect. Fixture fetches are bounded and restricted to configured private fixture hosts; an arbitrary URL field returned 422. Synthetic crawls cannot directly mutate finalized invoices/payments. Redis is private and non-authoritative. Existing authentication and authorization remained active. Metrics and error output did not expose patient clinical content or link tokens.

## 7. Limitations and completion verdict

- The authenticated short-link matrix is partial after the medium-resolution harness stopped on stale aliases and 429s. The high-concurrency gateway capacity criterion remains unresolved even though the adapter pool regression and core HTTP/UI security flows pass.
- A 100,000-entry autocomplete trie correctly falls back under the 64 MiB cap, but route latency at that full catalog size was not measured. The live source catalogs contain seven Doctors and four medicines.
- The cache improves warm storage-adapter results at medium/high size, but the authenticated five-Doctor endpoint was slower with cache enabled. Cache endpoint latency and resource use should not be presented as a performance win.
- The crawler throughput benchmark uses a fake persistence port; PostgreSQL repository and real Billing ingestion/estimate paths passed separately.
- Camera hardware verification was unavailable. No physical scan was performed.
- The measurements are component and bounded workflow evidence, not Phase 8 whole-system scalability, HA, clinical validation or emergency-dispatch guarantees.

Component status: rate limiter PASS; consistent hashing PASS; key-value cache PASS; distributed ID generator PASS under documented worker allocation; synthetic crawler PASS; autocomplete PASS with safe large-catalog fallback; appointment short links PARTIAL because the authenticated high-concurrency HTTP matrix is incomplete. Overall Phase 4 verdict: **PARTIAL**, so the phase is not declared fully complete.

Final Git status is recorded by the final local-main commit: clean after commit, agent branches/worktrees retained, no push. No Phase 5 work was started.
