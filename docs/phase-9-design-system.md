# Phase 9 design system

Approved palette: ivory paper `#f8f1e9`, limestone `#e6d6c0`, warm oak `#ac794b`, navy ink `#102638`, deep teal `#10383e`, medical red `#a51c18`. Inter Variable is bundled locally under its OFL license. No remote font requests. Tokens for spacing, materials, borders, radii, shadows, timing and header/directory geometry live in `frontend/src/styles/hospital.css`.

Persistent physical directory and warm cream header; solid legible paper surfaces, thin dividers, vector department glyphs, restrained depth. Department layouts differ: reception counter/slips, consultation directory/profile, booking/date/receipt, waiting kiosk/queue, pharmacy shelves/workspace, billing source/receipt, emergency queue/case/actions, records timeline/dossier, operations monitor/trends. All text and controls render as HTML/SVG.

At <=900px directory becomes a focus-managed drawer with Escape and overlay dismissal. Search uses native accessible dialog, Escape/return focus, permitted route destinations, and Cmd/Ctrl+K. No global clinical search API is implied. Keyboard skip link, active route aria-current, visible focus, local scroll for dense tables. Mobile 320px minimum. Reduced motion removes scene and panel movement. GSAP owns scene introductions only; Motion owns small component/dialog/status transitions on different elements. Emergency operations have no scene delay.

Preserve existing route titles as accessible navigation names while the directory groups them by their hospital department. Eight actual role groups; server remains authorization authority. Staff JWT provides subject rather than name; header shows that account identifier. Patient reception uses owner profile name.

Architecture images are generated clean environments, compressed to WebP and selected per active department; never full screenshot backgrounds. The shared design stylesheet intentionally overrides old lazy module CSS via scoped specificity, so loading a workflow cannot restore white/blue generic styles.
