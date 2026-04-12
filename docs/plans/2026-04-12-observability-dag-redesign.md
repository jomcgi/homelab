# Observability Demo DAG Redesign — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the hardcoded 9-node observability demo topology with a config-driven, dagre-auto-laid-out DAG reflecting the real homelab architecture, styled with a MotherDuck-inspired brutalist palette.

**Architecture:** A JSON config file defines nodes (with tier/status/SLO metadata) and edges (with protocols). At render time, dagre computes node positions from the graph structure (`rankdir: LR` for landscape, `TB` for portrait). The existing Rough.js animation pipeline (BFS sequencing, pencil→ink dual-pass, scribble highlights) renders the computed layout unchanged. CSS variables shift to a warm cream/charcoal brutalist palette.

**Tech Stack:** Svelte 5, Rough.js, dagre (new dep), Vite (JSON import), Bazel (pnpm workspace)

---

### Task 1: Add dagre dependency

**Files:**

- Modify: `projects/monolith/frontend/package.json`
- Modify: `pnpm-lock.yaml` (auto-generated)
- Modify: `projects/monolith/frontend/BUILD:25-46` (add `":node_modules/@dagrejs/dagre"`)

**Step 1: Add dagre to package.json**

Add `"@dagrejs/dagre": "^1.1.4"` to the `dependencies` object in `projects/monolith/frontend/package.json`. Use `@dagrejs/dagre` — the modern maintained fork under the dagrejs org.

```json
"dependencies": {
    "@dagrejs/dagre": "^1.1.4",
    "@opentelemetry/api": "^1.9.0",
    ...
}
```

**Step 2: Install dependency**

Run: `cd /tmp/claude-worktrees/observability-dag-redesign && pnpm install --filter monolith-frontend`
Expected: lockfile updates, `node_modules/@dagrejs/dagre` appears

**Step 3: Add to BUILD deps**

Add `":node_modules/@dagrejs/dagre",` to the `js_library` deps list in `projects/monolith/frontend/BUILD` (after the roughjs line):

```starlark
        # Hand-drawn SVG rendering
        ":node_modules/roughjs",
        # DAG layout engine
        ":node_modules/@dagrejs/dagre",
```

**Step 4: Verify build**

Run: `bb remote --os=linux --arch=amd64 test //projects/monolith/frontend:build_test --config=ci`
Expected: PASS — frontend builds with dagre available

**Step 5: Commit**

```bash
git add projects/monolith/frontend/package.json projects/monolith/frontend/BUILD pnpm-lock.yaml
git commit -m "build(monolith/frontend): add @dagrejs/dagre for auto-layout"
```

---

### Task 2: Create topology config file

**Files:**

- Create: `projects/monolith/frontend/src/routes/public/observability-demo/topology.json`

**Step 1: Write the topology config**

Create `topology.json` with the full node/edge/metadata structure. Vite imports JSON natively — no loader needed.

