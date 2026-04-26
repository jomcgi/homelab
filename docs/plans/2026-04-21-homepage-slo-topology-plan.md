# Homepage SLO Topology — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the index card grid with a scroll-triggered, interactive rough.js topology diagram drawing live SLO data on the homepage's blue section.

**Architecture:** Fork the drawing logic from `/slos/+page.svelte` into a simplified `HomepageTopology.svelte`. Extract reusable pieces (dagre layout, rough.js drawing primitives, animation timeline) into shared `components/dag/` for future reuse by the chat knowledge graph. Page restructured into three acts: hero+bio (100vh), topology (blue), footer.

**Tech Stack:** Svelte 5, rough.js 4.6.6, @dagrejs/dagre 1.1.4, IntersectionObserver

**Design doc:** `docs/plans/2026-04-21-homepage-slo-topology-design.md`

---

### Task 1: Extract shared dag-layout.js

Extract the dagre layout engine into a shared component. This is a straight copy from `slos/layout.js` since it has no dependencies on the page component.

**Files:**

- Create: `home/frontend/components/dag/dag-layout.js`
- Reference: `home/frontend/routes/public/slos/layout.js`

**Step 1: Copy layout.js to shared location**

Copy `home/frontend/routes/public/slos/layout.js` to `home/frontend/components/dag/dag-layout.js`. No modifications needed — the file already exports a clean `computeLayout(topology, rankdir)` function with no page-specific dependencies.

**Step 2: Verify the file exports**

Confirm the file exports:

- `computeLayout(topology, rankdir)` — returns `{ nodes, edges, groups, nodeById, groupById }`
- Constants: `HH`, `CHAR_WIDTH`, `NODE_PAD`, `GROUP_PAD`, `GROUP_LABEL_H`

**Step 3: Commit**

```bash
git add home/frontend/components/dag/dag-layout.js
git commit -m "refactor: extract dag-layout.js into shared components"
```

---

### Task 2: Create dag-animation.js (animation timeline computation)

Extract the BFS-based animation timeline logic from the SLO page's `animDelay` derived computation into a standalone module. This is the core "when does each element start drawing" calculator.

**Files:**

- Create: `home/frontend/components/dag/dag-animation.js`
- Reference: `home/frontend/routes/public/slos/+page.svelte` (the `animDelay` $derived block)

**Step 1: Create the animation module**

Export a single function `computeAnimationTimeline(layout, opts)` that takes the output of `computeLayout()` and returns timing metadata for every node, edge, and group.

```javascript
/**
 * @param {object} layout — output of computeLayout()
 * @param {object} opts
 * @param {number} opts.boxPenSpeed — SVG units/sec for box strokes (default 332)
 * @param {number} opts.edgePenSpeed — SVG units/sec for edge strokes (default 349)
 * @param {number} opts.maxCursors — parallel drawing cursors (default 2)
 * @param {number} opts.cascadeStagger — stagger between cursors in seconds (default 0.3)
 * @param {number} opts.charMs — seconds per label character (default 0.03)
 *
 * @returns {{
 *   node: Record<string, NodeTiming>,
 *   edge: Record<string, EdgeTiming>,
 *   group: Record<string, GroupTiming>,
 *   edgeDir: Record<string, boolean>,
 *   totalDur: number
 * }}
 */
export function computeAnimationTimeline(layout, opts = {}) { ... }
```

Port the BFS traversal from `animDelay` in the SLO page:

1. Start from "external" node (or first ingress node if no "external")
2. BFS-traverse edges, assigning pencil→ink→fill→text timings per node
3. Schedule cross-edges after both endpoints are visited
4. Schedule groups after all children's ink phases complete
5. Position unvisited infra nodes with brief pauses
6. Return per-element timing objects + totalDur

**Key constants to export:**

