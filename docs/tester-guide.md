# PulseGrid functional testing guide

Prepared 24 October 2026. This is a test procedure based on the current routes, components, owner APIs and contracts; it is not a report that these tests have passed.

## 1. Start here

Use this guide to answer two separate questions for every feature:

1. **Is it present?** Can the correct role reach the screen, find the control and load real owner data?
2. **Does it work?** Does the action produce the expected result, survive refresh, appear in related workspaces and reject unauthorized or invalid attempts?

A visible button, screenshot, successful HTTP response or passing unit test alone does not establish the complete workflow. Check the returned resource and reload it after each important action.

Record each case using these values:

| Field | Values |
| --- | --- |
| Presence | PRESENT, MISSING, PLACEHOLDER, API ONLY, BLOCKED |
| Result | NOT RUN, PASS, FAIL, BLOCKED, NOT APPLICABLE |
| Evidence | Screenshot and sanitized request/response details, resource ID, UTC time and defect reference |

All cases start **NOT RUN**. A missing account, empty fixture, unavailable server or unsupported camera makes the dependent case BLOCKED, not PASS. Use NOT APPLICABLE only for an explicitly unsupported feature or an agreed exclusion, with a reason.

### Login credentials

All roles use the same [sign-in screen](http://127.0.0.1:5173/login). There is no separate staff password or role selector that grants access.

**Open the [private local login appendix](../secrets/tester/login-credentials.md) for the recovered email/password pairs and account sources.** This appendix is inside the existing Git-ignored `secrets/` directory. It is intentionally unavailable in a fresh clone. Keep it local and do not attach it to defects or publish it. Missing credentials and verification limits are listed there explicitly.

| Login type | Required backend role | First page |
| --- | --- | --- |
| Patient | `patient` | `/patient/dashboard` |
| Doctor | `doctor` | `/doctor/dashboard` |
| Pharmacist | `pharmacist` | `/pharmacist/dashboard` |
| Billing staff | `billing_staff` | `/billing/dashboard` |
| Emergency staff | `emergency_staff` | `/emergency/dashboard` |
| Hospital administrator | `hospital_admin` | `/admin/dashboard` |
| Receptionist | `receptionist` | `/receptionist/dashboard` |
| Operations | `ops` | `/ops/dashboard` |

Use separate browser profiles for different accounts. Two tabs on the same origin share refresh cookies and can change each other's session. Use two patient-only accounts, two mapped doctors and two emergency staff accounts for ownership, queue and claim tests. A multi-role administrator account cannot prove patient-only or ops-only restrictions.

### Environment and test data

1. Follow [README startup](../README.md#run-locally). For an existing installation, preserve its `.env`, signing keys, Compose overlays and volumes. Successful frontend startup alone does not mean the backend works.
2. Open `http://127.0.0.1:5173`. Gateway default: `http://127.0.0.1:8080`. Use the configured hostname consistently; `localhost` and `127.0.0.1` are different authentication origins.
3. Check Patient readiness at `http://127.0.0.1:8080/api/v1/patients/health/ready`. Ask the maintainer to confirm all seven domains and migrations are healthy. Record the actual frontend URL, backend URL, commit and overlays in the report.
4. Obtain synthetic accounts from the appendix. For initial administrator setup only, see [Patient bootstrap instructions](../services/patient/README.md). Normal registration grants a patient identity; authorized administrators assign staff roles. A doctor account also needs a Doctor-owned profile mapped to its user ID.
5. Prepare a new test run prefix such as `QA-20261024-01`, synthetic `.test` emails, active doctors/specialties, accepted future slots, medicine stock in unexpired batches and Billing tariffs for consultation and the selected medicines. Record all full IDs; short display labels are not API IDs.
6. For check-in, prepare a visit whose start is near the current server time. The check-in window is **30 minutes before start through 15 minutes after start, excluding the end instant**. Old demo dates are historical evidence and cannot support a new booking/check-in test.
7. For insurance, the maintainer must configure the allowlisted synthetic provider fixtures and worker. For telemetry, use the [observability runbook](phase-7-observability-design.md). No samples or missing optional telemetry must be reported honestly.
8. Open browser developer tools for the Network and Console panels. Capture safe error codes, HTTP status and request IDs. Redact Authorization/Cookie headers, passwords, QR secrets and raw short-link aliases from shared evidence.

Create new synthetic resources for tests. Keep retained visits and audit history intact. Do not rerun fixture scripts blindly: some create data, perform payments or change infrastructure. No outage, load experiment, clock manipulation or volume reset is part of the ordinary browser checklist.

**Hosted demo limitation observed 24 October 2026:** `pulsegrid-ruddy.vercel.app`
was in mock-data mode and stated that it does not create accounts. Its Patient
readiness route fell through to the demo's not-found page. Use a service-backed
installation for AUTH-02 and verify Patient readiness before entering any
registration details. A static frontend deployment alone cannot create a
Patient identity.

## 2. Route and feature presence inventory

Visit every path as its permitted role, both through navigation and by typing the URL, then refresh. Base paths such as `/doctor` should redirect to that workspace's dashboard. Check each alias even when it shares a component.

| Workspace | Paths to visit | Expected content |
| --- | --- | --- |
| Public | `/`, `/login`, `/register` | Landing page, sign-in, synthetic patient registration |
| Patient | `/patient/dashboard` | Reception, current patient details and expandable profile editor |
| Patient | `/patient/doctors` | Consultation directory, specialties/search, doctor details and booking |
| Patient | `/patient/appointments` | Booking and own appointment management |
| Patient | `/patient/waitlist` | Join/withdraw entries and temporary slot offers |
| Patient | `/patient/check-in` | One-time QR issue/redeem, camera and manual fallback |
| Patient | `/patient/queue` | Own live queue, token, position and aggregate counts |
| Patient | `/patient/journey` | Six care stages, freshness, reconciliation and history |
| Patient | `/patient/records` | Visit history, selected clinical record, related prescriptions and access grants |
| Patient | `/patient/prescriptions` | Own prescription details and fulfillment context |
| Patient | `/patient/pharmacy` | Medicine catalog and own reservation/dispensing status |
| Patient | `/patient/billing` | Own invoices, simulated payment/history and insurance estimates |
| Patient | `/patient/emergency` | Synthetic request submission, tracking and permitted cancellation |
| Doctor | `/doctor/dashboard` | Own mapped profile, accepted availability and schedule proposal/decision/reconcile tools |
| Doctor | `/doctor/consultations` | Assigned consultation create/draft/finalize, authorized records and amendment tools |
| Doctor | `/doctor/queue` | Assigned queue, call next, skip/recall and history |
| Doctor | `/doctor/prescriptions` | Medicine lookup and authorized prescription review/revocation |
| Pharmacist | `/pharmacist/dashboard`, `/pharmacist/inventory` | Catalog, stock/batches, maintenance and link to dispensing |
| Pharmacist | `/pharmacist/prescriptions` | Prescription validation, fulfillment lookup, reservation/revalidation/release/dispense and history |
| Billing | `/billing/dashboard`, `/billing/invoices`, `/billing/payments` | Shared invoice/payment workspace, source imports, read-only tariff reference and expandable tariff creation desk |
| Billing | `/billing/insurance` | Synthetic providers, refresh commands and run progress |
| Emergency | `/emergency/dashboard`, `/emergency/requests` | Shared staff request register, priority, claim and state actions |
| Admin | `/admin/dashboard` | Patient demographics and authorized catalog tools |
| Admin | `/admin/staff` | Account search, role replacement and active/disabled state |
| Admin | `/admin/doctors` | Specialty/doctor creation, profile management and schedules |
| Admin | `/admin/control-room`, `/admin/traces` | Technical telemetry, administrative Surge controls and traces |
| Admin | `/admin/settings` | **Navigation-only administration desk.** Links to staff, doctors and operations; explicitly no settings API or settings save action |
| Receptionist | `/receptionist/dashboard` | Patient demographics search and permitted edits |
| Receptionist | `/receptionist/appointments` | Booking/management/walk-in and expandable check-in/journey operations |
| Operations | `/ops/dashboard`, `/ops/traces` | Technical monitoring and traces; ops-only account has no Surge mutation controls |
| Short links | Generated `/s/<alias>` and `/short-link` landing | Authorized navigation only; an alias never checks a patient in |

There are **35 workspace routes**, plus public and short-link entry points. `/admin/settings` is the explicit directory placeholder, not a functioning configuration editor. Mark missing supported controls as defects; do not mistake old fallback text in route metadata for proof that a mounted feature is absent.

## 3. First complete patient journey

Run this once before the detailed cases. Keep the same patient, appointment and doctor throughout. Record appointment, journey, consultation, record, prescription, reservation, dispensing, dispensing-item and invoice IDs as they are returned.

| Step | Role and action | Expected result |
| --- | --- | --- |
| 1 | Patient: register, sign in, open Reception and update synthetic contact | Profile is owner-confirmed and persists on reload |
| 2 | Doctor/admin: prepare a future schedule, request Appointment's decision and reconcile Doctor | Accepted revision has actual bookable slots |
| 3 | Patient: choose that doctor/date/slot, review and confirm booking | One confirmed appointment, with workflow/journey discoverable for new enrolled bookings |
| 4 | Patient: issue QR and explicitly confirm check-in inside the server window | One checked-in workflow and one queue token; issuing/opening QR alone did not check in |
| 5 | Doctor: open assigned queue and call next | Correct FIFO entry enters consultation; patient sees the change |
| 6 | Doctor: create assigned consultation, save draft, finalize with one stocked medicine | Finalized consultation, immutable record, issued prescription; queue completes after owner confirmation/reconciliation |
| 7 | Patient/pharmacist: reserve the prescribed quantity; pharmacist validates/revalidates and dispenses | One dispensing; stock and prescribed allowance reflect actual quantities |
| 8 | Billing staff: create invoice and import consultation plus committed dispensing sources | Itemized authoritative INR invoice, quantities/prices and correct total; reservation alone added no charge |
| 9 | Patient or permitted Billing staff: submit a simulated successful payment | Paid/history/balance update; refresh confirms persistence |
| 10 | Patient/receptionist: reconcile journey; receptionist discharges when eligible | All required stages complete/skipped with source evidence, then administrative state `discharged` |

If blocked, record the earliest failing step and continue independent cases. A zero balance before all sources are imported does not establish financial completion. Administrative discharge is not a clinical fitness decision.

## 4. Detailed browser test cases

For every mutation that offers Review/Confirm, inspect the review, confirm once, inspect the owner response, then reload. Also cancel a review once and confirm it created no resource. Some controls, including waitlist offer actions, submit directly; record their actual behavior rather than assuming every button opens a review.

### A. Authentication, navigation and sessions

| ID | Action | Expected result |
| --- | --- | --- |
| AUTH-01 | Open landing, sign-in and registration; follow their links and use Back/Forward | Correct destination, readable content and no blank screen |
| AUTH-02 | In a service-backed installation, register a unique synthetic name/email with a 12+ character password, then sign in | Registration succeeds without automatic privileged access; sign-in restores server-authorized workspace |
| AUTH-03 | Submit invalid email, short/missing password, missing name and duplicate email | Field/server validation is safe; no extra account or privileged role is created |
| AUTH-04 | Try incorrect password and unknown account | Generic safe sign-in failure; no authenticated workspace |
| AUTH-05 | Sign in with each of the eight roles and open its permitted paths | Correct role routing; unavailable accounts are BLOCKED |
| AUTH-06 | Refresh a protected page and wait through access-token expiry while making a permitted read | Session restores/refreshes or explicitly asks for sign-in; no endless refresh loop |
| AUTH-07 | Sign out, revisit protected URL and use browser Back | Protected data/actions unavailable; no stale session restored |
| AUTH-08 | Patient-only user opens `/admin/staff`, `/doctor/queue`, `/ops/dashboard` | Access denied/redirected; no privileged requests succeed |
| AUTH-09 | Open an unknown public path and unknown workspace child | Useful not-found state; no unrelated action or data |
| AUTH-10 | Inspect browser storage after sign-in, QR issue and sign-out | No passwords/access tokens/QR secrets in localStorage or sessionStorage; HttpOnly cookies remain unreadable to app JavaScript |
| AUTH-11 | Use two same-origin tabs; sign out in one, make next refresh/privileged request in the other | Revoked authority fails as documented; immediate cross-tab UI logout is not assumed |

### B. Patient profile and administration

| ID | Action | Expected result |
| --- | --- | --- |
| PAT-01 | Open Reception → Your profile; edit name, date of birth and synthetic contact | Correct own profile/version after save and reload |
| PAT-02 | Enter future birth date, unchanged form and invalid field lengths | Clear validation and no unintended update |
| PAT-03 | Receptionist/admin searches patients and opens an authorized profile | Bounded results, correct selected patient and persisted permitted edit |
| PAT-04 | Patient A tries Patient B's full profile/resource ID | No unauthorized data or mutation; safe denied/concealed response |
| ADM-01 | Admin searches users, filters account state and paginates | Correct results and selected identity; no duplicate pages |
| ADM-02 | Admin replaces roles on a disposable test account, then signs into that account afresh | Exact requested roles persist; UI and backend permissions match |
| ADM-03 | Admin disables and reenables a disposable account | Disabled account loses the applicable authority/session access; reenabled account can sign in under current roles |
| ADM-04 | Non-admin attempts the same role/state APIs | Denied by server, including direct requests |
| ADM-05 | Open Administration desk and follow its three owner links | Working links; no invented hospital-settings save action |

Use a spare account for authority tests and retain an active administrator. Restore deliberate temporary role/state changes and record the restoration.

### C. Doctor discovery and schedules

| ID | Action | Expected result |
| --- | --- | --- |
| DOC-01 | Search directory, change specialty, select different doctors and load more | Real owner profiles; selected details and specialty agree; pagination remains usable |
| DOC-02 | Type matching/nonmatching prefixes in quick lookup; use keyboard selection | Relevant suggestions or explicit empty/error state; stale earlier search does not replace current text |
| DOC-03 | Admin creates a synthetic specialty and mapped doctor; edits profile | Entries persist; user has doctor role and correct staff-user mapping |
| DOC-04 | Mapped doctor loads `/doctor/dashboard`; unmapped doctor tries it | Own profile only; unmapped account receives a truthful error rather than another doctor's profile |
| DOC-05 | Submit future ordered intervals, timezone, duration and expected revision; request decision; reconcile | Proposal, persisted accepted decision and accepted availability agree |
| DOC-06 | Try past/overlapping intervals, invalid timezone, misaligned duration and stale revision | Rejected safely; previously accepted slots remain unchanged |
| DOC-07 | Propose a closure/change conflicting with a confirmed booking | Conflicts are explicit; no silent cancellation or loss of accepted bookings |
| DOC-08 | On a new empty doctor, accept/reconcile closure before deactivation | No new bookable capacity after closure/deactivation; existing data retained |
| DOC-09 | Ordinary doctor tries to edit another doctor, specialties or privileged mapping | Backend denies unauthorized changes |

Schedules use UTC interval timestamps even when their IANA timezone defines the queue day. A proposal alone is not an accepted operational schedule.

### D. Appointments and reception walk-ins

| ID | Action | Expected result |
| --- | --- | --- |
| APT-01 | Select doctor, UTC date and available slot from directory/booking desk | Summary reflects that doctor/date/time and actual patient |
| APT-02 | Change date, date range or doctor after choosing a slot | Previous slot clears; invalid range does not issue an invalid availability query |
| APT-03 | Review booking; attempt to change selection while review is frozen; cancel, then confirm a new review | Frozen command cannot silently change target; cancelled review writes nothing; confirm creates one booking |
| APT-04 | Patient opens My Appointments, including with a multi-role patient account | Own patient filter; another patient's staff-visible appointments do not leak into patient list |
| APT-05 | Reschedule a new confirmed appointment to another accepted slot | Same appointment ID, new slot/times, old capacity released and old QR credentials invalidated |
| APT-06 | Cancel a new confirmed appointment with a reason | Cancelled state persists; slot released and credentials revoked; unrelated visits unchanged |
| APT-07 | Two patients confirm the same slot near-simultaneously in separate browser profiles | At most one direct booking succeeds; loser gets safe conflict; inspect persisted owner state |
| APT-08 | Try overlapping appointments for the same patient, stale schedule revision and stale appointment version | Conflict/version rejection; no double booking or silent overwrite |
| APT-09 | Receptionist uses Walk-in: search existing patient, choose doctor/slot, confirm | Booking belongs to selected existing patient; no invented new-patient registration is implied |
| APT-10 | Try cancel/reschedule after check-in, consultation start and completion | Only contract-permitted actions succeed; checked-in reschedule/clinical hold/terminal workflow gates are enforced |
| APT-11 | Reload list/detail and navigate between booking/management after each action | Owner-confirmed values persist; receipt is not mistaken for current availability |

### E. Waitlists and temporary offers

Use two or more eligible synthetic patients and one occupied future slot. Record slot ID and accepted schedule revision. Release capacity by cancelling only a booking created for this run; wait for the configured worker and record elapsed time rather than assuming an SLA.

| ID | Action | Expected result |
| --- | --- | --- |
| WAIT-01 | Join the occupied slot waitlist; reload own list/count | One waiting entry, correct slot/revision and aggregate count; no invented exact personal position |
| WAIT-02 | Repeat active join, use invalid slot/stale revision and inspect another patient's entry | Safe duplicate/validation/conflict or scope rejection |
| WAIT-03 | Withdraw own waiting entry with reason | Persisted withdrawn state and changed waiting count |
| WAIT-04 | Join A then B; release capacity | First eligible FIFO candidate gets a durable temporary offer; no booking until acceptance |
| WAIT-05 | Accept pending unexpired offer | One confirmed appointment, accepted offer and promoted entry; direct arrivals could not take held capacity |
| WAIT-06 | On separate offers, decline and allow expiry | No appointment for declined/expired candidate; hold released and next eligible candidate can be offered capacity |
| WAIT-07 | Accept after expiry, accept twice or race expiry with acceptance | One durable outcome; no second booking or stale offer success |
| WAIT-08 | Patient and multi-role patient refresh offers/list | Own patient scope; no other patients' offers; full IDs discoverable for investigation |

Current extended behavior is **offer → explicit accept**. Older text about promotion without offers must not override this expectation. If Decline fails validation, record the server code/payload and report it; do not mark an offer passed merely because the button exists.

### F. QR, staff check-in and waiting room

| ID | Action | Expected result |
| --- | --- | --- |
| CHECK-01 | Select booked appointment and issue one-time QR/token | Valid same-origin fragment URL and expiry; workflow still booked |
| CHECK-02 | Open generated QR landing URL without confirming | Secret fragment cleared from address bar; no check-in mutation on navigation |
| CHECK-03 | Explicitly confirm inside allowed window; refresh own queue | One checked-in workflow, queue entry/token and journey stage |
| CHECK-04 | Reuse consumed token with a different command, use wrong/expired/revoked token | Safe rejection, no additional queue entry; identical successful-key replay tested separately below |
| CHECK-05 | Try before start−30 minutes and at/after start+15 minutes | Server rejects outside the window; issue and redemption are distinct actions |
| CHECK-06 | Patient B attempts Patient A's token/appointment; scan a foreign-origin or malformed QR | No unauthorized check-in or arbitrary navigation |
| CHECK-07 | Scan real displayed/printed QR on camera-capable device, review and confirm | Actual decode and owner-confirmed check-in; permission prompt alone is not a pass |
| CHECK-08 | Deny camera, cancel pending permission, leave route and use manual appointment/token entry | Camera lifecycle stops; manual flow still works; no camera requirement for check-in |
| CHECK-09 | Receptionist expands Check-in and journey operations; uses token and separate audited staff fallback | Appropriate scope/window/version/reason enforced; fallback does not require a QR secret |
| CHECK-10 | Receptionist marks a separate eligible visit no-show after its window | Workflow/queue/journey reflect no-show; early or clinically held attempts rejected |
| QUEUE-01 | Patient opens Waiting Room and selects checked-in appointment | Own token, state, position, counts and freshness; no other patient identities or fabricated minute estimate |
| QUEUE-02 | Update queue as doctor while patient page remains visible | Polling reflects owner change; page refresh confirms it |
| QUEUE-03 | Temporarily use browser offline mode, then restore; hide/show tab | Explicit stale/reconnecting/error state and recovery; no false live success or duplicate mutation |

### G. Doctor queue and clinical records

| ID | Action | Expected result |
| --- | --- | --- |
| CLIN-01 | Doctor opens own queue/date and calls next with confirmation | Oldest waiting entry starts; queue, workflow and patient view agree |
| CLIN-02 | Attempt another start while doctor is busy, non-head start and another doctor's entry | Server rejects invalid/unauthorized start; no parallel consultation for that doctor |
| CLIN-03 | Skip waiting entry with reason, inspect history, recall it and explicitly start | History persists; skipped position absent; recall uses original token order, does not finalize clinical work |
| CLIN-04 | Create consultation for assigned in-consultation visit; save summary/assessment/plan draft | Correct appointment/patient/doctor mapping and persisted draft version |
| CLIN-05 | Finalize draft with valid medicine/quantity/dosage/instructions | Finalized consultation, immutable record and issued prescription; queue completes only after confirmed owner coordination |
| CLIN-06 | Finalize separate consultation without a prescription | Record exists; journey prescription/pharmacy stages skip only on confirmed no-prescription source |
| CLIN-07 | Repeat finalize, edit finalized draft and attempt unassigned visit | No duplicate record/prescription; no unauthorized edit or clinical access |
| CLIN-08 | Patient opens Medical Records and switches between two visits | Correct summary/assessment/plan, revision and prescriptions filtered by selected consultation AND own patient |
| CLIN-09 | Authorized doctor amends a record with required reason | New immutable revision/supersession; original preserved; journey review/reopening handled explicitly |
| CLIN-10 | Patient grants historical access to a doctor for a supported scope/expiry, tests access, then revokes/expires it | Only permitted scope and resources accessible; subsequent checks reject expired/revoked access |
| CLIN-11 | Inspect records as billing staff/pharmacist/admin without clinical permission | No clinical notes exposed just because user has a staff/admin role |
| CLIN-12 | Doctor opens/revokes a test prescription; patient reloads visit history and prescription page | Revoked state and retained historical instructions; no silent deletion |

Keep the returned access-grant ID and version: the current UI/API does not provide a general historical-grant list/lookup endpoint. Do not report this as a working grant directory.

### H. Pharmacy catalog, stock and fulfillment

| ID | Action | Expected result |
| --- | --- | --- |
| PHARM-01 | Patient searches catalog, uses quick lookup and availability filters, opens medicine | Owner name/status/version and explicit unknown state; filters apply to the displayed page where labelled |
| PHARM-02 | If development demo cohort is enabled, toggle Show all owner records and search legacy fixture | Full catalog remains accessible; illustrative labels do not rewrite owner records |
| PHARM-03 | Pharmacist creates medicine, edits active/catalog fields and reloads | Correct persisted medicine/version; patient lacks maintenance controls and server permission |
| PHARM-04 | Pharmacist adds synthetic batch stock and performs permitted adjustment with expected batch version/reason | on-hand/reserved/available remain consistent; stale adjustment rejected |
| PHARM-05 | Test expired batch, insufficient stock, invalid quantity and reduction below reserved stock | Safe rejection/exclusion; no negative usable stock |
| PHARM-06 | Patient selects own issued prescription and reserves part/all allowed quantity | Correct reservation/expiry and reserved allowance; reservation does not mean dispensed |
| PHARM-07 | Release a new reservation; allow another to expire | Availability restored once, durable history retained |
| PHARM-08 | Pharmacist loads prescription fulfillment and checks available stock | Records state/revision agrees with Pharmacy; quantity and reservation/dispensing source IDs visible |
| PHARM-09 | Revalidate and dispense valid reservation; refresh patient/staff views | Exactly one dispensing, correct stock decrease and dispensed/remaining quantity |
| PHARM-10 | Repeat dispense; try over-prescribed reservation/dispensing and another patient's resources | No duplicate dispensing or exceeded prescription allowance; unauthorized access rejected |
| PHARM-11 | Revoke unfilled prescription then revalidate its reservation | Unfilled reservation released; history retained and no further dispensing allowed |
| PHARM-12 | In separate synthetic fixture, revoke after partial/completed dispensing | Dispensed history retained; review flag and journey blocking/reopening, no fabricated stock rollback |
| PHARM-13 | In separate profiles race reservations for limited stock/remaining allowance | Sum of successful allocations stays within actual stock and prescribed allowance; inspect owner state |

### I. Billing, payments and insurance

| ID | Action | Expected result |
| --- | --- | --- |
| BILL-01 | Billing staff opens all three invoice/payment route aliases and creates invoice for test appointment | Correct appointment/patient invoice; aliases share supported cashier behavior |
| BILL-02 | Inspect Charge pricing reference | Actual Billing tariff revisions/INR values, including historical revisions; reference does not add charges |
| BILL-03 | Import finalized Records consultation and committed Pharmacy dispensing sources | Correct source IDs, quantity, tariff revision, integer-paise arithmetic and itemized total |
| BILL-04 | Repeat import; try wrong-appointment source or reservation ID as dispensing source | No duplicate charge, foreign charge or charge from a reservation |
| BILL-05 | Patient opens own invoice; attempts staff creation/import/tariff APIs directly | Own authorized view/payment only; no staff actions or unauthorized server success |
| BILL-06 | Submit simulated decline, reload history, then a simulated success | Decline retained with unchanged paid balance; success updates balance once |
| BILL-07 | Make partial payment, pay remaining balance, retry original payment command | Correct remaining balance and final paid state; successful replay adds no duplicate money |
| BILL-08 | Try negative/zero/noninteger amount, excess payment, stale invoice and foreign invoice | Validation/version/ownership rejection with correct retained balance |
| BILL-09 | Billing staff refreshes configured synthetic provider and follows run progress | Accepted run reaches truthful success/failure; bounded fixture source, timestamps and safe error state |
| BILL-10 | Patient/staff creates estimate for authorized invoice/provider/policy and reloads estimate history | Simulated label, estimate/eligible amount, invoice/rule revisions and source run present |
| BILL-11 | Change invoice/rules then read old estimate; try provider/worker unavailable | Stale/unavailable explicitly shown; no fabricated coverage approval |
| BILL-12 | Compare invoice and payment history before/after estimate refresh/calculation | Estimate did not alter actual charges, balance or payment history |
| BILL-13 | Billing staff expands Tariffs and charge pricing, creates a new tariff revision for a test charge code and reloads | Revision and integer-paise INR amount persist; existing imported invoice lines retain their recorded tariff revision |

The cashier's Charge pricing reference is read-only. Tariff creation is a separate staff-only disclosure labelled **Tariffs and charge pricing** near the end of the billing workspace; expand it to find Create tariff revision. Do not mark it missing after inspecting only the reference panel. Its owner API is `POST /api/v1/billing/tariffs`.

### J. Emergency requests

| ID | Action | Expected result |
| --- | --- | --- |
| EMER-01 | Patient submits clearly synthetic description/contact and reported urgency | One submitted request; tracked owner ID/state persists |
| EMER-02 | Patient cancels a separately created request when permitted | Cancelled state with reason; no staff priority or claim controls |
| EMER-03 | Emergency staff opens register and sets numeric priority | Owner-assigned priority/state persists; priority differs from patient-reported urgency |
| EMER-04 | Staff claims, releases and reclaims test request | Actor-bound claim/lease and valid transitions; no arbitrary supplied staff identity |
| EMER-05 | Claimant starts processing and resolves | Valid processing/resolved history; claim released as owner contract specifies |
| EMER-06 | Two staff members race claim; nonclaimant tries processing/resolution | One claim wins; unauthorized transition rejected |
| EMER-07 | Test lease expiry/reclaim and stale resource version | No stale claimant or stale-version overwrite |
| EMER-08 | Patient B attempts Patient A's request/tracking details; patient attempts priority/claim API | Ownership/role rejection; no leaked request details |
| EMER-09 | Submit invalid/oversized content and attempt terminal-state commands | Clear validation/transition conflict; retained final state unchanged |

These are simulated request workflows. No ambulance dispatch, predictive triage, vitals, treatment, admission or bed-management feature is implied.

### K. Journeys and reconciliation

| ID | Action | Expected result |
| --- | --- | --- |
| JOUR-01 | Patient opens journey for test appointment and history | Six stages: appointment, check-in, consultation, prescription, pharmacy, billing; timestamps/source versions/pending reasons |
| JOUR-02 | Reconcile during incomplete care, reserved-only pharmacy and missing/unpaid charges | Stages remain pending for actual missing effects; no premature ready/discharge |
| JOUR-03 | Complete clinical work, full dispensing and all charge imports/payment, then reconcile | Ready/eligible only with required complete authoritative sources and no review flag |
| JOUR-04 | Receptionist discharges eligible journey; patient tries same command | Administrative discharged state persists; patient command denied |
| JOUR-05 | Try discharge before ready, with stale version or after a source change | Rejected/pending/review as appropriate; no false completion |
| JOUR-06 | After discharge make a separately scoped test amendment/revocation and reconcile | Later owner change reopens/flags review; original record/financial effects retained |
| JOUR-07 | Open another patient's journey with patient account; another doctor's with doctor account | Scoped denial; no clinical content in journey metadata |

Legacy Phase 2 appointments can have a null journey reference. Test new enrolled appointments; do not mark historical absence as a new-booking failure. Owner snapshots are not a globally atomic snapshot, and later changes can reopen a discharged journey.

### L. Control Room, traces and Surge Mode

| ID | Action | Expected result |
| --- | --- | --- |
| OPS-01 | Admin and ops-only user open Control Room and inspect each service | Seven domains, real readiness/replica data and clear missing-data state |
| OPS-02 | Inspect throughput, p95, HTTP errors, alerts/trends, RabbitMQ, outbox, Redis, topology and circuit/bulkhead panels | Measured values or explicit unavailable/no-data; missing sample not presented as measured zero |
| OPS-03 | Click service inspection, event history, traces and configured Grafana link | Correct disclosures/navigation; real owner audit/event data and optional monitoring |
| OPS-04 | Open recent trace and span summary; inspect shared evidence | Real safe service/operation timing; no token/clinical content exposure |
| OPS-05 | Patient/ordinary staff directly attempts monitoring and Surge APIs | Current role checked by backend; no unauthorized telemetry/operations data |
| OPS-06 | Compare admin with ops-only account | Admin Surge controls present; ops-only has monitoring access and no Surge write authority |
| OPS-07 | In a separately approved isolated run: admin enters SURGE, begins RECOVERY and waits for NORMAL | Reviewed reason/version/audit and actual server transition; recovery confirmed, not inferred from click |
| OPS-08 | In that same scope test invalid incident-override combination and stale command | Validation/version conflict; no accidental global policy change |

OPS-07/08 change shared admission policy. Schedule them with the maintainer and restore/check the original state before ending. Ordinary visual inspection must not change Surge Mode. Missing telemetry must not block unrelated hospital workflows.

### M. Secure short links

| ID | Action | Expected result |
| --- | --- | --- |
| LINK-01 | Expand appointment Secure appointment links; create/copy appointment and eligible check-in navigation link | Owner-created opaque same-origin alias, expiry and copy/manual fallback |
| LINK-02 | Open alias signed out, as correct owner and as another patient | Authentication/authorization required; no public clinical data or check-in effect |
| LINK-03 | Open check-in-purpose alias | Navigates to workflow; no QR credential issued and no check-in on GET |
| LINK-04 | Revoke alias, try it after expiry and after relevant appointment lifecycle changes | Safe unavailable response; no bypass via old link or arbitrary redirect |

## 5. Engineer-assisted correctness and recovery checks

These prove properties a browser walkthrough cannot establish. Use disposable synthetic fixtures and current [Phase 2](phase-2-api-contracts.md), [Phase 3](phase-3-api-contracts.md) and [Phase 4](phase-4-component-contracts.md) schemas. Keep tokens/passwords in a local API tool environment; never paste them into this guide or a shared report.

For retryable owner POST commands, capture the exact body and `Idempotency-Key`. For conditional changes, GET the resource, retain its actual ETag and send `If-Match`; do not substitute a shortened ID or guess a current version. Register/login have their own anonymous command/CSRF/Origin requirements in [authentication integration](authentication-integration.md).

| ID | Procedure | Required evidence/result |
| --- | --- | --- |
| API-01 | Replay same authorized body/key; reuse key with different body; omit required key/version; send stale If-Match | Same saved effect on valid replay; safe mismatch/missing/stale rejection, no duplicate effect |
| API-02 | Lose a mutation response and recover using original command where supported | Determine actual committed owner state; no blind new-key duplicate. QR secret issuance has special no-secret-replay/reissue rules |
| API-03 | Send missing/invalid/expired JWT, foreign/missing Origin, missing/bad CSRF and forged public actor headers | Appropriate safe denial; backend authorizes independently of UI hints |
| API-04 | Revoke role/disable account and retry privileged command with still-unexpired access token | Current authority gates privileged writes; no stale role bypass |
| API-05 | Exercise stable pagination/cursor filters and queue changes between pages | Bounded pages, no silent scope expansion; queue snapshot conflict reloads first page |
| API-06 | Run actual PostgreSQL concurrency tests for bookings, waitlist offers, queue start, stock, payments and audit append | Durable constraints/locks enforce one legal effect; mocked DB tests are insufficient |
| API-07 | Verify audit append/chain and per-service DB ownership with scoped tooling | Mutation evidence and continuity; no cross-domain database queries or credentials |
| API-08 | Exercise configured admission limit with a bounded request count | 429 and Retry-After handled distinctly from validation/5xx; no claimed throughput from this functional test |
| API-09 | Inspect cache freshness and autocomplete after owner changes | Updated owner state or documented bounded staleness; cache never authorizes booking/stock/payment correctness |
| API-10 | Test new IDs across authorized worker/clock/restart scenarios with existing integration suite | Decimal-string uniqueness and safe refusal on invalid clock/worker state; no collision claim without execution |
| REC-01 | In separately approved scope stop broker, commit one eligible synthetic owner mutation, restore/replay including duplicate/out-of-order event | Owner commit survives; existing outbox published and inbox/effects deduplicate; owner-backed journey eventually reconciles |
| REC-02 | In separately approved scope interrupt cache/admission dependency and restore | Safe documented fallback/degraded behavior; booking/financial constraints remain PostgreSQL-owned |
| REC-03 | In separately approved scope make Records/Pharmacy/Billing unavailable during reconciliation/discharge | Bounded failure, retained source data and pending/owner-unavailable; recovery reconciles and no false discharge |
| REC-04 | In separately approved scope interrupt optional telemetry, then restore | Clear monitoring failure; core hospital workflow remains available |
| REC-05 | In separately approved scope restart worker/API during pending idempotent/outbox/recovery work | Durable recovery, no duplicate booking/dispensing/payment; readiness restored |

For each recovery test agree on target, stop condition, maximum duration and recovery command before starting. Preserve volumes. Verify readiness, outstanding work and original admission/configuration state afterwards. Use [event delivery](phase-5-integration-verification.md), [resilience](phase-6-integration-verification.md) and [observability](phase-7-integration-verification.md) runbooks. These rows are not authorization to run destructive or shared-stack chaos.

## 6. Usability and display checks

Repeat primary patient and staff routes at **1536×1024, 1440×900, 1280×800 and 390×844**. Check narrower devices used by the actual tester as additional coverage.

| ID | Check | Expected result |
| --- | --- | --- |
| UX-01 | Resize, scroll and open disclosures/forms on each department | Readable content; no unintended page-wide horizontal overflow, clipped confirmation or inaccessible actions |
| UX-02 | Use Tab/Shift+Tab/Enter/Space through navigation, search and forms | Visible focus, labels, usable keyboard controls and no keyboard trap |
| UX-03 | Use browser zoom and reduced-motion preference | Essential content and controls remain usable; motion preference respected |
| UX-04 | Trigger empty results, loading, validation error, network error and safe retry | Truthful distinct states; no fake records, prices, queue positions or success receipts |
| UX-05 | Switch selected patient/visit/prescription/invoice rapidly | Old response never appears under a different selected resource; pending command target stays frozen |
| UX-06 | Inspect all numbers, dates, statuses and histories | UTC clearly labelled; INR integer minor units converted correctly; full IDs available where needed and statuses match owner responses |
| UX-07 | Check browser Console/Network after each main workflow | Investigate unexplained exceptions, failed requests, duplicate submits and leaked secrets |

## 7. Known boundaries to classify correctly

These are source/documentation observations, not newly executed test results:

- Administration settings is a navigation desk, not a separate configuration API.
- The cashier pricing reference is read-only; tariff creation is in the separate expandable staff tariff desk.
- Historical access grant IDs must be retained; no general grant directory exists.
- The current UI contains some legacy waitlist wording; verify actual temporary-offer accept/decline behavior and report contradictions.
- Physical QR camera decoding and an ops-only browser session were not fully verified in the recorded Phase 9 checkpoint. Test them afresh; a camera permission prompt does not prove scanning.
- Patient lists, waitlists, offers, visit prescriptions and queue data must stay owner-scoped even when an account also has staff roles.
- Payments/insurance and emergency requests are synthetic. No real payment gateway, insurer decision, ambulance dispatch, labs/imaging/vitals, retail cart, beds or staff census is supported.
- Password reset, MFA and production deployment/clinical certification are not established features. Do not invent tests claiming they exist.
- Prior screenshots, fixture files, test counts and benchmark numbers are historical evidence. They do not prove the currently running checkout is healthy. See [README status](../README.md#current-status), [Phase 9 continuation](phase-9-resume.md) and [latest visual limits](phase-9-visual-fidelity-corrections.md).

## 8. Optional automated verification

From the repository root, with the existing frontend dependencies installed:

```sh
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build
git diff --check
```

Backend tests are colocated in each service. Ask the maintainer to select the correct package environment and disposable PostgreSQL setup from [regression runner](../tests/run_phase2_regressions.py) and the phase-specific verification docs. Do not copy infrastructure-failure or fixture commands onto a retained stack without checking their prerequisites and effects. Automated results supplement, but do not replace, the role and real workflow checklist.

## 9. Tester report template

Copy this into a new local report; do not overwrite this guide. Never include the credential appendix, passwords, tokens or unredacted HAR/cookies.

```markdown
# PulseGrid test run

- Tester / date / timezone:
- Commit / branch:
- Frontend URL / gateway URL / Compose overlays:
- Browser / OS / tested viewports:
- Accounts available (roles and nonsecret labels only):
- New fixture/run prefix and resource IDs:
- Environment/account/data blockers:

| Case ID | Presence | Result | Actual result and evidence | Defect |
| --- | --- | --- | --- | --- |
| CASE-ID | | NOT RUN | | |

## Defect
- ID / title / severity:
- Case ID / route / role:
- Preconditions and synthetic resource IDs:
- Exact steps:
- Expected:
- Actual:
- HTTP status / safe error code / request ID / UTC time:
- Redacted screenshot or response:
- Reproduced after refresh?:

## Completion
- Cases: planned / run / passed / failed / blocked / not applicable / not run:
- Presence: present / missing / placeholder / API only / blocked:
- First complete patient journey result:
- Open defects and exclusions:
- Restoration/readiness check for any temporary changes:
- Overall: PASS / PARTIAL / BLOCKED, with explicit reasons:
```

Use PASS only for the agreed coverage that was actually executed successfully. Use PARTIAL when required checks remain unrun, missing or failing, and BLOCKED when prerequisites prevent meaningful execution. List every exclusion; do not turn missing credentials, pending data or an untested camera into a passing feature.
