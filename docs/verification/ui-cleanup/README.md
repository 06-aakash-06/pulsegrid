# PulseGrid shell cleanup

Fresh `main` base: `5c64ece`. Local branch: `ui/cleanup-shell`. Node: 24.22.0.
Only the `pulsegrid-ui` checkout was used. No backend, Docker, push or deployment was run.

The shared layout now supplies a 256px directory, a 1280px content limit, solid cream surfaces, a 12px card radius, the requested spacing scale and one page-header component. `PageGrid` provides single-column, 8/4 and 3/6/3 presets. Page-level coordinate positioning no longer controls forms, slips or supporting panels. The existing room photos and angled directory frame remain.

Every role uses the same numbered navigation row, with single-line labels, subtitle tooltips, white active text, internal scrolling and a separate footer. The mock indicator lives in that footer. Reception/Admin registers use the available width until a record is selected. Consultation finalization flows after the draft fields. Control Room charts follow topology directly, independently of the height of the side panels.

Appointment tabs have separate untransformed hit boxes. Sign-out revokes local access immediately and waits for cookie revocation before navigating; the browser demo clears its separate stored session before waiting for fixture latency. API paths, request bodies, role gates, ETags, If-Match, idempotency keys and command review/confirmation handlers were retained.

## Reproduce

From `frontend/`, use Node 24, run `npm ci`, then start `npm run dev:mock`. In another terminal:

```sh
npm run typecheck
npm test
npm run build
npm run ui:audit
npm run build:demo -- --outDir dist-demo
npm run ui:regressions
```

`ui:regressions` serves the compiled demo assets through Playwright request interception on the existing mock-server origin; it does not start another server or backend. It tests all eight demo buttons and immediate-reload sign-out in both development and the compiled `VITE_DEMO_MOCK` bundle.

The audit discovers all sidebar routes after signing in as each of the eight mock roles. It checks 1536×864, 1280×800 and 390×844, including each mobile drawer. It uses text-node ranges against their nearest painted/bordered ancestor, clipping-aware intersections between unrelated visible cards/controls, centre-point hit tests, horizontal page overflow, and visible text below 12px. Intentional local scrollers and ellipsis are respected; the drawer scrim is an intentional overlay, with navigation hit tests confirming that the drawer is above it.

Background checks require a fixed, inset-zero cover photo and compare rendered background pixels at three document scroll positions, with content hidden temporarily for sampling. A 1% raster tolerance avoids false failures from isolated pixel rounding. The check rejects a flat raster or a changed backdrop. Full-page screenshots capture all content; fixed layers may flatten outside the initial viewport in Chromium's full-page capture, so the three actual viewport raster samples are the continuity check.

Playwright uses Chromium under `/opt/pw-browsers` when available, otherwise its managed Chromium (`npx playwright install chromium`). Optional filters: `UI_AUDIT_ROLES`, `UI_AUDIT_WIDTH`, `UI_AUDIT_ROUTES`; `UI_AUDIT_OUTPUT` selects a separate evidence directory. The default run audits the complete matrix and exits nonzero on any violation.

## Results

- `npm run typecheck`: passed.
- `npm test`: 162 tests passed across 13 files.
- Normal production build and `VITE_DEMO_MOCK` build: passed. The demo build retains Vite's non-fatal bundle-size notice.
- Complete audit: 105 route/viewports passed, zero failures (35 routes × three sizes), including every mobile drawer.
- Final shared-card styling of lazy-loaded Operations panels: all 24 Admin/Ops route/viewports rechecked, zero failures. Their screenshots were refreshed from this run.
- Both development and compiled-demo regressions: all eight account buttons fill both fields; sign-out survives immediate reload.
- `git diff --check`: passed.

## Evidence

- [Complete audit output](audit-output.txt)
- [Machine-readable route results](audit-report.json)
- [Final Admin/Ops output](final-operations-output.txt) and [route results](final-operations-report.json)
- [Typecheck, tests and both builds](check-output.txt)
- [Development and compiled-demo regressions](regression-output.txt)

Baseline screenshots were captured from the untouched base before the shared shell changes. All screenshots use synthetic fixtures.

| Page, 1536×864 | Before | After |
| --- | --- | --- |
| Reception | [Before](before/reception-1536.png) | [After](after/patient-dashboard-1536.png) |
| Appointments | [Before](before/appointments-1536.png) | [After](after/patient-appointments-1536.png) |
| Doctor consultations | [Before](before/doctor-consultations-1536.png) | [After](after/doctor-consultations-1536.png) |
| Pharmacist | [Before](before/pharmacist-1536.png) | [After](after/pharmacist-dashboard-1536.png) |
| Admin | [Before](before/admin-1536.png) | [After](after/admin-dashboard-1536.png) |

The `after/` directory also contains every other route at all three sizes and a drawer capture for every mobile route.

## Live demo check

On 25 October 2026, a Chromium mouse click on the Patient demo button at <https://pulsegrid-ruddy.vercel.app/login> filled `patient@mock.test` and `demo`, with no browser errors. The published bundle contains the browser-demo entry and demo account UI. The reported autofill failure did not reproduce on the currently served deployment.

The public bundle cannot establish the exact deployed Git revision or the dashboard's environment-variable configuration; those require authenticated Vercel project metadata, which was unavailable here. No Vercel settings were changed. Before a future deployment, upgrade the outdated Vercel CLI with `npm i -g vercel@latest` for current compatibility.

These checks exercise the synthetic browser interface, not backend authorization, real clinical workflows or production sessions.

## Fix 3: page polish (`ui/polish`)

Each screen's remaining defects were fixed in `frontend/src/styles/polish.css` (loaded last) plus the components that owned the markup. Reception merges the greeting and visit stats into one card and gives the four slips their own row; the queue panel shows "Not checked in yet" with a Check in button before a token exists and "Visit completed" with a summary link afterwards. Availability now loads whenever the doctor or date changes, so the "Load availability" button is gone and its tests were updated. Slot times use the one-line format "25 Oct · 14:00".

Billing cannot list a visit's finalized consultations or completed dispensings (the Records and Pharmacy list endpoints reject billing staff), so the checkbox import list was not built; the reference form moved behind "Advanced: import by reference" as the brief allows.

The doctor's Finalize section is a sticky footer inside the dossier card on screens 900px and wider. Because a sticky footer overlaps the draft fields by design, `scripts/ui-audit.mjs` now skips the card-overlap check for elements inside `[data-sticky-footer]`; the covered-control hit test still runs for every control there.

### Results

- `npm run typecheck`: passed.
- `npm test`: 165 tests passed across 14 files.
- `npm run build`: passed.
- `UI_AUDIT_OUTPUT=../docs/verification/ui-cleanup/polish node scripts/ui-audit.mjs`: 105 route/viewports (35 routes at 1536×864, 1280×800 and 390×844, including mobile drawers), zero failures. Log in `polish-audit-output.txt`, report in `polish/audit-report.json`; the audit's raw PNGs were not kept.
- `review.html`: before (`main`) and after pairs for all 35 routes at 1536px and 390px, from `review/before` and `review/after`. Rebuild with `python3 build_review.py`.