```javascript
export const DEFAULTS = {
  BOX_PEN_SPEED: 332,
  EDGE_PEN_SPEED: 349,
  MIN_SIDE_DUR: 0.22,
  MIN_EDGE_DUR: 0.2,
  TRAVEL_PAUSE: 0.12,
  CHAR_MS: 0.03,
  MIN_TEXT: 0.06,
  MAX_CURSORS: 2,
  CASCADE_STAGGER: 0.3,
  MIN_LINE_STAGGER: 0.3,
  INK_SPEED: 0.85,
  PEN_EASE: "cubic-bezier(0.65, 0, 0.15, 1)",
};
```

**Step 2: Verify exports**

The module should have no Svelte imports, no DOM dependencies — pure computation.

**Step 3: Commit**

```bash
git add home/frontend/components/dag/dag-animation.js
git commit -m "refactor: extract dag-animation.js timeline computation"
```

---

### Task 3: Create DagRenderer.svelte (shared rough.js drawing component)

The core SVG rendering component. Takes positioned layout + animation timeline and draws everything with rough.js. No data fetching, no scroll detection, no page-specific UI.

**Files:**

- Create: `home/frontend/components/dag/DagRenderer.svelte`
- Reference: `home/frontend/routes/public/slos/+page.svelte` (SVG structure, rough.js drawing, highlight logic)

**Step 1: Define the component API**

```svelte
<script>
  /**
   * @type {{
   *   layout: object,           — output of computeLayout()
   *   timeline: object,         — output of computeAnimationTimeline()
   *   drawing: boolean,         — true while animation is running
   *   selected: string|null,    — currently selected node/group ID
   *   hovered: string|null,     — currently hovered node/group ID
   *   colors: object,           — color overrides (nodeFill, ink, edge, groupBorder, etc.)
   *   onselect?: (id: string|null) => void,
   *   onhover?: (id: string|null) => void,
   * }}
   */
</script>
```

**Step 2: Port the SVG structure**

From the SLO page, port:

- The SVG element with viewBox computed from layout bounds
- Layer groups: roughGroups → roughEdges → hoverBorderG → roughNodes → roughArrows → tooltipRough
- Hit area rects (transparent overlays for click/hover)
- Text labels with animation delays from timeline

**Step 3: Port the rough.js drawing logic**

From the SLO page's `$effect` blocks, port:

- `drawNodes()` — pencil rect + ink rect per node, with stroke-dasharray animation
- `drawEdges()` — pencil line + ink line per edge, with edgeDraw keyframe
- `drawGroups()` — group boundary rects (pencil + ink)
- `drawArrows()` — arrowhead lines at edge endpoints
- Highlight/dim logic for hover and selection states

**Step 4: Port CSS**

Port from the SLO page:

- `edgeDraw` keyframe (strokeDashoffset 100% → 0)
- `nodeIn` keyframe (opacity 0 → 1 for fills)
- `textJot` keyframe (opacity 0 → 1 for labels)
- `.map` SVG styling
- Node/edge/group CSS classes

Do NOT port:

- Theme toggle CSS (`.theme-light`/`.theme-dark`)
- 3D flip transitions
- Scribble-out animation
- Portrait/landscape responsive flip
- Drawer/sidebar styles
- Sparkline styles

**Step 5: Commit**

```bash
git add home/frontend/components/dag/DagRenderer.svelte
git commit -m "feat: add shared DagRenderer component with rough.js drawing"
```

---

### Task 4: Export shared dag components from component index

**Files:**

- Create: `home/frontend/components/dag/index.js`
- Modify: `home/frontend/components/index.js` (if it exists, add dag re-export)

**Step 1: Create barrel export**

```javascript
export { default as DagRenderer } from "./DagRenderer.svelte";
export { computeLayout } from "./dag-layout.js";
export {
  computeAnimationTimeline,
  DEFAULTS as DAG_DEFAULTS,
} from "./dag-animation.js";
```

**Step 2: Commit**

```bash
git add home/frontend/components/dag/index.js
git commit -m "chore: add dag component barrel export"
```

---

### Task 5: Create ScrollCta.svelte

