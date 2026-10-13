# Phase 9 approved reference inventory

All ten attached images inspected before implementation. Images are visual specifications, not runtime data or capability authorization. Functional UI is HTML/SVG; reference screenshots are never application backgrounds.

## Reception

- Reference: `home.png` (original `/Users/aakash/Downloads/inages/`).
- Existing routes: `/; /patient/dashboard`.
- Composition/components: Suspended directional signs, welcome wall and central robot behind reception counter; four paper action slips and bottom queue display.
- Environment/materials/colors/type: Warm oak reception desk, limestone wall, marble floor; navy grotesk heading and restrained teal/red signs.
- Proportions and interaction expectations: Header 5–8%; directory 16–19%; central wall 55%; paper actions along bottom; no invented hospital counts.
- Navigation: shared physical numbered hospital directory, department icon, description, directional arrow, inset teal active row; emergency uses red. Wide cream header with wordmark, search, account.

## Consultation

- Reference: `consultation.png` (original `/Users/aakash/Downloads/inages/`).
- Existing routes: `/patient/doctors; /doctor/*; /admin/doctors`.
- Composition/components: Specialties rail at left; doctor directory center; selected profile right; appointment timeline and contextual clinical actions below.
- Environment/materials/colors/type: Clinical desk, warm stone and oak; cream directory rows, teal selection and thin separators.
- Proportions and interaction expectations: Directory 18%; workspace 48%; profile 28%; actual specialties, profiles and accepted slots only.
- Navigation: shared physical numbered hospital directory, department icon, description, directional arrow, inset teal active row; emergency uses red. Wide cream header with wordmark, search, account.

## Appointments

- Reference: `appointment.png` (original `/Users/aakash/Downloads/inages/`).
- Existing routes: `/patient/appointments; /receptionist/appointments`.
- Composition/components: Booking tabs; doctor selector left, dates/slots and patient fields center, confirmation receipt right.
- Environment/materials/colors/type: Reception countertop, limestone, plants; deep teal slots and primary action.
- Proportions and interaction expectations: Directory 18%; doctor rail 20%; slot/form 42%; receipt 18%; real concurrency/version responses.
- Navigation: shared physical numbered hospital directory, department icon, description, directional arrow, inset teal active row; emergency uses red. Wide cream header with wordmark, search, account.

## My Appointments / Reschedule / Walk-in

- Reference: `resehduele waiting and walkin.png` (original `/Users/aakash/Downloads/inages/`).
- Existing routes: `/patient/appointments?view=upcoming; /receptionist/appointments`.
- Composition/components: Top: appointment strips, state tabs and overview. Bottom left: current appointment slip, calendar, time grid and change reason. Bottom right: step rail, patient details and walk-in guidance.
- Environment/materials/colors/type: Reception countertop with paper forms; cream panels; navy headings; red cancellation outlines.
- Proportions and interaction expectations: Three distinct compositions, not one screenshot: appointment list plus details; reschedule local selection; walk-in maps to existing demographic lookup and booking without prior appointment. No unsupported guest creation.
- Navigation: shared physical numbered hospital directory, department icon, description, directional arrow, inset teal active row; emergency uses red. Wide cream header with wordmark, search, account.

## Waiting Room / Check-in

- Reference: `waiting room.png` (original `/Users/aakash/Downloads/inages/`).
- Existing routes: `/patient/check-in; /patient/queue; /patient/waitlist; /doctor/queue; /receptionist/appointments`.
- Composition/components: Kiosk on left, queue display center, personal queue status at right.
- Environment/materials/colors/type: Warm limestone wall, vertical oak slats, plants; legible cream queue board; teal/amber state labels.
- Proportions and interaction expectations: Kiosk 22%; board 50%; status 22%; patient sees own entry/counts only. No invented wait estimate or other patient names.
- Navigation: shared physical numbered hospital directory, department icon, description, directional arrow, inset teal active row; emergency uses red. Wide cream header with wordmark, search, account.

## Pharmacy

- Reference: `pharmacy.png` (original `/Users/aakash/Downloads/inages/`).
- Existing routes: `/patient/pharmacy; /patient/prescriptions; /pharmacist/*`.
- Composition/components: Wide shelf catalog and search center; prescription workspace below; selected medicine/fulfillment at right.
- Environment/materials/colors/type: Oak medicine shelves, stone dispensing counter; cream bag/prescription surfaces and teal buttons.
- Proportions and interaction expectations: Catalog 65%; fulfillment 30%; use owner availability hints, not made-up precise stock or retail order basket.
- Navigation: shared physical numbered hospital directory, department icon, description, directional arrow, inset teal active row; emergency uses red. Wide cream header with wordmark, search, account.

## Billing

- Reference: `billing.png` (original `/Users/aakash/Downloads/inages/`).
- Existing routes: `/patient/billing; /billing/*`.
- Composition/components: Patient/invoice context band; source charge construction left; itemized invoice and total right.
- Environment/materials/colors/type: Warm reception/billing counter; crisp ivory worksheets, pale green total, teal generate/pay action.
- Proportions and interaction expectations: Source/history 65%; invoice receipt 32%; consultation/dispensing imports only. Labs, beds, custom retail prices, discounts/drafts/printing are unsupported.
- Navigation: shared physical numbered hospital directory, department icon, description, directional arrow, inset teal active row; emergency uses red. Wide cream header with wordmark, search, account.

## Emergency

- Reference: `emergency.png` (original `/Users/aakash/Downloads/inages/`).
- Existing routes: `/patient/emergency; /emergency/*`.
- Composition/components: Emergency queue left; active case and assessment center; allowed transitions/actions right.
- Environment/materials/colors/type: Warm emergency entrance; red cross and deep red action treatment.
- Proportions and interaction expectations: Queue 28%; case 45%; actions 25%; preserve advisory urgency, owner priorities/leases/legal transitions; no fabricated vitals, treatment or admission.
- Navigation: shared physical numbered hospital directory, department icon, description, directional arrow, inset teal active row; emergency uses red. Wide cream header with wordmark, search, account.

## Medical Records

- Reference: `medicalrecords.png` (original `/Users/aakash/Downloads/inages/`).
- Existing routes: `/patient/records; /doctor/prescriptions; /patient/journey`.
- Composition/components: Patient band and tabs; chronological visits left; active clinical dossier center; contextual prescriptions and access tools right.
- Environment/materials/colors/type: Warm stone archive/care room, cream dossier paper; navy headings, teal active tab, colored timeline markers.
- Proportions and interaction expectations: Timeline 24%; record 50%; tools 24%; no invented labs/imaging/vitals. Selecting entry loads authorized record.
- Navigation: shared physical numbered hospital directory, department icon, description, directional arrow, inset teal active row; emergency uses red. Wide cream header with wordmark, search, account.

## Control Room

- Reference: `controlroom.png` (original `/Users/aakash/Downloads/inages/`).
- Existing routes: `/ops/*; /admin/control-room; /admin/traces`.
- Composition/components: Summary strip; dominant overview monitors; status/alerts right; trends and system health below.
- Environment/materials/colors/type: Warm oak operations room, monitor panels, ivory surfaces with teal lines.
- Proportions and interaction expectations: Dense technical monitors from Phase 7 APIs only; no bed map, CCTV, staff occupancy or fabricated operational values.
- Navigation: shared physical numbered hospital directory, department icon, description, directional arrow, inset teal active row; emergency uses red. Wide cream header with wordmark, search, account.

