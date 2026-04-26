# Homepage SLO Topology Integration

**Date:** 2026-04-21
**Status:** Approved

## Summary

Replace the index card grid on the public homepage with an interactive, scroll-triggered rough.js topology diagram showing live SLO data. The hero + bio sections stretch to fill the first viewport, then the topology draws itself on the blue background as the user scrolls down.

## Page Structure

```
┌─────────────────────────────────┐
│  Nav (sticky)                   │
│  Marquee                        │
├─────────────────────────────────┤
│                                 │
│  Hero (mono headline, CTAs)     │  cream background
│  Bio (two-column grid)          │  min-height: 100svh
│                                 │  (minus nav+marquee)
│  ┌───────────────────────┐      │
│  │  ↓ HOMELAB SLOS        │     │  scroll CTA at border
│  └───────────────────────┘      │
├─────────────────────────────────┤
│                                 │
│  SLO Topology                   │  blue background
│  (rough.js DAG, scroll-trigger) │  no decorative shapes
│  Interactive: hover/select      │
│                                 │
├─────────────────────────────────┤
│  Footer (contact links)         │  cream background
└─────────────────────────────────┘
```

### Changes from current page

- Hero + bio get `min-height: 100svh` (minus nav/marquee height)
- Index panel removed entirely (cards, chat CTA, stickers, decos)
- Decorative SVG shapes removed from blue section
- New `HomepageTopology` component replaces index
- New `ScrollCta` component at cream/blue border
- `Stamp` component already removed

## Component Architecture

```
home/frontend/
├── components/
│   ├── dag/
│   │   ├── DagRenderer.svelte     shared: rough.js SVG drawing engine
│   │   ├── dag-layout.js          shared: dagre layout computation
│   │   └── dag-animation.js       shared: pencil→ink→fill→text timeline
│   └── ScrollCta.svelte           "↓ HOMELAB SLOS" prompt
├── routes/public/
│   ├── +page.svelte               imports HomepageTopology
│   └── HomepageTopology.svelte    data fetch, filtering, color, scroll trigger
```

### Shared vs page-specific

| Shared (`components/dag/`)         | Page-specific (`HomepageTopology`)    |
| ---------------------------------- | ------------------------------------- |
| rough.js rect/line/arrow rendering | Node filtering (exclude groups)       |
| dagre layout computation           | Color palette (blue-adapted)          |
| Animation timeline & easing        | Scroll trigger (IntersectionObserver) |
| SVG group management               | Tooltip/selection UI                  |
| Stroke dash animation utils        | Data fetching & fallback              |

### Reuse

The chat page's knowledge graph can later import `DagRenderer` + `dag-layout.js` to replace its own drawing logic. The `/slos` page will be deprecated.

## Data & Filtering

**API:** `GET /api/public/observability/topology` (existing)

**Filtering in HomepageTopology:**

- Remove nodes where group is `agent-platform` or `context-forge`
- Remove edges where source or target is a filtered node
- Remove those group definitions
- Keep: MONOLITH group + standalone infra-tier nodes

**Fallback:** Bake a static topology snapshot into the component as default data. API fetch overwrites when available. Homepage must not 5xx if the API is down.

## Animation

Triggered by IntersectionObserver (threshold 0.15) when blue section scrolls into view.

```
Phase 1: Groups sketch in
  └─ MONOLITH boundary — rough.js, pencil gray, low opacity

Phase 2: Nodes sketch in (staggered left→right by dagre rank)
  └─ Each: pencil outline → ink retrace → fill → text jot
  └─ ~80ms stagger between nodes

Phase 3: Edges draw (stroke-dashoffset animation)
  └─ Edge draws after both endpoints are inked
  └─ Arrowheads appear at end of edge draw

Phase 4: SLO badges fade in
  └─ Labels on nodes: "99.97%" etc.
  └─ Color-coded by status
```

## Interaction

- **Hover node:** highlight connected edges + neighbors, dim others
- **Click node:** selected state, tooltip with service name + SLO % + status text
- **Click background:** deselect
- No theme toggle, no portrait/landscape flip, no scribble-out

## Scroll CTA

- Brutalist sticker style: "↓ HOMELAB SLOS" on blue bg with ink border
- Gentle bounce animation (translateY, 2s loop)
- Click smooth-scrolls to topology section
- Fades out once topology starts drawing

## Color Palette

All from existing design system tokens, tuned for `var(--blue)` background:

| Element               | Color                    |
| --------------------- | ------------------------ |
| Pencil sketch         | `rgba(26, 26, 26, 0.3)`  |
| Ink retrace / strokes | `var(--ink)`             |
| Node fill             | `var(--paper)`           |
| Node text             | `var(--ink)`             |
| Group boundary        | `rgba(26, 26, 26, 0.15)` |
| Group label           | `var(--ink-2)`           |
| Edges / arrowheads    | `var(--ink-3)`           |
| Selected node fill    | `var(--accent)`          |
| Dimmed nodes          | `opacity: 0.3`           |

### SLO badge colors

| Status           | Color           |
| ---------------- | --------------- |
| Healthy (≥99.9%) | `var(--teal)`   |
| Warning (≥99%)   | `var(--accent)` |
| Burning (<99%)   | `var(--coral)`  |
