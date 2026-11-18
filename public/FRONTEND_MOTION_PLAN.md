# SupeRR Selector — Frontend Motion Plan

**Status: PROPOSAL — awaiting owner approval.** This file is the read-only audit and proposed design plan. No visual implementation has been made.

## Scope and safety

- Dashboard inspected: `index.html` (single HTML document with inline CSS and vanilla JS), plus existing `dashboard_data.json` (read-only; not linked by the dashboard runtime).
- Backup created before this plan: `index.backup.html`.
- Backup SHA-256: `54a877bdacf66e59219e4faa2a31e42ab0c5453e1e07c576298619f6f76fee69` — matches `index.html` at backup time.
- On approval, proposed new files are only `motion.css` and `motion.js` beside `index.html`; existing frontend files may be changed only to add local links and hook classes/data attributes. No network asset requests or runtime CDN dependencies.
- No data, wording, values, rankings, formulas, filter/sort behavior, element IDs, existing JS-dependent classes/attributes, chart geometry/data, backend, pipeline, tests, reports, or PDFs will be changed.

## React Bits research (read-only)

React Bits describes itself as a source-copy library of React components/backgrounds offered in JS/TS and CSS/Tailwind variants. Its categories include Text Animations, Animations, Components, Backgrounds, and Micro Interactions. The site states MIT + Commons Clause: use in products is permitted, but the components themselves may not be sold, sublicensed, or redistributed. Plan: recreate visual principles independently in local vanilla CSS/JS, do not copy/vend component source; add a concise in-code credit/comment acknowledging inspiration and link to React Bits.

### Candidate scan and vanilla suitability

| Category / examples reviewed | Visual behavior | Vanilla fit and dashboard decision |
|---|---|---|
| Text Animations: Split Text, Blur Text, Shiny Text, Gradient Text, Scroll Reveal, Count Up, Decrypted Text, Scrambled Text, Stroke Text, Scroll Float, Text Type | Staggered word/character reveal, blur-to-clear, moving sheen/gradient, number interpolation, glyph scrambling, drawn type, scroll response | Split/blur and restrained shiny text are CSS+small JS suitable. Count Up can interpolate already-rendered static numeric text without recalculating. Decrypt/scramble/typewriter risk transiently changing exact data and readability; omit. Stroke/float are unnecessary. |
| Animations: Animated Content, Fade Content, Spotlight Card, Glare Hover, Click Spark, Magnet, Electric Border, Cursor Grid, Noise, Gradual Blur, Star Border, Pixel Transition | Scroll reveal/stagger, pointer-lighting, glint, click particles, spring movement, animated edge/background textures | Animated Content/Fade Content, Spotlight Card and Glare Hover can be approximated with IntersectionObserver, CSS gradients, opacity and transform. Use subtle spotlight and reveal only. Avoid sparks/magnets/electric edges/noise/pixel effects as distraction or extra DOM/work. |
| Components: Spotlight Card, Tilted Card, Reflective Card, Glass Surface, Border Glow, Line Sidebar, Pill Nav, Counter, Animated List | Pointer-driven lighting/tilt, reflective/glass surfaces, active navigation movement, rolling digits, list entry | Spotlight is low-cost and suitable. Adapt Counter only if it preserves exact final strings and reserves width; do not tilt dense data tables. Keep existing navigation mechanics; add only brief visual feedback. Glass/reflective effects add contrast/performance risk and are not proposed. |
| Backgrounds: Aurora, Particles, Dot Grid, Grid Motion, Silk, Waves, Grainient, Beams, Dark Veil, Topography | Ambient gradient/particle/grid/line movement, often WebGL/canvas or continuous animation | Choose a static layered CSS aurora/soft mesh with a very slow transform-only drift, paused when page hidden; no canvas/WebGL, particles, pointer following, or runtime assets. Low GPU cost, with reduced-motion/offscreen disable. |
| Micro Interactions: Glide Select, Rubber Segment, Warm Tooltip, Status Mark, Spring Check, Squish Switch, Pulse Heart, Swipe Row, Hold Button | Springy control feedback, tooltip delay, status glyph animation, press/release states | Use CSS-only press/focus/active feedback on current buttons/tabs and a concise tooltip fade. Do not replace select/filter semantics or alter sorting/filter state. No simulated loading/status effects. |
| SVG/visual effects (icons, chart SVGs, Shape Magic/Texture Lab tools) | Stroke drawing, geometric marks, texture/material effects | Existing inline SVGs are search/theme icons and data charts. Proposed: short opacity reveal on chart containers and a subtle hover/focus color transition on controls; preserve SVG paths, chart marks, values and accessibility labels. No generated artwork or external SVG. |

## Dashboard audit (current document)

### Persistent shell and controls

| Element/module | Current content/behavior | Classification |
|---|---|---|
| Sticky header `.top` / `.top-inner` | SupeRR Selector brand, Season 2 label, `nav.main`, verified badge, theme toggle button with sun/moon SVG | Interactive; nav is hash-routed, theme toggle sets `data-theme` |
| Main hero `#hero` | Overview eyebrow, H1, intro paragraph, four metadata pills; other tabs use section title/lede | Data-driven text; current overview word reveal and hero decoration hooks exist |
| Main region `#app` | Renders one of ten views inside `.view.active`; `aria-live=polite` | Data-driven, dynamically rendered |
| Footer `.foot` | Build/source note and data disclaimer | Static |
| Player drawer `#drawer` and scrim `#scrim` | Opens from clickable ranking/player/excluded rows; close button, scrim and Escape close; focus return | Interactive, data-driven |
| Tooltip `#tooltip` | Delegated hover tooltip for chart/table explanations | Interactive |

