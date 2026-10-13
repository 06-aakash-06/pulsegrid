# Phase 9 frontend redesign — current status

The initial design was rejected in the user's visual review. The current authorized stop point is the corrected **Reception/Homepage and Consultation/Doctor Directory** only. Other Phase 9 work and earlier verification artifacts are retained, but their presence does not establish visual approval.

See the [two-screen correction report](phase-9-visual-correction.md), [reference comparison](verification/phase9-correction/review.html), [asset provenance](phase-9-correction-assets.md), [reference inventory](phase-9-reference-inventory.md), [frontend audit](phase-9-frontend-audit.md) and [design tokens](phase-9-design-system.md).

The underlying React/TypeScript/Vite application keeps its eight role workspaces, bearer refresh/CSRF handling, owner API clients, bounded cursor lists, reviewed idempotent commands, ETag handling and lazy workflow modules. The complete inventory still has 35 workspace views and five public/auth/access views, with existing redirects. That audit count is not a claim that all 40 views have passed the revised visual acceptance gate.

For the corrected scenes, Inter and vector icons render sharp text/controls on cream physical surfaces within clean hospital architecture. Directory links expose only permitted workspaces. A native command dialog offers permitted route search. Real profile names come from owner reads; full internal IDs are secondary. Reception has suspended wayfinding, robot/counter, physical paper objects and owner-issued queue information. Consultation has a compact specialty/roster/profile board and a clinical desk schedule. Mobile reflows into a directory drawer, two-column paper objects, specialty chips and a stacked profile.

GSAP scene introductions use matchMedia, short durations and cleanup. Motion is lazy-loaded for existing small command/receipt/layout transitions. Reduced-motion tests verify the GSAP entrance is skipped. Essential tasks use semantic controls, labels, visible focus, text statuses and review/error states. No task depends on animation, hover or decorative imagery.

The local demo manifest is serve-only, development-only and ignored; production contains no fixture identities/credentials/ID mappings. The two corrected architectural WebPs load only when these scenes match; portraits are used only by the local demo mapping. Current production main JavaScript is approximately 420 KB (139 KB gzip), with owner workflows and QR libraries split into deferred chunks. No load-speed or throughput benchmark is claimed.

All 142 frontend tests, typechecking and production build pass. Actual browser search, role navigation, filtering, accepted availability and reviewed booking succeed; read-only owner verification inspected 13 responses. Final viewport captures cover 1536×1024, 1440×900, 1280×800 and 390×844 for both scenes. Remaining fidelity differences and unavailable reference features are explicitly listed in the correction report. Human visual review is pending. No push, deployment, backend business change, database reset or subsequent department redesign is part of this stop point.


## 14 October 2026 continuation

See [Phase 9 resume](phase-9-resume.md) for recovered work, the seven department compositions, owner-scoped patient registers, role-specific secondary screens, reused assets, four-size browser evidence and exact validation. Its PARTIAL acceptance verdict supersedes broader historical visual acceptance claims. Architectural layout and department scene extensions remain scoped to the existing design system; no backend domain boundary or API contract changed.
