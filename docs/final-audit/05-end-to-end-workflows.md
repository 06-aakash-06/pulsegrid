# Executed hospital workflows

25 October 2026. All new business data was fictional and created in the separately verified `pulsegrid-audit-20261025` project. Gateway `18880`, real frontend `19173`; no mock/demo flag. [Isolation manifest](evidence/isolation-manifest.json). No retained development/demo record was mutated for testing. The existing Patient owner bootstrap established only the isolated first administrator; later staff roles used authorized Patient APIs.

## Executed journeys

| Path | Actions and persistence verified | Result / limit |
|---|---|---|
| Patient with prescription | Register/authenticate → Doctor proposal/accept/reconcile → accepted availability → book → issue opaque check-in credential → server check-in → daily token/queue → Doctor start → Records draft/finalization → prescription → Pharmacy stock/reservation/dispense → Billing consultation and medicine imports → simulated payment → fresh owner reconciliation → receptionist discharge/history | PASS through actual gateway and independent owner DBs. Expected amount 15000 INR minor units, including 2 × 2500 medicine; backend authoritative. Physical camera not used. |
| No prescription | Book/check-in/start → clinical finalization with empty prescription items → Pharmacy stage skipped → consultation charge/payment → authorized discharge | PASS; no invented prescription or medicine purchase needed. |
| Temporary offer | Fully booked slot → two FIFO waiters → cancel original → durable offer reserves capacity → concurrent acceptance requests | PASS; one accepted booking/effect. Original 500 reproduced and B-01 repaired. |
| Natural expiry/restart | Pending offer plus successor → actual wall-clock expiry → worker recovery/promotion | PASS. Final DB history: successor created 5.185877 s after first expiry. Initial backoff overshoot was repaired (B-02). Later expiration of the successor is retained history, not a failed promotion. |
| Queue | Two check-ins → doctor skip → recall → FIFO start → busy guard → finalization/completion/history | PASS. These operations were restored explicitly by historical scope extension, not optional ideas. |
| Reception | Existing-patient booking/walk-in fixture, queue/journey controls, authorized discharge and history | PASS in gateway groups and PostgreSQL suites; browser route/read coverage only for most staff mutations. |
| Dependency degradation | Existing helper's bounded isolated Billing outage/restart and reconciliation branch | Completed `workflow6` group; no claim that every service-to-service fault was exercised. |
| Emergency | Submit → assign priority → claim/replay → release/reclaim → processing → resolved → history; separate patient cancellation | PASS; other patient denied, patient DTO omits staff description/contact. [Evidence](evidence/live-emergency-shortlinks.json). |
| Insurance | Requested fixture refresh → durable run complete → rule revision 2 → owner invoice estimate/provenance | PASS; invoice and payments unchanged. [Evidence](evidence/insurance-http.json). Provider fixture rows were seeded only into the isolated Billing owner database because provider creation has no HTTP contract. |
| Browser actions | Real registration/login/logout; Emergency review/send; doctor profile tabs → accepted-slot selection → review/confirm booking → saved list/detail → review/confirm cancellation | PASS with screenshots and actual owner confirmation. [Evidence](evidence/browser/browser-checks.json). Remaining staff mutations were not all repeated through the browser. |

[Ten gateway groups, owner offer history, publisher/inbox counts](evidence/live-workflows.json). Six selected Billing events and two Pharmacy events were published and had corresponding Appointment inbox effects in the final snapshot. The broker-specific outage/duplicate/poison exercise is [separate](evidence/live-broker-checks.json).

## Cross-service consistency

Booking capacity, overlap, stock reservations/dispensing, invoice imports/payments and audit mutations retain local PostgreSQL transactions/locks/constraints. Real database tests passed; mocks are not the concurrency evidence. Clinical and financial transitions use authenticated owner APIs. Appointment projection is reconciled from owner versions; a payment event alone never authorizes discharge. Both expected charge sources and stage states were checked before discharge, and a patient discharge command was rejected.

The run was resumable with persisted fixture resources and stable idempotency keys. One consultation request returned 504 `dependency_timeout`; resuming the same fixture completed without an extra business effect. That is recovery evidence, not proof of a resolved timeout cause or uninterrupted availability.

No global transaction, broker exactly-once, predictive triage or clinical correctness claim follows from these synthetic workflows. Follow-up is a supported new appointment; no automatic reminder/follow-up engine was agreed. Physical QR optical decode remains UNVERIFIED even though the actual server credential check-in/replay path passed.
