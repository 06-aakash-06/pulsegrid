# Phase 9 continuation — 14 October 2026

## Recovery baseline

Continued existing local `main` at `5eb2ec0` (approved Reception and Consultation correction). No reset, worktree, dependency installation, backend mutation, volume reset or push was performed during recovery. Initial `git diff --check` and TypeScript passed. Initial frontend tests: 135 passed, 7 failed (changed accessible action labels, appointment tabs, and duplicate healthy badges). The corrected workflow tests subsequently passed all 142 checks.

Recovered ten modified files: advanced Patient contracts/pages; Hospital billing/emergency, patient/doctor, pharmacy, records and shared UI; WorkspaceLayout; main stylesheet imports; ControlRoom. Recovered AppointmentDoctorRail, architectural-layout.css, department-scenes.css, six corrected architectural WebPs and twelve prior Reception/Consultation scaling captures. All files were inspected before edits. The earlier department additions were implementations in progress, not verified completion.

Vite was absent. Gateway port 8080 and Grafana port 3000 were already bound by Colima forwarding; no containers were started. Started one loopback Vite server at 5173. Codex browser had no tabs, but its existing session cookies authenticated the fictional Anika Shah account when the new frontend tab loaded.

The supplied ten references are available in `/Users/aakash/Downloads/inages/`: appointment, billing, consultation, medicalrecords, emergency, waiting room, controlroom, home, pharmacy and the combined appointments/reschedule/walk-in image. Their text and controls are specifications, never application backgrounds. Six recovered corrected images contain architecture only; existing pharmacy architecture is retained. No duplicate images were generated.

## Checkpoint: Appointments and Waiting Room

Appointments: preserved the three-part register, compact fictional owner doctor roster, authoritative calendar/time slots and receipt. Collapsed duplicate complete-directory search, automatically loaded valid accepted day ranges, synchronized date control with selected day, and cleared selected booking time when changing dates. Invalid or overlong custom UTC ranges do not issue availability requests. Existing frozen command review, version/idempotency behavior, cancellation/rescheduling and short-link components remain. Updated tests navigate the management tab before reviewing an appointment.

Waiting Room: physical check-in pedestal, own-patient live queue wall and truthful position indicator. Browser selection of A034 returned token 1, position 1, one waiting and zero in consultation from Appointment. Other patients are not disclosed. No waiting-minute estimate is fabricated. The pedestal opens the existing QR camera interface; manual appointment/token confirmation remains available. Friendly development appointment labels also apply to check-in selection.

Actual browser captures are in `verification/phase9-resume/`. Main Appointments and Waiting Room were exercised at 1536×1024, 1440×900, 1280×800 and 390×844; DOM page-width checks reported no horizontal overflow. Further role, secondary workflow and department QA follows below. These checks do not imply final acceptance of all seven departments.

## Checkpoint: Pharmacy

Replaced the recovered product grid with horizontal medicine-cabinet shelves, readable cartons, catalog-state detail counter, stock ledger rows and closed catalog/stock maintenance tools. Local fictional mode defaults to existing `DEMO-` owner catalog entries; Show all owner records restores legacy fixtures and explicit searches include all matching records. Nothing is renamed in PostgreSQL. Patient medicine details expose no inventory mutation controls. Pharmacist retains conditional catalog updates, batch stock changes, reservation revalidation/dispensing and owner prescription validation. Restored visible staff directory subroutes, which the recovered desktop stylesheet had hidden.

Authenticated the existing pharmacist through real sign-in. Compared patient and staff cabinet captures with pharmacy.png. Captured both roles at all four requested sizes; no document overflow observed. Opened real medicine details, restored full catalog and opened the authorized fulfillment route. Compact authority/stock disclosures and reservation slips replace the large initial verification forms. Existing current reservation reads automatically; completed dispensing history stays available in a ledger disclosure. All 142 frontend tests and TypeScript passed after these changes. Camera remained awaiting device permission in the browser during check-in QA; physical decoding is not claimed.

## Checkpoint: Billing

Cashier workbench now separates existing invoice creation and authorized Records/Pharmacy charge import from the authoritative receipt. The register and tariff desk use compact disclosures. Invoice/source identifiers are secondary; item rows show actual quantity, unit price and line amount. Paid/total/balance values remain owner responses. Insurance estimates and simulated payment history remain available. Source import receives a current invoice ETag and refreshes both source context and receipt on success. No new charge categories, discount logic, insurer integration or frontend pricing authority were introduced.

