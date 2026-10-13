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
