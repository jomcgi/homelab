<script>
  import rough from "roughjs";
  import { fly, fade } from "svelte/transition";
  import { cubicOut } from "svelte/easing";
  import topology from "./topology.json";
  import { computeLayout } from "./layout.js";

  // ── Topology (config-driven) ─────────────
  const HH = 18;
  const landLayout = computeLayout(topology, "LR");
  const portLayout = computeLayout(topology, "TB");

  // ── Service data (from config) ─────────────
  const svc = Object.fromEntries(topology.nodes.map((n) => [n.id, n]));

  // ── State ──────────────────────────────────
  let selected = $state(null);
  let hovered = $state(null);
  let drawing = $state(true);
  let drawStartTime = 0;
  let drawTimer = null;
  let scribbleG = $state(null); // overlay group for scribble-out effect
  let mapSvg = $state(null);
  let roughEdges = $state(null);
  let roughNodes = $state(null);
  let tooltipRough = $state(null);
  let sparkSvg = $state(null);
  let sparkRoughG = $state(null);
  let budgetSvg = $state(null);
  let budgetRoughG = $state(null);
  let drawerBorderSvg = $state(null);
  let drawerBorderG = $state(null);
  let hoverBorderG = $state(null);
  let roughArrows = $state(null);
  let mapPanG = $state(null);
  const active = $derived(hovered || selected);

  let isDark = $state((() => {
    const stored = localStorage.getItem("theme");
    const dark = stored !== null ? stored === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
    // Apply synchronously to prevent flash on first render
    document.documentElement.classList.toggle("theme-dark", dark);
    document.documentElement.classList.toggle("theme-light", !dark);
    return dark;
  })());
  $effect(() => {
    // Keep in sync on subsequent toggles
    document.documentElement.classList.toggle("theme-dark", isDark);
    document.documentElement.classList.toggle("theme-light", !isDark);
    localStorage.setItem("theme", isDark ? "dark" : "light");
  });
  function toggleTheme() {
    isDark = !isDark;
  }

  // ── Responsive layout ────────────────────
  let containerW = $state(960);
  let containerH = $state(700);

  // Use window dimensions (not element dimensions) to avoid
  // feedback loops when CSS 3D transforms change element size
  $effect(() => {
    function onResize() {
      containerW = window.innerWidth;
      containerH = window.innerHeight;
    }
    onResize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  });

  // Pick layout that minimizes whitespace by matching container aspect ratio
  function computeAR(layout) {
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (const n of layout.nodes) {
      minX = Math.min(minX, n.x - n.hw); maxX = Math.max(maxX, n.x + n.hw);
      minY = Math.min(minY, n.y - HH); maxY = Math.max(maxY, n.y + HH);
    }
    return (maxX - minX) / (maxY - minY);
  }
  const LAND_AR = computeAR(landLayout);
  const PORT_AR = computeAR(portLayout);
  const isPortrait = $derived.by(() => {
    const ar = containerW / containerH;
    return Math.abs(ar - PORT_AR) < Math.abs(ar - LAND_AR);
  });

  // activeLayout is what rough.js is currently rendering.
  // It lags behind isPortrait during the paper-turn transition.
  let activeLayout = $state((() => {
    const ar = window.innerWidth / window.innerHeight;
    return Math.abs(ar - PORT_AR) < Math.abs(ar - LAND_AR);
  })()); // matches initial isPortrait so no spurious flip

  const nodes = $derived(activeLayout ? portLayout.nodes : landLayout.nodes);
  const edges = $derived(activeLayout ? portLayout.edges : landLayout.edges);
  const nodeById = $derived(activeLayout ? portLayout.nodeById : landLayout.nodeById);

  let flipPhase = $state("none");   // "none" | "out" | "in"
  let scribbling = $state(false);   // true during scribble-out + fade
  let flipTimer = null;
  const FLIP_HALF = 300; // ms per half-turn
  // Initialize to current layout so first $effect run is a no-op (no spurious flip on mount)
  let lastFlipTarget = (() => {
    const ar = window.innerWidth / window.innerHeight;
    return Math.abs(ar - PORT_AR) < Math.abs(ar - LAND_AR);
  })();
  let drawGen = $state(0);
  const SCRIBBLE_DUR = 450; // ms — scribble lines draw across content
  const FADE_DUR = 350;     // ms — content fades out after scribble

  function doScribbleOut() {
    if (!scribbleG || !mapSvg) return;
    clearChildren(scribbleG);
    const c = colors();
    const rc = rough.svg(mapSvg);
    const vb = viewBox.split(" ").map(Number);
    const [vx, vy, vw, vh] = vb;
    const margin = 20;
    const now = Date.now();

    // Random jitter helper — different every time
    function j(i, axis) {
      const h = seed("scr" + i + axis + now);
      return ((h % 80) - 40); // ±40 SVG units
    }

    // 12 scratchy lines with jittered endpoints — chaotic cross-hatch
    const lines = [];
    for (let i = 0; i < 12; i++) {
      // Alternate between diagonal directions for cross-hatch feel
      const flip = i % 3;
      let x1, y1, x2, y2;
      if (flip === 0) {
        // top-left to bottom-right
        x1 = vx + margin + j(i,"x1"); y1 = vy + vh * (0.1 + (i * 0.07) % 0.5) + j(i,"y1");
        x2 = vx + vw - margin + j(i,"x2"); y2 = vy + vh * (0.4 + (i * 0.05) % 0.5) + j(i,"y2");
      } else if (flip === 1) {
        // top-right to bottom-left
        x1 = vx + vw - margin + j(i,"x1"); y1 = vy + vh * (0.05 + (i * 0.06) % 0.4) + j(i,"y1");
        x2 = vx + margin + j(i,"x2"); y2 = vy + vh * (0.5 + (i * 0.04) % 0.45) + j(i,"y2");
      } else {
        // more horizontal zigzag
        x1 = vx + vw * (0.1 + (i * 0.08) % 0.3) + j(i,"x1"); y1 = vy + vh * (0.3 + (i * 0.09) % 0.5) + j(i,"y1");
        x2 = vx + vw * (0.6 + (i * 0.05) % 0.35) + j(i,"x2"); y2 = vy + vh * (0.2 + (i * 0.07) % 0.6) + j(i,"y2");
      }
      lines.push([x1, y1, x2, y2]);
    }

    lines.forEach((coords, i) => {
      const el = rc.line(coords[0], coords[1], coords[2], coords[3], {
        stroke: c.danger,
        roughness: 2.5 + (seed("scr-r" + i + now) % 20) / 10,
        bowing: 1.5 + (seed("scr-b" + i + now) % 15) / 10,
        strokeWidth: 1 + (seed("scr-w" + i + now) % 10) / 10,
        seed: seed("scribble" + i + now),
      });
      const stagger = i * 0.03;
      el.querySelectorAll("path").forEach((path) => {
        try {
          const len = path.getTotalLength();
          path.style.strokeDasharray = String(len);
          path.style.strokeDashoffset = String(len);
          path.style.animation = `edgeDraw ${SCRIBBLE_DUR * 0.001}s ease-out ${stagger}s forwards`;
        } catch { /* ignore */ }
      });
      el.style.opacity = String(0.4 + (seed("scr-o" + i + now) % 30) / 100);
      scribbleG.appendChild(el);
    });
  }

  function resetTransitionState() {
    // Kill all in-flight timers and animation state
    if (flipTimer) { clearTimeout(flipTimer); flipTimer = null; }
    if (drawTimer) { clearTimeout(drawTimer); drawTimer = null; }
    scribbling = false;
    flipPhase = "none";
    if (scribbleG) clearChildren(scribbleG);
  }

  function startFlip(target) {
    // Clean up any in-progress transition first
    resetTransitionState();

    const wasMidDraw = drawing;

    if (wasMidDraw) {
      // Phase 0: scribble lines draw across existing content
      scribbling = true;
      doScribbleOut();

      flipTimer = setTimeout(() => {
        // Phase 1: after scribble, fade out (CSS handles the opacity)
        flipTimer = setTimeout(() => {
          // Phase 2: swap layout, full reset, start fresh
          scribbling = false;
          if (scribbleG) clearChildren(scribbleG);
          activeLayout = target;
          hasAnimated = false;
          drawStartTime = 0;
          drawing = true;
          drawGen++;
        }, FADE_DUR);
      }, SCRIBBLE_DUR);
    } else {
      // Already done drawing — paper turn flip
      flipPhase = "out";
      flipTimer = setTimeout(() => {
        activeLayout = target;
        drawGen++;
        flipPhase = "in";
        flipTimer = setTimeout(() => {
          flipPhase = "none";
        }, FLIP_HALF);
      }, FLIP_HALF);
    }
  }

  // Only track isPortrait — everything else is untracked
  $effect(() => {
    const target = isPortrait;
    if (target === lastFlipTarget) return;
    lastFlipTarget = target;
    startFlip(target);
  });

  const viewBox = $derived.by(() => {
    const layout = activeLayout ? portLayout : landLayout;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const n of layout.nodes) {
      minX = Math.min(minX, n.x - n.hw - 20);
      minY = Math.min(minY, n.y - HH - 20);
      maxX = Math.max(maxX, n.x + n.hw + 20);
      maxY = Math.max(maxY, n.y + HH + 20);
    }
    const pad = 40;
    return `${minX - pad} ${minY - pad} ${maxX - minX + pad * 2} ${maxY - minY + pad * 2}`;
  });

  function getNodePos(id) {
    return nodeById[id];
  }


  // ── Helpers ────────────────────────────────
  function seed(s) {
    let h = 0;
    for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
    return Math.abs(h) || 1;
  }

  function clearChildren(el) {
    while (el.firstChild) el.removeChild(el.firstChild);
  }

  function colors() {
    const s = getComputedStyle(document.documentElement);
    return {
      fg: s.getPropertyValue("--fg").trim(),
      fgSec: s.getPropertyValue("--fg-secondary").trim(),
      fgTer: s.getPropertyValue("--fg-tertiary").trim(),
      bg: s.getPropertyValue("--bg").trim(),
      border: s.getPropertyValue("--border").trim(),
      borderInk: s.getPropertyValue("--border-ink").trim(),
      surface: s.getPropertyValue("--surface").trim(),
      danger: s.getPropertyValue("--danger").trim(),
      warn: s.getPropertyValue("--warn").trim(),
      tierIngress: s.getPropertyValue("--tier-ingress").trim(),
      tierCritical: s.getPropertyValue("--tier-critical").trim(),
      tierInfra: s.getPropertyValue("--tier-infra").trim(),
      tooltipBg: s.getPropertyValue("--tooltip-bg").trim(),
    };
  }

  function isHighlighted(nodeId) {
    const src = hovered || selected;
    if (!src) return true;
    return nodeId === src;
  }

  function nodeDrawn(id) {
    if (!drawing) return true;
    if (!drawStartTime) return false;
    const elapsed = (performance.now() - drawStartTime) / 1000;
    return elapsed >= animDelay.node[id].box;
  }

  function selectNode(id) {
    if (!nodeDrawn(id)) return;
    selected = selected === id ? null : id;
  }

  function statusColor(s) {
    const c = colors();
    if (s === "warning") return c.warn;
    if (s === "degraded") return c.danger;
    return c.fg;
  }

  function budgetColor(consumed, elapsed) {
    const c = colors();
    if (consumed > elapsed * 1.5) return c.danger;
    if (consumed > elapsed) return c.warn;
    return c.fgTer;
  }

  function boxExit(cx, cy, hw, hh, tx, ty) {
    const dx = tx - cx;
    const dy = ty - cy;
    if (dx === 0 && dy === 0) return { x: cx, y: cy };
    const sx = dx !== 0 ? hw / Math.abs(dx) : Infinity;
    const sy = dy !== 0 ? hh / Math.abs(dy) : Infinity;
    const s = Math.min(sx, sy);
    return { x: cx + dx * s, y: cy + dy * s };
  }

  function tierFill(tier, c) {
    if (tier === "ingress") return c.tierIngress;
    if (tier === "infra") return c.tierInfra;
    return c.tierCritical;
  }

  function nodeRoughness(status) {
    if (status === "degraded") return 0.8;
    if (status === "warning") return 0.8;
    return 0.8;
  }

  // ── Animation constants (shared between timeline + draw effects) ──
  const BOX_PEN_SPEED = 332; // SVG units per second (box outlines)
  const EDGE_PEN_SPEED = 349; // SVG units per second (connecting lines)
  const MIN_SIDE_DUR = 0.22; // seconds — minimum per box side (must be perceptibly sequential)
  const MIN_EDGE_DUR = 0.2; // seconds — minimum per edge line
  const TRAVEL_PAUSE = 0.12; // seconds — hand repositioning between elements
  const CHAR_MS = 0.03; // seconds per character (quick jot, non-blocking)
  const MIN_TEXT = 0.06; // minimum text "jot" duration
  const MAX_CURSORS = 2; // parallel drawing streams
  const CASCADE_STAGGER = 0.3; // seconds between parallel cursor starts
  const MIN_LINE_STAGGER = 0.3; // seconds — minimum gap between any two pencil line starts
  const PEN_EASE = "cubic-bezier(0.65, 0, 0.15, 1)"; // pen dynamics: deliberate start, quick middle, slow landing

  // Deterministic jitter: ±25% so it looks human
  function jitter(key) {
    let h = 0;
    for (let i = 0; i < key.length; i++) h = ((h << 5) - h + key.charCodeAt(i)) | 0;
    return 0.75 + ((Math.abs(h) % 50) / 100);
  }

  // ── Sequential BFS animation timeline ─────
  // Each step blocks the next: box sides draw sequentially → text jots → travel pause → edge → next box
  const animDelay = $derived.by(() => {
    const _nodes = nodes;
    const _edges = edges;
    const _nodeById = nodeById;
    const _gen = drawGen;

    const __nodes = _nodes;
    const __edges = _edges;
    const __nodeById = _nodeById;

    const adj = {};
    __nodes.forEach((n) => (adj[n.id] = []));
    __edges.forEach((e) => {
      adj[e.from].push({ nb: e.to, edge: e });
      adj[e.to].push({ nb: e.from, edge: e });
    });

    function textDur(s) {
      return Math.max(MIN_TEXT, s.length * CHAR_MS * jitter(s + "txt"));
    }

    // Per-side durations for sequential box stroke animation
    function boxSideDurs(n) {
      const w = n.hw * 2 + 12;
      const h = HH * 2 + 6;
      return [
        Math.max(MIN_SIDE_DUR, (w / BOX_PEN_SPEED) * jitter(n.id + "top")),
        Math.max(MIN_SIDE_DUR, (h / BOX_PEN_SPEED) * jitter(n.id + "right")),
        Math.max(MIN_SIDE_DUR, (w / BOX_PEN_SPEED) * jitter(n.id + "bottom")),
        Math.max(MIN_SIDE_DUR, (h / BOX_PEN_SPEED) * jitter(n.id + "left")),
      ];
    }

    // Edge duration scales with actual distance between nodes
    function edgeDur(from, to, key) {
      const dist = Math.sqrt((from.x - to.x) ** 2 + (from.y - to.y) ** 2);
      return Math.max(MIN_EDGE_DUR, (dist / EDGE_PEN_SPEED) * jitter(key));
    }

    // Find which side of the box the incoming edge hits
    // Uses aspect-ratio-normalized angles — same logic as boxExit()
    // Sides: 0=top, 1=right, 2=bottom, 3=left
    function arrivalSide(n, fromX, fromY) {
      const dx = fromX - n.x;
      const dy = fromY - n.y;
      if (dx === 0 && dy === 0) return 0;
      const w = n.hw * 2 + 12, h = HH * 2 + 6;
      // Normalize by half-dimensions so rectangles behave like squares
      const sx = Math.abs(dx) / (w / 2);
      const sy = Math.abs(dy) / (h / 2);
      if (sy > sx) {
        return dy < 0 ? 0 : 2; // top or bottom
      } else {
        return dx > 0 ? 1 : 3; // right or left
      }
    }

    // BFS with layered pencil/ink timing:
    // 1. Pencil box draws (sequential sides)
    // 2. Pencil box done → simultaneously: text jots, ink retraces box, pencil line to next node
    // 3. Ink box done → ink line chases the pencil line
    // Pencil cursor drives the flow; ink/text are non-blocking overlays.
    const INK_SPEED = 0.85; // ink pass is 85% the duration of pencil (pencil sketches ahead, ink follows)

    const visited = new Set(["external"]);
    const nd = {};
    const ed = {};
    const edDir = {};

    // Schedule a node's pencil box. Returns pencil cursor after box completes.
    function scheduleNode(c, item) {
      const { id, fromX, fromY } = item;
      const n = __nodeById[id];
      const side = arrivalSide(n, fromX, fromY);
      const sides = boxSideDurs(n);
      const bDur = sides.reduce((a, b) => a + b, 0);
      const tDur = textDur(n.label);

      const fillStart = c + bDur + bDur * INK_SPEED; // fill scrubs in after ink completes
      const fillDur = 0.25;                          // quick color scrub
      nd[id] = {
        box: c,                              // pencil box start
        boxSides: sides,                     // pencil per-side durations
        boxStartSide: side,
        boxDur: bDur,                        // total pencil box duration
        inkBox: c + bDur,                    // ink retrace starts when pencil box finishes
        inkBoxDur: bDur * INK_SPEED,
        inkBoxSides: sides.map((d) => d * INK_SPEED),
        fill: fillStart,                     // color fill after ink outline
        fillDur,
        text: fillStart + fillDur * 0.5,     // text jots in as fill is completing
        textDur: tDur,
      };
      return c + bDur; // pencil cursor: box done, ready for edges
    }

    // Schedule an edge's pencil + ink lines. siblingIdx staggers ink starts.
    function scheduleEdge(pencilStart, parentId, edge, siblingIdx) {
      const key = edge.from + "-" + edge.to;
      edDir[key] = edge.from === parentId;
      const from = __nodeById[edge.from];
      const to = __nodeById[edge.to];
      const eDur = edgeDur(from, to, key);

      // Ink line waits for: parent's ink box + stagger, AND pencil line to complete + pause
      const parent = nd[parentId];
      const parentInkDone = parent ? parent.inkBox + parent.inkBoxDur : pencilStart;
      const inkStagger = (siblingIdx || 0) * CASCADE_STAGGER * jitter(key + "ink-stg");
      const pencilDone = pencilStart + eDur + TRAVEL_PAUSE;

      ed[key] = {
        pencilLine: pencilStart,
        pencilLineDur: eDur,
        inkLine: Math.max(parentInkDone + inkStagger, pencilDone),
        inkLineDur: eDur * INK_SPEED,
      };
      return pencilStart + eDur;
    }

    // Collect unvisited children
    function collectChildren(item) {
      const n = __nodeById[item.id];
      const children = [];
      let sibIdx = 0;
      for (const { nb: nbId, edge } of adj[item.id]) {
        if (visited.has(nbId)) continue;
        visited.add(nbId);
        children.push({ id: nbId, fromX: n.x, fromY: n.y, viaEdge: edge, parentId: item.id, siblingIdx: sibIdx++ });
      }
      return children;
    }

    // Schedule one complete item (edge if present, then node). Returns pencil cursor.
    function scheduleItem(c, item) {
      if (item.viaEdge) {
        c = scheduleEdge(c, item.parentId, item.viaEdge, item.siblingIdx);
      }
      return scheduleNode(c, item);
    }

    let batch = [{ id: "external", fromX: 0, fromY: __nodeById["external"]?.y ?? 240, viaEdge: null, parentId: null }];
    let cursor = 0.2;

    while (batch.length > 0) {
      const nextBatch = [];

      if (batch.length === 1) {
        cursor = scheduleItem(cursor, batch[0]);
        nextBatch.push(...collectChildren(batch[0]));
      } else {
        const numCursors = Math.min(MAX_CURSORS, batch.length);
        const cursors = Array.from({ length: numCursors }, (_, i) => cursor + i * CASCADE_STAGGER * jitter("cursor" + i));
        let lastLineStart = -Infinity;

        batch.forEach((item, i) => {
          const ci = i % numCursors;
          // Ensure no two pencil lines start within MIN_LINE_STAGGER of each other
          if (item.viaEdge) {
            cursors[ci] = Math.max(cursors[ci], lastLineStart + MIN_LINE_STAGGER * jitter(item.id + "line-stg"));
            lastLineStart = cursors[ci];
          }
          cursors[ci] = scheduleItem(cursors[ci], item);
          nextBatch.push(...collectChildren(item));
        });

        cursor = Math.max(...cursors);
      }

      batch = nextBatch;
    }

    // Cross-edges (both endpoints already visited)
    __edges.forEach((e) => {
      const key = e.from + "-" + e.to;
      if (ed[key]) return;
      const eDur = edgeDur(__nodeById[e.from], __nodeById[e.to], key);
      const fromDone = (nd[e.from]?.box ?? 0) + (nd[e.from]?.boxDur ?? 0);
      const toDone = (nd[e.to]?.box ?? 0) + (nd[e.to]?.boxDur ?? 0);
      edDir[key] = fromDone <= toDone;
      ed[key] = {
        pencilLine: cursor, pencilLineDur: eDur,
        inkLine: cursor + eDur * 0.3, inkLineDur: eDur * INK_SPEED,
      };
      cursor += eDur + TRAVEL_PAUSE;
    });

    // Schedule unvisited nodes (infra tier — no edges from critical path)
    // Sort left-to-right (by x) and stagger from the start of the animation
    // so they draw concurrently with the critical path
    const unvisited = __nodes
      .filter((n) => !visited.has(n.id))
      .sort((a, b) => a.x - b.x);
    if (unvisited.length > 0) {
      const infraStart = 0.8; // start shortly after cloudflare
      const infraSpacing = 0.4; // seconds between each infra node
      unvisited.forEach((n, i) => {
        visited.add(n.id);
        const t = infraStart + i * infraSpacing * jitter(n.id + "infra");
        scheduleNode(t, { id: n.id, fromX: n.x, fromY: n.y - 80 });
      });
    }

    let maxT = 0;
    for (const v of Object.values(nd)) maxT = Math.max(maxT, v.inkBox + v.inkBoxDur);
    for (const v of Object.values(ed)) maxT = Math.max(maxT, v.inkLine + v.inkLineDur);

    return { node: nd, edge: ed, edgeDir: edDir, totalDur: maxT + 0.5 };
  });

  // ── Draw topology ──────────────────────────
  // This effect draws all Rough.js elements once (and on dark mode change).
  // It does NOT track `active` — highlighting is handled by a separate effect
  // that updates opacity on existing elements, allowing CSS transitions to work.
  let hasAnimated = false;
  $effect(() => {
    if (!mapSvg || !roughEdges || !roughNodes || !roughArrows) return;
    const _layout = activeLayout;
    const _gen = drawGen; // bump to force redraw after flip

    const c = colors();
    const rc = rough.svg(mapSvg);
    clearChildren(roughEdges);
    clearChildren(roughNodes);
    clearChildren(roughArrows);
    const shouldAnimate = !hasAnimated;

    // Helper: draw a hand-drawn chevron arrowhead (two rough lines forming a ">")
    function drawArrowhead(rc, x, y, fromX, fromY, color, arrowSeed, hidden) {
      const dx = x - fromX;
      const dy = y - fromY;
      const len = Math.sqrt(dx * dx + dy * dy);
      if (len === 0) return null;
      const ux = dx / len;
      const uy = dy / len;
      const px = -uy;
      const py = ux;
      const size = 10;
      const spread = 6;
      // Two barb endpoints behind the tip
      const leftX = x - ux * size + px * spread;
      const leftY = y - uy * size + py * spread;
      const rightX = x - ux * size - px * spread;
      const rightY = y - uy * size - py * spread;

      const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      // First barb: outer → tip (drawing inward)
      const leftBarb = rc.line(leftX, leftY, x, y, {
        stroke: color, roughness: 1.0, bowing: 0.8,
        strokeWidth: 1.5, seed: arrowSeed,
      });
      leftBarb.dataset.barb = "left";
      g.appendChild(leftBarb);
      // Second barb: tip → outer (drawing outward, continuous stroke)
      const rightBarb = rc.line(x, y, rightX, rightY, {
        stroke: color, roughness: 1.0, bowing: 0.8,
        strokeWidth: 1.5, seed: arrowSeed + 3,
      });
      rightBarb.dataset.barb = "right";
      g.appendChild(rightBarb);
      // Hide all paths when animating — they'll be revealed via edgeDraw
      if (hidden) {
        g.querySelectorAll("path").forEach((p) => {
          try {
            const pLen = p.getTotalLength();
            p.style.strokeDasharray = String(pLen);
            p.style.strokeDashoffset = String(pLen);
          } catch {
            p.style.opacity = "0";
          }
        });
      }
      return g;
    }

    edges.forEach((e) => {
      const key = e.from + "-" + e.to;

      const fromPos = getNodePos(e.from);
      const toPos = getNodePos(e.to);
      const fromNode = nodeById[e.from];
      const toNode = nodeById[e.to];
      const p1 = boxExit(fromPos.x, fromPos.y, fromNode.hw + 6, HH + 4, toPos.x, toPos.y);
      const p2 = boxExit(toPos.x, toPos.y, toNode.hw + 6, HH + 4, fromPos.x, fromPos.y);

      // Draw line from BFS-earlier node toward BFS-later node
      const fwd = animDelay.edgeDir[key];
      const startPt = fwd ? p1 : p2;
      const endPt = fwd ? p2 : p1;
      const edgeSeed = seed(e.from + e.to);

      const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      g.dataset.edge = key;
      g.style.transition = "opacity 0.25s ease";

      // Pencil sketch (light guide)
      const pencil = rc.line(startPt.x, startPt.y, endPt.x, endPt.y, {
        stroke: c.border,
        roughness: 1.5,
        bowing: 1.2,
        strokeWidth: 1.0,
        seed: edgeSeed,
      });
      pencil.style.opacity = "0.6";
      pencil.dataset.layer = "pencil";

      // Ink overlay — darker final color
      const ink = rc.line(startPt.x, startPt.y, endPt.x, endPt.y, {
        stroke: c.fgTer,
        roughness: 1.5,
        bowing: 1.2,
        strokeWidth: 1.5,
        seed: edgeSeed + 7,
      });
      ink.dataset.layer = "ink";

      // Rough.js arrowheads — rendered in separate layer on top of nodes
      const fwdArrow = drawArrowhead(rc, endPt.x, endPt.y, startPt.x, startPt.y, c.fgTer, edgeSeed + 20, shouldAnimate);
      if (fwdArrow) {
        fwdArrow.dataset.edge = key;
        fwdArrow.style.transition = "opacity 0.25s ease";
        roughArrows.appendChild(fwdArrow);
      }

      // Bidirectional: arrowhead at the "from" end too
      let revArrow = null;
      if (e.bidi) {
        revArrow = drawArrowhead(rc, startPt.x, startPt.y, endPt.x, endPt.y, c.fgTer, edgeSeed + 30, shouldAnimate);
        if (revArrow) {
          revArrow.dataset.edge = key;
          revArrow.style.transition = "opacity 0.25s ease";
          roughArrows.appendChild(revArrow);
        }
      }

      if (shouldAnimate) {
        const anim = animDelay.edge[key];

        // Pencil: grey sketch, starts with parent's edges
        pencil.querySelectorAll("path").forEach((path) => {
          try {
            const len = path.getTotalLength();
            path.style.strokeDasharray = String(len);
            path.style.strokeDashoffset = String(len);
            path.style.animation = `edgeDraw ${anim.pencilLineDur.toFixed(3)}s ${PEN_EASE} ${anim.pencilLine.toFixed(3)}s forwards`;
          } catch {
            path.style.opacity = "0";
            path.style.animation = `nodeIn 0.3s ease ${anim.pencilLine.toFixed(3)}s forwards`;
          }
        });

        // Ink: colored, chases after parent's ink box finishes
        ink.querySelectorAll("path").forEach((path) => {
          try {
            const len = path.getTotalLength();
            path.style.strokeDasharray = String(len);
            path.style.strokeDashoffset = String(len);
            path.style.animation = `edgeDraw ${anim.inkLineDur.toFixed(3)}s ${PEN_EASE} ${anim.inkLine.toFixed(3)}s forwards`;
          } catch {
            path.style.opacity = "0";
            path.style.animation = `nodeIn 0.3s ease ${anim.inkLine.toFixed(3)}s forwards`;
          }
        });

        // Arrowheads: draw in after edge ink + target node ink both complete
        const edgeInkDone = anim.inkLine + anim.inkLineDur;
        // Find when the "to" node's ink box finishes (if it has anim data)
        const toNodeAnim = animDelay.node[fwd ? e.to : e.from];
        const fromNodeAnim = animDelay.node[fwd ? e.from : e.to];
        const toInkDone = toNodeAnim ? toNodeAnim.inkBox + toNodeAnim.inkBoxDur : 0;
        const arrowStart = Math.max(edgeInkDone, toInkDone);
        const arrowDur = 0.375;

        const barbStagger = 0.08; // slight delay between left and right barb
        function animateArrow(arrow, delay) {
          if (!arrow) return;
          // Animate each barb separately with stagger
          arrow.querySelectorAll("[data-barb]").forEach((barbG, i) => {
            const barbDelay = delay + i * barbStagger;
            barbG.querySelectorAll("path").forEach((p) => {
              try {
                p.style.animation = `edgeDraw ${arrowDur}s ${PEN_EASE} ${barbDelay.toFixed(3)}s forwards`;
              } catch {
                p.style.opacity = "0";
                p.style.animation = `nodeIn ${arrowDur}s ease ${barbDelay.toFixed(3)}s forwards`;
              }
            });
          });
        }
        animateArrow(fwdArrow, arrowStart);
        if (e.bidi) {
          const fromInkDone = fromNodeAnim ? fromNodeAnim.inkBox + fromNodeAnim.inkBoxDur : 0;
          const revStart = Math.max(edgeInkDone, fromInkDone);
          animateArrow(revArrow, revStart);
        }
      }
      g.appendChild(pencil);
      g.appendChild(ink);
      roughEdges.appendChild(g);
    });

    nodes.forEach((n) => {

      const pos = getNodePos(n.id);
      const w = n.hw * 2 + 12;
      const h = HH * 2 + 6;
      const inkCol = n.status === "degraded" ? c.danger : n.status === "warning" ? c.warn : c.borderInk;
      const r = nodeRoughness(n.status);
      const bow = n.status === "warning" ? 1.2 : 0.5;

      const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      g.dataset.node = n.id;
      g.style.transition = "opacity 0.25s ease";

      // Solid fill — starts transparent, scrubs in after ink outline completes
      const fillCol = tierFill(n.tier, c);
      const fillEl = rc.rectangle(pos.x - w / 2, pos.y - h / 2, w, h, {
        stroke: "none", fill: fillCol, fillStyle: "solid",
        roughness: r, seed: seed(n.id + "fill"),
      });
      fillEl.dataset.layer = "fill";
      if (shouldAnimate) {
        fillEl.style.opacity = "0";
      }
      g.appendChild(fillEl);

      // 4 sequential strokes, rotated to start from the nearest corner to the incoming edge
      const x1 = pos.x - w / 2, y1 = pos.y - h / 2;
      const x2 = pos.x + w / 2, y2 = pos.y + h / 2;
      // Canonical order starting from each corner (clockwise):
      // Corner 0 (TL): top→right→bottom→left
      // Corner 1 (TR): right→bottom→left→top
      // Corner 2 (BR): bottom→left→top→right
      // Corner 3 (BL): left→top→right→bottom
      const allSides = [
        { from: [x1, y1], to: [x2, y1], key: "top" },
        { from: [x2, y1], to: [x2, y2], key: "right" },
        { from: [x2, y2], to: [x1, y2], key: "bottom" },
        { from: [x1, y2], to: [x1, y1], key: "left" },
      ];

      const anim = shouldAnimate ? animDelay.node[n.id] : null;
      const corner = anim ? anim.boxStartSide : 0;
      // Rotate sides and durations to start from the chosen corner
      const sides = [...allSides.slice(corner), ...allSides.slice(0, corner)];
      const pencilDurs = anim
        ? [...anim.boxSides.slice(corner), ...anim.boxSides.slice(0, corner)]
        : null;
      const inkDurs = anim
        ? [...anim.inkBoxSides.slice(corner), ...anim.inkBoxSides.slice(0, corner)]
        : null;

      let pencilOffset = 0;
      let inkOffset = 0;

      sides.forEach((side, i) => {
        const sideSeed = seed(n.id + side.key);

        // Pencil sketch
        const pencil = rc.line(side.from[0], side.from[1], side.to[0], side.to[1], {
          stroke: c.border,
          roughness: r,
          bowing: bow,
          strokeWidth: 1.0,
          seed: sideSeed,
        });
        pencil.style.opacity = "0.5";
        pencil.dataset.layer = "pencil";

        // Ink overlay — always the strong/final color
        const ink = rc.line(side.from[0], side.from[1], side.to[0], side.to[1], {
          stroke: inkCol,
          roughness: r,
          bowing: bow,
          strokeWidth: 2,
          seed: sideSeed + 7,
        });
        ink.dataset.layer = "ink";

        if (anim) {
          // Pencil: sequential sides starting at anim.box
          const pencilStart = anim.box + pencilOffset;
          const pDur = pencilDurs[i];
          pencil.querySelectorAll("path").forEach((path) => {
            try {
              const len = path.getTotalLength();
              path.style.strokeDasharray = String(len);
              path.style.strokeDashoffset = String(len);
              path.style.animation = `edgeDraw ${pDur.toFixed(3)}s ${PEN_EASE} ${pencilStart.toFixed(3)}s forwards`;
            } catch {
              path.style.opacity = "0";
              path.style.animation = `nodeIn 0.15s ease ${pencilStart.toFixed(3)}s forwards`;
            }
          });
          pencilOffset += pDur;

          // Ink: sequential sides starting at anim.inkBox (after ALL pencil sides done)
          const inkStart = anim.inkBox + inkOffset;
          const iDur = inkDurs[i];
          ink.querySelectorAll("path").forEach((path) => {
            try {
              const len = path.getTotalLength();
              path.style.strokeDasharray = String(len);
              path.style.strokeDashoffset = String(len);
              path.style.animation = `edgeDraw ${iDur.toFixed(3)}s ${PEN_EASE} ${inkStart.toFixed(3)}s forwards`;
            } catch {
              path.style.opacity = "0";
              path.style.animation = `nodeIn 0.15s ease ${inkStart.toFixed(3)}s forwards`;
            }
          });
          inkOffset += iDur;
        }
        g.appendChild(pencil);
        g.appendChild(ink);
      });

      // Animate fill scrub: fade in after ink outline completes
      if (anim) {
        fillEl.style.animation = `nodeIn ${anim.fillDur.toFixed(3)}s ease-out ${anim.fill.toFixed(3)}s forwards`;
      }

      roughNodes.appendChild(g);
    });

    if (shouldAnimate) {
      hasAnimated = true;
      drawStartTime = performance.now();
      if (drawTimer) clearTimeout(drawTimer);
      drawTimer = setTimeout(() => { drawing = false; }, animDelay.totalDur * 1000);
    }
  });

  // Recolor rough.js strokes in-place when theme changes (no redraw needed)
  let prevDark = isDark;
  $effect(() => {
    const dark = isDark;
    if (dark === prevDark) return;
    prevDark = dark;

    const c = colors();
    // Recolor edges
    if (roughEdges) {
      roughEdges.querySelectorAll("[data-edge]").forEach((g) => {
        g.querySelector("[data-layer='pencil']")?.querySelectorAll("path").forEach((p) => { p.setAttribute("stroke", c.border); });
        g.querySelector("[data-layer='ink']")?.querySelectorAll("path").forEach((p) => { p.setAttribute("stroke", c.fgTer); });
      });
    }
    // Recolor arrowheads
    if (roughArrows) {
      roughArrows.querySelectorAll("[data-edge]").forEach((g) => {
        g.querySelectorAll("path").forEach((p) => { p.setAttribute("stroke", c.fgTer); });
      });
    }
    // Recolor nodes
    if (roughNodes) {
      roughNodes.querySelectorAll("[data-node]").forEach((g) => {
        const id = g.dataset.node;
        const n = nodeById[id];
        const inkCol = n.status === "degraded" ? c.danger : n.status === "warning" ? c.warn : c.borderInk;
        g.querySelectorAll("[data-layer='pencil'] path").forEach((p) => { p.setAttribute("stroke", c.border); });
        g.querySelectorAll("[data-layer='ink'] path").forEach((p) => { p.setAttribute("stroke", inkCol); });
        const fill = g.querySelector("[data-layer='fill']");
        if (fill) fill.querySelectorAll("path").forEach((p) => {
          p.setAttribute("fill", tierFill(n.tier, c));
        });
      });
    }
  });

  // ── Highlight effect ──────────────────────────
  // When a node is focused: connected edges become bold, others dim.
  // Separated from draw effect so selection/hover doesn't trigger a full redraw.
  $effect(() => {
    if (!roughEdges || !roughNodes || !roughArrows) return;
    const _hov = hovered;
    const _sel = selected;
    const dimSource = _hov || _sel;

    // Build set of connected edge keys for the focused node
    const connectedEdges = new Set();
    const connectedNodes = new Set();
    if (dimSource) {
      connectedNodes.add(dimSource);
      edges.forEach((e) => {
        if (e.from === dimSource || e.to === dimSource) {
          connectedEdges.add(e.from + "-" + e.to);
          connectedNodes.add(e.from);
          connectedNodes.add(e.to);
        }
      });
    }

    // Edges: connected ones become bold, others dim
    roughEdges.querySelectorAll("[data-edge]").forEach((g) => {
      const key = g.dataset.edge;
      if (!dimSource) {
        g.style.opacity = "1";
        g.querySelectorAll("path").forEach((p) => { p.style.strokeWidth = ""; });
      } else if (connectedEdges.has(key)) {
        g.style.opacity = "1";
        // Bold up the ink layer paths
        const ink = g.querySelector("[data-layer='ink']");
        if (ink) ink.querySelectorAll("path").forEach((p) => { p.style.strokeWidth = "3"; });
      } else {
        g.style.opacity = "0.08";
        g.querySelectorAll("path").forEach((p) => { p.style.strokeWidth = ""; });
      }
    });

    // Arrowheads: match their edge's visibility
    roughArrows.querySelectorAll("[data-edge]").forEach((g) => {
      const key = g.dataset.edge;
      if (!dimSource) {
        g.style.opacity = "1";
      } else if (connectedEdges.has(key)) {
        g.style.opacity = "1";
      } else {
        g.style.opacity = "0.08";
      }
    });

    // Nodes: focused + connected neighbors stay bright
    roughNodes.querySelectorAll("[data-node]").forEach((g) => {
      const id = g.dataset.node;
      g.style.opacity = (!dimSource || connectedNodes.has(id)) ? "1" : "0.15";
    });

  });

  // ── Hover scribble highlight ────────────────
  // Chaotic scribble lines behind hovered node — keeps scribbling while cursor stays.
  // 500ms hover delay prevents scribble on casual mouseover.
  let hoverFadeTimer = null;
  let scribbleInterval = null;
  let scribbleDelayTimer = null;
  let activeScribbleNode = null; // tracks which node has an active scribble

  function clearAllScribbles(except) {
    if (!hoverBorderG) return;
    const children = [...hoverBorderG.children];
    children.forEach((g) => {
      if (g.dataset.node === except) return;
      g.style.opacity = "0";
      const dying = g;
      setTimeout(() => { if (dying.parentNode) dying.remove(); }, 300);
    });
  }

  $effect(() => {
    if (!hoverBorderG || !mapSvg) return;
    const _hov = hovered;
    const _sel = selected;
    const keep = _hov || _sel;

    // Clear any scribbles that don't match the current target
    clearAllScribbles(keep);

    // If nothing to keep, kill the interval and delay
    if (!keep) {
      if (scribbleInterval) { clearInterval(scribbleInterval); scribbleInterval = null; }
      if (scribbleDelayTimer) { clearTimeout(scribbleDelayTimer); scribbleDelayTimer = null; }
      activeScribbleNode = null;
      return;
    }

    // If the target changed, kill old interval + delay
    if (keep !== activeScribbleNode) {
      if (scribbleInterval) { clearInterval(scribbleInterval); scribbleInterval = null; }
      if (scribbleDelayTimer) { clearTimeout(scribbleDelayTimer); scribbleDelayTimer = null; }
      activeScribbleNode = null;
    }

    // Already scribbling this node — nothing to do
    if (activeScribbleNode === keep) return;

    // Start scribble after delay (immediate if clicking/selecting)
    const delay = _sel === keep && !_hov ? 0 : 500;

    scribbleDelayTimer = setTimeout(() => {
      scribbleDelayTimer = null;
      // Re-check that the target hasn't changed during the delay
      if ((hovered || selected) !== keep) return;
      activeScribbleNode = keep;
      startScribble(keep);
    }, delay);
  });

  function startScribble(target) {
      const n = nodeById[target];
      const pos = getNodePos(target);
      const rc = rough.svg(mapSvg);
      const pad = 20;
      const hw = n.hw + 6 + pad;
      const hh = HH + 3 + pad;

      // MotherDuck-inspired brutalist palette — vibrant everywhere
      const scribbleCol = n.status === "degraded"
        ? (isDark ? "#ff3333" : "#dc2626")
        : n.status === "warning"
          ? "#ff9500"
          : (isDark ? "#7dd3fc" : "#38bdf8");

      const wrap = document.createElementNS("http://www.w3.org/2000/svg", "g");
      wrap.dataset.node = target;
      wrap.style.transition = "opacity 0.3s ease";

      function addScribbleBurst(batch, baseDelay) {
        const now = Date.now();
        const linesPerBurst = 6;
        for (let i = 0; i < linesPerBurst; i++) {
          const idx = batch * linesPerBurst + i;
          const s = seed(target + "scr" + idx + now);
          const jx = ((s % 80) - 40);
          const jy = ((seed(target + "jy" + idx + now) % 60) - 30);
          const direction = s % 5;

          let x1, y1, x2, y2;
          if (direction === 0) {
            // diagonal TL→BR
            x1 = pos.x - hw + jx; y1 = pos.y - hh + jy;
            x2 = pos.x + hw + jx * 0.3; y2 = pos.y + hh + jy * 0.3;
          } else if (direction === 1) {
            // diagonal TR→BL
            x1 = pos.x + hw + jx; y1 = pos.y - hh + jy;
            x2 = pos.x - hw + jx * 0.3; y2 = pos.y + hh + jy * 0.3;
          } else if (direction === 2) {
            // horizontal
            x1 = pos.x - hw + jx; y1 = pos.y + jy;
            x2 = pos.x + hw + jx * 0.4; y2 = pos.y + jy * 0.6;
          } else if (direction === 3) {
            // vertical
            x1 = pos.x + jx * 0.8; y1 = pos.y - hh + jy;
            x2 = pos.x + jx * 0.5; y2 = pos.y + hh + jy * 0.3;
          } else {
            // steep diagonal
            x1 = pos.x - hw * 0.6 + jx; y1 = pos.y - hh + jy;
            x2 = pos.x + hw * 0.6 + jx * 0.2; y2 = pos.y + hh + jy * 0.2;
          }

          const line = rc.line(x1, y1, x2, y2, {
            stroke: scribbleCol,
            roughness: 2.5 + (s % 20) / 10,
            bowing: 1.5 + (seed(target + "bow" + idx) % 15) / 10,
            strokeWidth: 1.5 + (s % 12) / 10,
            seed: s,
          });

          const stagger = baseDelay + i * 0.04;
          const dur = 0.12 + (s % 10) / 100;
          line.querySelectorAll("path").forEach((path) => {
            try {
              const len = path.getTotalLength();
              path.style.strokeDasharray = String(len);
              path.style.strokeDashoffset = String(len);
              path.style.animation = `hoverBorderDraw ${dur}s ease-out ${stagger}s forwards`;
            } catch { /* ignore */ }
          });
          // No opacity — bold brutalist strokes, color does the work

          wrap.appendChild(line);
        }
      }

      // Initial burst
      addScribbleBurst(0, 0);

      // Keep scribbling every 250ms for up to 7s
      let batch = 1;
      const maxBatches = Math.floor(7000 / 250);
      scribbleInterval = setInterval(() => {
        if (batch >= maxBatches) { clearInterval(scribbleInterval); scribbleInterval = null; return; }
        addScribbleBurst(batch, 0);
        batch++;
      }, 250);

      hoverBorderG.appendChild(wrap);
  }

  // ── Hover tooltip ──────────────────────────
  $effect(() => {
    if (!tooltipRough || !mapSvg) return;
    clearChildren(tooltipRough);
    const _hovered = hovered;
    if (!_hovered || selected) return;

    const pos = getNodePos(_hovered);
    const s = svc[_hovered];
    if (!s?.brief) return;

    const c = colors();
    const rc = rough.svg(mapSvg);
    const tipW = s.brief.length * 5.2 + 20;
    const tipY = pos.y - HH - 24;

    tooltipRough.appendChild(
      rc.rectangle(pos.x - tipW / 2, tipY - 9, tipW, 18, {
        stroke: c.border,
        fill: c.tooltipBg,
        fillStyle: "solid",
        roughness: 0.5,
        strokeWidth: 0.6,
        seed: seed("tip-" + _hovered),
      }),
    );
  });

  // ── Drawer border ──────────────────────────
  $effect(() => {
    if (!drawerBorderSvg || !drawerBorderG || !selected) return;
    const _dark = isDark;
    const c = colors();
    const rc = rough.svg(drawerBorderSvg);
    clearChildren(drawerBorderG);
    drawerBorderG.appendChild(
      rc.line(3, 0, 3, 800, {
        stroke: c.fg,
        roughness: 2.5,
        bowing: 2,
        strokeWidth: 1,
        seed: seed("drawer-border"),
      }),
    );
  });

  // ── Drawer: sparkline ──────────────────────
  $effect(() => {
    if (!sparkSvg || !sparkRoughG || !selected) return;
    const s = svc[selected];
    if (!s?.spark) { clearChildren(sparkRoughG); return; }
    const _dark = isDark;
    const c = colors();
    const rc = rough.svg(sparkSvg);
    clearChildren(sparkRoughG);

    const data = s.spark;
    const max = Math.max(...data);
    const min = Math.min(...data);
    const range = max - min || 1;
    const chartH = 40;

    data.forEach((v, i) => {
      const h = ((v - min) / range) * 28 + 6;
      const x = i * 8 + 4;
      const el = rc.line(x, chartH, x, chartH - h, {
        stroke: c.fg,
        roughness: 0.4,
        strokeWidth: 3,
        seed: seed("spark" + i),
      });
      el.style.opacity = String(0.2 + (i / data.length) * 0.8);
      sparkRoughG.appendChild(el);
    });

    if (s.latency && s.latency.target <= max) {
      const targetY = chartH - (((s.latency.target - min) / range) * 28 + 6);
      const el = rc.line(0, targetY, data.length * 8, targetY, {
        stroke: c.danger, roughness: 0.8, strokeWidth: 0.8, seed: seed("target"),
      });
      el.style.opacity = "0.5";
      sparkRoughG.appendChild(el);
    }
  });

  // ── Drawer: budget burn ────────────────────
  $effect(() => {
    if (!budgetSvg || !budgetRoughG || !selected) return;
    const s = svc[selected];
    if (!s?.budget) { clearChildren(budgetRoughG); return; }
    const _dark = isDark;
    const c = colors();
    const rc = rough.svg(budgetSvg);
    clearChildren(budgetRoughG);

    const trackW = 240;
    const trackH = 10;

    budgetRoughG.appendChild(
      rc.rectangle(0, 0, trackW, trackH, {
        stroke: c.border, fill: c.surface, fillStyle: "solid",
        roughness: 0.6, strokeWidth: 0.8, seed: seed("budget-track"),
      }),
    );

    const exceeded = s.budget.consumed > 100;
    const fillW = Math.min(s.budget.consumed, 100) / 100 * trackW;
    if (fillW > 0) {
      budgetRoughG.appendChild(
        rc.rectangle(1, 1, fillW - 2, trackH - 2, {
          stroke: "none", fill: budgetColor(s.budget.consumed, s.budget.elapsed),
          fillStyle: exceeded ? "cross-hatch" : "solid",
          fillWeight: exceeded ? 0.8 : undefined,
          roughness: exceeded ? 1.5 : 0.4,
          seed: seed("budget-fill"),
        }),
      );
    }

    const markerX = (s.budget.elapsed / 100) * trackW;
    budgetRoughG.appendChild(
      rc.line(markerX, -4, markerX, trackH + 4, {
        stroke: c.fg, roughness: 0.3, strokeWidth: 1.5, seed: seed("budget-marker"),
      }),
    );
  });

  // ── Pan to selected node ─────────────────────
  // Smoothly reposition the map so the selected node centers in the
  // available whitespace (viewport minus drawer width).
  const DRAWER_REM = 22;
  $effect(() => {
    if (!mapPanG || !mapSvg) return;
    const _sel = selected;

    if (!_sel) {
      mapPanG.style.transform = "translate(0, 0)";
      return;
    }

    const pos = getNodePos(_sel);
    const vb = viewBox.split(" ").map(Number);
    const [vbX, vbY, vbW, vbH] = vb;

    // SVG center without drawer
    const svgCenterX = vbX + vbW / 2;
    const svgCenterY = vbY + vbH / 2;

    // Drawer takes DRAWER_REM from the right — compute how much SVG-space
    // that consumes, then find the center of the remaining whitespace.
    const remPx = parseFloat(getComputedStyle(document.documentElement).fontSize);
    const drawerPx = DRAWER_REM * remPx;
    const drawerFraction = Math.min(drawerPx / containerW, 0.9);
    // Available width fraction (left side)
    const availFraction = 1 - drawerFraction;
    // Center of available space in SVG coords
    const targetX = vbX + (availFraction / 2) * vbW;

    const dx = targetX - pos.x;
    const dy = svgCenterY - pos.y;

    mapPanG.style.transform = `translate(${dx}px, ${dy}px)`;
  });

  // ── Keyboard ───────────────────────────────
  $effect(() => {
    function onKey(e) {
      if (e.key === "Escape" && selected) {
        e.preventDefault();
        selected = null;
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });

</script>

<div class="root" class:portrait={isPortrait}>
  <button class="theme-toggle" onclick={toggleTheme} aria-label="Toggle theme">
    {#if isDark}
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2m0 18v2M4.22 4.22l1.42 1.42m12.72 12.72l1.42 1.42M1 12h2m18 0h2M4.22 19.78l1.42-1.42m12.72-12.72l1.42-1.42"/></svg>
    {:else}
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>
    {/if}
  </button>
  <div
    class="map-wrap"
    class:scribbling
    class:flip-out={flipPhase === "out"}
    class:flip-in={flipPhase === "in"}
  >
  <svg
    bind:this={mapSvg}
    viewBox={viewBox}
    class="map"
    role="img"
    aria-label="Service topology"
    preserveAspectRatio="xMidYMin meet"
  >
    <defs></defs>
    <g bind:this={mapPanG} class="map-pan">
    <g bind:this={hoverBorderG}></g>
    <g bind:this={roughEdges}></g>
    <g bind:this={roughNodes}></g>
    <g bind:this={roughArrows}></g>

    {#key drawGen}
      {#each nodes as n}
        {@const pos = getNodePos(n.id)}
        {@const dimmed = !isHighlighted(n.id)}
        {@const visible = nodeDrawn(n.id)}
        {#if visible || flipPhase === "none"}
          <text
            x={pos.x} y={pos.y + 4}
            class="node-label"
            class:node-label--dimmed={dimmed}
            class:node-label--active={active === n.id}
            style={drawing && flipPhase === "none" ? `opacity:0;animation:textJot ${animDelay.node[n.id].textDur.toFixed(3)}s cubic-bezier(0.2,0,0.1,1) ${animDelay.node[n.id].text.toFixed(3)}s forwards` : visible ? '' : 'opacity:0'}
          >
            {n.label}
          </text>
        {/if}
      {/each}
    {/key}

    <g bind:this={scribbleG}></g>
    <g bind:this={tooltipRough}></g>

    {#if hovered && !selected}
      {@const pos = getNodePos(hovered)}
      {@const s = svc[hovered]}
      {#if s?.brief}
        <text x={pos.x} y={pos.y - HH - 24} class="tooltip-text" dominant-baseline="central">{s.brief}</text>
      {/if}
    {/if}

    {#each nodes as n}
      {@const pos = getNodePos(n.id)}
      {@const w = n.hw * 2 + 12}
      <rect
        x={pos.x - w / 2}
        y={pos.y - HH - 3}
        width={w}
        height={HH * 2 + 6}
        fill="transparent"
        class="hit-area"
        style:cursor={!drawing || nodeDrawn(n.id) ? "pointer" : "default"}
        role="button"
        tabindex="0"
        aria-label="{n.label} — {svc[n.id]?.brief ?? ''}"
        onclick={() => selectNode(n.id)}
        onkeydown={(ev) => {
          if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); selectNode(n.id); }
        }}
        onmouseenter={() => { if (nodeDrawn(n.id)) hovered = n.id; }}
        onmouseleave={() => { hovered = null; }}
        onfocus={() => { if (nodeDrawn(n.id)) hovered = n.id; }}
        onblur={() => { hovered = null; }}
      />
    {/each}
    </g>
  </svg>
  </div>


  <!-- ── Detail drawer ────────────────────── -->
  {#if selected && svc[selected]}
    <button
      class="backdrop"
      tabindex="-1"
      aria-label="Close detail panel"
      transition:fade={{ duration: 200 }}
      onclick={() => (selected = null)}
    ></button>
    <aside class="drawer" transition:fly={{ x: 340, duration: 280, easing: cubicOut }}>
      <svg
        bind:this={drawerBorderSvg}
        class="drawer-border"
        viewBox="0 0 6 800"
        preserveAspectRatio="none"
      >
        <g bind:this={drawerBorderG}></g>
      </svg>

      <div class="drawer-content">
        <button class="drawer-back" onclick={() => (selected = null)}>&larr; esc</button>
        <div class="drawer-title-row">
          <h2 class="drawer-name">{nodeById[selected].label}</h2>
          <span class="drawer-status" style="color: {statusColor(nodeById[selected].status)}">{nodeById[selected].status}</span>
        </div>
        <p class="drawer-desc">{svc[selected].description}</p>

        {#if svc[selected].slo}
          <section class="drawer-section">
            <h3 class="section-label">slo</h3>
            <div class="slo-row">
              <span class="slo-label">availability</span>
              <span class="slo-value">{svc[selected].slo.current}%</span>
              <span class="slo-target">target {svc[selected].slo.target}%</span>
            </div>
            {#if svc[selected].latency}
              <div class="slo-row">
                <span class="slo-label">latency p99</span>
                <span class="slo-value">{svc[selected].latency.p99}{svc[selected].latency.unit}</span>
                <span class="slo-target">target {svc[selected].latency.target}{svc[selected].latency.unit}</span>
              </div>
            {/if}
          </section>
        {/if}

        {#if svc[selected].budget}
          {@const budget = svc[selected].budget}
          <section class="drawer-section">
            <h3 class="section-label">error budget</h3>
            <svg
              bind:this={budgetSvg}
              viewBox="0 -6 240 22"
              class="budget-chart"
              preserveAspectRatio="xMidYMid meet"
            >
              <g bind:this={budgetRoughG}></g>
            </svg>
            <div class="budget-labels">
              <span>{budget.consumed}% consumed</span>
              <span>{budget.consumed >= 100 ? "exhausted" : budget.remaining + " left"}</span>
            </div>
            <div class="budget-meta">
              {budget.window} window · day {Math.round((budget.elapsed * 30) / 100)} of 30
            </div>
            {#if budget.consumed >= 100}
              <div class="budget-alert">
                budget exhausted — {budget.consumed - 100}% over
              </div>
            {:else if budget.consumed > budget.elapsed}
              <div class="budget-alert">
                burning {Math.round((budget.consumed / budget.elapsed) * 100 - 100)}% faster than expected
              </div>
            {/if}
          </section>
        {/if}

        {#if svc[selected].spark}
          {@const spark = svc[selected].spark}
          {@const max = Math.max(...spark)}
          {@const min = Math.min(...spark)}
          <section class="drawer-section">
            <h3 class="section-label">latency 24h</h3>
            <svg
              bind:this={sparkSvg}
              viewBox="0 0 {spark.length * 8} 40"
              class="spark-chart"
              preserveAspectRatio="xMidYMid meet"
            >
              <g bind:this={sparkRoughG}></g>
            </svg>
            <div class="spark-labels">
              <span>{min}{svc[selected].latency?.unit ?? "ms"}</span>
              <span>{max}{svc[selected].latency?.unit ?? "ms"} peak</span>
            </div>
          </section>
        {/if}

        <section class="drawer-section">
          <h3 class="section-label">metrics</h3>
          {#each svc[selected].metrics as m}
            <div class="metric-row">
              <span class="metric-key">{m.k}</span>
              <span class="metric-val">{m.v}</span>
            </div>
          {/each}
        </section>
      </div>
    </aside>
  {/if}
</div>

<style>
  :global(.theme-light) {
    --bg: #f5f0e8;
    --surface: #ebe5d9;
    --tooltip-bg: #f5f0e8;
    --fg: #1a1a1a;
    --fg-secondary: #4a4a4a;
    --fg-tertiary: #7a7a7a;
    --border: #1a1a1a;
    --border-ink: #1a1a1a;
    --danger: #dc2626;
    --warn: #ff9500;
    --tier-ingress: #bfdbfe;
    --tier-critical: #fef08a;
    --tier-infra: #bbf7d0;
    --node-text: #1a1a1a;
    --font: "JetBrains Mono", "SF Mono", "Fira Code", ui-monospace, monospace;
  }

  :global(.theme-dark) {
    --bg: #0f0f0f;
    --surface: #1a1a1a;
    --tooltip-bg: #d4cfc7;
    --fg: #f0f0f0;
    --fg-secondary: #b0b0b0;
    --fg-tertiary: #808080;
    --border: #ffffff;
    --border-ink: #ffffff;
    --danger: #ff4444;
    --warn: #ff9500;
    --tier-ingress: #93c5fd;
    --tier-critical: #fde047;
    --tier-infra: #86efac;
    --node-text: #1a1a1a;
    --font: "JetBrains Mono", "SF Mono", "Fira Code", ui-monospace, monospace;
  }

  /* ── Layout ──────────────────────────────── */

  .root {
    position: relative;
    display: flex;
    flex-direction: column;
    height: 100vh;
    width: 100%;
    font-family: var(--font);
    font-size: 16px;
    line-height: 1.5;
    color: var(--fg);
    background: var(--bg);
    overflow: hidden;
    -webkit-font-feature-settings: "liga" 0;
    font-feature-settings: "liga" 0;
    transition: color 0.3s ease, background 0.3s ease;
    perspective: 1200px;
  }

  .map-wrap {
    flex: 1;
    width: 100%;
    min-height: 0;
    padding: 16px;
    overflow: hidden;
    transform-origin: center center;
    transform-style: preserve-3d;
    transition: opacity 0.15s ease;
  }

  .map {
    width: 100%;
    height: 100%;
  }
  .map :global(path) {
    stroke-linecap: round;
    stroke-linejoin: round;
  }

  /* Scribble-out: scribble draws (250ms), then content fades out (200ms) */
  .map-wrap.scribbling {
    animation: scribbleFade 0.8s ease-in forwards;
  }

  @keyframes scribbleFade {
    0%   { opacity: 1; }
    56%  { opacity: 1; }   /* hold while scribble lines draw (450/800) */
    100% { opacity: 0; }   /* fade to nothing over remaining 350ms */
  }

  /* Paper turn: used for post-draw layout transitions only */
  .map-wrap.flip-out {
    animation: flipOut 0.3s ease-in forwards;
  }

  .map-wrap.flip-in {
    animation: flipIn 0.3s ease-out forwards;
  }

  @keyframes flipOut {
    from { transform: rotateY(0deg); }
    to   { transform: rotateY(90deg); }
  }

  @keyframes flipIn {
    from { transform: rotateY(-90deg); }
    to   { transform: rotateY(0deg); }
  }

  /* ── Theme toggle ─────────────────────────── */

  .theme-toggle {
    position: absolute;
    top: 0.75rem;
    right: 0.75rem;
    z-index: 30;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--fg-secondary);
    cursor: pointer;
    padding: 0.35rem;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: color 0.2s ease, background 0.2s ease, border-color 0.2s ease;
    line-height: 0;
  }

  .theme-toggle:hover {
    color: var(--fg);
    background: var(--border);
  }

  /* ── Drawing animation: per-element DFS stagger */

  @keyframes -global-nodeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  @keyframes -global-edgeDraw {
    to { stroke-dashoffset: 0; }
  }

  @keyframes -global-hoverBorderDraw {
    to { stroke-dashoffset: 0; }
  }

  @keyframes -global-textJot {
    0% { opacity: 0; transform: translate(-1px, 0.5px); }
    40% { opacity: 0.85; }
    100% { opacity: 1; transform: translate(0, 0); }
  }

  /* ── SVG: topology text ──────────────────── */

  .map-pan {
    transition: transform 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  }

  .node-label {
    font-family: var(--font);
    font-size: 9px;
    font-weight: 800;
    fill: var(--node-text);
    text-anchor: middle;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    transition: opacity 0.2s ease;
  }

  .node-label--dimmed { opacity: 0.25; }
  .node-label--active { text-decoration: underline; }

  .tooltip-text {
    font-family: var(--font);
    font-size: 8px;
    font-weight: 700;
    fill: var(--node-text);
    text-anchor: middle;
  }


  .hit-area {
    outline: none;
    transition: x 0.5s cubic-bezier(0.4, 0, 0.2, 1), y 0.5s cubic-bezier(0.4, 0, 0.2, 1);
  }

  /* ── Backdrop + Drawer ───────────────────── */

  .backdrop {
    all: unset;
    position: fixed;
    inset: 0;
    background: transparent;
    z-index: 10;
    cursor: default;
  }

  .drawer {
    position: fixed;
    right: 0;
    top: 0;
    bottom: 0;
    width: 22rem;
    max-width: 90vw;
    background: var(--bg);
    z-index: 20;
    display: flex;
  }

  .drawer-border {
    width: 6px;
    height: 100%;
    flex-shrink: 0;
  }

  .drawer-content {
    flex: 1;
    padding: 2.5rem 2rem 2.5rem 1.5rem;
    overflow-y: auto;
    scrollbar-width: none;
  }

  .drawer-content::-webkit-scrollbar { display: none; }

  .drawer-back {
    font-family: var(--font);
    font-size: 0.7rem;
    color: var(--fg-tertiary);
    background: none;
    border: none;
    padding: 0;
    cursor: pointer;
    margin-bottom: 0.75rem;
    display: block;
  }

  .drawer-back:hover { color: var(--fg-secondary); }

  .drawer-title-row {
    display: flex;
    align-items: baseline;
    gap: 0.75rem;
  }

  .drawer-name {
    font-size: 1rem;
    font-weight: 700;
  }

  .drawer-status {
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.14em;
  }

  .drawer-desc {
    font-size: 0.75rem;
    color: var(--fg-tertiary);
    margin-top: 0.25rem;
  }

  .drawer-section {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    margin-top: 1rem;
  }

  .section-label {
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: var(--fg);
    padding-bottom: 0.3rem;
    border-bottom: 0.04rem solid var(--border);
    margin-bottom: 0.15rem;
  }

  /* ── SLO / Budget / Spark / Metrics ──────── */

  .slo-row { display: flex; align-items: baseline; gap: 0.5rem; }
  .slo-label { font-size: 0.75rem; color: var(--fg-secondary); min-width: 6rem; }
  .slo-value { font-size: 0.8rem; font-weight: 700; font-variant-numeric: tabular-nums; }
  .slo-target { font-size: 0.65rem; color: var(--fg-tertiary); }

  .budget-chart { width: 100%; height: 1.5rem; }
  .budget-labels {
    display: flex; justify-content: space-between;
    font-size: 0.7rem; color: var(--fg-secondary); font-variant-numeric: tabular-nums;
  }
  .budget-meta { font-size: 0.65rem; color: var(--fg-tertiary); }
  .budget-alert {
    font-size: 0.65rem; font-weight: 700; color: var(--danger);
    text-transform: uppercase; letter-spacing: 0.08em;
  }

  .spark-chart { width: 100%; height: 2.5rem; }
  .spark-labels {
    display: flex; justify-content: space-between;
    font-size: 0.65rem; color: var(--fg-tertiary); font-variant-numeric: tabular-nums;
  }

  .metric-row {
    display: flex; justify-content: space-between; align-items: baseline; padding: 0.15rem 0;
  }
  .metric-key { font-size: 0.75rem; color: var(--fg-secondary); }
  .metric-val { font-size: 0.75rem; font-weight: 700; font-variant-numeric: tabular-nums; }

  /* ── Reduced motion ──────────────────────── */

  @media (prefers-reduced-motion: reduce) {
    :global(svg path), .node-label {
      animation: none !important;
      opacity: 1 !important;
      stroke-dashoffset: 0 !important;
      transform: none !important;
      transition: none;
    }
  }
</style>
