# Missing features after reconciling history

The [history register](05-history-source-register.md) covers all 42 accessible PulseGrid Codex chats, ten pasted briefs and limited related ChatGPT context. The [94-group matrix](02-feature-traceability.md) distinguishes implementation, current execution and acceptance. There is **no confirmed wholly absent finalized current business feature group**. That finding does not close partial implementations or unverified requirements.

## Actual limitations and earlier targets

| Feature / source | Expected behavior | Existing implementation | Missing pieces | Dependencies | Repaired? | Safe to complete now? | Remaining decision |
|---|---|---|---|---|---|---|---|
| Persistent record grant management; H25/P2, L-01 | Patient can create/revoke a scoped historical grant; persistent self-service would also survive reload | Owner POST/DELETE and tested grant checks; UI retains newly issued grant/ETag while mounted | No frozen grant list/detail API or durable list-driven revoke UI | Additive Records API, minimum disclosure, ETags and privacy tests | No; accepted contract limitation retained | Technically possible, but changes frozen interface rather than fixes missing promised GET | Decide whether persistent grant management is required; then define additive listing/detail/expiry visibility. |
| Hash-ring/key distribution viewer; H34, S-01 | Earlier design asks for ring/key placement visualization | Actual virtual-node cache ring; Control Room epoch/configured node metadata | Bounded ring positions/key distribution API and viewer | Owner topology snapshot, safe bounded configured-versus-live semantics | No | Possible after clarifying scope; no invented health/placement measurements | Later A08 list is narrower; confirm whether original viewer remains required. |
| Periodic new insurance refresh scheduling; H34 versus P4, S-02 | Earlier original design schedules refreshes without an operator request | Requested refresh API, durable pending-run polling/recovery and real fixture-backed estimates | Producer that periodically enqueues new provider refreshes | Cadence, dedup/overlap/backoff, source/version policy and audit | No; requested refresh is verified working | Can be designed safely, but adding cadence without a decision invents operational behavior | Is automatic refresh retained beyond the narrowed requested-run contract? |
| Resource and detailed Emergency business telemetry; H34/A08/P7, S-03 | CPU/memory plus dedicated priority/backlog/processing views where supported | Generic HTTP/readiness, bounded component/broker/cache metrics; truthful no-exporter dashboard | Resource collection and dedicated Emergency business instruments/queries | Approved bounded exporter, owner metric/cardinality/privacy definitions | No; partial telemetry target remains visible | Feasible with a reviewed deployment/metrics choice; not appropriate to fabricate unavailable series | Decide exporter/environment and which Emergency business metrics are required. |
| Backup/restore/soak exercise; original roadmap/later partial P8, S-06 | Demonstrate recoverable durable data/audit chains and bounded stability | Infrastructure/runbooks and narrower experiment campaigns | Complete isolated exercise/evidence not established | Separate restored owner DBs, secrets handling, duration/stop/recovery plan | No | Yes in a dedicated approved exercise that never restores over retained data; not run here | Retain original demonstration target and define acceptance conditions. |
| Broader evaluation; H34/A07 narrowed by A05, V-07 | Compare matched NORMAL/SURGE and hospital workload categories where retained | Historical six-cell Doctor replica/client matrix and component harnesses | Remaining broader workload/event-throughput/soak evidence | Matched conditions, bounded matrix, raw results, recovery checks | No new broad campaign; 100-request burst here checks admission correctness | Feasible but requires its own bounded campaign; no capacity claim from this audit | Which earlier evaluation goals remain required beyond the explicitly completed Doctor matrix? |

## Required verification is different from missing implementation

Physical QR optical decode is required acceptance but unavailable evidence, not an absent scanner: encoder/decoder/camera UI/manual fallback/server validation exist. Actual token check-in and replay protection passed; a physical camera capture and end-to-end decode/redeem remain V-01.

Every-control/all-role responsive coverage, live alert firing/outage isolation and sustained Tempo stability remain incomplete acceptance. One consultation timeout and one Surge-status failure remain unresolved diagnostic observations. These cannot be closed by a high pass count or by inventing new backend endpoints.

## Repaired existing functionality

Five application/deployment/UI defects were fixed: waitlist eligibility transport, durable offer deadline scheduling, consumer DLX ACL, hidden staff navigation and selected-subtitle contrast. Three diagnostics were corrected. They were broken existing functionality, not missing features. [Before/after and commits](04-issue-register.md).

## False missing-feature claims rejected

- Temporary offers and queue skip/recall were explicitly restored by H11 after the earlier freeze omitted them; current implementation was exercised.
- Doctor history/amendments are reachable through `/doctor/prescriptions` → RecordsPage; top-level route naming does not prove absence.
- Only two selected RabbitMQ paths were finalized by the later contract. The broad initial event catalog is proposed/deferred.
- Manual Surge is an explicit later choice. Automatic activation without safe shared signals is deferred.
- Snowflake adoption is intentionally additive for short links/insurance; legacy entity IDs are preserved.
- Queue polling is accepted. WebSockets are not a forgotten requirement.
- `/admin/settings` is an administration directory, not a promised settings mutation service.
- Follow-up can be a new booking. No separate reminder engine, eighth notification service or real insurer/payment gateway was finalized.
- Multi-hospital, bed management and family profiles are explicitly excluded. Predictive triage/autoscaling/clinical certification and reference-only labs/vitals/imaging/retail carts/discounts are excluded or illustrative.
- Development mock and browser-local static demo are separate supported modes. Their existence does not mean normal API integration is missing; their results cannot prove seven-service persistence/security.

Unavailable private teammate conversations and earlier inaccessible ChatGPT content are a provenance limit. Requirements were not invented to fill those gaps. No unresolved scope item was silently accepted, implemented or relabelled complete.