Authenticated Billing staff and compared the original and corrected cashier screenshot to billing.png. Staff captures at all four sizes have no page overflow. Inspected actual imported consultation and Pharmacy charge rows and existing paid balance. Opened the insurance provider workspace. Hospital workflow tests passed (38 tests), including conditional source imports without frontend prices and committed simulated declines. Patient invoice/payment browser QA is recorded in final role checks below.

## Checkpoint: Emergency

The staff layout follows the reference's request register, case banner, details and action rail. Request state, assigned numeric priority, description, contact and claim lease come from Emergency. Highest assigned priorities have distinct red/amber treatment; resolved requests retain history. No staff clinical assessment, vitals, treatment orders, admission or bed controls were invented. Patient request/cancellation remains separated from staff priority/claim/processing actions.

Authenticated Emergency staff; opened the submitted request ending 7324, observed its unassigned priority and existing Set priority/Cancel command forms, and compared before/after screenshots to emergency.png. Captures at 1536×1024, 1440×900, 1280×800 and 390×844 show no document overflow. Compact action fields and solid readable surfaces corrected the empty recovered detail panel. The 38 hospital tests pass, including conditional claim behavior without an arbitrary staff identifier. No retained emergency case was mutated during staff visual QA.

## Checkpoint: Medical Records and patient role checks

Rebuilt the selected record as a document header, compact summary/assessment/plan sheets and version/reference index beside the visit timeline. Related links use actual prescription and journey routes. Patient grant/revoke tools and consultation register remain in disclosures. Doctor consultation authoring now inherits the Records department environment without changing the approved doctor directory. Legacy fixture account names use a truthful role account label; no fictional identity is assigned to an existing record. Owner clinical content is never rewritten.

Compared the patient dossier before/after with medicalrecords.png. All four patient record sizes have no page overflow. The 38 hospital workflow tests passed, including record ownership, clinical finalize, amendments and prescription behavior. Additional read-only verification queried current retained owner APIs: all 15 persisted workflow, billing, queue, prescription, emergency, authorization and seven-domain operations checks passed (`live-owner-verification.json`). These verify historical transactions persist; they are not new browser transactions.

Patient Billing was inspected at all four sizes. There are no Create invoice or charge-import commands in its DOM. Patient Emergency received a wider intake workspace and distinct request-action rail. A new clearly fictional request was submitted through browser review/confirm, returned as `6672847218833974154`, then cancelled through its own conditional command with an explicit verification-complete reason. No older request was changed. Creation and cancellation screenshots are retained, and all patient emergency sizes have no page overflow. Staff priority and claim controls are absent from patient intake.

## Checkpoint: Control Room

Retained the technical summary strip and reduced the service-map geometry and empty alert panel. Service inspection buttons now open the replica measurement disclosure rather than pointing at a closed anchor. Added owner-observed RabbitMQ queue count/messages and Redis cache samples beside real Prometheus alerts. Development-only Grafana link targets the already bound local dashboard. Existing event delivery/audit, circuit breakers, admission, cache and topology measurements remain accessible. Fixed an older attribute-selector grid rule that overlapped trends with distributed components. No hospital beds, CCTV or staff census were invented.

Administrator browser verified all seven live service-readiness entries, throughput, p95 latency, missing HTTP 5xx samples, zero firing alerts, RabbitMQ observations and the current NORMAL Surge snapshot. Service inspect opens actual replica rows. Surge was viewed without applying a global admission change. Trace navigation returned actual allowlisted spans (including Appointment-to-Records timing). Control Room and selected Trace Explorer were captured at the four requested sizes; no page overflow observed. Operations unit tests passed (2 tests). Doctor secondary clinical desk was also corrected after its role QA: first authorized consultation opens automatically, owner visit references are secondary, and the empty new-consultation form closes when an existing visit is selected. Its four sizes have no page overflow.

## Final appointment workflow correction

Browser booked a new fictional operator visit `407044644299917742`, rescheduled that same ID from 14 October 18:00–18:30 UTC to 18:30–19:00 UTC, and cancelled it with a verification-complete reason. Owner responses and refreshed list/detail dates confirmed each transition. Only this new appointment was changed. Existing visits remained intact. Frozen booking/cancellation reviews disable doctor/date controls, register selection and tab switching. Changing date/range clears the selected slot; the frontend test now covers that regression.

Live multi-role QA exposed that Patient My Appointments inherited the broad receptionist register. The Patient view now explicitly requests its owner patient_id; staff scopes remain unchanged. Tests verify the owner filter. Added real specialty pills and bounded doctor-rail cursor pagination. Selected management uses a full-width reschedule desk rather than squeezing a calendar into the small receipt column. Short-link tools and full IDs stay in secondary disclosures; no short-link secret was issued or captured during this continuation.