```json
{
  "nodes": [
    {
      "id": "cloudflare",
      "label": "CLOUDFLARE",
      "tier": "ingress",
      "status": "healthy",
      "description": "tunnel + gateway",
      "brief": "14.2k req/24h",
      "metrics": [
        { "k": "tunnel", "v": "connected" },
        { "k": "requests 24h", "v": "14.2k" },
        { "k": "cached", "v": "62%" }
      ]
    },
    {
      "id": "monolith",
      "label": "MONOLITH",
      "tier": "critical",
      "ingress": true,
      "status": "healthy",
      "description": "fastapi + sveltekit",
      "brief": "99.97% · 12.5 rps",
      "slo": { "target": 99.9, "current": 99.97 },
      "budget": {
        "consumed": 28,
        "elapsed": 40,
        "remaining": "31.1 min",
        "window": "30d"
      },
      "latency": { "p99": 42, "target": 200, "unit": "ms" },
      "metrics": [
        { "k": "rps", "v": "12.5" },
        { "k": "error rate", "v": "0.02%" },
        { "k": "p99", "v": "42ms" }
      ],
      "spark": [
        38, 42, 45, 41, 39, 44, 42, 40, 43, 41, 38, 42, 47, 44, 42, 39, 41, 43,
        42, 40, 38, 41, 43, 42
      ]
    },
    {
      "id": "postgres",
      "label": "POSTGRES",
      "tier": "critical",
      "status": "healthy",
      "description": "cnpg + pgvector",
      "brief": "100% · 8ms p99",
      "slo": { "target": 99.95, "current": 100 },
      "budget": {
        "consumed": 0,
        "elapsed": 40,
        "remaining": "21.6 min",
        "window": "30d"
      },
      "latency": { "p99": 8, "target": 50, "unit": "ms" },
      "metrics": [
        { "k": "connections", "v": "12 / 100" },
        { "k": "query p99", "v": "8ms" },
        { "k": "storage", "v": "2.1 GiB" }
      ],
      "spark": [
        6, 7, 8, 7, 6, 8, 7, 7, 8, 7, 6, 7, 9, 8, 7, 6, 7, 8, 7, 7, 6, 7, 8, 7
      ]
    },
    {
      "id": "nats",
      "label": "NATS",
      "tier": "critical",
      "status": "healthy",
      "description": "jetstream message bus",
      "brief": "100% · 45 msg/s",
      "slo": { "target": 99.99, "current": 100 },
      "budget": {
        "consumed": 0,
        "elapsed": 40,
        "remaining": "4.3 min",
        "window": "30d"
      },
      "metrics": [
        { "k": "msg/s", "v": "45" },
        { "k": "consumers", "v": "3" },
        { "k": "lag", "v": "0" }
      ],
      "spark": [
        40, 42, 48, 45, 43, 47, 44, 41, 46, 43, 42, 45, 50, 47, 44, 42, 45, 48,
        44, 43, 41, 44, 46, 45
      ]
    },
    {
      "id": "context-forge",
      "label": "CONTEXT FORGE",
      "tier": "critical",
      "ingress": true,
      "status": "healthy",
      "description": "mcp gateway",
      "brief": "99.98% · 8 rps",
      "slo": { "target": 99.9, "current": 99.98 },
      "budget": {
        "consumed": 12,
        "elapsed": 40,
        "remaining": "38.2 min",
        "window": "30d"
      },
      "latency": { "p99": 180, "target": 500, "unit": "ms" },
      "metrics": [
        { "k": "rps", "v": "8" },
        { "k": "mcp servers", "v": "3" },
        { "k": "p99", "v": "180ms" }
      ],
      "spark": [
        120, 140, 180, 160, 150, 170, 190, 165, 155, 175, 145, 160, 185, 170,
        160, 150, 165, 180, 160, 155, 140, 160, 175, 165
      ]
    },
    {
      "id": "agent-platform",
      "label": "AGENT PLATFORM",
      "tier": "critical",
      "ingress": true,
      "status": "degraded",
      "description": "orchestrator + mcp clients",
      "brief": "99.31% · 2 active",
      "slo": { "target": 99.5, "current": 99.31 },
      "budget": {
        "consumed": 138,
        "elapsed": 40,
        "remaining": "0 min",
        "window": "30d"
      },
      "latency": { "p99": 890, "target": 500, "unit": "ms" },
      "metrics": [
        { "k": "active jobs", "v": "2" },
        { "k": "completed 24h", "v": "47" },
        { "k": "mcp servers", "v": "4" }
      ],
      "spark": [
        420, 510, 680, 890, 750, 820, 940, 870, 780, 910, 850, 720, 880, 930,
        810, 760, 890, 950, 870, 820, 780, 850, 910, 890
      ]
    },
    {
      "id": "llama-cpp",
      "label": "LLAMA.CPP",
      "tier": "critical",
      "status": "healthy",
      "description": "gemma 4 inference",
      "brief": "99.9% · 1.2 rps",
      "slo": { "target": 99.5, "current": 99.9 },
      "latency": { "p99": 2400, "target": 5000, "unit": "ms" },
      "metrics": [
        { "k": "model", "v": "gemma-4" },
        { "k": "rps", "v": "1.2" },
        { "k": "vram", "v": "18.4 / 24 GiB" }
      ],
      "spark": [
        1800, 2100, 2400, 2200, 1900, 2300, 2600, 2400, 2100, 2500, 2300, 2000,
        2400, 2700, 2300, 2100, 2400, 2500, 2200, 2000, 1900, 2200, 2400, 2300
      ]
    },
    {
      "id": "voyage-embedder",
      "label": "VOYAGE EMBEDDER",
      "tier": "critical",
      "status": "healthy",
      "description": "voyage-4 embedding",
      "brief": "100% · 3.1 rps",
      "slo": { "target": 99.9, "current": 100 },
      "latency": { "p99": 85, "target": 200, "unit": "ms" },
      "metrics": [
        { "k": "model", "v": "voyage-4" },
        { "k": "rps", "v": "3.1" },
        { "k": "vram", "v": "5.8 / 6.2 GiB" }
      ],
      "spark": [
        60, 70, 85, 75, 65, 80, 90, 80, 70, 85, 75, 65, 80, 95, 80, 70, 85, 90,
        75, 70, 65, 75, 85, 80
      ]
    },
    {
      "id": "k8s-mcp",
      "label": "K8S MCP",
      "tier": "critical",
      "status": "healthy",
      "description": "kubernetes mcp server",
      "brief": "healthy",
      "metrics": [
        { "k": "resources", "v": "pods, svc, deploy" },
        { "k": "cluster", "v": "home-cluster" }
      ]
    },
    {
      "id": "argocd-mcp",
      "label": "ARGOCD MCP",
      "tier": "critical",
      "status": "healthy",
      "description": "argocd mcp server",
      "brief": "healthy",
      "metrics": [
        { "k": "applications", "v": "14" },
        { "k": "synced", "v": "14 / 14" }
      ]
    },
    {
      "id": "signoz-mcp",
      "label": "SIGNOZ MCP",
      "tier": "critical",
      "status": "healthy",
      "description": "signoz mcp server",
      "brief": "healthy",
      "metrics": [
        { "k": "queries 24h", "v": "2.4k" },
        { "k": "p99", "v": "120ms" }
      ]
    },
    {
      "id": "argocd",
      "label": "ARGOCD",
      "tier": "infra",
      "status": "healthy",
      "description": "gitops controller",
      "brief": "14/14 synced",
      "metrics": [
        { "k": "applications", "v": "14" },
        { "k": "synced", "v": "14 / 14" },
        { "k": "last sync", "v": "12s ago" }
      ]
    },
    {
      "id": "signoz",
      "label": "SIGNOZ",
      "tier": "infra",
      "status": "warning",
      "description": "observability platform",
      "brief": "99.84% · 450 spans/s",
      "slo": { "target": 99.9, "current": 99.84 },
      "budget": {
        "consumed": 66,
        "elapsed": 40,
        "remaining": "14.7 min",
        "window": "30d"
      },
      "latency": { "p99": 320, "target": 500, "unit": "ms" },
      "metrics": [
        { "k": "spans/s", "v": "450" },
        { "k": "ingestion p99", "v": "320ms" },
        { "k": "storage", "v": "82 / 150 GiB" }
      ],
      "spark": [
        280, 310, 350, 320, 290, 340, 380, 320, 310, 340, 290, 300, 360, 340,
        320, 300, 330, 350, 320, 310, 290, 320, 340, 320
      ]
    },
    {
      "id": "envoy-gateway",
      "label": "ENVOY GATEWAY",
      "tier": "infra",
      "status": "healthy",
      "description": "api gateway",
      "brief": "healthy · 14.2k req/24h",
      "metrics": [
        { "k": "routes", "v": "8" },
        { "k": "requests 24h", "v": "14.2k" },
        { "k": "error rate", "v": "0.01%" }
      ]
    },
    {
      "id": "longhorn",
      "label": "LONGHORN",
      "tier": "infra",
      "status": "healthy",
      "description": "distributed storage",
      "brief": "340 / 1000 GiB",
      "metrics": [
        { "k": "volumes", "v": "8" },
        { "k": "replicas", "v": "healthy" },
        { "k": "used", "v": "340 / 1000 GiB" }
      ]
    },
    {
      "id": "seaweedfs",
      "label": "SEAWEEDFS",
      "tier": "infra",
      "status": "healthy",
      "description": "object storage",
      "brief": "healthy · 28 GiB",
      "metrics": [
        { "k": "buckets", "v": "4" },
        { "k": "objects", "v": "12.4k" },
        { "k": "storage", "v": "28 GiB" }
      ]
    },
    {
      "id": "otel-operator",
      "label": "OTEL OPERATOR",
      "tier": "infra",
      "status": "healthy",
      "description": "opentelemetry operator",
      "brief": "healthy · 3 collectors",
      "metrics": [
        { "k": "collectors", "v": "3" },
        { "k": "pipelines", "v": "traces, metrics, logs" }
      ]
    },
    {
      "id": "linkerd",
      "label": "LINKERD",
      "tier": "infra",
      "status": "healthy",
      "description": "service mesh",
      "brief": "healthy · 12 meshed",
      "metrics": [
        { "k": "meshed pods", "v": "12" },
        { "k": "mtls", "v": "100%" },
        { "k": "success rate", "v": "99.99%" }
      ]
    }
  ],
  "edges": [
    { "from": "cloudflare", "to": "monolith", "protocol": "https" },
    { "from": "cloudflare", "to": "context-forge", "protocol": "https" },
    { "from": "cloudflare", "to": "agent-platform", "protocol": "https" },
    { "from": "monolith", "to": "postgres", "protocol": "sql" },
    { "from": "monolith", "to": "nats", "protocol": "nats" },
    { "from": "monolith", "to": "context-forge", "protocol": "grpc" },
    { "from": "monolith", "to": "llama-cpp", "protocol": "http" },
    { "from": "monolith", "to": "voyage-embedder", "protocol": "http" },
    { "from": "nats", "to": "agent-platform", "protocol": "nats" },
    { "from": "agent-platform", "to": "context-forge", "protocol": "grpc" },
    { "from": "context-forge", "to": "k8s-mcp", "protocol": "mcp" },
    { "from": "context-forge", "to": "argocd-mcp", "protocol": "mcp" },
    { "from": "context-forge", "to": "signoz-mcp", "protocol": "mcp" }
  ]
}
```

