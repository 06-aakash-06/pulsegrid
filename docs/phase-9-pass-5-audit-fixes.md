# Pass 5 audit fixes — continuation on 25 October 2026

Worktree: `pulsegrid`, branch `phase9/audit-fixes`, descended from `phase9/ui-refresh`.

The interrupted run ended after Part D (`6bfd320`). Parts A, B and C were already committed as `7a4e0ad`, `1f39765` (assertion follow-up `067741f`) and `100b20e`. The continuation adds Part E (`3f1a3c2`), Part F (`b1935b8`), Part G (`143acab`) and Part H with verification-discovered follow-ups.

## Verification boundary

The implementation and automated checks are complete. The requested visual acceptance gate is **not verified**. No Docker, backend or push was used.

`npm run dev:mock -- --port 5199` failed with `listen EPERM: operation not permitted 127.0.0.1:5199`. Both the reused full `sweep.js` and `act.js` failed at Chromium launch (`SIGABRT`, process operations denied). They did not produce a new sweep. There are no new screenshots or measured geometry/contrast results. Do not interpret source changes as proof of zero critical/major findings.

The retained `/tmp/pulsegrid-audit/sweep.json` has 35 routes × 5 viewports = 175 page observations and 3,865 raw flags, including 1,881 tiny-text flags. It does **not** assign critical/major/minor severity. Counts therefore are:

| Measure | Before | After |
| --- | --- | --- |
| Critical / major / minor | Not classified in saved sweep | Not measurable: browser execution blocked |
| Raw sweep flags | 3,865 across 175 observations | Not measured |
| Visible tiny text | 1,881 flags | Not measured; static scan finds zero literal font-size declarations below 12px |
| Frontend tests | 145 at continuation start | 150 passing |
| TypeScript | Passing at continuation start | Passing |
| Production build | Previously passing | Passing; no `dev-mock` matches in `dist/` |

Logs on this machine: `/tmp/pulsegrid-audit/final-tests.log`, `final-build.log`, `final-sweep.log`, `final-flows.log`. The prior `sweep.json` was preserved.

## Item status

“Fixed” describes an implemented behavior supported by source review and/or automated tests. “Partially fixed” identifies layout changes that need browser acceptance, or a stated API limitation. No visual measurements are implied.

