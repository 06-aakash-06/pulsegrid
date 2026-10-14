# Phase 9 — three visual fidelity corrections

Baseline: local main `b7939a152580efab6cc5ccd2e8bc04e70e1e1d9f`, clean working tree. Single agent, no worktree. Read AGENTS, Phase 9 audit/redesign/resume documents and the existing owner integrations. Backend and persistent data remain intact.

## References and original discrepancies

Exact approved references were inspected at `/Users/aakash/Downloads/inages/`: `home.png`, `consultation.png`, `waiting room.png`, and `pharmacy.png`. They remain unchanged. Existing architecture-only WebPs are reused.

Real browser baselines at 1536×1024 are saved in `verification/phase9-fidelity/`:

- `reception-before-1536.jpg` and `consultation-before-1536.jpg`: approved composition retained; directory is a flat rectangle without a receding edge or mounting depth.
- `waiting-before-1536.jpg`: kiosk contains a calendar symbol rather than a scanner aperture; central queue is a pale table panel, and right status repeats that same pale surface. Controls and tiny queue token lack electronic-display hierarchy.
- `pharmacy-patient-before-1536.jpg`: three broad horizontal catalog tiles cover the cabinet; search occupies a separate large panel; selected medicine is an isolated detail card; the prescription counter begins below the viewport instead of integrating with the cabinet and dispensing workspace.

The current checked-in operator visit A034 supplies real token 1, position 1 and waiting state. Other patient identities are not requested. Medicine names and stock hints come from Pharmacy. No reference queue rows, stock quantities, retail prices or clinical content will be invented.

## Directory checkpoint

A shared `physical-directory` shell applies to authenticated workspaces and the public entrance. Its material faces use a trapezoid with an 18px far-edge recession (12px at narrower desktop widths), visible 7px near-edge thickness, restrained edge highlights and mounting details. Text, icons, links and hit targets remain untransformed. Existing internal navigation scrolling, role gates, route destinations and mobile focus handling remain. Hover displacement is 2px and is removed for reduced motion. Mobile retains the existing accessible drawer without the desktop perspective.

Verification and subsequent equipment checkpoints are recorded below as they complete.

Directory browser verification: nine department routes at 1536×1024 show the shared physical shell without horizontal page overflow. Reception and Consultation composition source files and the shared header were not edited. Consultation at 1440×900 and 1280×800 also fits without overflow. Mobile at 390×844 opens the existing directory drawer, focuses its first link, and Escape closes it and restores focus to the menu button. A keyboard Tab check displays a solid focus outline. Screenshots include `directory-reception-1536.jpg`, `directory-consultation-{1536,1440,1280}.jpg`, `directory-mobile-390.jpg` and the remaining department captures. TypeScript passes. Focused application/design tests pass (totals recorded in the final validation section).

## Waiting Room checkpoint

The three-part composition now contains a framed scanner aperture in the physical kiosk, a dark teal electronic queue monitor with a large owner token and real count strip, and a separate cream position display. The kiosk directly mounts the existing scanner. A validated scan follows the existing same-origin fragment landing flow, which clears the fragment and still requires authenticated review/confirmation. Existing permission, detection, cancellation and stream cleanup code remains. Manual check-in and waitlist links remain visible. No new check-in command or queue authority is introduced.

Live operator browser selected the retained checked-in visit A034 and returned token 1, position 1, waiting state, one waiting and zero in consultation. Refresh retained those owner values. A real camera request remained pending in this environment; cancellation returned the manual fallback and the manual check-in route opened its existing fields. Physical camera decoding is unverified. Receptionist workflow read returned checked_in and disabled repeat token/manual check-in; no clinical or appointment mutation was performed. Camera lifecycle tests cover late permission resolution and cleanup.

Compared `waiting-comparison.jpg` (reference/original/corrected at equal aspect ratio). The QR equipment and center display now dominate the composition. Fixed excessive kiosk height, a legacy scanner text contrast issue, scanner width spilling beyond the enclosure at 1280, and mobile kiosk density. Freshness/errors remain visible. The board only shows this patient's authorized queue entry; the reference's other people and 15-minute estimate are intentionally absent because the owner API does not authorize/supply them.

Responsive captures: `waiting-after-{1536,1440,1280,390}.jpg`, `waiting-after-mobile-full.jpg`, camera request/cancellation captures, manual check-in and receptionist workflow captures. All four widths report no horizontal page overflow. TypeScript and 56 focused application/design/patient/staff workflow tests pass. A small directory follow-up scrolls the selected row into its own navigation viewport so it remains visible on shorter laptops.

## Pharmacy recovery checkpoint — in progress

Work stopped at the user's request to resume later. The current implementation is saved as a recoverable checkpoint, not a completed visual correction.

The owner catalog now uses continuous wood cabinet bays, medicine cartons, direct autocomplete and actual availability filters. Patient Pharmacy integrates an owned prescription stand and reservation counter. Pharmacist pages retain catalog editing, batch inventory and authorized dispensing actions; secondary fulfillment uses a prescription stand and receipt composition. Medicine names and quantities are read from owner APIs, with technical references kept secondary. Existing Records layouts retain their default behavior outside the pharmacist compact view. No retail prices, stock values or backend business rules were invented.

The counter selection locks during pending or ambiguous reservation attempts. A focused test verifies the selection lock, safe retry with the same idempotency key and body, returned reservation state, and absence of patient dispensing controls. The 78 focused Pharmacy-related tests and TypeScript check passed.

Browser evidence: `pharmacy-pharmacist-before-1536.jpg`, `pharmacy-pharmacist-after-1536.jpg`, and `pharmacy-fulfillment-before-1536.jpg`. The pharmacist cabinet was inspected against the approved reference. Search density improved, but the cabinet remains too tall and the foreground prescription stand starts too low in the 1536×1024 viewport. This discrepancy remains unresolved. Patient counter, corrected secondary fulfillment, autocomplete selection and four-size responsive browser verification remain unfinished. No live inventory or dispensing mutation was performed.

## Wrap-up validation and next resume point

- `npm --prefix frontend test -- --reporter=dot`: PASS, 11 files / 142 tests.
- TypeScript check: PASS; production build also runs TypeScript.
- `npm --prefix frontend run build`: PASS.
- `git diff --check`: PASS.
- Directory checkpoint: `20c365e`; Waiting Room checkpoint: `8c5f1ec`.

Resume with Pharmacy counter positioning and cabinet height, then patient/pharmacist primary and secondary workflow browser checks at 1536×1024, 1440×900, 1280×800 and 390×844. Physical QR camera decoding remains unverified. Reception and Consultation scene implementations remain preserved. Development servers are left running; no database reset or push was performed.

Final verdict for the three-correction task: **PARTIAL**. Directory and Waiting Room corrections are complete within the recorded limitations; Pharmacy is a validated implementation checkpoint with remaining visual and browser verification work.