**Step 2: Verify JSON is valid**

Run: `node -e "require('./projects/monolith/frontend/src/routes/public/observability-demo/topology.json')"`
Expected: no error

**Step 3: Commit**

```bash
git add projects/monolith/frontend/src/routes/public/observability-demo/topology.json
git commit -m "feat(observability-demo): add topology config with real homelab services"
```

---

### Task 3: Add dagre layout module

**Files:**

- Create: `projects/monolith/frontend/src/routes/public/observability-demo/layout.js`

This module takes the topology config and returns positioned nodes for a given `rankdir`. It encapsulates all dagre interaction so `+page.svelte` never imports dagre directly.

**Step 1: Write the layout module**

```javascript
import dagre from "@dagrejs/dagre";

const HH = 18; // half-height of a node (matches +page.svelte)
const CHAR_WIDTH = 6.5; // approximate monospace character width at 11px
const NODE_PAD = 12; // padding around label text

/**
 * Compute half-width from label length.
 * Ensures all nodes size to fit their uppercase label.
 */
function computeHW(label) {
  return Math.max(
    24,
    Math.ceil((label.length * CHAR_WIDTH) / 2) + NODE_PAD / 2,
  );
}

/**
 * Run dagre layout on the topology config.
 *
 * @param {Object} topology - The topology.json structure ({ nodes, edges })
 * @param {"LR"|"TB"} rankdir - Layout direction
 * @returns {{ nodes: Array<{id,label,x,y,hw,status,...}>, edges: Array, nodeById: Object }}
 */
export function computeLayout(topology, rankdir) {
  const g = new dagre.Graph();
  g.setGraph({
    rankdir,
    nodesep: rankdir === "LR" ? 40 : 50,
    ranksep: rankdir === "LR" ? 80 : 60,
    marginx: 40,
    marginy: 40,
  });
  g.setDefaultEdgeLabel(() => ({}));

  // Add all nodes with computed dimensions
  for (const node of topology.nodes) {
    const hw = computeHW(node.label);
    g.setNode(node.id, {
      width: hw * 2 + NODE_PAD,
      height: HH * 2 + 6,
      tier: node.tier,
    });
  }

  // Add edges (only critical-path edges — infra nodes are unconnected)
  for (const edge of topology.edges) {
    g.setEdge(edge.from, edge.to);
  }

  // Pin infra nodes to the last rank by adding invisible edges from an anchor
  const infraNodes = topology.nodes.filter((n) => n.tier === "infra");
  if (infraNodes.length > 0) {
    // Create an invisible anchor node at the same rank as the deepest critical node
    g.setNode("__infra_anchor", { width: 0, height: 0 });
    // Connect anchor to a deep critical node to push it down
    const lastCritical = topology.nodes
      .filter((n) => n.tier === "critical")
      .at(-1);
    if (lastCritical) {
      g.setEdge(lastCritical.id, "__infra_anchor", { minlen: 2 });
    }
    for (const n of infraNodes) {
      g.setEdge("__infra_anchor", n.id, { minlen: 1 });
    }
  }

  dagre.layout(g);

  // Build positioned nodes (exclude anchor)
  const nodes = topology.nodes.map((n) => {
    const pos = g.node(n.id);
    return {
      ...n,
      x: pos.x,
      y: pos.y,
      hw: computeHW(n.label),
    };
  });

  const nodeById = Object.fromEntries(nodes.map((n) => [n.id, n]));

  return { nodes, edges: topology.edges, nodeById };
}
```

