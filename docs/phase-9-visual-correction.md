# Phase 9 — Reception and Consultation correction

The user's visual review rejected the first Phase 9 design. This supersedes its visual acceptance claims. That correction checkpoint was limited to Reception/Homepage and Consultation/Doctor Directory. The seven remaining departments are now continued in [the Phase 9 resume report](phase-9-resume.md), which records their implementation and remaining acceptance limits. Previously completed and pending Phase 9 work is preserved in the local history.

## Reference and rendered evidence

Original references are `home.png` and `consultation.png`, each 1536 × 1024 (3:2). Exact copies and actual browser captures are in [the comparison directory](verification/phase9-correction/). [The comparison page](verification/phase9-correction/review.html) renders each pair at the same 3:2 ratio, without cropping. The screenshots contain live owner responses, not React fixtures or rasterized controls.

| Screen | Route and permission context | Final evidence |
|---|---|---|
| Reception | `/patient/dashboard`, fictional Anika Shah; actual Patient workspace, with authorized administrator/receptionist alternatives | [Reference](verification/phase9-correction/references/reception.png), [1536](verification/phase9-correction/reception-1536.jpg), [1440](verification/phase9-correction/reception-1440.jpg), [1280](verification/phase9-correction/reception-1280.jpg), [390](verification/phase9-correction/reception-390.jpg) |
| Consultation | `/admin/doctors`, actual Hospital administrator workspace; the same directory and booking also exercised at `/patient/doctors` | [Reference](verification/phase9-correction/references/consultation.png), [1536](verification/phase9-correction/consultation-1536.jpg), [1440](verification/phase9-correction/consultation-1440.jpg), [1280](verification/phase9-correction/consultation-1280.jpg), [390](verification/phase9-correction/consultation-390.jpg) |

## Structural correction and comparison rounds

Reception formerly separated generic information panels from a background and let long fixture names dominate. It now places suspended signs above a restrained first-name welcome on the stone wall, exposes the central robot, labels the reception counter, and arranges four distinct physical objects on the foreground counter: spiral appointment pad, green folder stack, check-in tent and record files. The real queue number appears on a standing paper token and a flip-style display. The lower rail contains actual visit information and truthful announcement availability. Profile editing remains in a closed, accessible disclosure below the scene.

Consultation formerly used oversized separate lookup panels and an empty profile placeholder. It now opens the first returned doctor automatically. One directory board contains a specialty rail, compact search, scrollable doctor roster and adjacent selected profile. The selected profile has a fictional illustrative portrait only in local demo mode, actual owner specialties/status, next accepted time, real open-time/day/revision values, About/Schedule/Details tabs and a booking action. Authorized appointment slips and workflow links sit on the clinical desk beneath it. Internal IDs are secondary Details fields and accessible labels, not the roster's visible titles. Opaque cursor pagination, advanced search/autocomplete and administrator commands remain available.

The comparison rounds corrected these specific defects:

1. Removed giant greeting names, generic homepage panels and rectangular four-card navigation; rebuilt physical counter objects.
2. Matched the two architectural frames with clean generated assets; relocated the signs, welcome text, speech bubble, profile and desk instruments to their physical surfaces.
3. Compressed search/roster/profile spacing; moved administrative tools into disclosures; restored all eight permitted directory departments at smaller laptop width.
4. Added real demo queue and appointment reads; prevented a future appointment from hiding an already checked-in same-day queue.
5. Fixed a mobile grid's intrinsic minimum width, bounded the tab strip locally, and moved Reception statistics away from the robot face. Final 390px page widths have no horizontal overflow.
6. Kept roster/profile navigation locked during frozen booking review. Completed a real booking through the corrected profile.

## Fictional demo data and production boundary

`frontend/scripts/phase9_demo_hospital.py` adds records through existing owner APIs on loopback only. It never edits/deletes earlier integration fixtures or resets persistent data. Six fictional doctors, six specialties, six patient-role accounts, accepted schedules, eight appointments (including the browser-confirmed booking), three catalog medicines and their stock were added. The near-term visit was checked in with an actual one-time link and workflow ETag. Its waiting token is owner-issued.

