# Phase 9 frontend visual audit

Audit date: 18 October 2026. **Verdict: PARTIAL — source and historical visual review completed; fresh runtime verification blocked.** Pharmacy composition remains the first fix. No fixes are implemented by this report.

The ten images in the supplied `inages.zip` are the visual specification. The handoff, README and six requested Phase 9 documents were read, together with the prior review page, manifests, comparisons and selected desktop/mobile/secondary captures. The handoff's instruction to finish Pharmacy is context, not authorization to implement it during this audit.

## 1. Provenance, Git state and checks

### Git

The supplied local directory is an export with no `.git`. `git log --oneline -10`, `git status --short`, and `git status --branch` could not report history/status: `fatal: not a git repository (or any of the parent directories): .git` (exit 128). **Local branch, dirty-file list and clean-tree status are unavailable.** No Git initialization, checkout replacement, reset, commit, remote creation or push was performed.

`git ls-remote https://github.com/06-aakash-06/pulsegrid.git HEAD refs/heads/main` failed with DNS resolution error (exit 128). A read-only browser request to GitHub's API succeeded. [Remote main history](https://github.com/06-aakash-06/pulsegrid/commits/main/) returned this equivalent ten-entry listing; this is **not local command output**:

```text
698d31c docs: publish current project overview and local setup guide
27f8476 phase9: save pharmacy cabinet and counter progress checkpoint
8c5f1ec phase9: rebuild waiting kiosk and electronic queue equipment
20c365e phase9: shape shared directory as a physical hospital signboard
b7939a1 phase9: refine cashier pricing ledger and visit prescription dossier
6a119ba phase9: finalize owner-scoped secondary workflows and visual evidence
223c48a phase9: verify owner-scoped appointments rescheduling and walk-in intake
023b486 phase9: refine live operations monitors and verify trace and doctor desks
94fec9e phase9: refine clinical dossiers and verify patient billing and emergency access
c3170a8 phase9: refine emergency request banner and authorized action rail
```