**Step 2: Commit**

```bash
git add projects/monolith/frontend/src/routes/public/observability-demo/layout.js
git commit -m "feat(observability-demo): add dagre layout module"
```

---

### Task 4: Update +page.svelte — replace hardcoded topology with config + dagre

This is the largest task. It modifies `+page.svelte` to:

1. Import the topology config and layout module
2. Replace hardcoded `nodes`, `edges`, `nodeById`, portrait positions with dagre-computed layouts
3. Replace the `svc` metadata object with config-driven lookups
4. Update the viewBox to use dagre's computed graph dimensions
5. Update the BFS animation to use `"cloudflare"` as root (unchanged) but with dynamic node/edge lists
6. Update the brutalist color palette CSS variables

**Files:**

- Modify: `projects/monolith/frontend/src/routes/public/observability-demo/+page.svelte`

**Step 1: Replace topology section (lines 1-32)**

Remove the hardcoded `nodes`, `edges`, `nodeById`, and `HH` constant. Replace with imports:

```javascript
import rough from "roughjs";
import { fly, fade } from "svelte/transition";
import { cubicOut } from "svelte/easing";
import topology from "./topology.json";
import { computeLayout } from "./layout.js";

// ── Topology ───────────────────────────────
const HH = 18;
```

**Step 2: Replace service data section (lines 34-136)**

