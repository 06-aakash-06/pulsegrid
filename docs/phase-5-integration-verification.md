# Phase 5 integration and verification

Completed 2026-10-12 for the synthetic single-hospital development stack. The
existing 17-container Compose project and PostgreSQL volumes were retained. No
volume reset, new long-running service, or remote push was used.

## Implemented checkpoints

1. Froze the two selected event contracts and their ownership rules in
   [Phase 5 event contracts](phase-5-event-contracts.md).
2. Added transactional Billing and Pharmacy outbox events, publisher-confirmed
   delivery, lease recovery, bounded retries, and event-worker metrics. The
   Pharmacy runtime role can update only outbox delivery metadata; it cannot
   rewrite the event envelope.
3. Added Appointment's two durable quorum-queue subscriptions, manual
   acknowledgments, validated envelopes, bounded redelivery, dead-letter
   handling, and an atomic inbox-plus-journey-wakeup transaction. The existing
   Appointment worker still fetches owner snapshots after the transaction.
4. Activated the publisher and consumer workers in the existing service
   containers. Billing and Pharmacy migrations advanced to their Phase 5
   revisions. No domain state is changed directly from an event.
5. Recorded live workflow, outage recovery, poison-message, regression, and
   retained-stack results below.

The Pharmacy dispense and Billing payment messages are wake-up signals only.
Appointment validates the local appointment reference, records its own inbox
row, and schedules a fresh owner-snapshot reconciliation. Inventory, payments,
authorization, and discharge eligibility remain owned by their existing
services and APIs.

## Verification results

### Isolated PostgreSQL and service tests

- `.venv/bin/python services/pharmacy/tests/run_isolated.py`: **17 basic tests
  and 11 PostgreSQL workflow tests passed**. Coverage includes producer/outbox
  rollback, publisher-confirm timeout and retry, expired lease recovery,
  concurrent claims, selected metadata grants, and denied event-envelope
  updates.
- `.venv/bin/python -m pytest services/appointment/tests/phase5_events -q`:
  **3 passed** against disposable PostgreSQL. Coverage includes concurrent
  duplicate delivery, independent subscription inbox keys, atomic rollback on
  transient failure, permanent invalid references, envelope validation, and
  the passive RabbitMQ queue declaration used by dead-letter depth polling.
- `tests/run_phase2_regressions.py services/billing/tests/test_billing_api.py`:
  **8 Billing tests and 77 Records tests passed**. Coverage includes the
  minimal payment event payload and atomic payment/outbox persistence.
- The broad `.venv/bin/python tests/run_phase2_regressions.py` run reported
  **593 passed, 52 skipped, and 3 failures**. The failures were existing Doctor
  Phase 4 async test functions collected without an async pytest plugin. Each
  of those three functions was then invoked directly with `asyncio.run` against
  its disposable PostgreSQL/Redis fixture; all three passed. Records' separate
  isolated suite passed **77 tests**. The 52 skips include its intentionally
  separate database cases and the benchmark driver case.

### Live retained-stack workflows

- `python3 tests/verify_phase3.py --fixture
  /tmp/pulsegrid-phase5-live-fixture.json` completed **10 gateway workflow
  groups** through the existing Traefik and owner APIs, using synthetic
  accounts. The run executed a real Pharmacy dispense and successful Billing
  payment. Both selected event types were confirmed in their producer outboxes
  and appeared once in their corresponding Appointment inbox subscriptions.
- RabbitMQ reported both Appointment consumers active. Appointment, Pharmacy,
  and Billing readiness returned HTTP 200, and each event-worker connection
  metric reported `1` after activation.
- A final steady-state check found that the worker's five-second dead-letter
  depth poll used an unsupported `Queue.declare(passive=True)` argument. The
  consumer reconnected repeatedly after registering both queues. This was
  corrected to use `channel.declare_queue(..., passive=True)` and its returned
  declaration result. After rebuilding and recreating only Appointment, its
  connection metric remained `1` beyond multiple polling intervals; both work
  queues reported one consumer and zero messages, both DLQ depth metrics were
  zero, and all 17 containers remained running.
- A second full gateway-fixture run after that repair was attempted with a new
  synthetic fixture, but registration returned HTTP 429 `rate_limited` before
  workflow setup. The earlier 10-group end-to-end gateway run remains the
  completed cross-service workflow check; the repaired consumer's live
  registration, metrics, and PostgreSQL tests were checked separately.
- A bounded RabbitMQ outage was exercised with a new synthetic Billing payment.
  With the broker stopped, Billing returned HTTP 201 with `status=success` in
  **0.289 seconds**; the selected outbox event remained unpublished and had no
  Appointment inbox row. The same RabbitMQ container was started again. The
  publisher then received confirmation, and Appointment recorded the event
  once.
- A malformed JSON message was published to the Pharmacy route. Appointment
  rejected it, RabbitMQ placed it in the Pharmacy dead-letter queue, and the
  replay tool's safe peek reported the dead-letter reason without printing the
  message body. The single injected poison message was acknowledged after
  inspection. Both dead-letter queues and both work queues were empty at the
  final check.
- Only Appointment, Pharmacy, and Billing API containers were recreated for
  activation and final worker verification. All **17 containers** were running
  at the final check. Pharmacy, Billing, and Appointment migration heads were
  `0007_phase5_outbox_grants`, `0010_phase5_event_delivery`, and
  `0011_phase4_alias_parent_guard`, respectively.

## Commands and limits

The three updated images built with the active authenticated Phase 4 Compose
overlays. `docker compose config --quiet`, Python compilation, and
`git diff --check` passed. The actual event payloads, inbox rows, broker queues,
worker connection metrics, service readiness, and migration heads were checked
on the retained stack.

No throughput or latency benchmark was run. The 0.289-second value is one
observed local API response during the bounded broker outage, not a performance
claim. This verification does not claim broker high availability, exactly-once
delivery, clinical validity, or coverage of the broader event proposal catalog.
All created records were synthetic.
