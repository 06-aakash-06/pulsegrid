# Phase 6 integration and verification

Completed 2026-10-13 on local `main` for the synthetic single-hospital
prototype. The retained PostgreSQL volumes were not reset. Only the seven API
containers were recreated for the final image check; PostgreSQL, Redis,
RabbitMQ, and their volumes were left in place. No remote push or Phase 7 work
was performed.

**Verdict: PASS.** Phase 6 controls were integrated into the existing limiter,
Appointment snapshot client, owner audit chain, and Phase 5 outbox/inbox paths.
The focused outage and surge scenarios, application regressions, and retained
Compose checks passed as recorded below.

## Architecture and scope

The seven FastAPI services retain their separate PostgreSQL ownership. Phase 6
reuses the Phase 4 Redis admission limiter and Phase 5 transactional outbox,
publisher confirmation, retry, dead-letter, and Appointment inbox. No second
limiter, broker, domain authority, dashboard, or cross-service database access
was added. Existing Doctor cache and autocomplete database fallbacks remain the
source of read results when optional cache structures are unavailable.

## Surge Mode and operation classes

Route class is assigned from the service, HTTP method, and route template. A
request cannot choose its class through headers, query parameters, body fields,
or token claims.

| Class | Example operations | SURGE budget | RECOVERY budget |
|---|---|---:|---:|
| A — critical | Emergency admission and staff lifecycle actions; Appointment check-in and queue start; Records clinical finalization; Pharmacy dispensing | 100% of owner budget | 100% |
| B — important | Booking and journey operations; ordinary clinical work; billing and payment; authentication | 60% | 80% |
| C — deferrable | Doctor and Pharmacy directory/autocomplete; synthetic insurance refresh and estimates | 15% | 50% |

The single control state is stored in the existing private Redis admission
namespace. NORMAL keeps the existing budget profile. SURGE expires after at
most 30 minutes into a two-minute RECOVERY period; manual deactivation also
starts RECOVERY. Minimum state durations and the separately audited incident
override prevent rapid oscillation. The state version remains monotonic across
timed recovery.

Manual control is exposed only at
`POST /api/v1/appointments/operations/surge-mode` and requires a currently
authorized `hospital_admin`, an idempotency key, and a reason code. An
unauthenticated status read returned 401. Authorized manual transitions were
recorded as requested/applied entries in Appointment's existing hash-chain
audit table. The durable entries showed NORMAL → SURGE at version 1 and SURGE →
RECOVERY at version 2. A later shared-state read returned NORMAL, version 2,
with `recovery_elapsed` after the recovery window expired.

Automatic activation is disabled. Existing admission and latency counters are
process-local, and the stack has no shared signal that safely distinguishes
system-wide pressure from one abusive client. A single 429 is not used as a
trigger.

## Circuit breaker, timeout, retry, and bulkhead

Appointment's optional journey snapshot reads to Records, Pharmacy, and Billing
use one process-local breaker and bulkhead per owner. Each logical read has a
250 ms connect timeout, 500 ms read timeout, and one-second overall deadline.
Idempotent GETs get at most two attempts, with a 50 ms delay plus up to 25 ms
jitter. A bounded `Retry-After` is honored only when it fits the deadline.
Mutations are not retried by this client. Business 4xx responses and 429 do not
count as dependency failures.

Three counted logical failures in a rolling ten-second window open the breaker
for five seconds. HALF_OPEN permits one concurrent probe. The per-owner
bulkhead admits two reads and waits at most 50 ms for a slot. A full bulkhead or
open breaker leaves the snapshot pending and uses Appointment's existing
durable reconciliation path; it does not create source data or permit
discharge. The HTTP pool is bounded to six total and three keep-alive
connections.

The focused artificial-workload test held two snapshot responses open, observed
exactly two in-flight reads, rejected the third with `dependency_saturated`,
then verified both permits returned after completion. Separate tests cover
timeouts, cancellation, retry limits, 4xx/429 classification, threshold,
OPEN fast-failure, one HALF_OPEN probe, recovery, and reopening.

## Live failure, recovery, and workflow results