Patient registration also creates Patient-owned profiles for the six new doctor accounts; only the six patient-role accounts represent demo patients.

A new fictional operator has patient, hospital_admin and receptionist roles for the local demonstration. Existing approved operator credentials provisioned these accounts. Credentials, raw link tokens and the resume manifest remain outside Git in a private file with mode 0600; nothing is printed into the screenshots.

`frontend/.demo/hospital.json` contains reversible portrait indexes and friendly display labels mapped to the actual owner IDs. It is ignored. `VITE_LOCAL_HOSPITAL_DEMO=true` is set only in ignored `.env.local`. A Vite **serve-only** middleware exposes the metadata on loopback. The React hook additionally requires `MODE === development`. The manifest, identities and credentials are not bundled in production, and the demo mechanism never grants API permission. The advanced directory includes a reversible Show all owner records toggle; creating a directory entry also reveals the complete owner list, so the demo cohort never removes access to older fixtures. Outside this mode the UI uses actual returned records and initials. Search in demo mode accommodates the seeded `Dr.` honorific while retaining the owner's prefix-search contract.

## Verification

Browser checks used the actual Vite/gateway deployment and the fictional accounts. Verified login, permitted workspace handoff, reception action routes, the mobile directory drawer, specialty filtering, doctor name search, automatic profile selection, profile Schedule/Details, reversible full-owner-record search, accepted availability, reviewed booking, locked review controls and successful owner confirmation. Browser booking `8361876042933944065` was returned by Appointment with the requested patient, doctor and 19:00–19:30 UTC slot. No frontend-only success was used. The earlier broader Phase 9 integration checks are historical evidence, not a claim that the other designs passed visual review.

Typecheck, all 142 frontend tests and production build pass. Tests cover existing auth, RBAC, retry/idempotency/version contracts plus first-profile selection and secondary internal-ID presentation. Production output is inspected for absence of the local demo manifest and IDs. No backend business code, schema, contract, container or persistent volume was changed. No backend suite, chaos, performance benchmark, external payment or physical camera test was rerun for this correction.

## Exact differences remaining

- Directory icons use the existing outlined vector glyphs rather than the reference's heavier filled symbols.
- The references' photographic objects/people, perspective and plant arrangement are not pixel-identical. Clean architecture generated from the two supplied references preserves their framing; the reference's embedded UI is never used as application graphics.
- Counter pads, folder stacks and standing token are CSS/HTML objects; their perspective is simpler than the photographed paper objects. The robot is a static high-quality architectural asset, with surrounding UI motion rather than an animated robot model.
- Reception reports this account's authorized visits and queue, not fabricated hospital-wide activity/emergency totals. There is no announcements API; the rail states that and provides working visit/check-in links.
- Consultation has six fictional clinicians instead of 24, and six real owner specialties. Ratings, qualifications, experience, clinical biographies, labs and imaging are omitted because the current Doctor contract does not supply them. Real schedule values occupy the profile's metadata strip.
- Appointment references A028–A034 are development-only presentation labels. The live queue number A001 comes from the owner token. Full internal IDs remain accessible in Details and command context.
- Clinical authoring actions are not shown to this administrator/patient account; they remain in the authorized doctor workspace. The corrected Quick Actions use permitted appointments, records, prescriptions and staff-directory routes.
- Staff Consultation uses actual administrator permissions. Reception is the actual Patient workspace of the same fictional multi-role account; its header states Patient. It does not impersonate the operator role depicted in the reference.
- The directory includes extra workspace controls; its height differs from the photographed sign. On mobile it becomes a drawer; papers reflow into two columns and the profile stacks under the roster. The desktop composition is not shrunk wholesale.

The two corrected scenes are ready for the requested human visual review. This report does **not** declare the overall Phase 9 redesign visually accepted. Stop here; no further department redesign is authorized until that review.