Remove the entire `const svc = { ... }` object. Replace with a config-driven lookup:

```javascript
// ── Service data (from config) ─────────────
const svc = Object.fromEntries(topology.nodes.map((n) => [n.id, n]));
```

This works because the topology config already has `description`, `brief`, `metrics`, `slo`, `budget`, `latency`, `spark` on each node — the same shape the drawer expects.

**Step 3: Replace layout computation (lines 7-17, 340-360)**

Remove the hardcoded `nodes` and `portraitNodes` arrays and the `getNodePos` function. Replace with dagre-computed reactive layouts:

```javascript
// ── Layout (dagre-computed) ────────────────
// Re-run dagre when orientation changes — replaces hand-tuned coordinate sets
const landLayout = computeLayout(topology, "LR");
const portLayout = computeLayout(topology, "TB");

// Expose the active layout's data
const nodes = $derived(activeLayout ? portLayout.nodes : landLayout.nodes);
const edges = $derived(activeLayout ? portLayout.edges : landLayout.edges);
const nodeById = $derived(
  activeLayout ? portLayout.nodeById : landLayout.nodeById,
);

function getNodePos(id) {
  const n = nodeById[id];
  return { x: n.x, y: n.y };
}
```

**Step 4: Replace viewBox computation (line 335)**

