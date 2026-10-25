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
- [ ] Add algorithm tests, observe import failures, implement ring/token bucket/Snowflake/trie and ancillary demonstrators; verify unit tests; commit.
- [ ] Add measured registry sourced from phase 4, phase 6 and phase 8.2 docs; implement cards and functional visuals; source-integrity/render tests.
- [ ] Add route/header/admin+ops links and system-design tour/picker entry; extend audit/tour harnesses for lab.
- [ ] Write three-minute four-presenter script and verification report, noting unavailable original team split.
- [ ] Run dev:mock, layout audits at 1536/1280/390, tour e2e and functional checks; inspect screenshots; typecheck/test/build; commit.
- [ ] Review final diff, merge both authorized feature branches into ui/cleanup locally, verify clean tree and no push.
