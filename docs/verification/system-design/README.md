# System Design Lab verification — 2026-10-25

## Result

PASS: typecheck, 193 tests, production build, three layout-audit viewports and three complete eight-step guided tours. The earlier sandbox restrictions were removed later in the session; these successful browser runs replace the initial blocked result. No Docker or backend was started.

## Screenshots

| Width | Layout audit | Guided tour |
|---|---|---|
| 1536 | [Full page](after/system-design-1536.png) | [First step](system-design/step-01-1536.png) |
| 1280 | [Full page](after/system-design-1280.png) | [First step](system-design/step-01-1280.png) |
| 390 | [Full page](after/system-design-390.png) | [First step](system-design/step-01-390.png) |

Every tour step has a screenshot in `system-design/`. Desktop and mobile full-page images were inspected. The layout audit found no text-size, overflow, overlap or covered-control issues. Engineering terms/large numbers are justified content on this route. Its standalone layout has no drawer; the audit returns to the admin workspace to verify sign-out and reload.

## Checks actually run

| Check | Result | Evidence |
|---|---|---|
| `npm run typecheck --prefix frontend` | PASS | `typecheck.txt` |
| `npm test --prefix frontend` | PASS: 193 tests, 18 files | `tests.txt` |
| `npm run build --prefix frontend` | PASS | `build.txt` |
| `git diff --check` | PASS | No whitespace errors |
| Fresh whole-change review | Completed; important findings fixed | Details below |
| `npm run dev:mock --prefix frontend` | Running at 127.0.0.1:5175 | Existing ports 5173/5174 were occupied; the initial blocked-start log remains as historical evidence |
| Fix 1 Playwright audit at 1536/1280/390 | PASS: 3 cases, zero findings | `ui-audit-output.txt`, `audit-report.json`, `after/` |
| `system-design` tour e2e at 1536/1280/390 | PASS: 8 steps at each width | `tour-e2e-output.txt`, `system-design/` |

## Implementation and review

- `/system-design` uses eight cream/teal cards, shared PageHeader/PageGrid, 12px minimum lab text, accessible controls, desktop columns and mobile stacking.
- Header access for all signed-in roles and demo mode; Admin/Ops links; Simulation Mode picker and role-neutral tour.
- All lab figures live in `frontend/src/systemDesign/measuredResults.ts`. Source documents are emitted as assets. Short-link figures explicitly describe adapter/fake-port conditions and partial authenticated high-concurrency endpoint verification.
- SHA-256 hash ring matches backend framing, full digest and clockwise lookup with 128 virtual nodes. Browser remap compares the same ten thousand keys with modulo.
- Fixed-point token bucket matches the single-replica integer Surge floors. It models one bucket, not shared Redis coordination.
- Snowflake uses the implemented epoch, service/replica partition and sequence-overflow wait, with actual collision/order checks. Browser allocation does not claim durable worker ownership or restart protection.
- Trie/linear scan uses generated data, alternating batches and median timing; the lab baseline was sorted-prefix rather than SQL.
- Random Base62/digest, local TTL cache, validated synthetic fixtures, conflict quarantine and illustrative blocked cross-database join/outbox path.
- API buttons use ordinary authentication. Link creation reads its workflow ETag and sends the real `appointment` purpose plus idempotency. Permission/unavailable responses remain explicit.
- Review fixes included budget floors, spotlight-compatible tour instructions, adapter-only provenance and intermediate-width header spacing. Existing conditional tour-target scan and admin navigation inventory were corrected.

## Local integration

`feature/simulation-mode` merged into `ui/cleanup` at `db341b1`; `feature/system-design-playground` at `414f827`. Post-merge typecheck, 193 tests and build passed. The user subsequently authorized pushing to GitHub and redeploying; browser evidence was completed before publication.

## Remaining limits / omitted spec items

1. `UI_SIMULATION_SPEC.md` and section 11/team split were not attached in the accessible workspace. The corrected user brief is the implementation specification. `docs/system-design-lab-script.md` therefore uses explicitly provisional Presenter 1–4 assignments rather than claiming the unavailable team's exact split.
2. The dev mock has medicine autocomplete and Control Room data, but lacks doctor-autocomplete and short-link creation handlers. Those buttons call the existing backend contracts and show the unavailable mock response. No backend was started or endpoint performance remeasured.
3. Stampede locks, custom aliases, click counters, Redis link caches, crawler robots/ETag fetches and sharding are excluded because the repo does not implement them.

## Re-run

Keep `npm run dev:mock` running from `frontend/`, then use its reported port:

```bash
UI_AUDIT_URL=http://127.0.0.1:5175 UI_AUDIT_ROLES=admin UI_AUDIT_ROUTES=/system-design UI_AUDIT_OUTPUT=../docs/verification/system-design npm run ui:audit
TOUR_E2E_URL=http://127.0.0.1:5175 TOUR_E2E_ROLES=system-design TOUR_E2E_OUTPUT=../docs/verification/system-design npm run tour:e2e
```