| Item | Status | Evidence or remaining limit |
| --- | --- | --- |
| A1 Finalize refresh / optional prescription ID | Fixed | Register and dossier refetch; regression checks two Finalized badges and absence of Draft. |
| A2 Check-in states and manual fallback | Fixed | Already-checked-in state, calm window explanation, tokenless supported command and checkable fixture retained from Part A. |
| A3 Remounts / receipts | Fixed | Stable selection keys and lifted flash state; tests cover import, claim, priority, release, cancellation and reschedule confirmations. |
| A4 Booking and walk-in slot reset | Fixed | Clears selection, reloads availability, disarms review and offers Book another. Disabled Booked marker uses actual successful receipt; available API slots remain authoritative. |
| A5 Emergency reset | Fixed | Test checks cleared description, default urgency and visible receipt. Register refreshes after creation. |
| A6 412 reload control | Fixed | Conditional commands use resource reload context or explicit reload, including appointment reload/reset. |
| A7 Emergency order / Closed | Fixed | Priority and age sort tests; rendered Closed divider tested. |
| A8 Today's visits in UTC | Fixed | UTC calendar-day filtering, empty-today message and next visit. |
| A9 Latency contradiction | Fixed | Value/no-data determines detail text. |
| A10 Admin directory | Fixed | Every admin route and aria-current tested. |
| B Sidebar laptop tier | Partially fixed | Number, icon, wrapping name retained; subtitles/arrows hidden. Needs 1024px measurement. |
| B Billing invoice cards | Partially fixed | Visit hidden and labelled card rows below 1200; needs overflow measurement. |
| B Emergency two-column desk | Partially fixed | Queue left, case/steps right, wrapping header, growing count boxes; needs screenshots. |
| B Pharmacy two-column shelf | Partially fixed | Two bays below 1100; two-line medicine labels have full title. Needs screenshots. |
| B Prescription paper | Partially fixed | Counter stacks below 1200, drug column minimum retained. Needs measured width. |
| B Reception laptop slips / robot bubble | Partially fixed | Two rows below 1300, token stand repositioned, bubble auto height. Needs visual acceptance. |
| B Control Room laptop | Partially fixed | Ready text stays together; alert list scrolls within card. Needs geometry check. |
| B Phone fulfillment / fixed heights | Partially fixed | Touched panels use natural height, no capped prescription list on phones; needs phone screenshot. |
| C Patient reservation action / quantities | Partially fixed | Panel grows and form remains outside capped history; needs visual reachability check. |
| C Pharmacist dispense first / paging | Partially fixed | Dispense primary, secondary actions separated, natural panel height; needs screenshots. |
| C Booking / walk-in slip position | Partially fixed | Receipt in side position; needs measured fold/phone layout. |
| C Doctor sticky finalize | Partially fixed | Sticky dossier action bar retained; 1536px reachability not remeasured. |
| C Reservation review step | Fixed | Explicit review/confirm flow retained. |
| C Medicine handoff | Fixed | Selected medicine carried in route query and consumed by dispensing workspace. |
| D Compact doctor/admin medicine catalogue | Fixed | Visual cabinet replaced on these routes; patient/pharmacist cabinet retained. API has name/SKU, no separate form/strength fields to invent. |
| D Cabinet signage / contrast | Partially fixed | Spaced catalogue signage with ink on light surface; contrast not measured. |
| D Prescription authoring above fold | Partially fixed | Prescription tools precede catalogue; first action links to consultation authoring, which owns the finalize API. Fold not measured. |
| E Popover Escape / outside dismissal | Fixed | Tests both popovers and trigger-focus restoration. |
| E Search input focus | Fixed | Explicit focus after showModal, including keyboard shortcut. |
| E Drawer navigation focus | Fixed | Navigation closes drawer and schedules main focus after inert removal. |
| E Header inset | Fixed | 24px desktop inset shared across departments; existing phone inset retained. |
| E Directory numbering | Fixed | Consecutive rendered positions; admin test checks 01–06. |
| E Direct-load header identity | Fixed | Layout fetches patient/doctor owner profile once per mounted layout. Staff without a display-name owner endpoint retain truthful role labels. |
| E Photo headings / QR | Partially fixed | Shared frosted heading surface with ink text; needs screenshot/contrast check. |
| E Trace footnote | Fixed | Inside selected-trace card, frosted surface and ink. |
| E Minimum text | Partially fixed | --text-min:12px and all literal sub-12px font declarations replaced. Computed visible-text sweep remains blocked. |
| E Phone touch targets | Partially fixed | Disclosures/buttons/week controls have 40px minimum; needs computed target sweep. |
| E Disclosure chevrons | Fixed | Native disclosure markers restored; account menu retains its explicit chevron. |
| E Truncation / search placeholders | Fixed | Full titles on medicine/emergency/trace/doctor names and search controls; shorter placeholders. |
| E Read-only email | Fixed | Booking contact uses a wrapping text block. |
| F Human CommandForm labels | Fixed | Explicit review/confirm/success labels retained at command call sites. |
| F Shared date formatter | Fixed | Full timestamp displays use UTC helper, including insurance, links, traces and stock expiry; calendar/day/time-only labels remain compact. |
| F Remove dev wording | Fixed | User-facing paise/workflow/debug copy removed, advisory urgency humanized, Surge reasons humanized. |
| F Distinct reasons | Fixed | Starting/releasing/priority/cancellation reasons are distinct. |
| F Reception and staff labels | Fixed | Receptionist Appointments and admin Staff & roles. |
| F Missing confirmations | Fixed | Import, claim, priority, release, reschedule and cancel success assertions. |
| F Hide unauthorized admin schedule | Fixed | ScheduleRail returns nothing without an authorized destination. |
| F Cancelled doctor switch | Fixed | Doctor-switch disclosure only on confirmed appointments. |
| F Booking form padding | Fixed | Booking section has padding. |
| F Roster scroll hint / compact date | Partially fixed | Scroll hint added and availability line kept together; needs geometry validation. |
| F Consumers header | Partially fixed | Header can wrap; needs 1536px screenshot. |
| F Insurance providers mock | Fixed | Authorized handler returns explicit empty synthetic list; no fabricated provider records. |
| G Consultation avatar | Fixed | Teal initials fallback, preserving existing portraits. |
| G Doctor week / today's slots | Fixed | Shared week/calendar grids, availability auto-load. |
| G Empty shelf rows | Fixed | Grid creates only occupied tiers. |
| G Emergency rows / counts / steps / gap | Partially fixed | One-line titled name, priority right, frosted counts, real action buttons, no forced case minimum. Needs screenshot. |
| G Records timeline type | Fixed | Neutral date chip because record summary supplies no visit type. |
| G Control Room icons / trends / empty space | Partially fixed | Icons and computed available-series trends; main aligns to content. No invented latency/backlog series. Needs geometry review. |
| G Waiting Room | Partially fixed | Light live panel, shared heading alignment, kiosk grounded by grid alignment. Needs screenshot. |
| G Billing action bar / tabs | Partially fixed | Strong payment bar and icon tiles with phone stacking. Needs screenshot. |
| H1 Two original failures | Fixed | Relative date and inline past-date validation; stable request key, Surge tests pass. |
| H2 Regression coverage | Fixed | Finalize, slot clear/reload, emergency reset/order, header dismissal and full admin directory covered. |
| H3 Typecheck / tests / build / mock isolation | Fixed | Typecheck, 150 tests, build and empty dev-mock search. |
| H4 Full sweep / click-through / zero critical-major gate | Not fixed | Attempted reused scripts; sandbox blocks Vite listener and Chromium launch. Acceptance counts cannot be asserted. |
| H5 Logical commits / no push | Fixed | Local part commits; nothing pushed. |