A brutalist sticker-style scroll prompt that sits at the bottom of act 1.

**Files:**

- Create: `home/frontend/components/ScrollCta.svelte`

**Step 1: Build the component**

```svelte
<script>
  /** @type {{ target?: string, visible?: boolean }} */
  let { target = "#homelab", visible = true } = $props();

  function handleClick() {
    const el = document.querySelector(target);
    if (el) el.scrollIntoView({ behavior: "smooth" });
  }
</script>

{#if visible}
  <button class="scroll-cta" onclick={handleClick} transition:fade>
    <span class="scroll-cta-arrow">↓</span>
    <span class="scroll-cta-label">HOMELAB SLOS</span>
  </button>
{/if}
```

Style with the brutalist sticker motif:

- `var(--blue)` background, `var(--ink)` 2px border, `var(--ink)` text
- `font-family: var(--mono)`, 12px, font-weight 700, letter-spacing 0.12em
- Gentle bounce: `@keyframes bounce { 0%,100% { transform: translateY(0) } 50% { transform: translateY(6px) } }` — 2s infinite
- Centered horizontally, positioned at the bottom of the hero+bio section
- `transition: opacity 300ms ease` for fade-out when topology starts drawing

**Step 2: Commit**

```bash
git add home/frontend/components/ScrollCta.svelte
git commit -m "feat: add ScrollCta component for homepage"
```

---

### Task 6: Create HomepageTopology.svelte

The page-specific wrapper: fetches data, filters nodes, triggers drawing on scroll, provides homepage color palette.

**Files:**

- Create: `home/frontend/routes/public/HomepageTopology.svelte`

**Step 1: Build the component**

```svelte
<script>
  import { onMount } from "svelte";
  import { DagRenderer, computeLayout, computeAnimationTimeline } from "$lib/public/components/dag";

  /** @type {{ topology: object }} */
  let { topology } = $props();

  let drawing = $state(false);
  let hasDrawn = $state(false);
  let selected = $state(null);
  let hovered = $state(null);
  let sectionEl;
</script>
```

**Step 2: Filter topology data**

Remove agent-platform and context-forge groups, their child nodes, and connected edges:

```javascript
const filtered = $derived.by(() => {
  const excludeGroups = new Set(["agent-platform", "context-forge"]);
  const groups = topology.groups.filter((g) => !excludeGroups.has(g.id));
  const excludeNodes = new Set(
    topology.nodes
      .filter((n) => n.group && excludeGroups.has(n.group))
      .map((n) => n.id),
  );
  // Also exclude group IDs themselves as nodes
  for (const gid of excludeGroups) excludeNodes.add(gid);
  const nodes = topology.nodes.filter((n) => !excludeNodes.has(n.id));
  const edges = topology.edges.filter(
    (e) => !excludeNodes.has(e.from) && !excludeNodes.has(e.to),
  );
  return { groups, nodes, edges };
});
```

**Step 3: Compute layout and timeline**

```javascript
const layout = $derived(computeLayout(filtered, "LR"));
const timeline = $derived(computeAnimationTimeline(layout));
```

**Step 4: Scroll trigger with IntersectionObserver**

```javascript
onMount(() => {
  const observer = new IntersectionObserver(
    ([entry]) => {
      if (entry.isIntersecting && !hasDrawn) {
        drawing = true;
        hasDrawn = true;
        setTimeout(() => {
          drawing = false;
        }, timeline.totalDur * 1000);
      }
    },
    { threshold: 0.15 },
  );
  observer.observe(sectionEl);
  return () => observer.disconnect();
});
```

**Step 5: Define homepage color palette**

```javascript
const colors = {
  pencil: "rgba(26, 26, 26, 0.3)",
  ink: "var(--ink)",
  nodeFill: "var(--paper)",
  nodeText: "var(--ink)",
  groupBorder: "rgba(26, 26, 26, 0.15)",
  groupLabel: "var(--ink-2)",
  edge: "var(--ink-3)",
  arrow: "var(--ink-3)",
  selectedFill: "var(--accent)",
  sloHealthy: "var(--teal)",
  sloWarning: "var(--accent)",
  sloBurning: "var(--coral)",
};
```

