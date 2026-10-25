# System Design Lab Implementation Plan

**Goal:** Build the eight-card lab specified in the user's PulseGrid prompt 5, explaining the seven implemented components and database isolation.
**Architecture:** Small browser algorithm modules; a single measured-results registry with document provenance; shared card rendering; existing header, grid and simulation engine. Authenticated API calls retain owner permissions.
**Tech stack:** Existing React, TypeScript, CSS, Vitest and Playwright. No dependencies, backend or Docker.
**Spec:** User's prompt 5 and mandatory corrections. UI_SIMULATION_SPEC.md was not attached in the accessible workspace; presenter names/team allocation cannot be recovered from it.

## Constraints and review focus
- Keep browser timings separate from lab measurements. No invented gains, aliases, cache locks, crawler robots/ETags or sharding.
- Hash ring uses the Python component's SHA-256 framing, full digest, 128 virtual nodes and clockwise lookup.
- Snowflake uses the implemented epoch/layout, rejects rollback, handles sequence overflow and validates worker allocation.
- Guard input sizes and pending runs; preserve accessible controls at mobile width.
- API actions retain authentication, ownership, ETags and idempotency. Mock responses must be labelled.
- Source links must work in development and built output.

## Tasks
- [x] Add algorithm tests, observe import failures, implement ring/token bucket/Snowflake/trie and ancillary demonstrators; verify unit tests; commit.
- [x] Add measured registry sourced from phase 4, phase 6 and phase 8.2 docs; implement cards and functional visuals; source-integrity/render tests.
- [x] Add route/header/admin+ops links and system-design tour/picker entry; extend audit/tour harnesses for lab.
- [x] Write three-minute four-presenter script and verification report, noting unavailable original team split.
- [ ] Run dev:mock, layout audits at 1536/1280/390, tour e2e and functional checks; inspect screenshots; typecheck/test/build; commit.
- [ ] Review final diff, merge both authorized feature branches into ui/cleanup locally, verify clean tree and no push.

## Execution record
- Algorithms observed failing at missing imports, then passed; added fixed-point refill and single-replica Surge floors after reviewing policies.py.
- Full test suite at first UI pass: one expected admin-navigation inventory failure; updated inventory to include the authorized seventh lab link. Subsequent suite passed 186 tests before adding seven widget interactions.
- Corrected existing simulation target scan to include conditional data-tour literals, and stubbed jsdom scrollBy like the existing scrollTo stub.
- Fresh reviewer checked backend parity, provenance, API contracts, tours and responsive risks. Fixed small-bucket floor; tour wording now only requests controls permitted by its spotlight. Clarified adapter-only link figures and reduced header crowding at intermediate widths.
- Ruling: original UI_SIMULATION_SPEC.md/team split is unavailable; use the full corrected user brief and explicitly provisional presenter assignments rather than inventing names or claiming a match.
- Browser execution is blocked: localhost listen EPERM and Chromium MachPort permission denied. No visual pass or screenshot is claimed.