### Views and modules

| View | Modules and visible structures | Classification |
|---|---|---|
| Overview | Four KPI cards (bowler count, batter count, innings-1 eligibility, matches/deliveries); “What this is” and “What this is not” cards; results summary cards; interval/scatter charts; methodology callout; quick-link cards | Data-driven, navigation-linked; KPI count animation/spotlights currently exist |
| Bowlers | Ranking filter bar (search, tier, format, minimum balls, published/all scope); sortable clickable table; interval chart; reliability/performance scatter chart; explanatory card and callout | Interactive/data-driven |
| Batters | Search/tier/format/minimum-ball filters; sortable clickable table including ranks 1–10 (two marked below-gate); interval chart; explanatory card/callout | Interactive/data-driven |
| Players | Search, role/context/format/other filters; sortable, paginated table with clickable player rows and “show more” button | Interactive/data-driven |
| Formats | Format comparison cards/tables/charts with linked navigation where present | Data-driven/static within view |
| Contexts | Context summary cards, explanations and comparisons | Data-driven/static within view |
| Excluded | Search, role and reason selects; summary cards; sortable/paginated table; clickable detail rows | Interactive/data-driven |
| Uncertainty | Bootstrap stability, intervals, sensitivity cards/charts/tables | Data-driven/static within view |
| Method | Formula panel, rule/method explanation cards and tables | Data-driven/static within view |
| Data | Data-quality/provenance summary cards, internal/independent check tables, frozen hash table | Data-driven/static within view |

### Shared components and modules

- `.card`, `.chart-card`, `.issue`, `.callout`, `.pill`, `.formula`, `.kv`, `.grid`, `.table-wrap`, `.filters`, `.search`, `.seg`, `.select`, `.chip`, `.load-more`, `.tooltip`, `.drawer`.
- Tables use sticky sortable headers where applicable, responsive stacked rows on mobile, clickable player rows, and SVG interval graphics. Their text/rows are data-bearing; proposed styling must not hide content or alter values.
- Inline SVG includes search icon, theme sun/moon, confidence-interval glyphs, charts (interval, scatter, distribution, stability, sensitivity, separation). Chart data and SVG calculations are frozen.
- Buttons include theme toggle, segmented filter buttons, sortable table headings (interactive headers), pagination/load-more and drawer close. Links include navigation, quick links and contextual cross-links.

## Proposed match plan (approval required)

Palette direction: deep forest/ink green base with restrained copper accent, guided by the report v2 reference. Use semantic tokens and `light-dark()` pairs; preserve contrast for data tiers/status and keep chart categorical series distinguishable. Typography remains system/local (no remote font request); use clear type scale and consistent spacing/radius/shadow. Background should remain calm and behind content.

| Element | Proposed effect | React Bits inspiration | Vanilla implementation | Estimated cost |
|---|---|---|---|---|
| Page background, especially Overview hero | Faint green/copper CSS mesh/aurora with slow drift, fade to surface; pause when hidden | Aurora / Silk / Gradient Waves | A few radial gradients on a pseudo-element, transform/opacity keyframes; `visibilitychange`, `IntersectionObserver`, reduced-motion stop | Low GPU; no canvas/network |
| Hero H1 and view H1/H2 | Staggered words, opacity + slight blur-to-clear; keep original accessible text | Split Text / Blur Text / Scroll Reveal | Add spans to visual clone while preserving an accessible original label; run on newly rendered view headings | Low startup DOM; bounded to headings |
| KPI values | Smooth count from zero to exact existing integer/locale string; reserve width | Count Up / Counter | Parse only marked existing text, animate presentation, restore exact original string; no data edits | Low CPU, <1.2s per view entry |
| All cards and modules | Consistent surface, border, radius/shadow; subtle pointer spotlight/glare on hover; scroll-in reveal for card groups | Spotlight Card / Glare Hover / Animated Content | Shared added class; CSS radial gradient driven by local pointer coordinates; `IntersectionObserver` for opacity/translate stagger; no layout changes | Low–moderate; animate once, observer disconnects |
| Tables and rows | Header/module reveal, first 12–15 visible rows fade upward with 8–12ms stagger; filter result set re-enters | Animated Content / Fade Content / Animated List | Observer or per-render decoration of current DOM rows only; leave row count, order and values untouched | Bounded; max 15 animated rows/table |
| Buttons, tabs, nav, segmented filters | Subtle active/focus/press color and 1–2px transform feedback; existing selected state remains authoritative | Glide Select / Rubber Segment / Specular Button | CSS `:hover`, `:focus-visible`, `:active`, existing active class/ARIA state | Negligible |
| SVG icons and chart containers | Fade/draw-in for decorative theme/search icons; chart container reveal; no data mark animation | Stroke Text / Orbit Images (visual cue only) | CSS opacity/scale for icons; container reveal; leave SVG paths, labels and plotted values intact | Negligible |
| Drawer, tooltip, callouts | Short fade/translate entrance and opacity exit; preserve focus/close semantics | Fade Content / Warm Tooltip | CSS transitions on existing classes, reduced motion instant/crossfade | Low |
| Dark/light theme | Cohesive green/copper semantic roles in both existing manual modes; ensure status and chart contrast | Theme is project-specific | CSS custom-property overrides and `light-dark()`; do not change the toggle's JS | Negligible |

## Approval gate

Please approve or edit this plan before implementation. After approval, implementation will be limited to dashboard frontend files, with the exact visual/content invariants above. No implementation has been performed yet.