Remove the hardcoded viewBox strings. Compute from dagre's graph dimensions:

```javascript
const viewBox = $derived.by(() => {
  const layout = activeLayout ? portLayout : landLayout;
  // Find bounding box of all nodes
  let minX = Infinity,
    minY = Infinity,
    maxX = -Infinity,
    maxY = -Infinity;
  for (const n of layout.nodes) {
    minX = Math.min(minX, n.x - n.hw - 20);
    minY = Math.min(minY, n.y - HH - 20);
    maxX = Math.max(maxX, n.x + n.hw + 20);
    maxY = Math.max(maxY, n.y + HH + 20);
  }
  const pad = 40;
  return `${minX - pad} ${minY - pad} ${maxX - minX + pad * 2} ${maxY - minY + pad * 2}`;
});
```

**Step 5: Update aspect ratio constants**

The aspect ratio constants need to adapt to the dagre-computed graph dimensions. Replace the hardcoded `LAND_AR` and `PORT_AR`:

```javascript
const LAND_AR = $derived.by(() => {
  const ns = landLayout.nodes;
  let minX = Infinity,
    maxX = -Infinity,
    minY = Infinity,
    maxY = -Infinity;
  for (const n of ns) {
    minX = Math.min(minX, n.x - n.hw);
    maxX = Math.max(maxX, n.x + n.hw);
    minY = Math.min(minY, n.y - HH);
    maxY = Math.max(maxY, n.y + HH);
  }
  return (maxX - minX) / (maxY - minY);
});
const PORT_AR = $derived.by(() => {
  const ns = portLayout.nodes;
  let minX = Infinity,
    maxX = -Infinity,
    minY = Infinity,
    maxY = -Infinity;
  for (const n of ns) {
    minX = Math.min(minX, n.x - n.hw);
    maxX = Math.max(maxX, n.x + n.hw);
    minY = Math.min(minY, n.y - HH);
    maxY = Math.max(maxY, n.y + HH);
  }
  return (maxX - minX) / (maxY - minY);
});
```

**Step 6: Fix BFS animation timeline**

The `animDelay` IIFE (lines 458-636) references `nodes` and `edges` directly. Since those are now `$derived`, the IIFE needs to become a `$derived` or a function that recomputes when layout changes.

The simplest approach: make `animDelay` a `$derived.by()` that recomputes when `drawGen` bumps (which happens on layout flip). The existing code inside stays nearly identical — just wrap it:

```javascript
const animDelay = $derived.by(() => {
  const _gen = drawGen; // recompute on layout flip
  const _nodes = nodes;
  const _edges = edges;
  const _nodeById = nodeById;

  // ... existing BFS code, but replace bare `nodes` with `_nodes`,
  // `edges` with `_edges`, `nodeById` with `_nodeById`
  // Change the BFS start: { id: "cloudflare", fromX: 0, fromY: _nodeById["cloudflare"]?.y ?? 240 }

  // Return { node: nd, edge: ed, edgeDir: edDir, totalDur: maxT + 0.5 };
});
```