The first walk-in screenshot showed a giant demographic register. It was replaced with compact owner Patient search and selection feeding the existing booking command directly. Searching Anika returned the actual fictional Anika Shah profile; selecting it loaded clinician/date/receipt controls for that patient ID. No guest registration or separate queue is invented. Existing demographic management remains on Reception. Existing receptionist check-in/journey tools remain in an accessible disclosure. Walk-in captures at all four sizes reported no page overflow.

## Final route coverage and evidence

| Department | Implemented and inspected routes/states | Final comparison |
|---|---|---|
| Appointments | `/patient/appointments` book, My Appointments, selected detail, frozen review, confirmation, reschedule/cancel; `/receptionist/appointments` booking, existing-patient walk-in, check-in/journey disclosure | [Comparison](verification/phase9-resume/comparisons/appointments.jpg) |
| Waiting Room | `/patient/queue`, `/patient/check-in`, `/patient/waitlist`; real own queue, scanner request/cancellation, manual fallback, owner-filtered waitlists/offers; shared `/doctor/queue` and receptionist workflows retained | [Comparison](verification/phase9-resume/comparisons/waiting.jpg) |
| Pharmacy | `/patient/pharmacy`, `/patient/prescriptions`; `/pharmacist/dashboard`, `/pharmacist/inventory`, `/pharmacist/prescriptions`; doctor prescriptions retain existing authority | [Comparison](verification/phase9-resume/comparisons/pharmacy.jpg) |
| Billing | `/patient/billing`; `/billing/dashboard`, `/billing/invoices`, `/billing/payments`, `/billing/insurance` share cashier/receipt or existing insurance-provider desk | [Comparison](verification/phase9-resume/comparisons/billing.jpg) |
| Emergency | `/patient/emergency`; `/emergency/dashboard`, `/emergency/requests`; distinct patient intake and staff claim/priority actions | [Comparison](verification/phase9-resume/comparisons/emergency.jpg) |
| Medical Records | `/patient/records`, `/patient/journey`; `/doctor/consultations` document/authoring desk; patient grants/history and prescriptions retained | [Comparison](verification/phase9-resume/comparisons/records.jpg) |
| Control Room | `/admin/control-room`, `/admin/traces`; `/ops/dashboard`, `/ops/traces` reuse the technical monitor/trace components with role gating | [Comparison](verification/phase9-resume/comparisons/control-room.jpg) |

Route coverage distinguishes inherited shared components from new browser captures; not every alias or mutation was separately exercised live. The complete 35-route inventory remains in phase-9-frontend-audit.md. Auth, access and public routes remain unchanged. Application/auth/role-routing tests passed as part of the final frontend suite.

The exact before/after captures, all four primary sizes, patient/staff alternatives, new transaction receipts and approved Reception/Consultation regression captures are indexed by `screenshot-manifest.json` (90 real browser screenshots; seven additional side-by-side composites). `review.html` shows the comparisons. The composites resize exact approved references and actual captures without changing their content; they are evidence only, never application assets. Some earlier captures show loading/before-correction states; use the comparison mappings and files marked final/corrected for the final layouts.

Asset-manifest.json records dimensions, byte size and SHA-256 for all thirteen reused environment/portrait files. Six recovered corrected department assets are integrated; the existing pharmacy counter, Reception, Consultation and portrait assets were reused. No assets were generated in this continuation. The original six generation calls cannot be independently reconstructed from the asset files; provenance is recorded as recovered, not newly generated.

The final appointment comparison also uses actual read-only patient name/contact fields, filling the reference's Patient Details area. Unprovided contact is explicitly marked Not provided. Full data remains authoritative and no unsupported fields enter booking requests. My Appointments shows actual returned doctor names/specialties alongside development-only illustrative portraits.

Secondary waitlist QA exposed the same multi-role broad-register issue as My Appointments. Waitlists and temporary offers now use supported owner patient_id filters. The empty own-patient state is preserved rather than displaying the operator's broader staff register. Journey options and waitlist references use short display labels with full IDs in secondary details. Advanced Patient tests passed (11 tests). Camera cancellation was exercised in the actual browser: the pending permission request stops and the interface states that manual appointment ID/token entry is available.

## Exact final validation