| Scenario | Observed result |
|---|---|
| Deferrable traffic during SURGE | Twenty concurrent authenticated Doctor autocomplete requests produced 4 accepted responses and 16 bounded 429 responses. Every observed `Retry-After` was at least one second. |
| Critical workflow during SURGE | A synthetic Emergency request was admitted; authorized staff completed its priority/claim and resolution workflow. Class A remains subject to finite source and aggregate quotas. |
| Admission Redis outage | A 20-request Doctor autocomplete burst used the conservative local fallback and returned a mix of 200 and 429 with bounded `Retry-After`. The immediate post-restart probe was still limited because the local bucket had been depleted; after waiting for the retry interval it returned 200. A separate live check after the small-bucket correction logged a Patient in successfully while Redis was down, then read the same Patient profile after Redis recovery. |
| Records service outage | Three Appointment reconciliation attempts received owner-unavailable results and opened the Records breaker. A subsequent open-breaker request returned in 39 ms. After restarting only Records and waiting six seconds, reconciliation succeeded, the breaker closed, and the journey returned to `ready` with no recorded source error. |
| RabbitMQ outage and recovery | A new Billing payment committed while RabbitMQ was stopped; its outbox row was initially unpublished and Appointment had no inbox row. After the same broker container restarted, the event was published on attempt 2 and processed by Appointment. The owner database check found one matching inbox row. The recorded times were 19:47:59 UTC (outbox create), 19:48:07 UTC (publish), and 19:48:09 UTC (inbox processing), 2026-10-12. |
| Appointment, journey, payment | A new synthetic appointment/consultation and Billing payment completed through the gateway. A later patient-owned journey read returned `ready`. |
| Prescription fulfillment | After the image rebuild, a patient-owned Pharmacy API read of the retained synthetic prescription reported state `issued`, quantity 2 dispensed, zero remaining, and one dispensing record. This was a read-only retained-data check, not a second dispensing. |
| Shared recovery state | After API recreation, the shared state still read NORMAL, version 2; the expiry decision was held in Redis rather than process memory. |

All test actors and domain data were synthetic. The Records outage stopped and
restarted only the Records API container. The Redis and RabbitMQ scenarios
stopped and restarted only the corresponding infrastructure container.

## Audit, migrations, and regressions

Appointment migration `0012_phase6_surge_audit` was at head. The live audit
history contained both transition intent and applied records. Audit events
store the administrative actor, action, bounded reason, state/version, and
request/correlation identifiers; they do not store the raw idempotency key or
clinical text. High-frequency admission decisions remain metrics rather than
audit rows.

The broad backend runner initially exposed three Doctor async tests that were
collected under pytest-asyncio strict mode. The plugin was added to Doctor's
test extra, Doctor's pytest config now uses auto mode, and the cross-service
runner explicitly applies that mode. The complete rerun passed:

| Check | Result |
|---|---:|
| `.venv/bin/python tests/run_phase2_regressions.py` | 609 passed, 52 skipped |
| Records isolated PostgreSQL suite, run by the same command | 77 passed |
| Shared rate-limiter tests (`test_surge_mode.py`, `test_adapter.py`, `test_limiter.py`) | 67 passed |
| Python compile check | Passed |
| `git diff --check` | Passed |

The 52 skips are the existing Records cases requiring its isolated runner and
the dedicated Phase 4 benchmark-driver case. The broad-run and isolated
Records totals are reported separately, not added together. Frontend files were
unchanged, so frontend tests were not run.

## Deployment health and remaining limits

All seven owner readiness aliases returned HTTP 200 through Traefik after the
seven API images were rebuilt and recreated. All seven API containers, plus
PostgreSQL, Redis, and RabbitMQ, reported healthy. Appointment remained at
`0012_phase6_surge_audit` head. Database volumes were not reset.

The circuit breakers and bulkheads are process-local by design. Their
thresholds and concurrency caps apply per API process. Redis local fallback
quotas are conservative but approximate across replicas. Automatic Surge Mode
activation remains deferred until a reliable aggregate signal is deployed.
These bounded synthetic checks are not a Phase 8 capacity campaign, production
SLO, clinical validation, infrastructure HA claim, or emergency-dispatch
guarantee.

The implementation was at local `main` commit `5406021` when final runtime
verification completed. The verification report is committed as the next local
checkpoint; neither commit was pushed.
