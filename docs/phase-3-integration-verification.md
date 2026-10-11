# Phase 3 integration and verification

In progress, 2026-10-11. Synthetic single-hospital prototype. Phase 3 is **not complete** until checkpoints B–J and the frozen/extended acceptance gates pass. Coordinator now owns sequential integration fixes following final agent commits; original branches/worktrees are preserved.

## Checkpoint A: source integration

Initial main clean at `b7f74cb9f47b764989d2540695b4ed05ed8c1b28`. All supplied objects exist. G0 source `20debbf` was already integrated as `b7f74cb`, with identical tree; it was not applied twice. All seven G1 commits directly descend from b7f74cb. Ordered cherry-picks were conflict-free:

| Module | Original | Integrated main |
|---|---|---|
| G0 | 20debbfa679b60ff3fe749d3d9103415e2819e13 | b7f74cb9f47b764989d2540695b4ed05ed8c1b28 |
| Waitlist | 0d661b1fd6565095d6faed1a500336b5c5535d7f | ccabd32 |
| Queue | 336594a053cdb690998dccb995a6b3eab38d304e | b23ecce |
| Check-in | ce4ef78b230561ab30098afa290c399b15ffad17 | ac876d1 |
| Journey | e6bf4d9873ded822c7fb2829510f199f55242bbc | 348360a |
| Records/Pharmacy | e6d66e4f2619b1ab2ff78b0cf544f804fead6003 | 495ca2c |
| Patient frontend | a71cf8d4d7af4fef93caa84eae8b2674b53a84e4 | 5da7127 |
| Staff frontend | 167876c88c0799497b9b932e43cfcafee509095a | 217a531 |

Reviewed handoffs, schema manifests, runtime interfaces and ownership. Staff UI uses `frontend/src/hospital/staffAdvanced` and `frontend/tests/staff-advanced` instead of the reserved paths; these are isolated new files with no overlap, preserved at user-requested integration. No agent/worktree was reset or overwritten.

Frontend typecheck and tests pass: 107 tests in six files. Appointment integrated regression suite passed: 174 tests, including PostgreSQL tests. The suite uses isolated temporary PostgreSQL databases, never development databases. Compile and diff checks accompany checkpoint commits.

## Open integration work

- Implement reviewed 0005–0008 forward chain; retain prior data and preflight dormant rows.
- Explicitly extend G1 freeze for durable temporary waitlist offers/accept/decline/expiry and queue skip/recall. Existing G1 implemented neither.
- Resolve queue allocator/check-in duplicate workflow update; supply complete doctor/day lock discovery.
- Complete journey list/history/reconciliation/discharge/worker and authoritative Patient/Billing leaves.
- Wire owner scopes/Records gate, feature registration/lifecycle hooks, frontend QR encoding/scanning/forms and real existing Compose stack.
- Execute full regressions, concurrency, gateway workflows and browser verification. No claims of these gates passing yet.

No Phase 4 algorithm, RabbitMQ business delivery, predictive scaling, redesign or push. Final SHA and clean status are reported after final verification commit rather than embedded into their own commit.
