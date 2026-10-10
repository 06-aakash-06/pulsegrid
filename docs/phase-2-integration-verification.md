# Phase 2.9 integration and verification

Work in progress, 2026-10-11. Synthetic single-hospital prototype. Common base `de63867adb7f5863c708ee19f4376ccbb49a0691`. This report records executed checks; incomplete checkpoints are not completion claims.

## Checkpoint A: integration complete

Initial main was clean at the common base. All eight source commits existed locally, descended from that base and changed only their assigned service/frontend prefixes. Reviewed route/dependency/migration changes and parsed Python syntax before applying. Every cherry-pick completed without conflict, expected files were present and status was clean after each. Original branches and worktrees were neither modified nor deleted.

| Domain | Original SHA | Cherry-picked main SHA |
|---|---|---|
| Patient | 280b4e3bdb7d39faf2fb9137cb61da0543f3305d | 71bb99710f6eddc9f34c412524c3d8a3023829dc |
| Doctor | a09b16d4e5bb70c15ea6f095e580cf9dc3ad0e56 | d678f0fc8a43fba4fe9a42f35fac5c1639aa7c78 |
| Appointment | 60161d12ae2263ab19e855c81fa43cd522f3d5fc | fed08f6763d85dfaac737fecaf67bdfcb748713a |
| Records | a1fca50144103e7019a30eabe0d3befa8d0a79f6 | 225efbf28baec73eab29c7576b57d7844d872998 |
| Pharmacy | a6931a100e3dbbdddb147e5cb115b3c3d622c00d | 081410a114d0cc8107e1ed6eb040a22b61e6596b |
| Billing | 7f490f9d688248fd1e057082d2332ddfa53cd3f9 | fdc1b6fd6560df5c2f96646cd311b6e97c649d84 |
| Emergency | 8917af46c09f599bae6ca2ba3b86be5e24d2e09e | 344f163ef490484947b6948c3117d259c66cce6a |
| Frontend | e700170d9dd62501a5244f6fd738e4e004bf1d8b | 48a8fe1fee4178d4df7d04c268515d03c9d1b483 |

## Integration fixes so far

- Emergency agent introduced a custom Snowflake allocator despite Phase 2 exclusions. Replaced runtime allocation with bounded positive CSPRNG candidates and local uniqueness checks; retained schema/history without destructive cleanup. Added two regression tests.
- Combined backend collection exposed service-local test imports and namespace collisions. Relative imports, test package markers and root pytest namespace/importlib settings allow all 452 current tests to collect together.
- Existing cross-service authorization regressions exposed changed timeout status in Appointment/Records and malformed authority JSON being treated as a permission denial in Pharmacy. Restored Phase 1 fail-closed authority timeout 503 and invalid-response 503. Targeted authorization/ID run: 160 passed.
- Contract clarification documents Records' owned PostgreSQL sequence as an internal allocator choice without changing decimal-string IDs; no custom Snowflake is active.

## Environment and preliminary checks

Existing Colima VM was stopped. Started that same VM with 4 CPUs/6 GiB, without changing or removing persistent volumes. Existing PulseGrid Compose containers resumed healthy. Before migration, Patient contained 17 users, 29 refresh rows and 84 audit entries; later preservation verification must account for added synthetic test identities.

Docker build initially stalled in the user's desktop credential helper. A temporary credential-free Docker client configuration for public image pulls uses the same Colima socket; the user's Docker configuration was not changed. Images are rebuilt sequentially to bound memory use. No duplicate Compose stack is created.

Frontend initial `npm run typecheck`, `npm test`, `npm run build`: passed, 85 tests in four files. These are local UI regressions/build, not browser or live compatibility proof.

Initial backend combined run after collection correction: 357 passed, 92 skipped, 3 failed (authority regressions listed above). A disposable PostgreSQL runner now provisions separate throwaway test databases; agent tests that truncate tables never target Compose's persistent databases. Records/Appointment retain their separately isolated fixtures. Full corrected counts are pending.

## Remaining checkpoints

B migrations, C live services/private communication, D complete regressions, E real gateway workflows/concurrency/security, F browser verification are pending. No Phase 2 completion claim yet.

## Scope and limits

No waitlists, QR/check-in, live queues, automated journeys, distributed caching/hashing, custom Snowflake, URL shortening, insurance crawling, trie, surge, chaos or control-room implementation. REST validation, explicit clinical holds and manual charge import remain the Phase 2 workflow. Outbox rows are durable but RabbitMQ publication/consumption is not implemented. No global transaction, instantaneous remote prescription revocation, complete-charge coverage from a paid invoice, clinical certification or infrastructure HA is claimed.