The API parent chain confirms **all five requested commits on remote `main`**, ending at `698d31c11e087fe1572ce7e2c3f8c5c5eeb1ef8c`. Pharmacy `27f8476` is explicitly an unfinished checkpoint, not visual acceptance. The remote [Git tree](https://api.github.com/repos/06-aakash-06/pulsegrid/git/trees/698d31c11e087fe1572ce7e2c3f8c5c5eeb1ef8c?recursive=1) was not truncated. Git blob SHA-1 comparisons for local `frontend/src/**`, `frontend/tests/**`, `package.json` and `package-lock.json`: **87 compared, 87 matched, 0 mismatches**. This establishes the inspected frontend's content provenance; it does not establish a clean Git working tree or verify every repository file.

### Baseline and environment

| Exact check | Result this audit | Counts / limitation |
| --- | --- | --- |
| `npm --prefix frontend ci --cache /private/tmp/pulsegrid-audit-npm-cache --no-audit --no-fund --fetch-retries=0 --fetch-timeout=15000` | FAILED, exit 1 | `node_modules` was absent. Tarball downloads failed `ENOTFOUND registry.npmjs.org`; npm ended with `Exit handler never called!`. Partial dependency directories may have been created. |
| `npm --prefix frontend run typecheck` | UNAVAILABLE, exit 127 | `tsc: command not found`; no typecheck executed. |
| `npm --prefix frontend test -- --reporter=dot` | UNAVAILABLE, exit 127 | `vitest: command not found`; **0 test files executed, 0 assertions passed, 0 assertions failed**. This is not a passing suite. |
| `npm --prefix frontend run build` | UNAVAILABLE, exit 127 | `tsc: command not found`; Vite build never ran. Bundle size/warnings could not be assessed. |
| `docker ps --format '{{.Names}} {{.Status}} {{.Ports}}'` | FAILED, exit 1 | Permission denied on the Docker socket; existing stack state could not be inspected or started. |
| `curl -I --max-time 3 http://127.0.0.1:5173` and corresponding `:8080` | FAILED, each exit 7 | Both connection attempts refused. Browser navigation to `:5173` also returned `ERR_CONNECTION_REFUSED`. |
| Git status/log and `git ls-remote` | FAILED | As described above. `git diff --check` unavailable without repository metadata. |
| Frontend content hashes vs remote tree | PASS | 87/87 matched; 0 mismatches. |
| Reference extraction/dimensions | PASS | 10/10 PNGs, each 1536×1024. Extracted unchanged to audit evidence, excluding macOS metadata. |
| Report/evidence verification | PASS | See final artifact checks below; no runtime claims follow from these checks. |

Install also emitted `EBADENGINE`: locked `@zxing/library@0.23.0` requires Node `>=24.0.0`; local Node is `v22.22.0`, npm `10.9.4`. This is an environment compatibility warning, not proof of a scanner failure. No dependency versions or lockfiles were changed. Dependency log: `/private/tmp/pulsegrid-audit-npm-cache/_logs/2026-10-18T06_29_18_653Z-debug-0.log` (temporary, not portable).

**Historical only:** the fidelity checkpoint reports **142 tests passing across 11 files, 0 failures**, TypeScript/build/diff checks passing. Those were not reproduced here. No current production bundle warning is asserted. No backend regression, load, chaos, clinical or Mermaid-render checks were run.

## 2. Capture coverage and scoring

**Fresh captures: 0 of 84 route/viewport combinations.** There are 21 requested base routes × four sizes, before extra appointment tab/reschedule states. No role was signed in during this audit; private local demo credentials/runtime state were not supplied in the export. No replacement users, data fixtures or mocked API responses were created. No command form was submitted.

Every route below is unverified live at **1536×1024, 1440×900, 1280×800 and 390×844**. `document.documentElement.scrollWidth > innerWidth` is **unmeasured for every combination**. Prior claims of no overflow are historical and cannot substitute for this measurement.

| Department | Requested routes / roles | Historical evidence reviewed; 1536 first-fold assessment only |
| --- | --- | --- |
| Reception | `/` public; `/patient/dashboard` patient | Approved patient reception and 390 regression. Counter slips and queue strip visible. Public variant inspected in source; no fresh public capture. |
| Consultation | `/patient/doctors` patient | Corrected directory captures at 1536/1440/1280 and regression evidence. Roster, profile and schedule visible at 1536. |
| Appointments | `/patient/appointments` patient (book, management, reschedule); `/receptionist/appointments` receptionist | Booking, My Appointments, reschedule review and corrected walk-in. Primary booking fits narrowly; selected management/reschedule and walk-in extend below fold. Reschedule evidence includes a scrolled page, not a top-of-page fit proof. |
| Waiting Room | `/patient/queue`, `/patient/check-in` patient | Latest equipment captures at all four sizes; manual check-in. Three equipment objects visible at 1536. |
| Pharmacy | `/patient/pharmacy`, `/patient/prescriptions` patient; `/pharmacist/dashboard`, `/pharmacist/inventory`, `/pharmacist/prescriptions` pharmacist | Latest pharmacist cabinet; older patient catalog/fulfillment and secondary fulfillment captures. Rx stand only starts at y≈906 in latest cabinet image. Current patient counter and latest secondary layout remain unverified. |
| Billing | `/patient/billing` patient; `/billing/dashboard`, `/billing/invoices` billing_staff | Patient billing and later cashier price-book captures including four exact viewport sizes. Receipt/balance visible at 1536; source desk continues below. |
| Emergency | `/patient/emergency` patient; `/emergency/dashboard` emergency_staff | Patient and staff captures, including mobile. Staff register/case visible; full action stack does not fit in first viewport. |
| Records | `/patient/records` patient; `/doctor/consultations` doctor | Later visit-prescription dossier at four exact sizes; corrected doctor consultation. Timeline/dossier visible at 1536; prescription/history extends below. |
| Control Room | `/admin/control-room`, `/admin/traces` hospital_admin | Primary four sizes and administrator trace captures. Summary/map/alerts visible; trends begin near fold, lower distributed-component content below. |

The new [comparison gallery](verification/phase9-audit/review.html) and [evidence manifest](verification/phase9-audit/evidence-manifest.json) explicitly identify **historical** actual-image sources and their SHA-256 values. Each comparison has an unchanged 1536×1024 reference on the left and historical actual viewport on the right (3072×1024 composite). No historical JPEG was renamed into the requested fresh `<dept>-<role>-<width>.png` pattern. `capture-coverage.json` records all 84 unavailable fresh combinations.

Some prior files are full-page captures: e.g. `appointments-final-390.jpg` is 390×2417 and `pharmacy-staff-390.jpg` is 390×3441. A width suffix is not proof of viewport height, first-fold fit, or no horizontal overflow. The report uses exact 1536×1024 images for its primary comparisons.

### Provisional scores

1 = substantial mismatch; 3 = usable adaptation with visible gaps; 5 = closely meets the reference within actual contracts. A11y scores are review risk estimates, **not WCAG certification**. Overall is the arithmetic mean of the six displayed scores, rounded to one decimal. Scores describe inspected source/historical evidence, not today's authenticated app.

| Department | Composition | Metaphor | Density | Copy | A11y | Motion | Overall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Reception — approved | 5 | 5 | 4 | 4 | 3 | 4 | 4.2 |
| Consultation — approved | 5 | 4 | 4 | 3 | 3 | 3 | 3.7 |
| Appointments | 3 | 4 | 2 | 2 | 2 | 3 | 2.7 |
| Waiting Room | 4 | 5 | 4 | 3 | 3 | 3 | 3.7 |
| Pharmacy | 2 | 2 | 1 | 2 | 2 | 3 | 2.0 |
| Billing | 3 | 4 | 3 | 2 | 2 | 3 | 2.8 |
| Emergency | 3 | 3 | 2 | 3 | 2 | 4 | 2.8 |
| Medical Records | 3 | 4 | 3 | 2 | 2 | 3 | 2.8 |
| Control Room | 3 | 3 | 3 | 4 | 3 | 3 | 3.2 |

## 3. Department findings

In the citations below, stylesheet filenames are under `frontend/src/styles/` unless otherwise qualified. Component names/selectors identify the issue's implementation location. Any proposed change remains subject to separate authorization.

### Reception — retain approval

[Reference vs historical actual](verification/phase9-audit/compare-reception.jpg).

1. **Composition fidelity (5/5):** Signage, welcome wall, robot, foreground slips and bottom token strip read as one room. The crop differs from the reference but remains coherent. Preserve `frontend/src/design/ReceptionScene.tsx › ReceptionScene` and `architectural-layout.css › .reception-scene`, `.appointment-slips`.
2. **Physical metaphor (5/5):** Four bound paper slips are real links; queue stand is separate from the room image. No generic dashboard replacement is warranted (`ReceptionScene.tsx › .appointment-slip`, `frontend/src/design/ReceptionVisit.tsx`).
3. **Hierarchy/density (4/5):** Secondary rail and tiny wayfinding descriptions are dense at laptop widths; record for approval review, not a reason to redesign the scene (`architectural-layout.css › .wayfinding-sign small`, `.reception-information-rail`).
4. **Copy (4/5):** “Fictional demo · Owner service data” is implementation vocabulary. If copy changes are later allowed, use “Synthetic demo visit”; keep real freshness/status context (`ReceptionVisit.tsx › ReceptionVisit`). Public guidance correctly requires sign-in (`frontend/src/pages/HomePage.tsx › HomePage`).
5. **Design consistency (4/5):** Approved warm materials and bundled Inter match the system. Numerous viewport-based hard-coded geometry values are intentional scene alignment; do not replace them with shared panel styles (`architectural-layout.css › .reception-scene`, `hospital.css › :root`).
6. **Accessibility (3/5):** Wayfinding descriptions reach 9px; actual contrast at each crop and 200% text scaling remain untested. Preserve focus outlines and mobile reflow (`architectural-layout.css › .wayfinding-sign small`; `hospital.css › :focus-visible`).
7. **Motion (4/5):** GSAP introduces only signs/slips with y=10, opacity .6, .45s and .045s stagger, gated to no-preference with cleanup. Workspace also has its .35s entrance; layering may feel redundant but is not grounds to alter approval without observation (`ReceptionScene.tsx › useEffect`; `WorkspaceLayout.tsx › useEffect`).
8. **Truthfulness:** Source uses real visit state rather than reference A028/counts. Synthetic portrait/demo presentation is documented. Live owner values and public rendering could not be revalidated; no new values were invented by this audit (`ReceptionVisit.tsx`, `frontend/src/hospital/patientDoctor.tsx › PatientDashboard`).

### Consultation — retain approval

[Comparison](verification/phase9-audit/compare-consultation.jpg).

1. **Composition (5/5):** Specialty rail, compact roster, selected profile and desk schedule align to the room. This is the standard other departments should reach (`frontend/src/design/ReferenceConsultation.tsx › ReferenceConsultation`; `architectural-layout.css › .reference-consultation`).
2. **Metaphor (4/5):** Directory/profile boards and bottom schedule read as physical work surfaces. Profile is simpler than the reference; absent ratings/credentials are a truthful omission (`ReferenceConsultation.tsx › DoctorAvailability`, `ProfileSchedule`, `ScheduleRail`).
3. **Density (4/5):** Profile's “Accepted revision” competes with patient-facing availability. Move version context into existing secondary details only if this approved screen receives separate copy approval (`ReferenceConsultation.tsx › .profile-schedule-metrics`).
4. **Copy (3/5):** “Accepted times” can become “Available appointment times”; “Accepted revision” can become “Schedule details” in a disclosure. Keep UTC and the booking recheck explanation (`ReferenceConsultation.tsx › ProfileSchedule`, `DoctorAvailability`).
5. **Consistency (4/5):** Dedicated grid and cream/teal surfaces are successful; profile/roster typography is more compressed than root 14px body (`architectural-layout.css › .reference-doctor-row`, `.doctor-availability--profile`; `reference-scenes.css`).
6. **A11y (3/5):** 8–11px secondary type at narrower desktop widths warrants text-scaling/contrast checks. Fictional photos have descriptive accessibility labels and unmapped clinicians use initials; retain this (`architectural-layout.css › laptop media rules`; `frontend/src/design/localDemo.tsx › DoctorPortrait`).
7. **Motion (3/5):** GSAP workspace entrance is wired. Profile/slot changes have no dedicated state transition; an unobtrusive highlight could orient selection later, with focus and reduced motion preserved (`WorkspaceLayout.tsx`; `ReferenceConsultation.tsx › selected doctor state`).
8. **Truthfulness:** Slot counts/revision/availability come from Appointment; fictional photos are presentation metadata, not credentials. Do not import reference star ratings, years of experience or patient counts without owner support (`ReferenceConsultation.tsx › DoctorAvailability`; `localDemo.tsx`).

### Appointments

[Booking comparison](verification/phase9-audit/compare-appointments.jpg); [management comparison](verification/phase9-audit/compare-appointments-management.jpg). The combined reference contains three separate compositions, not one layout that should all render simultaneously.

1. **Composition (3/5):** Booking retains the useful three-column doctor/date/receipt composition. Its board fills nearly the whole working area vertically rather than sitting cleanly behind a foreground counter. Walk-in adds a step rail, patient lookup, nested booking and help column; it extends substantially below the fold (`frontend/src/hospital/patientDoctor.tsx › Booking`, `Appointments`; `department-scenes.css › .booking-composition`, `.walkin-workspace`).
2. **Metaphor (4/5):** Date controls, doctor slips and receipt are meaningful physical objects. Reschedule adds cancellation, share tools and availability into a tall editing desk; cancellation visually competes with changing time (`patientDoctor.tsx › Appointments`; `department-scenes.css › .appointment-edit-desk`).
3. **Density (2/5):** Management allocates a large empty detail pane before selection; selecting then stacks a register above the full editor. Reschedule capture is scrolled, concealing the top of the composition. Use a compact selected-visit strip with adjacent calendar/receipt, retain local list scrolling, and make destructive cancellation secondary without hiding it (`patientDoctor.tsx › Appointments`; `.appointment-management--selected`, `.appointment-edit-desk`, `.appointment-share`).
4. **Copy (2/5):** “Move appointment [long ID] to slot [long ID]”, resource reload and accepted-revision prose dominate. Replace the primary review sentence with selected doctor and real old/new date/time; retain full IDs and versions in details and the exact request payload internally (`patientDoctor.tsx › reschedule CommandForm`; `frontend/src/hospital/ui.tsx › Resource`, `CommandForm`).
5. **Consistency (3/5):** The selected doctor uses blue `#1689da` and management strips use blue edges, diverging from deep-teal selection. Use a semantic selected token in a future scoped change (`department-scenes.css › .appointment-doctor-rows > button[aria-pressed=true]`, `.appointment-management .hospital-item`).
6. **A11y (2/5):** Specialty controls specify 9px text/24px minimum height; date/time buttons specify 11px/34px. These are readability/target risks; actual bounding boxes were not measured. Increase readable type and comfortable targets before compressing the board further (`department-scenes.css › .appointment-specialties button`, `.booking-schedule button`). Keep labeled native dates and the UTC context.
7. **Motion (3/5):** Shared GSAP entrance and `CollectionPage` position layout animation are present. Lists use `initial={false}`: this is not staggered entry. A small receipt/selection transition could help after layout is corrected; never animate availability into a claim of booking success (`ui.tsx › CollectionPage`, `CommandForm`; `WorkspaceLayout.tsx`).
8. **Truthfulness:** Existing patient lookup supports walk-in; guest creation does not. Accepted slots, persisted booking review, stale ETags, frozen idempotency retries and patient filtering must survive. Use a real selected-visit summary in the reference overview slot, not invented upcoming totals (`patientDoctor.tsx › Booking`, `Appointments`; `frontend/src/design/AppointmentDoctorRail.tsx`).

### Waiting Room

[Latest equipment comparison](verification/phase9-audit/compare-waiting.jpg); [manual check-in](verification/phase9-fidelity/checkin-manual-1536.jpg).

1. **Composition (4/5):** Kiosk left, framed dark monitor center and cream position display right are now distinct, wall-integrated objects. The equipment and personal status are visible together at 1536; do not revert to three generic cards (`frontend/src/advanced/patient/pages.tsx › PatientQueuePage`, `PatientCheckinPage`; `department-scenes.css › .queue-station`, `.queue-monitor`, `.queue-wait-sign`).
2. **Metaphor (5/5):** Scanner aperture, kiosk enclosure, large token and position display are physically legible. Preserve equipment dimensions and manual fallback (`pages.tsx`; `frontend/src/hospital/staffAdvanced/CheckinScanner.tsx`; `.scanner-viewport`, `.waiting-position-display`).
3. **Density (4/5):** Monitor mixes live token/counts with appointment selector, freshness and owner-reference details. Keep token/state dominant; combine secondary source/version disclosure rather than add more rows (`pages.tsx › PatientQueuePage`; `.queue-source-details`, `.queue-monitor-footer`). Mobile shows kiosk before queue token, requiring scrolling; later consider a small owner-token summary above equipment without removing it.
4. **Copy (3/5):** “Owner details and freshness” can become “Queue details · updated [real time]”. A “LIVE” badge should be understood alongside its actual observation/fetch state; on refresh failure show last-known/degraded status rather than imply continuous delivery (`pages.tsx › PatientQueuePage`; `.queue-monitor-heading`, `.queue-source-details`). No current stale-badge behavior was exercised.
5. **Consistency (4/5):** Dark teal equipment and cream position slip improve hierarchy. Many bespoke teal/cream values repeat root tokens; a future token pass should preserve appearance (`department-scenes.css › .queue-monitor`, `.queue-wait-sign`).
6. **A11y (3/5):** Latest scanner button minimum is 44px and text contrast received specific overrides. Source still sets 10–11px instructions/monitor labels. Mobile drawer, scanner focus and camera behavior require fresh device checks; historical evidence is not current verification (`department-scenes.css › .checkin-kiosk .staff-advanced-scanner`, `.queue-monitor label`; `CheckinScanner.tsx`).
7. **Motion (3/5):** Workspace entrance exists; token/position changes have no dedicated transition. A restrained change highlight and appropriate live status could orient users, avoiding repeated announcements of polling content (`WorkspaceLayout.tsx`; `pages.tsx › PatientQueuePage`).
8. **Truthfulness:** Own token/position/state and returned counts replace the reference's other patients and estimated minutes. “Your current queue position” is the honest right panel. Physical QR decoding remains unverified; do not call the kiosk physically validated (`pages.tsx`; `CheckinScanner.tsx`).

### Pharmacy — P0 composition

[Latest pharmacist comparison](verification/phase9-audit/compare-pharmacy.jpg); [older patient comparison](verification/phase9-audit/compare-pharmacy-patient.jpg). The latter predates the current counter implementation and is **not** proof of its present rendering.

1. **Composition (2/5):** The translucent hero overlays pictured shelves rather than forming a wall sign; separated search, medicine details, stock ledger and cabinet read as stacked UI over another cabinet image. The foreground Rx stand begins at y≈906, leaving the working area cut by the fold (`frontend/src/hospital/HospitalPage.tsx › page-heading/pharmacist route`; `department-scenes.css › .department-page--pharmacy > .page-heading`, `.pharmacy-counter-workspace`).
2. **Metaphor (2/5):** Source builds actual carton geometry and joinery, but the fixed three-column grid, one large carton per visible bay, brown body and bottom pagination resemble a boxed catalog. The reference's seven bays × three shelf rows have a continuous furniture rhythm. Do not fabricate medicines to fill them (`frontend/src/hospital/pharmacy.tsx › MedicineCatalog`, `.medicine-shelves`, `.medicine-shelf-slot`; `department-scenes.css › .medicine-shelves .hospital-items`, `.carton-space`, `.medicine-box`).
3. **Density (1/5):** The tallest right-hand detail sets grid row 1 height, producing an extra gap beneath shorter search; cabinet then consumes ≈428px. Rx content is downstream of both. Search should be a cabinet rail and the right counter should span independently of the left rows (`department-scenes.css › .pharmacy-search-counter`, `.dispensing-counter`, `.prescription-stand`, `.pharmacy-inventory-ledger`). See the measured budget and proposed grid below.
4. **Copy (2/5):** “Stock hint”, “Not reported”, “Owner service data”, raw “Item … quantity”, versions and source wording occupy primary space. Use “Availability”, “Availability not supplied”, “[real medicine name] — quantity”, “Prescription details” and a single real updated-at line where supported. Availability is advisory; never relabel it as confirmed stock (`pharmacy.tsx › MedicineCatalog`; `ui.tsx › CollectionPage`, `Resource`; `frontend/src/advanced/patient/PatientFulfillmentPanel.tsx › ReservationStatus`).
5. **Consistency (2/5):** Material colors, grid rules and font sizes are repeatedly overridden in the same stylesheet. The medicine-box text drops to 6px (decorative, aria-hidden), while operational labels use 9–11px. Scope future rules to Pharmacy rather than alter the default Records prescription layout (`department-scenes.css › Pharmacy section and final overrides`; `frontend/src/hospital/records.tsx › PrescriptionDetail`).
6. **A11y (2/5):** Availability pills use 36px minimum targets/11px text, cohort text 9px, allowance table 10px, and reload action 30px. Small secondary text over warm brown requires computed contrast checks. Decorative carton text should not carry information absent from the adjacent accessible medicine button (`department-scenes.css › .medicine-availability-tabs > button`, `.catalog-cohort`, `.pharmacy-allowance-table`; `pharmacy.tsx › aria-hidden medicine-box`).
7. **Motion (3/5):** Shared entrance/list layout is present; no cabinet selection/Rx-to-reservation orientation animation is wired. After composition is fixed, subtly mark the selected bay and updated owner slip; no decorative conveyor/pickup animation implying dispensing occurred (`ui.tsx › CollectionPage`; `pharmacy.tsx › selected`; `PatientFulfillmentPanel.tsx › ReservationStatus`).
8. **Truthfulness:** Catalog and stock values are API-backed; patient counter selects owned prescriptions and locks selection during pending/ambiguous reservation attempts. Preserve these. Reference prices/cart/“Generate Bill”/upload/Ready–Pickup–Dispatch are unsupported. The shelf availability pills are local **page** filters, not clinical categories; keep that scope clear and don't promise a full-catalog negative result (`pharmacy.tsx › itemFilter`, `MedicineCatalog`; `PatientFulfillmentPanel.tsx › ReservationStatus`; `ui.tsx › CollectionPage`). Empty architectural bays may remain empty. No clinical taxonomy can be inferred from a medicine name.

Secondary findings: `/patient/prescriptions` mounts the default `Prescriptions` component, while pharmacist fulfillment wraps the existing `Fulfillment` plus authority/stock verification panels. Their raw lookup IDs, registers and multiple technical disclosures still need an object-first review. Prior corrected fulfillment screenshot shows selected reservation below a tall register, but predates the latest compact stand; no current fit claim is possible (`HospitalPage.tsx › prescriptions routes`; `frontend/src/hospital/staffAdvanced/StaffFulfillmentPanel.tsx › StaffFulfillmentPanel`, `FulfillmentStatusLookup`, `StockVerification`; `pharmacy.tsx › Fulfillment`; `records.tsx › Prescriptions`).

### Billing

[Later cashier comparison](verification/phase9-audit/compare-billing.jpg).

1. **Composition (3/5):** Two-column workbench/receipt is appropriate, but create form, tariff list and source imports are stacked independent panels; the selected visit context is secondary instead of a clear cashier context band (`frontend/src/hospital/billingEmergency.tsx › BillingPage`, `InvoiceChargeSources`; `department-scenes.css › .billing-workbench`, `.billing-source-desk`, `.invoice-receipt`).
2. **Metaphor (4/5):** Itemized receipt, balance strip and tariff sheet are meaningful. Preserve these rather than introduce reference retail line-item shopping (`billingEmergency.tsx › .invoice-lines`, `.invoice-total`, `.cashier-price-book`).
3. **Density (3/5):** Staff source desk starts with creation even when an existing invoice is selected, pushing imports and register down. Patient mobile puts the whole invoice register before the selected receipt. Use an existing-invoice context strip and compact register with a clear selection, keeping creation available separately (`billingEmergency.tsx › BillingPage`; `.invoice-register`, `.billing-source-desk`).
4. **Copy (2/5):** “Medicine …7826”, “Amount in paise (integer)”, source IDs and reload wording are technically truthful but hard to scan. Resolve medicine display names only through authorized Pharmacy APIs; retain charge codes if resolution fails. Explain “Payment amount (paise)” and display its exact INR equivalent without silently changing submitted units (`billingEmergency.tsx › tariff renderItem`, `Submit simulated payment`; `ui.tsx › money`, `Resource`).
5. **Consistency (3/5):** Cream receipt and pale-green balance match; 10–11px pricing notes/table text and one-off backgrounds drift from root type/material tokens (`department-scenes.css › .cashier-price-row small`, `.cashier-price-book > p`, `.invoice-lines`).
6. **A11y (2/5):** Small line-item/source text and horizontal table region need keyboard/zoom testing. The table already has caption, scoped headers and a labeled focusable scroll region; retain them when changing density (`billingEmergency.tsx › .invoice-line-scroll`; `department-scenes.css › .invoice-lines`).
7. **Motion (3/5):** Shared commands animate review and confirmation; there is no distinct invoice selection transition. A small receipt highlight after an owner refresh is sufficient; never animate balance as paid before confirmation (`ui.tsx › CommandForm`; `billingEmergency.tsx › selected`, `payment`).
8. **Truthfulness:** Prices come from Billing tariffs/imports; historical tariff revisions are explicitly labeled and not used as an unreviewed frontend calculator. Receipt uses returned invoice amounts. No discounts, drafts, lab/bed charges or real payment processing should be added to match the picture (`billingEmergency.tsx › BillingPage`, `InvoiceChargeSources`). Keep simulation notice visible.

### Emergency

[Staff comparison](verification/phase9-audit/compare-emergency.jpg).

1. **Composition (3/5):** Register/case/actions is correct, but the hero and separate note consume vertical space while a long case/action panel continues beyond the fold. The physical station is less convincing than the reference's integrated header/context band (`frontend/src/hospital/billingEmergency.tsx › EmergencyPage`; `department-scenes.css › .emergency-workbench`, `.emergency-case-layout`; `HospitalPage.tsx › .page-heading`).
2. **Metaphor (3/5):** Case register and triage form are functional, but right-hand actions are stacked generic command forms rather than a compact case-specific console (`billingEmergency.tsx › .emergency-actions`, `CommandForm`; `department-scenes.css › .emergency-active`).
3. **Density (2/5):** On mobile the register precedes the active request; on desktop priority/cancel/claim controls can create a long competing stack. Put selected case and its current legal next action first on small screens; keep explicit cancellation/reason/confirmation reachable (`billingEmergency.tsx › EmergencyPage`; `.emergency-register`, `.emergency-actions`).
4. **Copy (3/5):** “Authorized actions” can become “Next steps”; “Awaiting assigned priority” can become “Priority not yet assigned”. Never translate advisory urgency into a medical triage conclusion. Keep “synthetic” where needed to prevent entering real emergency data (`billingEmergency.tsx › .emergency-case-header`, `.emergency-actions`, patient intake fields).
5. **Consistency (3/5):** Generic `.owner-state` has a green default across domains, potentially making “submitted” look like a success/completion signal. Use explicit neutral active states and restrained priority emphasis, preserving numeric priority semantics (`department-scenes.css › .owner-state`, `.emergency-triage-row`; `billingEmergency.tsx › data-priority`). This is a visual ambiguity, not evidence of a wrong backend state.
6. **A11y (2/5):** 10–11px times/form labels and small register review buttons are risks. Preserve textual state/priority in addition to color; verify focus through reviewed commands at each width (`department-scenes.css › .emergency-triage-row time`, `.emergency-actions .hospital-form label`, `.emergency-register .hospital-item > button`).
7. **Motion (4/5):** `WorkspaceLayout` explicitly skips GSAP for Emergency. Shared Motion confirmation opacity and receipt movement remain but don't gate network requests. Do not add scene delay or stagger urgent actions (`WorkspaceLayout.tsx › department === emergency guard`; `ui.tsx › CommandForm`).
8. **Truthfulness:** Current request/priority/lease/state replace unsupported treatment, vitals, active orders, beds and admission. Keep the prototype/dispatch limitation. Do not put reference “4 critical”/“12 waiting” into a summary without a suitable owner aggregate (`billingEmergency.tsx › EmergencyPage`).

### Medical Records

[Later visit-prescription comparison](verification/phase9-audit/compare-records.jpg); [doctor consultation evidence](verification/phase9-resume/records-doctor-corrected-1536.jpg).

1. **Composition (3/5):** Timeline plus dossier is present; the patient strip and header add duplicate heading bands while dossier/prescription content descends beyond the first viewport. Doctor consultations remain a separate register/editor composition rather than a generic record card (`frontend/src/hospital/records.tsx › History`, `RecordsPage`, `Consultations`; `department-scenes.css › .record-patient-strip`, `.record-history`, `.consultation-clinical`).
2. **Metaphor (4/5):** Clinical document, timeline spine and history index are credible. Several boxed summary/assessment/plan sections still look like nested cards; consolidate borders within the document without flattening their semantic headings (`records.tsx › ClinicalFacts`, `History`; `.active-dossier .clinical-content`, `.record-document-index`).
3. **Density (3/5):** Full history list appears before selected document on mobile; document context (“Revision”, “Records service”, “Document history”) repeats around short actual notes. Prioritize selected visit and keep the timeline collapsible/compact on small screens (`records.tsx › History`; `.visit-timeline`, `.record-document-heading`, `.record-document-index`).
4. **Copy (2/5):** “Clinical record …5”, “Medicine reference …7826”, “Owner references”, “Supersedes”, “Reload resource” obscure the visit. Use actual date + “Visit record”, “Earlier version”, “Reference details” and authorized medicine display names with reference fallback. Never rewrite stored clinical text for polish (`records.tsx › History`, `ClinicalFacts`; `ui.tsx › Resource`).
5. **Consistency (3/5):** Cream dossier works; timeline blue `#2286cc` differs from teal, prescription labels use 10px and history metadata 11px. Prefer selected/status tokens and a shared readable secondary scale (`department-scenes.css › .visit-timeline .hospital-item`, `.prescription-instruction-list dt`, `.record-document-heading p`).
6. **A11y (2/5):** Dense prescription columns and version disclosures need zoom/table reading checks; revoked warning must remain perceivable and not be hidden with technical metadata. Source distinguishes retained revoked history with text, which is valuable (`records.tsx › .dossier-prescriptions`, `.prescription-revoked-note`; `department-scenes.css › .prescription-instruction-list`).
7. **Motion (3/5):** Shared list positioning and command reviews are wired; selecting a timeline entry has no dedicated dossier transition. A brief selection highlight can reinforce correspondence without animating clinical text or disturbing reading position (`records.tsx › History`; `ui.tsx › CollectionPage`).
8. **Truthfulness:** Selected-visit prescriptions are filtered by **patient_id and consultation_id**; keep that scope and revoked-history wording. The reference's vitals/labs/imaging slots should contain actual document history, prescriptions or care links. Doctors' record grants do not automatically authorize prescription history (`records.tsx › History`, `Grants`, `Consultations`).

### Control Room

[Primary comparison](verification/phase9-audit/compare-control-room.jpg); [administrator traces](verification/phase9-resume/traces-admin-1536.jpg).

1. **Composition (3/5):** Summary, dominant service map, side alerts and trends broadly match the reference. Large flat cream service blocks are less like a bank of technical monitors; room scenery remains behind independent cards (`frontend/src/ops/ControlRoom.tsx › ControlRoom`; `department-scenes.css › .reference-operations`, `.ops-service-map`, `.ops-map-rooms`).
2. **Metaphor (3/5):** Service map is an honest substitute for hospital census, but the seventh service stretches across a whole row, leaving an unbalanced topology. Draw a compact seven-service console with actual health/readiness, not a fabricated hospital floor plan (`ControlRoom.tsx › .ops-map-rooms`; `department-scenes.css › .ops-map-room:last-child`).
3. **Density (3/5):** Trends begin near the fold while service map takes the central region. Trace Explorer leaves a large selected-detail panel empty until selection. Use a compact named empty state with a clear instruction; don't enlarge placeholder panels merely to fill the room (`ControlRoom.tsx › TraceExplorer`, `TrendChart`; `.ops-trace-layout`, `.ops-service-map`).
4. **Copy (4/5):** Technical vocabulary belongs here; do not apply patient-copy simplification indiscriminately. Rename “Hospital Service Map” to “Service topology” to reduce physical-department ambiguity while retaining missing-sample explanations (`ControlRoom.tsx › service-map-title`, `MetricCard`, `TraceExplorer`).
5. **Consistency (3/5):** Monitor sheets, StatusBadge and summary tokens are coherent, but alert/map/trend dimensions and hard-coded cream variants are spread between `frontend/src/ops/controlRoom.css`, `hospital.css` and `department-scenes.css › .reference-operations`. Tokenize scoped materials after visual acceptance, preserving lazy-style precedence.
6. **A11y (3/5):** Trend SVG has a label but no equivalent numeric/time-series table; provide an accessible summary/list of returned samples if later authorized. Small unit/chart captions and status colors need computed contrast checks (`ControlRoom.tsx › TrendChart`; `controlRoom.css › .ops-chart-caption`; `department-scenes.css › .ops-metric-detail`, `.ops-map-room small`).
7. **Motion (3/5):** GSAP entrance exists; refreshed metric values/chart paths have no purposeful transition. Avoid tweening through invented intermediate values; at most highlight updated actual values without delaying alerts (`WorkspaceLayout.tsx`; `ControlRoom.tsx › refresh`, `MetricCard`, `TrendChart`).
8. **Truthfulness:** `number()` returns “No data” for missing/non-finite values; map/readiness/alerts/trends use monitoring responses. Preserve the distinction between 0 and no measurement; no smooth fake charts or bed/census/staff metrics. Surge Mode stays administrator-only and reviewed; it was not toggled. Ops-only live login was not attempted/verified (`ControlRoom.tsx › number`, `ControlRoom`; `frontend/src/ops/SurgeModeControls.tsx`).

## 4. Shared shell and design system

**Header:** Search truthfully indexes permitted routes, not patients or clinical entities. The current primary text “Search hospital departments & workflows…” is supported and should not be replaced by the reference's global patient/medicine promise. The dialog input placeholder “Appointments, medicines, records…” is more ambiguous: “Find a department or workflow…” would better describe route search. `frontend/src/design/HospitalHeader.tsx › HospitalHeader`, `.global-search`, `.command-search`.

The account fallback “Account …994792” is truthful but gives identifiers the strongest position. Use an authorized owner display name when already available, otherwise “[role] account” with the full subject only in account details. Do not invent a staff name. The notification bell opens an unavailable-feed explanation; it has no badge and fabricates no activity, but offers little actionable value. Consider a clearly labeled prototype information action only under later shell-copy authorization. `HospitalHeader.tsx › identity`, `.account-menu`, `.notification-wrap`; `frontend/src/design/hospitalIdentity.ts`.

**Directory:** The depth correction is present in current source and latest historical frames: 18px recession, 7px near-edge material face, untransformed interactive text, mounting points and restrained highlight. This is substantially closer to the reference; retain it. “Need help?” sits in the expected footer position, but authenticated text says “Synthetic hospital prototype” rather than promising nonexistent staff assistance. Public text points users to sign-in. Do not introduce a fake contact/support workflow. `department-scenes.css › .physical-directory::before/::after`, `.directory-heading`; `frontend/src/layouts/WorkspaceLayout.tsx › .directory-help`; `frontend/src/pages/HomePage.tsx › HomePage`.

No new depth regression was established. Two **source review risks**, not proven regressions from the depth commit: department-active styling is manually applied to NavLink aliases although native `aria-current` follows exact route matching; e.g. queue link styled active on check-in may lack current-page semantics. Mobile focus loop/Escape restoration exists, but main content is not made inert and the custom sidebar is not a modal dialog: verify background access with a screen reader. Preserve current behavior until specific fixes are authorized/tested. `WorkspaceLayout.tsx › referenceItems/NavLink className`, mobile `menuOpen` effect and `.sidebar-scrim`. Historical mobile/Escape/focus evidence exists; no current interaction test ran.

**Background treatment:** `hospital.css › .workspace-shell, .public-page, .auth-route-layout` uses fixed architecture backgrounds. `department-scenes.css › .reference-departments` sizes the image to `100vw auto` and uses `#c9aa88` below it. At 1536px width, a 3:2 image ends around 1024px; content beyond that falls into the solid base. This is conspicuous in long Pharmacy pages. Fix the composition and material alignment before tuning opacity or generating replacement rooms. Never use full reference screenshots as runtime backgrounds.

**Tokens and layering:** Root tokens cover approved ivory, limestone, oak, ink, teal, red, spacing, 7px radius and durations. Department additions repeatedly hard-code colors/type/materials and override previous definitions within one file. Blue selected lines in Appointments/Records drift; 9–11px operational text is widespread. `frontend/src/main.tsx` loads global → hospital → reference → architectural → department styles; lazy workflow CSS adds another precedence constraint. A broad stylesheet cleanup would risk approved layouts; use department-scoped changes with regression captures. `hospital.css › :root`; `department-scenes.css › selected states and Pharmacy final overrides`.

**Actual motion wiring:** `frontend/src/app/App.tsx › PulseGridRoutes` provides `MotionConfig reducedMotion="user"` and lazy `domAnimation`; it does not itself animate routes/dialogs. `WorkspaceLayout` GSAP animates main opacity .8→1 and y=8→0 over .35s, with `matchMedia`/cleanup, except Emergency. `ReceptionScene` separately introduces signs/slips. `ui.tsx › CollectionPage` uses `m.article initial={false} layout="position"` with .18s transitions; `CommandForm` fades review (.18s) and moves/fades receipt (.22s). There is no coordinated room exit/enter sequence, staggered list entry, or dedicated cabinet/token/dossier transition. Native header dialog is not a Motion dialog. Reduced-motion source is present; runtime behavior/performance has not been measured. Do not animate successful state before owner confirmation.

**Accessibility limits:** Static font rules below 12px are confirmed; this alone is not a blanket WCAG failure. Focus styling and semantic table regions are present. Computed contrast against photos, computed target dimensions, keyboard order, 200% text resizing, screen-reader output and mobile drawer behavior need a working app. No contrast ratio or audit pass is invented here.

## 5. Pharmacy vertical budget and concrete layout proposal

### Observed latest pharmacist image

Measurements below are **raster-boundary estimates, approximately ±4px**, from the unchanged 1536×1024 `phase9-fidelity/pharmacy-pharmacist-after-1536.jpg`. They are not `getBoundingClientRect()` results. Patient counter's current dimensions are unmeasured. The earlier patient image shows the old layout and cannot establish the current counter budget.

| Object | Approximate y range | Height / impact | Source |
| --- | --- | --- | --- |
| Fixed header | 0–76 | 76px | `hospital.css › --header-height`, `.hospital-header` |
| Header-to-title gap | 76–90 | 14px | `.reference-departments` padding |
| Translucent title block | 90–230 | 140px | `department-scenes.css › .department-page--pharmacy > .page-heading` |
| Gap before grid | 230–246 | 16px | `hospital.css › .page-stack` |
| Search/filter panel | 246–384 | 138px | `.pharmacy-search-counter` |
| Medicine details, same grid row | 246–448 | 202px | `.dispensing-counter`; taller sibling determines row height |
| Apparent blank space below search | 384–465 | 81px | ≈64px sibling-height difference + ≈16px grid gap |
| Cabinet body, heading through pagination | 465–893 | 428px | `.medicine-shelves`, `.hospital-items`, `.hospital-actions` |
| Foreground stand | starts ≈906 | Only ≈118px remain; full stand/action area does not fit | `.prescription-stand` in row 3 |
| Right batch ledger | 465–851 | ≈386px; separate loose sheet | `.pharmacy-inventory-ledger` |

The stand heading **does** appear above the fold. The problem is that the stand/counter cannot be used or seen as a complete foreground object there. The cabinet is pushed down not only by its own height, but by the title and independently sized details/search row. Reducing carton height alone will not solve it.

### Proposed 1536×1024 geometry — not implemented or measured

Keep header/directory geometry. Available main width is approximately x=320…1505 (**1185px**). Use a scoped Pharmacy grid: **778px left + 16px gap + 391px right** (equivalent responsive fractions around 2:1). Left furniture rows and right counter must have independent sizing, so expanding medicine detail cannot push the cabinet down.

| Region | Proposed bounds | Purpose |
| --- | --- | --- |
| Wall sign | x320–1098, y96–192 (96px) | Opaque wall-mounted pharmacy sign; no floating hero box. |
| Cabinet rail | x320–1098, y208–304 (96px) | Name autocomplete, actual availability filters, compact page navigation/search options in a single cabinet top rail. |
| Continuous shelf face | x320–1098, y304–640 (336px) | Seven architectural bays where width permits, three shallow shelf tiers; actual selectable medicine objects only. Empty bays stay unpopulated. |
| Foreground left counter | x320–1098, y656–976 (320px) | Rx stand (~310px wide) plus paper tray / concise document summary (~452px with 16px gap). No actionable fake scanner or upload. |
| Right upper counter | x1114–1505, y208–568 (360px) | Role-specific current owner slip/selected inventory or reservation context. |
| Right lower context | x1114–1505, y584–976 (392px) | Owned patient/prescription or medicine/batch context, with bounded local detail overflow. |
| Bottom clearance | y976–1024 | 48px visual breathing room. |

The shelf face budget can hold approximately 28px bay labels + three 92px rows + 32px total rails/padding. Usable left width after cabinet frame is ≈762px; seven bays ≈109px each. Keep names in readable adjacent buttons, cartons decorative. This is a proposed furniture rhythm, **not a demand for 21 medicines or seven clinical categories**. If the backend has three medicines, show three real medicine objects and empty material space. Current contracts do not support the reference's Pain Relief/Antibiotics/Gastro taxonomy; use neutral bay labels or real supported availability labels, without inferring therapeutic class. Keep bounded pagination in the rail and state its current-page scope.

This proposed grid fits summaries and the primary action at 1536×1024. Large prescriptions/stock histories/command reviews need local scrolling or an expanded existing workspace; do not truncate dosage, reasons, warnings or confirmation payloads to force every possible state into 320px. A 1536×1024 fit is not acceptance at shorter heights. At 1440×900 and 1280×800, reduce sign/decorative shelf tiers first, preserve text/control size, then allow natural vertical scroll. At 390×844, put owned prescription/current reservation before catalog, offer the catalog as a clear secondary section, and keep the existing directory drawer. All proposed breakpoints require live verification later.

### Map reference slots to existing owner-backed components

| Reference slot | Patient use | Pharmacist use | Existing source / owner reads |
| --- | --- | --- | --- |
| Wall pharmacy sign | Same department sign | Same department sign | `HospitalPage.tsx › heading`; presentation only |
| Search + category rail | Medicine autocomplete + actual availability filters | Same + optional existing catalog tools in secondary detail | `pharmacy.tsx › MedicineCatalog`; `/api/v1/pharmacy/medicines`; existing Phase 4 autocomplete |
| Multi-bay shelving | Real catalog names/advisory availability | Same; select medicine for inventory | `MedicineCatalog`; no fabricated stock on carton faces |
| Bottom-left Rx stand | Owned prescription selector, issued/revoked status, real dosage/instructions | Existing Records prescription lookup/compact prescription document, permitted by role | `PatientFulfillmentPanel counter`; `records.tsx › Prescriptions`, `PrescriptionDetail`; `/api/v1/records/prescriptions` and detail |
| Foreground tray/bag/scanner | Real reservation summary, or purely decorative neutral tray/bag | Existing reservation/dispensing receipt; scanner remains decorative unless a supported flow is supplied | `PatientFulfillmentPanel.tsx › ReservationStatus`; `pharmacy.tsx › Fulfillment`; no new scanner workflow |
| “Current Order” + prices | Current owned reservation/fulfillment summary and permitted reservation action; no ₹ basket | Dashboard/inventory: selected medicine and real batch quantities. Dispensing route: selected reservation plus existing allowed revalidate/dispense/release reviews | `/api/v1/pharmacy/prescriptions/{id}/fulfillment`, scoped reservations; `MedicineCatalog inventory`, `Fulfillment`; `/api/v1/pharmacy/inventory` |
| Lower patient/prescription panel | Owned profile and selected prescription summary | Only patient/visit references already authorized by prescription/reservation responses; don't fetch demographics/clinical data merely to imitate the reference | `PatientFulfillmentPanel`; `StaffFulfillmentPanel`, `PrescriptionDetail` |
| “Generate Bill & Proceed” | No such action. Preserve actual request-reservation flow | Preserve actual reviewed dispensing flow on the dispensing route; Billing imports its authoritative source separately | Existing `ReservationStatus`, `Fulfillment`, `CommandForm`; no new money action |

Role-specific adjustment: on pharmacist dashboard/inventory, use the right upper counter for selected medicine/batches and lower context for the existing dispensing-workspace entry plus concise source context. On `/pharmacist/prescriptions`, reuse the same geometry for Rx stand left and current reservation right; keep authority/stock tools secondary but visible when review is required. Do not duplicate stock-adjustment/dispensing actions into patient UI or turn lookup-only review into a command.

## 6. Ranked fix backlog — proposal only

S = focused local change; M = component/layout change with several responsive states; L = coordinated role/department layout work. File lists name expected edit scope for a future authorized fix, not changes made here. Shared styles/tests require integrator ownership.

| Rank / priority | Department | Problem → proposed change | Expected files | Risk / validation | Size |
| --- | --- | --- | --- | --- | --- |
| 1 · P0 | Pharmacy | Floating hero/search/three-carton box pushes Rx below useful fold → wall sign + integrated cabinet rail + independent left shelves/right counter + foreground Rx using grid above | `hospital/HospitalPage.tsx`, `hospital/pharmacy.tsx`, `advanced/patient/PatientFulfillmentPanel.tsx`, `styles/department-scenes.css` | High visual/medium workflow risk: DOM reorder must not remount pending reservation attempts or break selection lock. Recheck both roles, secondary fulfillment, autocomplete, idempotency/ETag tests and all four sizes. | L |
| 2 · P1 | Pharmacy / shared typography | 6–11px text, small filters, low-contrast metadata → readable secondary scale, comfortable controls, opaque material behind operational text; decorative cartons remain aria-hidden | `styles/department-scenes.css`, scoped `hospital/pharmacy.tsx` markup if necessary | Medium: cabinet fit must be solved without shrinking type. Check computed contrast, zoom, keyboard and targets; retain adjacent accessible names. | M |
| 3 · P1 | Mobile across active workflows | Long registers/catalogs precede selected task → compact selected-context-first ordering; bounded registers and clear links to full existing lists | `hospital/billingEmergency.tsx`, `hospital/records.tsx`, `hospital/patientDoctor.tsx`, `advanced/patient/PatientFulfillmentPanel.tsx`, scoped department CSS | Medium/high: preserve reading/focus order, current selection, pagination and frozen attempts. Scope per department, not one broad DOM rewrite. | L |
| 4 · P1 | Emergency | Header + register + stacked commands obscure case's legal next step → concise case/priority strip and primary legal action with secondary explicit cancel/release | `hospital/billingEmergency.tsx`, `styles/department-scenes.css` | High workflow sensitivity: preserve state/lease/owner gates, reasons and confirmation. No urgent-workflow animation delay. | M |
| 5 · P1 | Shared copy | Owner-service/reload/IDs dominate primary UI → contextual refresh, human state/visit labels, full identifiers/versions in a single details area | `hospital/ui.tsx`, `design/HospitalHeader.tsx`, affected Pharmacy/Billing/Records/Appointment components | Medium: tests often query action labels; preserve accessible names or update meaningful assertions. Never conceal stale/degraded/ambiguous outcomes. Shell copy needs explicit scope. | M |
| 6 · P1 | Shared navigation a11y | Active alias semantics and background screen-reader access need verification → test current-page semantics on check-in/prescriptions and drawer isolation; correct only confirmed defects | `layouts/WorkspaceLayout.tsx`, `tests/application.test.tsx`, `tests/design.test.tsx` | Medium: preserve directory depth, role navigation, Escape/return focus, scroll selection and approved scenes. This is a verification-led backlog item, not a proven depth regression. | M |
| 7 · P2 | Appointments | Management/reschedule/walk-in grow into tall nested desks → compact selected-visit strip, calendar next to actual review receipt, secondary cancellation; avoid huge preselection pane | `hospital/patientDoctor.tsx`, `design/AppointmentDoctorRail.tsx`, `styles/department-scenes.css` | High: accepted slots/date synchronization, patient scope, concurrency errors, review/frozen retry and short-link behavior must survive. | L |
| 8 · P2 | Billing | Creation/tariff/history/source panels compete → selected-invoice context band, concise tariff reference, invoice receipt/authorized source import kept primary | `hospital/billingEmergency.tsx`, `styles/department-scenes.css` | Medium: tariff history remains reference-only; do not alter money units, source imports, balance or simulated payment semantics. | M |
| 9 · P2 | Records | Duplicate dossier bands/version copy and small prescription fields → coherent document sections, concise real visit context, related authorized prescriptions/history | `hospital/records.tsx`, `styles/department-scenes.css` | Medium: preserve patient+consultation filtering, grants, revisions, revoked-history notice, finalize/amend behavior. Never rewrite clinical text. | M |
| 10 · P2 | Control Room | Cream service blocks and stretched last tile lack console rhythm → balanced seven-service console, compact trends, clear trace empty state and accessible chart summary | `ops/ControlRoom.tsx`, `ops/controlRoom.css`, scoped department CSS | Medium: retain no-data vs zero, raw observed values, polling/error visibility and administrator-only Surge. | M |
| 11 · P2 | Design system | Hard-coded blue/cream/type overrides drift → semantic selected/material/type tokens applied only to approved fix scope | `styles/hospital.css`, `styles/department-scenes.css` | Medium/high cascade risk: lazy import order matters; no global typography or geometry change to approved scenes. | M |
| 12 · P3 | Purposeful motion | Generic main fade doesn't orient cabinet/dossier/token changes → small selection/status highlight after successful owner reads, no fabricated intermediate numbers | `layouts/WorkspaceLayout.tsx`, `hospital/ui.tsx`, scoped department components/styles | Medium: reduced motion, focus, error states, pending locks and Emergency exemption must remain. Do after composition. | M |
| 13 · P3 | Reception / Consultation | Minor technical metadata and tiny secondary type in approved layouts → observation-only regression checklist; any correction needs separate explicit approved-scene scope | `design/ReceptionScene.tsx`, `design/ReceptionVisit.tsx`, `design/ReferenceConsultation.tsx`, corresponding styles | High approval/regression sensitivity; no scene redesign proposed. | S |

Environment prerequisite, **not a UI defect**: obtain a working dependency/toolchain and access to the retained synthetic installation/accounts. Do not reset data or create demo transactions to make captures attractive. Verify the Node engine warning against the locked dependency before claiming scanner compatibility; no upgrade is performed here.

## 7. Things that must not change

- Approved Reception and Consultation scene compositions, their physical slips/roster/profile and architectural alignment. Minor findings above do not revoke approval.
- Shared angled directory geometry, untransformed text/hit targets, role-aware destinations, local nav scrolling, selected-item scrolling, mobile drawer/Escape/focus return and skip link. Investigate specific semantic risks without redesigning it.
- Waiting Room scanner aperture, electronic monitor, cream personal-position display, manual fallback and camera lifecycle cleanup. Do not restore generic pale panels or claim physical decoding is verified.
- All API paths/contracts, server authorization and owner scopes; CSRF/session/refresh/token behavior; idempotency, frozen requests and safe ambiguous retries; ETag/If-Match requirements, stale/missing-version handling and command confirmation.
- Patient-only filtering even for multi-role operators; selected-visit prescription filters; historical/revoked records; grant/lease/legal-transition rules; quantity/stock authority and patient absence of dispensing actions.
- Money as integer minor units, authoritative tariffs/imports and simulation notices. Reservation is not dispensing, and dispensing is not automatically an invoice payment.
- Honest loading/empty/error/degraded/freshness states, bounded pagination, no-data vs zero, reduced motion and the Emergency no-scene-delay guard.
- Seven independent backend domains, their persisted data/volumes/audit history, infrastructure ownership and synthetic-only use. No fabricated queue rows, wait times, prices, stock, vitals, beds, census, ratings or readiness results.

## 8. Unverified work and handoff

Fresh 84-image route/viewport capture matrix, appointment tab/autocomplete/disclosure interactions, all role logins, DOM overflow, current first-fold bounds, computed contrast/targets/focus, reduced-motion runtime behavior and browser performance remain **unverified**. The current patient Pharmacy counter and latest pharmacist secondary fulfillment have source inspection only; old captures must not be presented as current evidence. Physical camera/QR decoding and ops-only role behavior remain unverified too. No live writes were performed to test any workflow.

The full requested live audit is therefore not accepted as complete. The evidence-based backlog is ready for review; implementation must wait for separate authorization. For later live verification, use the retained stack and existing accounts, preserve data, run the exact baseline checks, capture genuine settled states at the four requested viewports, record actual DOM overflow/fold bounds and replace the **historical designation only when new captures exist**.

Artifacts produced here: this report; ten unchanged extracted references; eleven historical-reference composites; provenance/coverage manifests; read-only comparison gallery. Dependency installation was the only attempted generated frontend-tree operation; source/test/package content remains unchanged as verified against remote.

### Final artifact checks actually run

A Python/Pillow/path/hash validation checked **17/17 local report links**, **47/47 gallery links/assets**, **11/11 composite dimensions and actual-source/composite SHA-256 records**, and **10/10 reference byte comparisons against `inages.zip` plus 1536×1024 dimensions**. It asserted exactly **84 coverage entries and 0 fresh captures**. All passed; 0 broken links or provenance/dimension failures. These are artifact checks, not frontend runtime tests. [Recorded baseline outcomes](verification/phase9-audit/check-results.json) retain the unavailable typecheck/test/build and denied Docker results.

## Fix pass 1 — Pharmacy

Branch `phase9/pharmacy-composition`, based on `698d31c`. This pass covers backlog items 1 (P0 composition) and 2 (P1 readability), for Pharmacy only. **All runtime evidence below comes from the dev-only mock API (`npm run dev:mock`), not from the retained backend.** The backend, Docker stack and real accounts were not used: no PulseGrid installation exists on the machine that ran this pass, and this pass was scoped to run without one. Mock pages carry a red MOCK DATA ribbon.

### Mock API mode

`frontend/dev-mock/` contains a Vite plugin that runs only on the dev server (`apply: "serve"`). It is active only when `VITE_MOCK_API=true`, and it answers `/api/*` from in-memory fixtures before the gateway proxy sees the request. Sign-in accepts any password, and the email picks the role: `patient@`, `pharmacist@`, `doctor@` or `admin@mock.test`. The fixtures are 14 synthetic medicines with mixed availability, nine batches, three prescriptions for one patient (a 3-item and a 1-item issued prescription plus one revoked), and one active reservation. The contract's reservation states are `reserved`, `expired`, `released` and `dispensed`, so the "pending" fixture uses `reserved`. The mock caps pages at 12 items so that Previous and Next are exercised. Mutations replay by `Idempotency-Key`, return 412 for a stale `If-Match` and 428 when `If-Match` is missing, and they change only in-memory state. No source module imports `dev-mock/`. After `npm run build`, a grep of `dist/` for mock identifiers, fixture SKUs and the ribbon text found nothing.

### What changed

- **Composition.** `frontend/src/hospital/pharmacyRoom.tsx` adds an opaque wall sign that replaces the 140px translucent hero. It also adds a cabinet whose top rail holds the autocomplete, the availability filters, page controls and a refresh button. The shelf face has 7 bays by 3 tiers at 1536 wide and 6 bays at laptop widths. Empty slots stay as bare wood, and the bay labels are the neutral "Bay A" to "Bay G". Below the cabinet sit the foreground Rx stand and a paper tray. The right counter is an absolutely positioned flex stack inside its own grid area, so its height never affects the left rows.
- **Patient.** The Rx stand holds the owned-prescription selector. The tray holds the real dosage and instructions. The right upper panel is the reservation slip with the existing reserve form, and the right lower panel is the prescription summary. `PatientFulfillmentPanel` now hands its stand, tray and right-column slots to the room through a `room` render prop, so `ReservationStatus` keeps one stable parent. Its pending/ambiguous selection lock and same-key retry are unchanged, and the focused test still passes.
- **Pharmacist dashboard and inventory.** The Rx stand holds the Records prescription lookup, and the tray shows the compact prescription. The right upper panel shows the selected medicine, its advisory availability and its batch quantities. The right lower panel holds the link to the dispensing workspace plus disclosures for the catalog edit, new medicine, stock adjustment and inventory filter.
- **Pharmacist `/prescriptions`.** It uses the same geometry. The stand holds the lookup; the tray holds the prescription and the existing reserve form. The right upper panel shows the current reservation with its Release, Revalidate and Dispense reviews. The right lower panel holds the register, the ID lookup, the dispensing ledger and the authority/stock verification disclosures.
- **API behavior is unchanged.** Every API path, ETag/If-Match, idempotency key, role gate and `CommandForm` review step is the same as before. `Collection` gains an optional `sourceNote` prop whose default is unchanged; Pharmacy passes `null`.
- **CSS.** The stacked Pharmacy override blocks in `department-scenes.css` (the `.pharmacy-counter-workspace…` and `.staff-fulfillment…` overrides) were deleted. They are replaced by one section scoped to `.department-page--pharmacy`. Records' default `PrescriptionDetail` is untouched. The legacy `MedicineCatalog` used on the doctor and admin desks keeps its layout and gets only the copy changes.
- **Background seam.** Pharmacy shells use `background-size: cover` with a fixed attachment, so the flat `#c9aa88` band no longer appears. The composition ends on a marble counter top and an oak counter front.
- **Copy.** "Stock hint" is now "Availability". "Not reported" is now "Availability not supplied", shortened to "Not supplied" on narrow shelf labels with an accessible "Availability" prefix. "Reload resource" is now "Refresh". "Owner service data" is removed from Pharmacy. Medicine names replace raw item IDs in the patient reservation form, slip and history. IDs and versions are in a single "Details" disclosure per object.
- **Motion.** The selected carton lifts 3px only under `prefers-reduced-motion: no-preference`, and the selected bay gets a static highlight. The reservation slip and the dispensing confirmation flash a background colour only after the owner response.

### Measured budget at 1536×1024 (`getBoundingClientRect`, page y)

| Region | Patient before | Patient after | Pharmacist before | Pharmacist after |
| --- | --- | --- | --- | --- |
| Header | 0–76 | 0–76 | 0–76 | 0–76 |
| Heading or wall sign | 90–230 | 90–192 | 90–230 | 90–192 |
| Search panel or cabinet rail | 246–385 | 206–305 | 246–385 | 206–305 |
| Shelves | 438–988 | 311–619 | 464–1015 | 311–619 |
| Rx stand | 1004–1517 | 673–939 | 1031–1223 | 633–899 |
| Right upper | 246–422 | 200–607 | 246–448 | 200–584 |
| Right lower | 438–1407 | 619–939 | 464–968 | 596–899 |
| **Rx stand primary control bottom** | **1172** | **823** | **1164** | **854** |
| Document height | 1565 | 1024 | 1335 | 1024 |

The primary control is the prescription selector for the patient and the lookup's Open button for the pharmacist; before this pass, the pharmacist's was "Open dispensing workspace". Both roles now fit at 1536×1024 with no scroll. `/pharmacist/inventory` and `/pharmacist/prescriptions` also measure 1024 tall, with the primary control ending at 849 and 889.

Other sizes: at 1440×900 the controls end at 816 (patient) and 847 (pharmacist), and at 1280×800 at 839 and 847, with mild page scroll. At 390×844 the order is sign, Rx stand, tray, reservation, summary and then the cabinet. `scrollWidth > innerWidth` is false for all 26 captures. Full data is in [before](verification/phase9-pharmacy/before-measurements.json) and [after](verification/phase9-pharmacy/after-measurements.json) measurements.

### Checks run

| Check | Result |
| --- | --- |
| `npm run typecheck` (Node 24.22.0) | PASS |
| `npm test -- --reporter=dot` | PASS, 11 files and 142 tests. One test changed: in `tests/advanced_patient/patient-workflows.test.tsx` the reservation quantity label is now found by medicine name, and the reservation-history assertion checks "× 2" and "Reservation …91 · reserved" instead of the raw "72: 2". |
| `npm run build` plus grep of `dist/` for mock code | PASS; no matches |
| [Readability check](verification/phase9-pharmacy/readability-results.json) on 3 Pharmacy routes at 1536 | Minimum visible text 12px, with none below 12px. Minimum computed contrast 6.19:1 (patient), 6.85:1 (pharmacist dashboard) and 5.40:1 (`/prescriptions`); no text is below 4.5:1. Every visible control is at least 40px tall. Decorative carton text is `aria-hidden` and excluded. |
| [Interaction check](verification/phase9-pharmacy/interaction-results.json) | 12/12 PASS: auto-selection, carton selection updating the right counter, availability filter, Next/Previous, autocomplete selection, Tab order from cabinet to Rx stand to counter, opening the dispensing workspace with a lookup, current reservation shown, and a patient reservation request (mock write) producing a confirmed slip with no dispensing controls. |
| Regression captures: Reception, Consultation, Waiting Room at 1536 | Layout unchanged. Pixel differences are confined to timestamp text, because the mock derives slot, observed and expiry times from server start. |

Captures are `verification/phase9-pharmacy/{before,after}-<role>-<w>x<h>.png`. The reference, before and after composites are [patient](verification/phase9-pharmacy/compare-patient-1536x1024.jpg) and [pharmacist](verification/phase9-pharmacy/compare-pharmacist-1536x1024.jpg). Scripts: `capture.mjs`, `readability-check.mjs` and `interaction-check.mjs`.

### Still unverified or different from the reference

- Nothing here has run against the real backend, real accounts or real catalog sizes. A 20-item real page fills more bays, and the cabinet adds a fourth tier when a page exceeds the bay count. A live run with the retained stack is still required.
- The cartons are flat single boxes with one per medicine, sparser than the reference's photographic multi-box stock. The reference's category tabs, prices, cart, "Generate Bill", upload, scanner and Ready/Pickup/Dispatch remain intentionally absent.
- The pharmacist reserve form labels still read "Quantity for item … (medicine …)" because `Field.label` is a string and an existing test depends on it. Names are shown in the adjacent prescription paper.
- At 390 wide the visual order (Rx stand before cabinet) differs from the DOM order (cabinet first), which is kept so that the desktop Tab order runs cabinet, stand, counter. Screen-reader and mobile keyboard behavior were not tested.
- Contrast was computed against the nearest opaque fill, using the darker and lighter stops of gradients. It is not a WCAG certification. 200% zoom, screen-reader output and touch behavior were not tested.

## Fix pass 2 — Emergency, Billing, Medical Records and shared copy

Branch `phase9/clinical-desks`, created from `phase9/pharmacy-composition`. This pass covers backlog rows 4 (Emergency), 8 (Billing), 9 (Records) and 5 (shared copy), plus the mobile ordering from row 3 for these three departments. **All runtime evidence is from `npm run dev:mock`, not from the retained backend.** Reception, Consultation, the directory, Waiting Room and Pharmacy layouts were not edited.

### Mock additions

The mock adds two logins, `billing@mock.test` and `emergency@mock.test`, and fixtures for all three departments:

- **Emergency:** nine synthetic requests. They cover the submitted, triaged, claimed, processing, resolved and cancelled states, unassigned requests and priorities 1–5. One claim is held by the signed-in emergency user and one by another staff ID.
- **Billing:** three invoices: unpaid, partly paid and paid. One has an imported consultation plus two pharmacy lines. There are consultation tariff revisions 1 (historical) and 2 (current), plus declined and successful simulated payments.
- **Records:** one patient with five finalized visits and one amended record (revision 2 supersedes revision 1). The three prescriptions from the earlier fixtures are attached to visits, one of them revoked. The doctor has one draft consultation.

Access grants are created through the existing POST. The contract has no grant list, so none appears until one is created. Mutations honour `If-Match` (returning 412 or 428) and `Idempotency-Key` replay, as before.

### What changed

- **Emergency** (`billingEmergency.tsx › EmergencyPage`)
  - **Sign:** a compact red-cross department sign with counts computed only from the loaded list: Unassigned, Priority 1–2 and Claimed. The counts are labelled "in this list", or "in this list page" when the list is paginated.
  - **Queue:** the register is a scrollable queue. Each row has a P1/P2/P3–5 chip with visible text, the description, the elapsed time since `created_at` and the state.
  - **Case panel:** shows the description, submitted and updated times, advisory urgency, assigned priority, contact, and claim holder with the lease end. There are no vitals, orders, beds or disposition.
  - **Next steps:** only legal actions are shown, and the most likely one is a dark-red primary.

    | State | Primary | Secondary disclosures |
    | --- | --- | --- |
    | Submitted | Set priority | Cancel |
    | Triaged | Claim | Change priority, Cancel |
    | Own claim | Start processing | Release claim, Change priority, Cancel |
    | Someone else's claim | None (shown as a note) | Change priority, Cancel |
    | Own processing | Resolve | Change priority |
    | Resolved or cancelled | None | None |

    This is exactly the set the previous form stack allowed. Cancel and release still require a reason and confirmation.
  - **Status colours:** submitted, claimed and processing are blue, resolved is green and cancelled is grey. Every status and priority also carries text.
  - **Mobile:** the case and next steps come first, and the register is behind an "All requests (n)" toggle.
  - **Patient view:** the intake form and "Your requests" are separate columns, and the synthetic-not-dispatch notice is always visible.
  - **Motion:** the existing exemption is unchanged, so Emergency has no GSAP or scene delay.
- **Billing** (`billingEmergency.tsx › BillingPage`)
  - **Context band:** shows patient (the name for the patient themselves, an ID tail for staff), visit, invoice and a status chip. Status is Unpaid, Part paid or Paid, derived from `status` and `paid_minor`. "Change invoice" moves focus to the register.
  - **Staff workbench:** tabs for Import charges (the existing conditional import), Tariff reference (read-only, with current and historical revisions labelled) and New invoice. Below the tabs is a compact invoice register table with the selected row highlighted in teal.
  - **Receipt:** grouped into Consultation and Pharmacy, showing qty × unit and the line amount from the API. Total, Paid and Balance due sit in the pale-green strip.
  - **Payment amount:** the field is now entered in rupees, with a live "₹500.00 → 50000 paise will be submitted" preview. The submitted `amount_minor` is the same integer as before, parsed from the decimal string without floating point.
  - **Medicine names:** medicine charge codes resolve to Pharmacy names and fall back to the charge code.
  - **Patient view:** receipt first, then their invoices, with no import or create controls.
  - **Mobile:** context band, receipt, actions, then register.
- **Medical Records** (`records.tsx › RecordsPage, History, Consultations`)
  - **Patient band:** name, ID tail, last visit date and visit count. Records versions are grouped by consultation, so an amendment does not appear as a second visit.
  - **Visit timeline:** a vertical spine with teal selection, replacing the blue `#2286cc`.
  - **Dossier sheet:** a header with visit date, clinician and specialty (resolved from the consultation and the doctor directory) and a Current / Amended / Earlier version state. Summary, Assessment and Plan are sections on one sheet. Stored text is rendered with `white-space: pre-wrap`, never truncated or rewritten.
  - **Prescribed medicines:** a per-visit table (medicine name, quantity, dosage, instructions) loaded with `patient_id` + `consultation_id`. Revoked prescriptions stay visible with a "Revoked" label and a retained-as-history note. The data has no separate dose, frequency or duration fields, so those columns are not invented.
  - **Right column:** Record history (original and amendment versions, each openable), linked prescriptions, pharmacy and journey, access grants in a disclosure, and a single Details disclosure.
  - **Doctor's Consultations:** uses the same register, sheet and side layout. Create, save-draft, finalize and amend flows are unchanged.
  - **Mobile:** the timeline becomes a horizontal scroller above the dossier.
- **Shared copy** (`ui.tsx`, `HospitalHeader.tsx`, `patientDoctor.tsx`, `advanced/patient/api.ts`)
  - "Reload resource" is now "Refresh".
  - The 412 advice now reads "Refresh to load the latest version…".
  - "Owner service data" is no longer shown by default, and the touched panels use a single "Details" disclosure.
  - The header shows the role label ("Pharmacist") instead of "Account …1002", and the account ID moves into the account menu ("Account ID …").
  - The search placeholder is now "Find a department or workflow…".
  - The reschedule review reads "Move your visit on [date] to [date]".
  - Stale, error, ambiguous-retry and loading states are unchanged.
- **Tokens:** `hospital.css :root` gains `--text-secondary-size`, `--text-body-size`, `--select-teal(-soft)`, the `--status-*` pairs and `--emergency-red`. They are used only in the new Emergency, Billing and Records sections.
- **Legacy CSS:** the old Emergency, Billing and Records override blocks in `department-scenes.css` are deleted. `.prescription-revoked-note` is kept because Pharmacy uses it.

### Checks

| Check | Result |
| --- | --- |
| `npm run typecheck` | PASS |
| `npm test -- --reporter=dot` | PASS, 11 files and 142 tests. Changed assertions: the design test's two header checks now expect "Account ID 21" in the menu and a "Patient account menu" label; the stale-version test now expects "Refresh to load the latest version". |
| `npm run build` plus grep of `dist/` for mock code | PASS; no matches |
| [Captures](verification/phase9-pass2/after-measurements.json): 6 subjects × 4 sizes, plus `/billing/invoices` and 5 regression routes | 0 failing. No horizontal overflow at any size. At 1536×1024 the Emergency primary next step ends at y=581, the Billing balance strip at 697 (staff) and 717 (patient), and the Records dossier header at 393 (patient) and 304 (doctor). |
| [Readability](verification/phase9-pass2/readability-results.json) at 1536 on 6 routes | Minimum visible text 12px. Minimum computed contrast 5.95:1. Every control is at least 40px tall. |
| [Interactions](verification/phase9-pass2/interaction-results.json) | 17/17 PASS, including a mock claim that moves the next step to Start processing, the paise preview (100.5 becomes 10050 paise), focus moving to the register, the amendment history and the revoked prescription. |
| Regression at 1536 (Reception, Consultation, Waiting Room, both Pharmacy roles) | Layout unchanged. Differences are the intended header identity text and the mock's relative timestamps. |

Composites: [Emergency](verification/phase9-pass2/compare-emergency-staff-1536x1024.jpg), [Billing](verification/phase9-pass2/compare-billing-staff-1536x1024.jpg), [Records](verification/phase9-pass2/compare-records-patient-1536x1024.jpg).

### Still unverified or different from the reference

- No real backend run. Real role scopes, field omissions (for example, whether a patient's emergency response omits the description) and pagination sizes may differ from the mock.
- Emergency staff (1051px) and Billing (1172px) pages scroll slightly at 1536 because the register and payment form continue below the fold. The checked targets are above it.
- The reference's patient photo, age and sex, triage vitals, active orders, disposition, retail medicine picker, discounts, draft/print, blood group, allergies, labs and imaging are deliberately absent.
- The Records timeline cannot show doctor or visit type per entry, because the record summary does not return them; only the selected dossier resolves the clinician.
- Access grants have no list endpoint, so previously created grants cannot be shown.
- Screen-reader output, 200% zoom and touch behaviour were not tested.