Key changes inside the BFS:

- `nodes.forEach(...)` → `_nodes.forEach(...)`
- `edges.forEach(...)` → `_edges.forEach(...)`
- `nodeById[id]` → `_nodeById[id]`
- BFS start position uses computed cloudflare position

**Step 7: Update the draw effect**

The draw effect (lines 643-848) uses `nodes` and `edges`. Since these are now `$derived`, the effect will automatically re-run when layout changes. Just ensure:

- `nodes.forEach(...)` works with the new node shape (it does — same `id`, `hw`, `status` fields)
- `nodeById[id]` lookups work (they do — same lookup)

One change needed: the fill rectangle currently uses `c.bg`. For the brutalist style, use tier-based fills:

```javascript
function tierFill(tier, c) {
  const dark = isDark;
  if (tier === "ingress") return dark ? "#1e3a5f" : "#dbeafe";
  if (tier === "infra") return dark ? "#2a2a2a" : "#e8e8e8";
  return dark ? "#3d3520" : "#fff3c4"; // critical
}
```

Update the fill rectangle in the node drawing loop:

```javascript
const fillEl = rc.rectangle(pos.x - w / 2, pos.y - h / 2, w, h, {
  stroke: "none",
  fill: tierFill(n.tier, c),
  fillStyle: "solid",
  roughness: r,
  seed: seed(n.id + "fill"),
});
```

**Step 8: Update CSS variables for brutalist palette**

The CSS variables are defined in the global `<style>` or a parent layout. Since this page uses inline theme classes, update the `:global(.theme-light)` and `:global(.theme-dark)` blocks. If these are defined elsewhere, check the parent layout. If they're in this file's `<style>`, update them here.

The key color changes:

```css
:global(.theme-light) {
  --bg: #f5f0e8; /* warm cream (was white/grey) */
  --surface: #ebe5d9; /* slightly darker cream */
  --fg: #1a1a1a; /* near-black */
  --fg-secondary: #4a4a4a;
  --fg-tertiary: #7a7a7a;
  --border: #c8c0b4; /* warm grey border */
  --danger: #dc2626;
  --font: "JetBrains Mono", "SF Mono", "Fira Code", monospace;
}

:global(.theme-dark) {
  --bg: #1a1a1a; /* deep charcoal */
  --surface: #242424;
  --fg: #e8e0d4; /* warm off-white */
  --fg-secondary: #a89f94;
  --fg-tertiary: #6e665c;
  --border: #3a3530;
  --danger: #f87171;
  --font: "JetBrains Mono", "SF Mono", "Fira Code", monospace;
}
```

**Step 9: Update node label font**

Change `.node-label` to uppercase to match the brutalist style (labels are already uppercase in the config, but add CSS `text-transform` as a safety net):

```css
.node-label {
  font-family: var(--font);
  font-size: 10px; /* slightly smaller for more nodes */
  font-weight: 800; /* extra bold */
  fill: var(--fg);
  text-anchor: middle;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  transition: opacity 0.2s ease;
}
```

**Step 10: Update Rough.js stroke widths for brutalism**

In the node drawing code, increase stroke widths for the brutalist thick-border aesthetic:

- Pencil box sides: `strokeWidth: 0.7` → `strokeWidth: 1.0`
- Ink box sides: `strokeWidth: 1` → `strokeWidth: 2`
- Edge pencil: `strokeWidth: 0.8` → `strokeWidth: 1.0`
- Edge ink: `strokeWidth: 1` → `strokeWidth: 1.5`

**Step 11: Add protocol labels on edges**

After drawing each edge, add a small text label at the midpoint showing the protocol. In the edge drawing loop (inside the `edges.forEach` in the draw effect), after appending the ink line:

```javascript
// Protocol label at edge midpoint
const midX = (startPt.x + endPt.x) / 2;
const midY = (startPt.y + endPt.y) / 2;
const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
label.textContent = e.protocol;
label.setAttribute("x", String(midX));
label.setAttribute("y", String(midY - 4));
label.setAttribute("class", "edge-protocol");
label.dataset.layer = "protocol";
if (shouldAnimate) {
  const anim = animDelay.edge[key];
  label.style.opacity = "0";
  label.style.animation = `textJot 0.2s ease ${(anim.inkLine + anim.inkLineDur * 0.5).toFixed(3)}s forwards`;
}
g.appendChild(label);
```

Add CSS for the protocol label:

```css
.edge-protocol {
  font-family: var(--font);
  font-size: 7px;
  font-weight: 600;
  fill: var(--fg-tertiary);
  text-anchor: middle;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
```

**Step 12: Verify build**

Run: `bb remote --os=linux --arch=amd64 test //projects/monolith/frontend:build_test --config=ci`
Expected: PASS

**Step 13: Commit**

```bash
git add projects/monolith/frontend/src/routes/public/observability-demo/+page.svelte
git commit -m "feat(observability-demo): config-driven dagre layout with brutalist palette"
```

---

### Task 5: Visual verification

**Step 1: Run dev server**

Run: `cd /tmp/claude-worktrees/observability-dag-redesign/projects/monolith/frontend && pnpm dev`
Open: `http://localhost:5173/public/observability-demo`

**Step 2: Verify visually**

Check:

- [ ] All 19 nodes render without overlap
- [ ] Cloudflare is at the left/top entry point
- [ ] Critical path flows left-to-right (landscape) or top-to-bottom (portrait)
- [ ] Infra nodes cluster at the bottom/right, visually separated
- [ ] Warm cream background in light mode, charcoal in dark mode
- [ ] Tier-based node fills: yellow (critical), grey (infra), blue (cloudflare)
- [ ] Thick Rough.js borders (brutalist style)
- [ ] Protocol labels on edges (https, sql, nats, grpc, http, mcp)
- [ ] BFS draw animation plays from cloudflare outward
- [ ] Paper-flip transition works between portrait/landscape
- [ ] Click on any node opens the drawer with correct metadata
- [ ] Dark mode toggle works and recolors all elements
- [ ] Scribble highlight appears on hover/select

**Step 3: Fix any layout issues**

If dagre produces a layout that's too wide/tall or has awkward spacing, tune the `nodesep` and `ranksep` values in `layout.js`. If infra nodes overlap with critical path nodes, increase the `minlen` on the anchor edge.

**Step 4: Commit any fixes**

```bash
git add -u
git commit -m "fix(observability-demo): tune dagre layout spacing"
```

---

### Task 6: Push and create PR

**Step 1: Push branch**

```bash
cd /tmp/claude-worktrees/observability-dag-redesign
git push -u origin feat/observability-dag-redesign
```

**Step 2: Create PR**

```bash
gh pr create --title "feat(observability-demo): config-driven DAG with real services" --body "$(cat <<'EOF'
## Summary
- Replace hardcoded 9-node topology with 19-node config-driven DAG reflecting actual homelab architecture
- Add dagre for automatic graph layout (replaces hand-tuned coordinates)
- Three tiers: ingress (Cloudflare), critical path (monolith → postgres/NATS/context-forge/agent-platform/llama-cpp/voyage-embedder), infrastructure (ArgoCD, SigNoz, Envoy Gateway, Longhorn, SeaweedFS, OTel Operator, Linkerd)
- MotherDuck-inspired brutalist palette: warm cream background, thick borders, bold monospace, tier-based fills
- Protocol labels on edges (https, sql, nats, grpc, http, mcp)
- All existing animations preserved: BFS draw, pencil→ink dual-pass, scribble highlight, paper-flip transition

## Test plan
- [ ] Visual verification at `/public/observability-demo`
- [ ] Landscape and portrait layouts render correctly
- [ ] Dark mode toggle works
- [ ] Node click opens drawer with correct metadata
- [ ] CI build passes

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Step 3: Wait for CI**

Run: `gh pr checks --watch`
Expected: All checks pass