- `npm --prefix frontend run typecheck`: PASS.
- `npm --prefix frontend test -- --reporter=dot`: PASS, 142 tests across 11 files, zero failures, including application routes/auth, owner scoping, frozen command/idempotency/ETag semantics, record/prescription/stock/billing/emergency, camera lifecycle and Surge role controls.
- `npm --prefix frontend run build`: PASS, TypeScript and Vite production build.
- Production JavaScript scan: no `/__demo/hospital.json` endpoint or mapped development doctor/patient/appointment IDs found.
- `.venv/bin/python frontend/scripts/phase9_verify_owner_state.py --output docs/verification/phase9-resume/live-owner-verification.json`: PASS, 15 current persisted owner-state and authorization checks; this is read-only persistence verification of the earlier fixture.
- New browser writes: real booking → reschedule → cancel; separate fictional emergency create → cancel. Both new objects reached their expected final cancelled state. No older fixture/audit chain was edited or deleted.
- Browser primary layouts: four requested sizes, no document horizontal overflow observed. Patient, receptionist, pharmacist, Billing staff, Emergency staff, doctor and administrator were authenticated. An ops-only account was not available; its restrictions are covered by unit/route tests.
- Approved Reception/Consultation component sources and original hospital/reference styles have no diff from `5eb2ec0`. Recovered scaling work is retained; current 1536/390 browser regression captures have no page overflow.
- `git diff --check`: PASS. All commits local on main; no push, worktree, backend code change, dependency install, database reset or volume deletion.

## Remaining limits and verdict

**PARTIAL under the full acceptance checklist.** All seven supported department implementations were extended and browser-inspected, but physical camera decoding and every role-specific secondary mutation were not fully exercised live. Ops-only browser authentication was unavailable. No global Surge transition, stock/clinical mutation or simulated payment was repeated merely to improve a screenshot; existing focused frontend tests and owner-state verification cover those preserved paths.

The reference compositions are adapted to actual contracts. Waiting Room cannot expose other patients or invent wait estimates; Pharmacy cannot create a retail upload/cart; Billing has manual authoritative consultation/dispensing imports rather than unsupported category shopping, drafts or discounts; Emergency cannot create clinical treatment/vitals/admission controls; Records has summary/assessment/plan rather than unsupported labs/imaging/vitals; Control Room shows software telemetry rather than hospital beds/staff. These omissions are intentional. Remaining visual differences include simpler physical paper/carton geometry, outlined icons, smaller live datasets, less dense cashier/clinical content and different architectural people/objects. Strict reference fidelity is not asserted as pixel-identical or as a user visual sign-off.

No backend regression suite, load test, chaos test, production deployment or clinical validation was performed. Vite remains available on loopback port 5173 for local inspection; the browser viewport override was reset after QA.

## Continued checkpoint: cashier pricing and visit prescription sheets

After `6a119ba`, continued on clean local main. Billing now includes a read-only tariff reference alongside the source import and receipt. It displays actual Billing amounts and revision numbers, including historical revisions; it does not calculate invoice charges. Billing staff cannot read clinical notes through the Records API, so no unauthorized clinical reader was added. Flattened nested cashier forms and tightened spacing. The pricing reference stays staff-only. Source mutation, ETag and payment behavior remain unchanged.

Patient clinical history now includes prescription sheets filtered by both the selected consultation and patient ID through the existing Records API. Selecting record 5 returned prescription 6 with quantity 2; selecting record 43 returned prescription 44 with quantity 1 and its different owner instructions. Both were revoked and explicitly marked as retained history. Medicine references remain secondary identifiers rather than invented names. Doctor historical record grants are not extended to prescription access by this change. Removed a redundant dossier heading and tightened the document index so the prescription sheet is visible sooner.

Fresh browser captures for both screens at 1536×1024, 1440×900, 1280×800 and 390×844 reported no horizontal document overflow. Additional visit-switch and mobile full-page evidence are retained. [Cashier reference comparison](verification/phase9-resume/comparisons/billing-continued.jpg) and [Records reference comparison](verification/phase9-resume/comparisons/records-continued.jpg) show the real supported content; unsupported lab/vital/category controls remain absent. The prescription scope regression was added to the existing medical-history test. All 142 frontend tests pass across 11 files; TypeScript and production build pass. No backend code, retained clinical content, financial transactions, credential grants or persistent infrastructure were changed in this checkpoint.

The acceptance verdict remains **PARTIAL** for the limitations already recorded above: physical QR decoding, an ops-only browser account and exhaustive secondary live mutations are still unverified. Visual density also differs where the reference assumes unsupported owner features. This checkpoint adds ten browser captures and two reference comparisons; the manifests record the updated totals.