## Additional findings addressed

- A staff subroute CSS rule still hid directory entries despite correct navigation data; all staff subroutes now render.
- The week strip contains a calendar child wrapping seven buttons, so its outer grid needs three columns, with seven columns inside the calendar.
- A mount effect in Emergency Next steps could close an action opened immediately after mount. Action selection now carries its workflow identity; real state/claim changes invalidate it without a mount reset.
- Successful booking slots disappear from the availability response. A disabled marker now comes from the confirmed receipt rather than inventing an API slot state.
- Four additional 6–7px reception declarations remained after replacing the 8–11px values; they now use the minimum token too.
- Identity publication test now waits for React effects to settle before asserting external-store updates.

## Resume visual verification

From `pulsegrid`:

```sh
cd frontend
npm run dev:mock -- --port 5199
```

Then, in a shell that permits the browser and local listener:

```sh
cd /tmp/pulsegrid-audit
node sweep.js > final-sweep.log 2>&1
node summarize.js ./sweep.json
```

Reuse `act.js` for booking, check-in, reschedule/cancel, finalize, priority/claim/release, billing import and reservation/dispense review flows. `sweep.js` writes `sweep.json`, so preserve the original baseline before rerunning. Recheck 390×844 and 1024×768 especially, plus 1280×800 reception and 1536×1024 consultation/Control Room.

Routes worth clicking: `/patient/appointments`, `/patient/check-in`, `/patient/pharmacy`, `/emergency/requests`, `/doctor/consultations`, `/doctor/prescriptions`, `/pharmacist/prescriptions`, `/admin/staff`, `/admin/control-room`, `/billing/insurance`. Use the matching `role@mock.test` account with any password.
