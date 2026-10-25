# Seven integrated components and asynchronous consistency

All seven have concrete adopters; none was found to be a disconnected demonstration. [158 current component tests](evidence/final-test-results.json) supplement service/database/live integration evidence. Historical performance measurements are not new results from this audit.

| Component | Actual adopter / authority boundary | Current execution |
|---|---|---|
| Distributed token bucket | Seven service admission adapters, Redis atomic Lua; server identity/policy/class; PostgreSQL still enforces correctness | Refill/atomicity/Surge tests pass. Real Doctor two-replica burst: 100 attempts, 72 admitted, 28 HTTP 429, 0 errors; per-replica metric deltas match. Spoofed XFF cannot expand principal quota; Emergency request reaches normal validation afterward. [Evidence](evidence/admission-http.json). |
| Consistent hashing | Doctor directory projection cache over two Redis cache nodes, 128 virtual nodes/configured node and epoch namespaces | Ring/distribution/churn tests pass. Live directory uses configured cache integration and survives both cache nodes down. Ring placement is not replication/HA; no new churn benchmark or key-distribution viewer is claimed. |
| Key-value/cache-aside | Doctor owner projection, TTL/revision namespaces/invalidation, bounded Redis calls and DB fallback | Current cache/projection tests pass; both isolated cache nodes stopped, exact authoritative directory response retained, both restarted healthy. [Evidence](evidence/live-cache-surge-checks.json). No stale cache authorizes bookings. |
| Snowflake | New Appointment short links and Billing insurance runs/rules/estimates; durable worker ranges/state | Current generator/lease/clock-edge suites pass; real alias worker 256 verified, real insurance resources persisted. Original IDs retained. Historical collision/restart campaigns were not rerun as a new large benchmark. |
| URL shortener | Appointment/check-in navigation aliases; authenticated fixed destinations, expiry/revoke/hash-at-rest; alias is not a QR credential | Real create, HTML 303 to safe fragment landing with no-referrer, authenticated JSON owner resolution, other-patient denial and revoke denial pass. [Evidence](evidence/live-emergency-shortlinks.json). |
| Synthetic crawler | Billing allowlisted fixtures, bounded fetch/parse, durable requested run/leases, immutable rules and informational estimates | Current parser/bounds/retry/DB tests pass. Three configured fixture providers, real refresh complete at revision 2, informational estimate does not change paid invoice/payment history. [Evidence](evidence/insurance-http.json). Worker polling is not periodic refresh scheduling. |
| Trie autocomplete | Doctor name/specialty and Pharmacy medicine suggestions, normalization/dedup/ranking/revision rebuild, bounded fallback | Current trie/lifecycle/owner route tests pass; real discovery/catalog routes and UI mounted. Not every live autocomplete freshness/fallback case was manually repeated. No universal speedup claim. |

## Selected real RabbitMQ paths

Pharmacy `pharmacy.reservation.dispensed.v1` and Billing `billing.payment.succeeded.v1` publish from existing transactional outboxes. Appointment uses consumer-specific durable inboxes and schedules owner-snapshot reconciliation. Producer confirmation, retries/leases, inbox uniqueness and acknowledgement after commit preserve at-least-once recovery; ordering assumptions remain per selected aggregate, not globally ordered/exactly-once delivery.

The audit reproduced a fresh-deployment failure: consumer queue declaration with a DLX requires write access to `pulsegrid.dlx`, absent from the existing whitelist. B-03 adds only that exact existing exchange. Publisher authority was unchanged. Actual isolated checks after repair:

1. Stop only the isolated broker; a real simulated payment commits and its selected outbox row remains unpublished.
2. Restart broker; event is marked published and appears once in Appointment's Billing inbox.
3. Republish the exact existing event twice; one inbox effect remains.
4. Publish one intentionally invalid synthetic envelope; DLQ increments by one and active queues drain.

[Broker evidence](evidence/live-broker-checks.json). The intentional poison message remains in the isolated DLQ as evidence; it was not injected into retained queues. [Owner snapshot](evidence/live-workflows.json) shows six Billing and two Pharmacy selected events published with corresponding inbox effects. Retained final active queues have one consumer each and zero backlog/DLQ messages.

Optional owner snapshot breakers/bulkheads/bounded retries are covered by current tests. The live gateway helper also completed its isolated dependency outage/restart branch. No blind mutation retries, locks across HTTP, competing retry infrastructure or new domain package were added.
