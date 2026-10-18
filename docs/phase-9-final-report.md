# Phase 9 final report: UI refresh

**Status: complete in mock mode, unverified against the real backend.** Every department now follows its reference composition using only data the owner APIs return. Typecheck, 144/144 tests and the production build pass. Every capture in the final sweep is free of horizontal overflow, and every department's primary action sits above y=1024 at 1536×1024. Two categories of small text are left deliberately and are listed below. Runtime evidence comes from `npm run dev:mock` with synthetic fixtures. No Docker stack, real accounts or real data were used, and physical QR decoding remains untested.

Branches, all local and none pushed:

- `phase9/pharmacy-composition`: pass 1, Pharmacy.
- `phase9/clinical-desks`: pass 2, Emergency, Billing, Medical Records and shared copy.
- `phase9/final-polish`: pass 3, Appointments, Control Room, navigation accessibility, tokens, motion and this sweep.
- `phase9/ui-refresh`: the combined review branch, a fast-forward of the three.

Per-pass detail is in the "Fix pass 1" and "Fix pass 2" sections of [the audit](phase-9-ui-audit.md).

## How to view

From `frontend/`, using Node 24, run `npm run dev:mock` and open http://127.0.0.1:5173/login. Any password works. The email address chooses the role, and a red MOCK DATA ribbon marks every page in this mode.

| Login | Routes |
| --- | --- |
| `patient@mock.test` | `/patient/dashboard`, `/patient/doctors`, `/patient/appointments` (`?view=upcoming`, `?view=reschedule`), `/patient/queue`, `/patient/pharmacy`, `/patient/billing`, `/patient/emergency`, `/patient/records` |
| `receptionist@mock.test` | `/receptionist/appointments?view=walk-in` (also Book, My Appointments, Reschedule / Cancel) |
| `doctor@mock.test` | `/doctor/consultations` |
| `pharmacist@mock.test` | `/pharmacist/dashboard`, `/pharmacist/inventory`, `/pharmacist/prescriptions` |
| `billing@mock.test` | `/billing/dashboard`, `/billing/invoices` |
| `emergency@mock.test` | `/emergency/dashboard` |
| `admin@mock.test` | `/admin/control-room`, `/admin/traces` (Surge Mode controls are administrator-only) |
| `ops@mock.test` | `/ops/dashboard`, `/ops/traces` |

## What changed per department

- **Reception, Consultation and Waiting Room** keep their approved layouts. They pick up only shared changes:
  - The header shows the role label, with the account ID in the account menu.
  - The search placeholder reads "Find a department or workflow…".
  - "Refresh" replaces "Reload resource".
  - Directory alias links carry `aria-current`.
  - Lists use a first-load stagger.
  - The room transition no longer doubles the Reception intro.
- **Appointments** (pass 3)
  - **Desk tabs:** Book Appointment, My Appointments, Reschedule / Cancel, and Walk-in for receptionists, over one desk surface.
  - **Book:** three numbered columns.
    - Doctor roster: search, 13px/40px specialty pills, and teal selection replacing blue `#1689da`.
    - Date and time: a week strip with arrows, slots grouped Morning / Afternoon / Evening, an Available / Unavailable / Selected legend, and read-only profile fields that say "Not provided" when empty.
    - Summary: the Confirm action, then a printed slip after the service confirms.
  - **My Appointments:** Upcoming, Past and Cancelled tabs with counts from the loaded list, and rows with View / Reschedule / Cancel. An overview column shows counts labelled as loaded-list counts. No policy text is shown, because no API or document defines one.
  - **Reschedule / Cancel:** current appointment, month calendar and day slots, with Cancel (red outline) beside the reschedule review. The review sentence uses doctor names and old and new dates. The existing ETag, frozen review and idempotent retry are unchanged.
  - **Walk-in:** a step rail (find patient, doctor and slot, confirm). It uses the existing patient search, links to the Reception desk for registration, and shows static guidance with no waiting-time estimate.
- **Waiting Room** is unchanged, apart from the shared polish above.
- **Pharmacy** (pass 1)
  - **Room layout:** a wall sign, then a cabinet with a top rail and a 7-bay shelf face, then a foreground Rx stand and paper tray, with an independent right counter.
  - **Readability and copy:** text is 12px or more, targets are at least 40px, and the copy follows the audit.
- **Billing** (pass 2)
  - **Context band:** shows the selected invoice.
  - **Cashier tabs:** Import charges, Tariff reference with historical revisions labelled, and New invoice.
  - **Receipt:** grouped by source, with the Total / Paid / Balance strip.
  - **Payment amount:** entered in rupees with an exact paise preview.
- **Emergency** (pass 2)
  - **Counts:** the sign shows counts computed from the loaded list.
  - **Panels:** a queue with text-carried priority chips, and a case panel.
  - **Next steps:** shows only legal actions. Cancel and release are secondary.
  - **Status colours:** neutral or blue for active states, and green only for resolved.
  - **Motion:** Emergency remains exempt from scene motion.
- **Medical Records** (pass 2)
  - **Patient band and visit timeline:** a visit timeline with teal selection.
  - **Dossier:** a single-sheet dossier with that visit's prescribed medicines. Revoked prescriptions stay labelled.
  - **Record history:** shows each visit's versions.
  - **Doctor consultations:** share the layout.
- **Control Room** (pass 3)
  - **Wall monitor:** a sign with a dark-teal wall monitor showing services ready, p95, 5xx and firing alerts. "No data" never becomes 0.
  - **KPI row:** throughput, p95, 5xx, RabbitMQ backlog and Redis hit rate. Trend arrows come only from returned series.
  - **Service topology:** renamed, and laid out as a balanced 4 + 3 tile console with an inspector.
  - **Alerts and bus:** live alerts with severity text, plus a message bus and cache panel.
  - **Trends:** the trend charts break at missing samples and have a "View data" table.
  - **Surge Mode:** a panel with the unchanged administrator-only reviewed control.
  - **Traces:** a compact empty state and a span waterfall.
