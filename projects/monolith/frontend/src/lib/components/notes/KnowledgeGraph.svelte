<script>
  // Force-directed knowledge graph rendered to a canvas. Ported from the
  // single-file prototype: d3 force sim, quadtree hit-testing, zoom/pan
  // with click-vs-drag detection, viewport-aware zoom-to-node, and
  // greedy-collision label drawing. The component is purely the graph
  // surface — search box, legend, side panel, and status bar live in
  // sibling components and drive this one via props/events.

  import { onMount, onDestroy } from "svelte";
  import {
    forceSimulation,
    forceLink,
    forceManyBody,
    forceCollide,
    forceX,
    forceY,
  } from "d3-force";
  import { select } from "d3-selection";
  import { zoom as d3Zoom, zoomIdentity } from "d3-zoom";
  import { quadtree as d3Quadtree } from "d3-quadtree";
  import { colorFor, CLUSTER_COLORS } from "./clusters.js";

  /**
   * @typedef {{ id: string, title: string, type: string, degree: number }} Node
   * @typedef {{ source: string, target: string, kind?: string, edge_type?: string }} Edge
   */

  /** @type {{
   *   nodes?: Node[],
   *   edges?: Edge[],
   *   selectedId?: string | null,
   *   searchTerm?: string,
   *   activeClusters?: Set<string>,
   * }} */
  let {
    nodes = [],
    edges = [],
    selectedId = null,
    searchTerm = "",
    activeClusters = new Set(),
    onNodeClick = () => {},
    onNodeHover = () => {},
    onZoom = () => {},
  } = $props();

  // Force-sim tuning lifted from the prototype.
  const CFG = {
    linkDistance: 26,
    charge: -34,
    collidePad: 1.8,
    baseRadius: 3.2,
    hubBoost: 0.55,
    edgeOpacity: 0.16,
    edgeOpacityActive: 0.85,
    labelMinZoom: 1.2,
    labelMaxCount: 60,
  };

  // Used by applyFilters() to scale forces when a cluster is hidden.
  // Derived from CLUSTER_COLORS rather than hardcoded so adding a new
  // cluster CSS var is enough — no graph code change required.
  const CLUSTER_COUNT = Math.max(
    1,
    new Set(Object.values(CLUSTER_COLORS)).size,
  );

  // Internal mutable state. simNodes/simEdges are the d3-mutated copies
  // (positions, velocities, resolved source/target object refs).
  let stage; // root div
  let canvas; // <canvas>
  let ctx; // 2d context
  let dpr = 1;
  let resizeObserver;
  let simulation;
  let quadtree;
  let transform = zoomIdentity;
  let zoomBehavior;

  let simNodes = [];
  let simEdges = [];
  let byId = new Map();
  let neighborsOf = new Map();

  // Resolved cluster colours — concrete hex/rgb strings looked up from
  // CSS custom properties at mount time. Canvas can't consume var(...),
  // so we resolve once and hand it to the renderer.
  /** @type {Record<string, string>} */
  let resolved = {};

  // Hovered node (transient, internal). Selection is a prop.
  let hovered = $state(null);
  let panning = $state(false);
  let overNode = $state(false);

  let mouseDownAt = null;
  let didMove = false;

  // ───────────────────────── helpers ─────────────────────────

  function resolveColors() {
    const styles = getComputedStyle(document.documentElement);
    const out = {};
    for (const [type, varRef] of Object.entries(CLUSTER_COLORS)) {
      // varRef looks like 'var(--cluster-atom)'. Extract the variable name.
      const m = varRef.match(/var\((--[^)]+)\)/);
      const cssVar = m ? m[1] : null;
      const value = cssVar ? styles.getPropertyValue(cssVar).trim() : "";
      out[type] = value || "#888";
    }
    // Also resolve --cluster-other for unknown types.
    out.__other = styles.getPropertyValue("--cluster-other").trim() || "#888";
    return out;
  }

  function colorForResolved(type) {
    if (resolved[type]) return resolved[type];
    return resolved.__other ?? "#888";
  }

  function radiusFor(degree) {
    return CFG.baseRadius + CFG.hubBoost * Math.log2(1 + (degree || 0));
  }

  function rebuildGraph() {
    // Build mutable copies — d3-force mutates x/y/vx/vy in place and
    // forceLink replaces source/target strings with object refs.
    simNodes = nodes.map((n) => ({
      id: n.id,
      title: n.title,
      cluster: n.type,
      degree: n.degree ?? 0,
      r: radiusFor(n.degree ?? 0),
      color: colorForResolved(n.type),
      x: 0,
      y: 0,
    }));
    simEdges = edges.map((e) => ({
      source: e.source,
      target: e.target,
      kind: e.kind ?? e.edge_type ?? null,
    }));
    byId = new Map(simNodes.map((n) => [n.id, n]));
    neighborsOf = new Map(simNodes.map((n) => [n.id, new Set()]));
    for (const e of simEdges) {
      // edges still hold string ids at this point (forceLink resolves later)
      const s = neighborsOf.get(e.source);
      const t = neighborsOf.get(e.target);
      if (s) s.add(e.target);
      if (t) t.add(e.source);
    }
  }

  function resize() {
    if (!stage || !canvas) return;
    const w = stage.clientWidth;
    const h = stage.clientHeight;
    canvas.width = Math.max(1, Math.floor(w * dpr));
    canvas.height = Math.max(1, Math.floor(h * dpr));
    canvas.style.width = w + "px";
    canvas.style.height = h + "px";
    if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function rebuildQuadtree() {
    quadtree = d3Quadtree()
      .x((d) => d.x)
      .y((d) => d.y)
      .addAll(simNodes);
  }

  function findNode(mx, my) {
    if (!quadtree) return null;
    const [x, y] = transform.invert([mx, my]);
    const r = 14 / transform.k;
    const n = quadtree.find(x, y, r);
    return n && activeClusters.has(n.cluster) ? n : null;
  }

  // ───────────────────────── render ─────────────────────────

  function render() {
    if (!ctx || !stage) return;
    const w = stage.clientWidth;
    const h = stage.clientHeight;
    ctx.clearRect(0, 0, w, h);

    ctx.save();
    ctx.translate(transform.x, transform.y);
    ctx.scale(transform.k, transform.k);

    const term = (searchTerm || "").trim().toLowerCase();
    const selectedNode = selectedId ? byId.get(selectedId) : null;
    const filtering = !!term || !!selectedNode;
    const matchSet = new Set();
    if (term) {
      for (const n of simNodes) {
        if (
          activeClusters.has(n.cluster) &&
          n.title.toLowerCase().includes(term)
        ) {
          matchSet.add(n.id);
        }
      }
    } else if (selectedNode) {
      matchSet.add(selectedNode.id);
      const neigh = neighborsOf.get(selectedNode.id);
      if (neigh) for (const id of neigh) matchSet.add(id);
    }

    // Edges (faint).
    ctx.lineWidth = Math.max(0.4, 0.7 / transform.k);
    ctx.strokeStyle = `rgba(20,20,20,${CFG.edgeOpacity})`;
    ctx.beginPath();
    for (const l of simEdges) {
      const s = typeof l.source === "object" ? l.source : byId.get(l.source);
      const t = typeof l.target === "object" ? l.target : byId.get(l.target);
      if (!s || !t) continue;
      if (!activeClusters.has(s.cluster) || !activeClusters.has(t.cluster))
        continue;
      if (filtering && !(matchSet.has(s.id) && matchSet.has(t.id))) continue;
      ctx.moveTo(s.x, s.y);
      ctx.lineTo(t.x, t.y);
    }
    ctx.stroke();

    // Highlighted edges around the selected node.
    if (selectedNode) {
      ctx.lineWidth = Math.max(1.2, 1.6 / transform.k);
      ctx.strokeStyle = `rgba(20,20,20,${CFG.edgeOpacityActive})`;
      ctx.beginPath();
      for (const l of simEdges) {
        const s = typeof l.source === "object" ? l.source : byId.get(l.source);
        const t = typeof l.target === "object" ? l.target : byId.get(l.target);
        if (!s || !t) continue;
        if (s.id === selectedNode.id || t.id === selectedNode.id) {
          ctx.moveTo(s.x, s.y);
          ctx.lineTo(t.x, t.y);
        }
      }
      ctx.stroke();
    }

    // Nodes.
    ctx.lineWidth = Math.max(0.6, 1.2 / transform.k);
    for (const n of simNodes) {
      if (!activeClusters.has(n.cluster)) continue;
      const dim = filtering && !matchSet.has(n.id);
      ctx.globalAlpha = dim ? 0.08 : 1;
      ctx.fillStyle = n.color;
      ctx.strokeStyle = "#141414";
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    }
    ctx.globalAlpha = 1;

    // Hover ring.
    if (hovered) {
      ctx.strokeStyle = "#141414";
      ctx.lineWidth = Math.max(1, 1.6 / transform.k);
      ctx.beginPath();
      ctx.arc(
        hovered.x,
        hovered.y,
        hovered.r + 3 / transform.k,
        0,
        Math.PI * 2,
      );
      ctx.stroke();
    }

    // Selected box — uses --accent (blue) per the public site palette.
    if (selectedNode) {
      const s = selectedNode.r + 6 / transform.k;
      const accent =
        getComputedStyle(document.documentElement)
          .getPropertyValue("--accent")
          .trim() || "#3a6df0";
      ctx.strokeStyle = accent;
      ctx.lineWidth = Math.max(1.5, 2 / transform.k);
      ctx.strokeRect(selectedNode.x - s, selectedNode.y - s, s * 2, s * 2);
    }

    ctx.restore();

    drawLabels(w, h, filtering, matchSet, selectedNode);

    rebuildQuadtree();
  }

  function drawLabels(w, h, filtering, matchSet, selectedNode) {
    const candidates = [];
    const seen = new Set();
    const term = (searchTerm || "").trim().toLowerCase();
    const add = (n) => {
      if (n && !seen.has(n.id) && activeClusters.has(n.cluster)) {
        seen.add(n.id);
        candidates.push(n);
      }
    };

    if (selectedNode) {
      add(selectedNode);
      const neigh = neighborsOf.get(selectedNode.id);
      if (neigh) for (const id of neigh) add(byId.get(id));
    }
    add(hovered);

    if (transform.k > CFG.labelMinZoom) {
      const [x0, y0] = transform.invert([0, 0]);
      const [x1, y1] = transform.invert([w, h]);
      const vis = [];
      for (const n of simNodes) {
        if (!activeClusters.has(n.cluster)) continue;
        if (filtering && !matchSet.has(n.id)) continue;
        if (n.x < x0 || n.x > x1 || n.y < y0 || n.y > y1) continue;
        vis.push(n);
      }
      vis.sort((a, b) => b.degree - a.degree);
      for (const n of vis) {
        add(n);
        if (candidates.length > 250) break;
      }
    } else if (filtering && term) {
      const [x0, y0] = transform.invert([0, 0]);
      const [x1, y1] = transform.invert([w, h]);
      const vis = simNodes
        .filter(
          (n) =>
            matchSet.has(n.id) &&
            n.x >= x0 &&
            n.x <= x1 &&
            n.y >= y0 &&
            n.y <= y1,
        )
        .sort((a, b) => b.degree - a.degree)
        .slice(0, 30);
      for (const n of vis) add(n);
    }

    const placed = [];
    const fontPx = 11;
    ctx.font = `500 ${fontPx}px JetBrains Mono, ui-monospace, monospace`;
    ctx.textBaseline = "top";

    let drawn = 0;
    for (const n of candidates) {
      if (drawn >= CFG.labelMaxCount && n !== selectedNode && n !== hovered)
        continue;

      const sx = n.x * transform.k + transform.x;
      const sy = n.y * transform.k + transform.y;
      const t = n.title;
      const m = ctx.measureText(t);
      const padX = 4;
      const padY = 3;
      const bw = m.width + padX * 2;
      const bh = fontPx + padY * 2;
      const bx = sx + n.r * transform.k + 5;
      const by = sy - bh / 2;

      if (bx + bw < 0 || bx > w || by + bh < 0 || by > h) continue;

      let overlap = false;
      for (const p of placed) {
        if (
          bx < p.bx + p.bw &&
          bx + bw > p.bx &&
          by < p.by + p.bh &&
          by + bh > p.by
        ) {
          overlap = true;
          break;
        }
      }
      const force = n === selectedNode || n === hovered;
      if (overlap && !force) continue;
      placed.push({ bx, by, bw, bh });

      ctx.fillStyle = "#FFFFFF";
      ctx.fillRect(bx, by, bw, bh);
      ctx.lineWidth = 1;
      ctx.strokeStyle = "#141414";
      ctx.strokeRect(bx + 0.5, by + 0.5, bw - 1, bh - 1);
      ctx.fillStyle = "#141414";
      ctx.fillText(t, bx + padX, by + padY);
      drawn++;
    }
  }

  // ───────────────────────── focus / filter ─────────────────────────

  function focusNode(n) {
    if (!n || !zoomBehavior || !canvas || !stage) return;
    const w = stage.clientWidth;
    const h = stage.clientHeight;
    const m = 20;

    // Without surrounding UI metrics, just use a centred viewport box.
    // The parent component is responsible for placing the search box,
    // legend, and panel; viewport-padding here keeps the focus pleasant
    // even when those overlay it.
    const left = m;
    const right = w - m;
    const top = m;
    const bottom = h - m;
    const acx = (left + right) / 2;
    const acy = (top + bottom) / 2;

    let x0 = n.x;
    let x1 = n.x;
    let y0 = n.y;
    let y1 = n.y;
    let count = 0;
    const neigh = neighborsOf.get(n.id);
    if (neigh) {
      for (const id of neigh) {
        const nb = byId.get(id);
        if (!nb || !activeClusters.has(nb.cluster)) continue;
        if (nb.x < x0) x0 = nb.x;
        if (nb.x > x1) x1 = nb.x;
        if (nb.y < y0) y0 = nb.y;
        if (nb.y > y1) y1 = nb.y;
        count++;
      }
    }
    const bw = Math.max(60, x1 - x0);
    const bh = Math.max(60, y1 - y0);
    const pad = 40;
    const fitK = Math.min(
      Math.max(60, right - left - pad * 2) / bw,
      Math.max(60, bottom - top - pad * 2) / bh,
    );
    const k = count === 0 ? 3 : Math.max(0.6, Math.min(3.5, fitK));
    const cx = (x0 + x1) / 2;
    const cy = (y0 + y1) / 2;

    select(canvas)
      .transition()
      .duration(650)
      .call(
        zoomBehavior.transform,
        zoomIdentity.translate(acx, acy).scale(k).translate(-cx, -cy),
      );
  }

  function applyFilters() {
    if (!simulation) return;
    const activeLinks = simEdges.filter((l) => {
      const s = typeof l.source === "object" ? l.source : byId.get(l.source);
      const t = typeof l.target === "object" ? l.target : byId.get(l.target);
      return (
        s && t && activeClusters.has(s.cluster) && activeClusters.has(t.cluster)
      );
    });
    let activeCount = 0;

    for (const n of simNodes) {
      const isActive = activeClusters.has(n.cluster);
      if (isActive) {
        activeCount++;
        if (n._parked) {
          n.x = n._parkedX;
          n.y = n._parkedY;
          n.vx = 0;
          n.vy = 0;
          n._parked = false;
        }
        n.fx = null;
        n.fy = null;
      } else {
        if (!n._parked) {
          n._parkedX = n.x;
          n._parkedY = n.y;
          n._parked = true;
        }
        n.fx = -1e6;
        n.fy = -1e6;
      }
    }

    const factor = Math.min(
      4.5,
      CLUSTER_COUNT / Math.max(1, activeClusters.size || 1),
    );

    simulation
      .force("charge")
      .strength(CFG.charge * factor);
    simulation.force(
      "link",
      forceLink(activeLinks)
        .id((d) => d.id)
        .distance(CFG.linkDistance * factor)
        .strength(0.45 / Math.sqrt(factor)),
    );

    if (activeCount > 0 && stage) {
      let sumX = 0;
      let sumY = 0;
      for (const node of simNodes) {
        if (!activeClusters.has(node.cluster)) continue;
        sumX += node.x;
        sumY += node.y;
      }
      const dx = stage.clientWidth / 2 - sumX / activeCount;
      const dy = stage.clientHeight / 2 - sumY / activeCount;
      for (const node of simNodes) {
        if (!activeClusters.has(node.cluster)) continue;
        node.x += dx;
        node.y += dy;
      }
    }

    simulation.alpha(0.6).restart();
  }

  // ───────────────────────── pointer handlers ─────────────────────────

  function handleMouseDown(e) {
    const r = canvas.getBoundingClientRect();
    const mx = e.clientX - r.left;
    const my = e.clientY - r.top;
    mouseDownAt = { mx, my, node: findNode(mx, my) };
    didMove = false;
  }

  function handleMouseMove(e) {
    if (!canvas) return;
    const r = canvas.getBoundingClientRect();
    const mx = e.clientX - r.left;
    const my = e.clientY - r.top;
    if (
      mouseDownAt &&
      Math.hypot(mx - mouseDownAt.mx, my - mouseDownAt.my) > 4
    ) {
      didMove = true;
    }

    if (e.target === canvas && !mouseDownAt) {
      const n = findNode(mx, my);
      if (n !== hovered) {
        hovered = n;
        overNode = !!n;
        onNodeHover(
          n ? { id: n.id, title: n.title } : { id: null, title: null },
        );
        render();
      }
    }
  }

  function handleMouseUp(e) {
    if (mouseDownAt && !didMove) {
      if (mouseDownAt.node) {
        onNodeClick({ id: mouseDownAt.node.id });
      } else if (e.target === canvas) {
        onNodeClick({ id: null });
      }
    }
    mouseDownAt = null;
    panning = false;
  }

  function handleMouseLeave() {
    if (hovered) {
      hovered = null;
      overNode = false;
      onNodeHover({ id: null, title: null });
      render();
    }
  }

  // ───────────────────────── lifecycle ─────────────────────────

  onMount(() => {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    ctx = canvas.getContext("2d");
    resolved = resolveColors();

    rebuildGraph();
    resize();

    simulation = forceSimulation(simNodes)
      .force(
        "link",
        forceLink(simEdges)
          .id((d) => d.id)
          .distance(CFG.linkDistance)
          .strength(0.45),
      )
      .force(
        "charge",
        forceManyBody().strength(CFG.charge).theta(0.95).distanceMax(400),
      )
      .force(
        "collide",
        forceCollide()
          .radius((d) => d.r + CFG.collidePad)
          .strength(0.7),
      )
      .force("x", forceX(stage.clientWidth / 2).strength(0.02))
      .force("y", forceY(stage.clientHeight / 2).strength(0.02))
      .velocityDecay(0.5)
      .alphaDecay(0.018);

    for (let i = 0; i < 220; i++) simulation.tick();
    simulation.on("tick", render);

    rebuildQuadtree();

    zoomBehavior = d3Zoom()
      .scaleExtent([0.15, 8])
      .filter((event) => {
        if (event.type === "wheel") return !event.ctrlKey;
        if (event.type === "mousedown" || event.type === "touchstart") {
          const r = canvas.getBoundingClientRect();
          const mx =
            (event.clientX ?? event.touches?.[0]?.clientX ?? 0) - r.left;
          const my =
            (event.clientY ?? event.touches?.[0]?.clientY ?? 0) - r.top;
          return !findNode(mx, my);
        }
        return true;
      })
      .on("zoom", (e) => {
        transform = e.transform;
        onZoom(transform.k);
        if (e.sourceEvent && e.sourceEvent.type === "mousemove") {
          panning = true;
        }
        render();
      })
      .on("end", () => {
        panning = false;
      });

    select(canvas).call(zoomBehavior);

    canvas.addEventListener("mousedown", handleMouseDown);
    canvas.addEventListener("mousemove", handleMouseMove);
    canvas.addEventListener("mouseleave", handleMouseLeave);
    window.addEventListener("mouseup", handleMouseUp);

    resizeObserver = new ResizeObserver(() => {
      resize();
      render();
    });
    resizeObserver.observe(stage);

    // Settle the sim a touch — same trick the prototype uses to avoid
    // the layout looking frozen on first paint after pre-ticks.
    setTimeout(() => simulation.alphaTarget(0).alpha(0.05).restart(), 100);

    // Initial render with seeded positions before ticks fire.
    render();
  });

  onDestroy(() => {
    if (simulation) {
      simulation.on("tick", null);
      simulation.stop();
    }
    if (resizeObserver) resizeObserver.disconnect();
    if (canvas) {
      canvas.removeEventListener("mousedown", handleMouseDown);
      canvas.removeEventListener("mousemove", handleMouseMove);
      canvas.removeEventListener("mouseleave", handleMouseLeave);
    }
    if (typeof window !== "undefined") {
      window.removeEventListener("mouseup", handleMouseUp);
    }
  });

  // ───────────────────────── reactive effects ─────────────────────────

  // Rebuild the graph and restart the sim when nodes/edges change.
  // Tracked via referential identity — the parent should pass new array
  // refs when the data set actually changes.
  $effect(() => {
    // touch nodes/edges to register the dependency
    nodes;
    edges;
    if (!simulation || !ctx) return;
    rebuildGraph();
    simulation.nodes(simNodes);
    simulation.force(
      "link",
      forceLink(simEdges)
        .id((d) => d.id)
        .distance(CFG.linkDistance)
        .strength(0.45),
    );
    simulation.alpha(0.6).restart();
    rebuildQuadtree();
    render();
  });

  // React to selection changes — the parent owns selectedId; we just
  // animate the viewport to it. Falsy selectedId is a no-op (the parent
  // handles closing the panel).
  $effect(() => {
    if (!simulation) return;
    if (!selectedId) {
      render();
      return;
    }
    const target = byId.get(selectedId);
    if (target) focusNode(target);
    render();
  });

  // Cluster toggle reflows the layout.
  $effect(() => {
    activeClusters; // dependency
    if (!simulation) return;
    applyFilters();
    render();
  });

  // Search-term changes only need a re-render; render() reads the prop
  // directly to compute the dim mask.
  $effect(() => {
    searchTerm; // dependency
    if (!ctx) return;
    render();
  });
</script>

<div class="stage" bind:this={stage}>
  <canvas
    bind:this={canvas}
    class:panning
    class:over-node={overNode}
  ></canvas>
</div>

<style>
  .stage {
    position: relative;
    width: 100%;
    height: 100%;
    overflow: hidden;
    background: var(--bg);
  }
  .stage::before {
    content: "";
    position: absolute;
    inset: 0;
    background-image: radial-gradient(rgba(0, 0, 0, 0.07) 1px, transparent 1px);
    background-size: 24px 24px;
    pointer-events: none;
  }
  canvas {
    display: block;
    cursor: grab;
  }
  canvas.panning {
    cursor: grabbing;
  }
  canvas.over-node {
    cursor: pointer;
  }
</style>