**Step 6: Template**

```svelte
<section class="topology-section" id="homelab" bind:this={sectionEl}>
  <div class="topology-wrap">
    <DagRenderer
      {layout}
      {timeline}
      {drawing}
      {selected}
      {hovered}
      {colors}
      onselect={(id) => (selected = id)}
      onhover={(id) => (hovered = id)}
    />
  </div>
</section>
```

**Step 7: Styles**

```css
.topology-section {
  background: var(--blue);
  border-bottom: 2px solid var(--ink);
  padding: 64px 0;
  position: relative;
  min-height: 500px;
}

.topology-wrap {
  max-width: 1360px;
  margin: 0 auto;
  padding: 0 32px;
}
```

**Step 8: Commit**

```bash
git add home/frontend/routes/public/HomepageTopology.svelte
git commit -m "feat: add HomepageTopology with scroll-triggered drawing"
```

---

### Task 7: Add topology data loader to homepage

The homepage needs to fetch topology data server-side, same as the SLO page.

**Files:**

- Modify: `home/frontend/routes/public/+page.server.js`

**Step 1: Check if +page.server.js exists**

Check `home/frontend/routes/public/+page.server.js`. If it doesn't exist, create it. If it does, add the topology fetch to the existing `load` function.

**Step 2: Add topology fetch with static fallback**

```javascript
const API_BASE = process.env.API_BASE || "http://localhost:8000";

const STATIC_TOPOLOGY = {
  groups: [],
  nodes: [],
  edges: [],
};

export async function load({ fetch }) {
  try {
    const resp = await fetch(`${API_BASE}/api/public/observability/topology`, {
      signal: AbortSignal.timeout(5_000),
    });
    if (!resp.ok) return { topology: STATIC_TOPOLOGY };
    const topology = await resp.json();
    return { topology };
  } catch {
    return { topology: STATIC_TOPOLOGY };
  }
}
```

Note: Use a shorter timeout (5s vs 10s on SLO page) since this is the homepage — it must load fast. The static fallback prevents 5xx if the API is down. We can later bake a real snapshot into `STATIC_TOPOLOGY` once the filtering is confirmed working.

**Step 3: Commit**

```bash
git add home/frontend/routes/public/+page.server.js
git commit -m "feat: add topology data loader for homepage"
```

---

### Task 8: Restructure +page.svelte — remove index, add topology

The big page surgery: remove the index panel, add the topology section, stretch act 1 to 100vh, add scroll CTA.

**Files:**

- Modify: `home/frontend/routes/public/+page.svelte`

**Step 1: Update imports**

Remove `Stamp` (already removed). Add:

```javascript
import HomepageTopology from "./HomepageTopology.svelte";
import ScrollCta from "$lib/public/components/ScrollCta.svelte";
```

Add data prop:

```javascript
let { data } = $props();
```

**Step 2: Remove index data and markup**

Delete:

- The `INDEX` array (lines 6-13 currently)
- The entire `<!-- === Index panel (blue) === -->` section (id="index")
- All index-related CSS: `.index-panel`, `.index-header`, `.index-sub`, `.index-grid`, `.card`, `.card-wide`, `.card-head`, `.card-num`, `.card-tag`, `.card-title`, `.card-note`, `.card-foot`, `.card-arr`, `.chat-cta`, `.chat-cta-*`, `:global(.sticker-index)`, `.index-wrap`
- Decorative shape CSS for index: `.deco-idx-diamond`, `.deco-idx-circle`

**Step 3: Add topology section and scroll CTA**

After the bio panel, before the footer:

```svelte
<!-- === Scroll CTA === -->
<ScrollCta target="#homelab" visible={!topologyStarted} />

<!-- === SLO Topology (blue) === -->
<HomepageTopology topology={data.topology} bind:drawing={topologyStarted} />
```

