# System Design Lab verification — 2026-10-25

## Result

Implementation and automated unit/component checks pass. Visual acceptance is **not complete**: the sandbox prevents both binding the requested dev server and launching Playwright Chromium. There are **no screenshots** in this evidence set and no claim that the page/tour passed at any viewport.

## Implemented

- `/system-design`: eight cream/teal cards, shared PageHeader/PageGrid, 12px minimum lab text, keyboard-accessible controls, two columns with mobile stacking.
- Header access for every signed-in role and mock/demo mode; Administration and Operations sidebar links; Simulation Mode picker entry and an eight-step `system-design` tour.
- Measured figures only in `frontend/src/systemDesign/measuredResults.ts`, with lab workload caveats and source document paths. Source files are emitted as build assets; Vite's filesystem allowlist includes only the frontend and docs directories.
- Browser SHA-256 ring (128 virtual nodes, full digest, matching backend framing, clockwise lookup, actual ten-thousand-key ring/modulo remap, add/remove and key lookup).
- Fixed-point token bucket with capacity/refill/burst controls and real class A/B/C Surge factors, integer budget truncation and the backend's single-replica minimum floor. This models one bucket; it does not claim shared Redis coordination.
- Snowflake packing from the implemented epoch, service/replica worker split, sequence exhaustion wait, rollback rejection, actual collision and ordering checks. Browser allocator does not claim durable ownership/restart safety.
- Generated-data trie vs linear scan with alternating repeated batches and median lookup timings. Index preparation is excluded; the recorded lab baseline was sorted-prefix, not SQL.
- Random Base62 token/digest generation; local TTL cache; synthetic crawler validation/deduplication/quarantine; seven ownership tiles and an illustrative blocked join/outbox path.
- Authenticated API buttons for doctor/medicine autocomplete, directory reads, Control Room summary and appointment-link creation. Link creation uses current workflow ETag, the real `appointment` purpose, idempotency and the ordinary authenticated client. API permission and unavailable errors are displayed; no fabricated fallback result.
- Three-minute script: `docs/system-design-lab-script.md`.

## Local integration

Merged `feature/simulation-mode` into `ui/cleanup` at `db341b1`, then `feature/system-design-playground` at `414f827`. Both are ancestors of the review branch; no push or deployment. Re-ran typecheck, all 193 tests and production build on the merged tree successfully. The saved passing logs are from this post-merge run.

## Checks actually run

| Check | Result | Evidence |
|---|---|---|
| Initial algorithm test before implementation | Failed on missing module as expected | Execution history; followed by passing implementations |
| Algorithm + source provenance + widget interactions | 16 passed | Included in full suite |
| `npm run typecheck --prefix frontend` | PASS | `typecheck.txt` |
| `npm test --prefix frontend` | PASS: 193 tests, 18 files | `tests.txt` |
| `npm run build --prefix frontend` | PASS | `build.txt` |
| `git diff --check` | PASS | No whitespace errors |
| Fresh whole-change review | Completed; important findings fixed | See review fixes below |
| `npm run dev:mock --prefix frontend` | BLOCKED before serving | `dev-mock-output.txt`: listen EPERM on 127.0.0.1:5173 |
| Fix 1 Playwright audit, lab route, widths 1536/1280/390 | BLOCKED before any page executed | `ui-audit-output.txt`: Chromium MachPort bootstrap permission denied |
| `system-design` tour e2e, widths 1536/1280/390 | BLOCKED before any tour executed | `tour-e2e-output.txt`: same Chromium sandbox failure |

The audit retains layout/text-size/overlap/hit-target checks. Engineering words and large numbers are explicitly justified on this educational route rather than classified as accidental implementation leakage. There is no sidebar/drawer on the standalone lab route, so that route skips drawer-only checks. Tour harness signs in as Patient for the role-neutral lab tour, then runs the existing spotlight/card checks.

## Review fixes

- Ported the backend's fixed-point refill and small-budget floor rather than allowing fractional capacities below one token.
- Tour text asks only for controls that its spotlight permits; the remaining sibling controls are explicitly offered after the tour.
- Short-link lab figures explicitly identify adapter/fake-port conditions and partial authenticated high-concurrency endpoint acceptance.
- Hide the header tagline through intermediate widths to reserve space for the new link; this is inspected code, **not visually verified**.
- Existing target-discovery test now handles conditional `data-tour` literals; admin navigation inventory includes the new seventh link. jsdom's missing scrollBy is stubbed like scrollTo.

## Unavailable or deliberately excluded

1. `UI_SIMULATION_SPEC.md` was not attached in the accessible workspace or found under the SystemDesign folder. The user's full corrected prompt is the implementation specification. The presentation script uses clearly provisional Presenter 1–4 allocations because section 11 and its exact team split could not be read; no team names or assignments were invented as authoritative.
2. No screenshots, responsive visual approval, browser timing samples or tour e2e success: host sandbox denies local listening and Chromium's required MachPort access. Approval escalation is disabled in this session. Re-run the commands below in an ordinary local terminal.
3. Existing dev mock provides medicine autocomplete and Control Room data, but has no doctor-autocomplete or short-link creation handler. Their buttons still call the real backend contracts and display the unavailable response in mock mode. Backend endpoint behavior was not verified here, and no backend was started.
4. Stampede locking, custom aliases, link click counters/Redis link caching, crawler robots/ETag fetches, and sharding are excluded because the repo does not implement them. Browser demos explicitly disclose their teaching scope.

## Re-run visual acceptance

From `frontend/`, keep `npm run dev:mock` running in one terminal, then run:

```bash
UI_AUDIT_ROLES=admin UI_AUDIT_ROUTES=/system-design UI_AUDIT_OUTPUT=../docs/verification/system-design npm run ui:audit
TOUR_E2E_ROLES=system-design TOUR_E2E_OUTPUT=../docs/verification/system-design npm run tour:e2e
```

Audit screenshots will be saved under `after/`; tour screenshots under `system-design/`. Both harnesses cover 1536, 1280 and 390 widths. Docker and backend are unnecessary. No push is part of this work.