- **Shared shell, tokens and motion** (pass 3)
  - **Directory and drawer:** directory links active through an alias route get `aria-current="page"`. The open mobile drawer is `role="dialog"` with `aria-modal`, and the workspace behind it is `inert` and `aria-hidden`. Escape and return focus are unchanged and covered by new tests.
  - **Tokens:** `--select-teal`, `--status-success/warning/danger/neutral`, `--text-secondary-size: 13px` and `--target-min: 40px`, used in Appointments, the Control Room and shared `ui.tsx` styles.
  - **Motion:**
    - The room fade is 0.3s.
    - List entry staggers on first load only, at 30ms per row for up to 8 rows. A refetch never re-animates.
    - A brief selection pulse marks the chosen doctor, slot, tile, visit or carton.
    - Receipt and slip emphasis plays only after a confirmed response.
    - Reduced motion is respected.

## Before and after

| Pass | Composites |
| --- | --- |
| Pharmacy | [patient](verification/phase9-pharmacy/compare-patient-1536x1024.jpg) · [pharmacist](verification/phase9-pharmacy/compare-pharmacist-1536x1024.jpg) (reference, before, after) |
| Clinical desks | [Emergency](verification/phase9-pass2/compare-emergency-staff-1536x1024.jpg) · [Billing](verification/phase9-pass2/compare-billing-staff-1536x1024.jpg) · [Records](verification/phase9-pass2/compare-records-patient-1536x1024.jpg) (reference, before, after) |
| Pass 3 | [Book](verification/phase9-final/before-after-appointments-book.jpg) · [My Appointments](verification/phase9-final/before-after-appointments-manage.jpg) · [Walk-in](verification/phase9-final/before-after-appointments-walkin.jpg) · [Control Room](verification/phase9-final/before-after-control-admin.jpg) · [Traces](verification/phase9-final/before-after-traces-admin.jpg) |

Reference and actual composites for every department and role are collected in [review.html](verification/phase9-final/review.html). The pass 3 "before" images were captured from the `phase9/clinical-desks` UI served with the same mock fixtures.

## Checks run

| Check | Result |
| --- | --- |
| `npm run typecheck` | PASS |
| `npm test -- --reporter=dot` | PASS: 11 files, 144 tests. Two tests were added (alias `aria-current`; modal drawer with inert workspace and Escape focus return). Several Appointments assertions were updated for the renamed tabs, row actions and readable slot names, for example "Select 09:00 am, 1 Jan 2027 (UTC)" instead of "Select slot 41". |
| `npm run build` | PASS, with no bundle-size warning. The largest chunks are `qr-decoder` at 458 kB (118 kB gzip) and `index` at 421 kB (140 kB gzip). A grep of `dist/` for mock code found nothing. |
| [Sweep](verification/phase9-final/measurements.json): 19 subjects × 4 viewports, 76 captures | **No horizontal overflow** in any capture. **Primary action ≤ 1024** at 1536 for all 19 subjects. **No unresolved text under 12px or targets under 40px**, apart from the deliberately left items below. |
| [Keyboard pass](verification/phase9-final/keyboard-results.json) on all 19 subjects | Tab order runs skip link, header, directory, then main everywhere. Every focused element shows a visible indicator. Escape closes the search dialog on desktop and the directory drawer on mobile, returning focus to the menu button. |
| Earlier passes | Pharmacy readability: minimum text 12px and contrast 5.40:1. Clinical desks: minimum text 12px and contrast 5.95:1. 12/12 and 17/17 interaction checks passed. |

## Deliberately left, and why

- **Directory captions (shared signboard).** The descriptions under each department name are 9px, or 8px in the Reception and Consultation scenes. The "GENERAL HOSPITAL" lockup is 11px. At 12px the captions wrap, which would change the directory row heights and the signboard geometry this pass was told to keep. The department names themselves are 12px or more, and each link's accessible name is the department.
- **Approved scenes: Reception, Consultation and Waiting Room.** Their wayfinding labels, profile metadata, queue labels and scene typography contain small text (8–11px), and the mobile scenes have 23 small targets (specialty buttons, inline text links, small summaries). Changing them needs separate approved-scene scope, which this pass did not have.

## Remaining gaps and unverified work

- **No real backend.** Nothing ran against the Compose stack or real accounts. Real role scopes, page sizes, error envelopes and timing may differ from the mock. The mock caps pages at 12 items.
- **Physical QR decoding is untested.** The check-in scanner was not exercised with a camera.
- **Assistive technology.** Screen-reader output, 200% zoom and touch behaviour were not tested. Contrast figures are computed, not certified.
- **Appointments**
  - Doctor portraits appear only when the local demo mapping exists, which mock mode does not supply, so rows show initials.
  - The availability API does not distinguish "booked" from other unavailable slots, so the legend says "Unavailable".
  - Location and room are omitted because no API returns them.
- **Control Room**
  - The contract has no p95 latency time series, so the p95 card has no trend arrow and the chart shows throughput and 5xx.
  - The "replica rows" inspector shows the per-service aggregates the API returns, not individual replicas.
- **Reference features deliberately absent:**
  - beds, census, staff and CCTV
  - patient photos and demographics
  - vitals, labs and imaging
  - retail medicine shopping, discounts and drafts
  - SMS confirmations and guest walk-in registration
- **Mobile tab order.** On some mobile layouts the visual order (selection first) differs from DOM order, which is kept for desktop keyboard order.