Add state:

```javascript
let topologyStarted = $state(false);
```

**Step 4: Stretch act 1 to fill viewport**

Wrap hero + bio in a container or add min-height. The cleanest approach: add a wrapper `<div class="act-1">` around the hero and bio sections.

```svelte
<div class="act-1">
  <!-- === Hero === -->
  <section class="hero">...</section>

  <!-- === Bio panel === -->
  <section class="bio-panel reveal">...</section>
</div>
```

CSS:

```css
.act-1 {
  min-height: 100svh;
  display: flex;
  flex-direction: column;
}

.hero {
  flex: 1;
  /* ... existing styles, remove fixed padding-top, keep padding-bottom */
}
```

This makes the hero grow to fill remaining space after the bio, pushing the scroll CTA to the bottom of the viewport.

**Step 5: Update "SEE THE WORK" button href**

Change `href="#index"` to `href="#homelab"` on the hero CTA buttons (both "SEE THE WORK" and "ASK THE SITE").

**Step 6: Remove decorative SVGs from what was the blue section**

The blue section's decorative shapes (`.deco-idx-diamond`, `.deco-idx-circle`) are already removed with the index panel. No separate action needed.

**Step 7: Commit**

```bash
git add home/frontend/routes/public/+page.svelte
git commit -m "feat: replace index with SLO topology, stretch hero to viewport"
```

---

### Task 9: Update component barrel exports

Make sure `ScrollCta` is exported from the components index if one exists.

**Files:**

- Modify: `home/frontend/components/index.js` (if exists)

**Step 1: Check and update exports**

Add `ScrollCta` to the barrel export alongside existing components (Nav, Sticker, Marquee, Footer).

**Step 2: Commit**

```bash
git add home/frontend/components/index.js
git commit -m "chore: export ScrollCta from components index"
```

---

### Task 10: Visual testing and polish

**Step 1: Run the dev server**

Start the dev server from the monolith frontend and verify:

- [ ] Hero + bio fill the first viewport
- [ ] Scroll CTA appears at bottom of act 1 with bounce animation
- [ ] Clicking scroll CTA smooth-scrolls to topology
- [ ] Topology begins drawing when blue section enters viewport
- [ ] Drawing sequence: groups → nodes (staggered) → edges → SLO badges
- [ ] Hover highlights connections and dims unrelated nodes
- [ ] Click selects a node and shows tooltip
- [ ] Click background deselects
- [ ] Agent-platform and context-forge nodes/edges are filtered out
- [ ] Colors work on blue background (paper nodes, ink strokes)
- [ ] Footer renders correctly after topology
- [ ] Mobile: topology section is usable, scroll CTA hidden or adapted
- [ ] `prefers-reduced-motion`: animations disabled

**Step 2: Fix any visual issues**

Adjust spacing, colors, viewBox sizing as needed.

**Step 3: Commit**

```bash
git commit -m "fix: visual polish for homepage topology"
```

---

### Task 11: Push and verify CI

**Step 1: Push branch**

```bash
git push
```

**Step 2: Run remote tests**

```bash
bb remote test //projects/monolith/... --config=ci
```

**Step 3: Fix any CI issues**

Format, lint, or test failures.

---

## Execution Order

Tasks 1-4 (shared components) can be done in sequence — each builds on the previous.
Task 5 (ScrollCta) is independent.
Tasks 6-7 (HomepageTopology + data loader) depend on Tasks 1-4.
Task 8 (page surgery) depends on Tasks 5-7.
Tasks 9-11 are sequential cleanup.

```
[1: dag-layout] → [2: dag-animation] → [3: DagRenderer] → [4: barrel export]
                                                                    ↓
[5: ScrollCta] ──────────────────────────────→ [8: page restructure]
                                                        ↓
[6: HomepageTopology] → [7: data loader] ──→ [8] → [9: exports] → [10: polish] → [11: CI]
```
