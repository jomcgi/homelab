/**
 * BFS-based animation timeline for DAG topology visualization.
 *
 * Pure computation — no Svelte, no DOM. Takes the output of computeLayout()
 * and produces timing data for every node, edge, and group.
 */

const HH = 18; // half-height of a node (matches dag-layout.js)

/** Default animation constants. Override via `opts` parameter. */
export const DEFAULTS = {
  BOX_PEN_SPEED: 332, // SVG units per second (box outlines)
  EDGE_PEN_SPEED: 349, // SVG units per second (connecting lines)
  MIN_SIDE_DUR: 0.22, // seconds — minimum per box side
  MIN_EDGE_DUR: 0.2, // seconds — minimum per edge line
  TRAVEL_PAUSE: 0.12, // seconds — hand repositioning between elements
  CHAR_MS: 0.03, // seconds per character (quick jot, non-blocking)
  MIN_TEXT: 0.06, // minimum text "jot" duration
  MAX_CURSORS: 2, // parallel drawing streams
  CASCADE_STAGGER: 0.3, // seconds between parallel cursor starts
  MIN_LINE_STAGGER: 0.3, // seconds — minimum gap between any two pencil line starts
  INK_SPEED: 0.85, // ink pass is 85% the duration of pencil
};

/** Pen dynamics: deliberate start, quick middle, slow landing. */
export const PEN_EASE = "cubic-bezier(0.65, 0, 0.15, 1)";

// Deterministic jitter: +/-25% so it looks human
function jitter(key) {
  let h = 0;
  for (let i = 0; i < key.length; i++)
    h = ((h << 5) - h + key.charCodeAt(i)) | 0;
  return 0.75 + (Math.abs(h) % 50) / 100;
}

/**
 * Compute a BFS-driven animation timeline for all nodes, edges, and groups.
 *
 * @param {object} layout — output of computeLayout() { nodes, edges, groups, nodeById, groupById }
 * @param {Array} groupDefs — raw group definitions from topology config (with .children arrays)
 * @param {object} opts — optional overrides for DEFAULTS
 * @returns {{ node: Record<string, object>, edge: Record<string, object>, edgeDir: Record<string, boolean>, group: Record<string, object>, totalDur: number }}
 */
export function computeAnimationTimeline(layout, groupDefs, opts = {}) {
  const {
    BOX_PEN_SPEED,
    EDGE_PEN_SPEED,
    MIN_SIDE_DUR,
    MIN_EDGE_DUR,
    TRAVEL_PAUSE,
    CHAR_MS,
    MIN_TEXT,
    MAX_CURSORS,
    CASCADE_STAGGER,
    MIN_LINE_STAGGER,
    INK_SPEED,
  } = { ...DEFAULTS, ...opts };

  const { nodes, edges, groups, nodeById, groupById } = layout;

  const lookup = (id) => nodeById[id] || groupById[id];

  // Build adjacency lists (including group IDs as valid entries)
  const adj = {};
  nodes.forEach((n) => (adj[n.id] = []));
  for (const g of groupDefs) adj[g.id] = [];
  edges.forEach((e) => {
    if (adj[e.from] && adj[e.to]) {
      adj[e.from].push({ nb: e.to, edge: e });
      adj[e.to].push({ nb: e.from, edge: e });
    }
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
    if (!from || !to) return MIN_EDGE_DUR;
    const dist = Math.sqrt((from.x - to.x) ** 2 + (from.y - to.y) ** 2);
    return Math.max(MIN_EDGE_DUR, (dist / EDGE_PEN_SPEED) * jitter(key));
  }

  // Find which side of the box the incoming edge hits
  // Sides: 0=top, 1=right, 2=bottom, 3=left
  function arrivalSide(n, fromX, fromY) {
    const dx = fromX - n.x;
    const dy = fromY - n.y;
    if (dx === 0 && dy === 0) return 0;
    const isGrp = !!groupById[n.id];
    const w = isGrp ? n.hw * 2 : n.hw * 2 + 12;
    const h = isGrp ? n.hh * 2 : HH * 2 + 6;
    // Normalize by half-dimensions so rectangles behave like squares
    const sx = Math.abs(dx) / (w / 2);
    const sy = Math.abs(dy) / (h / 2);
    if (sy > sx) {
      return dy < 0 ? 0 : 2; // top or bottom
    } else {
      return dx > 0 ? 1 : 3; // right or left
    }
  }

  const visited = new Set(["external"]);
  const nd = {};
  const ed = {};
  const edDir = {};

  // Schedule a node's pencil box. Returns pencil cursor after box completes.
  function scheduleNode(c, item) {
    const { id, fromX, fromY } = item;
    const n = lookup(id);
    if (!n) return c;
    const side = arrivalSide(n, fromX, fromY);
    const sides = boxSideDurs(n);
    const bDur = sides.reduce((a, b) => a + b, 0);
    const tDur = textDur(n.label);

    const fillStart = c + bDur + bDur * INK_SPEED; // fill scrubs in after ink completes
    const fillDur = 0.25; // quick color scrub
    nd[id] = {
      box: c, // pencil box start
      boxSides: sides, // pencil per-side durations
      boxStartSide: side,
      boxDur: bDur, // total pencil box duration
      inkBox: c + bDur, // ink retrace starts when pencil box finishes
      inkBoxDur: bDur * INK_SPEED,
      inkBoxSides: sides.map((d) => d * INK_SPEED),
      fill: fillStart, // color fill after ink outline
      fillDur,
      text: fillStart + fillDur * 0.5, // text jots in as fill is completing
      textDur: tDur,
    };
    return c + bDur; // pencil cursor: box done, ready for edges
  }

  // Schedule an edge's pencil + ink lines. siblingIdx staggers ink starts.
  function scheduleEdge(pencilStart, parentId, edge, siblingIdx) {
    const key = edge.from + "-" + edge.to;
    edDir[key] = edge.from === parentId;
    const from = lookup(edge.from);
    const to = lookup(edge.to);
    const eDur = edgeDur(from, to, key);

    // Ink line waits for: parent's ink box + stagger, AND pencil line to complete + pause
    const parent = nd[parentId];
    const parentInkDone = parent
      ? parent.inkBox + parent.inkBoxDur
      : pencilStart;
    const inkStagger =
      (siblingIdx || 0) * CASCADE_STAGGER * jitter(key + "ink-stg");
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
    const n = lookup(item.id);
    if (!n) return [];
    const children = [];
    let sibIdx = 0;
    for (const { nb: nbId, edge } of adj[item.id]) {
      if (visited.has(nbId)) continue;
      visited.add(nbId);
      children.push({
        id: nbId,
        fromX: n.x,
        fromY: n.y,
        viaEdge: edge,
        parentId: item.id,
        siblingIdx: sibIdx++,
      });
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

  // BFS traversal starting from "external" node
  let batch = [
    {
      id: "external",
      fromX: 0,
      fromY: lookup("external")?.y ?? 240,
      viaEdge: null,
      parentId: null,
    },
  ];
  let cursor = 0.2;

  while (batch.length > 0) {
    const nextBatch = [];

    if (batch.length === 1) {
      cursor = scheduleItem(cursor, batch[0]);
      nextBatch.push(...collectChildren(batch[0]));
    } else {
      const numCursors = Math.min(MAX_CURSORS, batch.length);
      const cursors = Array.from(
        { length: numCursors },
        (_, i) => cursor + i * CASCADE_STAGGER * jitter("cursor" + i),
      );
      let lastLineStart = -Infinity;

      batch.forEach((item, i) => {
        const ci = i % numCursors;
        // Ensure no two pencil lines start within MIN_LINE_STAGGER of each other
        if (item.viaEdge) {
          cursors[ci] = Math.max(
            cursors[ci],
            lastLineStart + MIN_LINE_STAGGER * jitter(item.id + "line-stg"),
          );
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
  edges.forEach((e) => {
    const key = e.from + "-" + e.to;
    if (ed[key]) return;
    const eDur = edgeDur(lookup(e.from), lookup(e.to), key);
    const fromDone = (nd[e.from]?.box ?? 0) + (nd[e.from]?.boxDur ?? 0);
    const toDone = (nd[e.to]?.box ?? 0) + (nd[e.to]?.boxDur ?? 0);
    edDir[key] = fromDone <= toDone;
    ed[key] = {
      pencilLine: cursor,
      pencilLineDur: eDur,
      inkLine: cursor + eDur * 0.3,
      inkLineDur: eDur * INK_SPEED,
    };
    cursor += eDur + TRAVEL_PAUSE;
  });

  // Schedule unvisited nodes (infra tier — no edges from critical path)
  // Single cursor fills left-to-right sequentially
  const unvisited = nodes
    .filter((n) => !visited.has(n.id))
    .sort((a, b) => a.x - b.x);
  if (unvisited.length > 0) {
    let infraCursor = 0.8; // start shortly after cloudflare
    unvisited.forEach((n) => {
      visited.add(n.id);
      infraCursor = scheduleNode(infraCursor, {
        id: n.id,
        fromX: n.x,
        fromY: n.y - 80,
      });
      infraCursor += TRAVEL_PAUSE * 0.5; // brief pause between infra nodes
    });
  }

  // Schedule group boundaries — draw after all children complete their ink phase
  const gd = {};
  for (const group of groupDefs) {
    let latestChildInkDone = 0;
    for (const cid of group.children) {
      if (nd[cid]) {
        const childDone = nd[cid].inkBox + nd[cid].inkBoxDur;
        latestChildInkDone = Math.max(latestChildInkDone, childDone);
      }
    }
    const gStart = latestChildInkDone + TRAVEL_PAUSE;
    // Group boundary is larger — estimate perimeter for timing
    const gNode = groups.find((g) => g.id === group.id);
    if (!gNode) continue;
    const gSides = [
      Math.max(
        MIN_SIDE_DUR,
        ((gNode.hw * 2) / BOX_PEN_SPEED) * jitter(group.id + "top"),
      ),
      Math.max(
        MIN_SIDE_DUR,
        ((gNode.hh * 2) / BOX_PEN_SPEED) * jitter(group.id + "right"),
      ),
      Math.max(
        MIN_SIDE_DUR,
        ((gNode.hw * 2) / BOX_PEN_SPEED) * jitter(group.id + "bottom"),
      ),
      Math.max(
        MIN_SIDE_DUR,
        ((gNode.hh * 2) / BOX_PEN_SPEED) * jitter(group.id + "left"),
      ),
    ];
    const gDur = gSides.reduce((a, b) => a + b, 0);
    const tDur = textDur(group.label);
    gd[group.id] = {
      box: gStart,
      boxSides: gSides,
      boxStartSide: 0,
      boxDur: gDur,
      inkBox: gStart + gDur,
      inkBoxDur: gDur * INK_SPEED,
      inkBoxSides: gSides.map((d) => d * INK_SPEED),
      fill: gStart + gDur + gDur * INK_SPEED,
      fillDur: 0.35,
      text: gStart + gDur + gDur * INK_SPEED + 0.1,
      textDur: tDur,
    };
  }

  let maxT = 0;
  for (const v of Object.values(nd))
    maxT = Math.max(maxT, v.inkBox + v.inkBoxDur);
  for (const v of Object.values(ed))
    maxT = Math.max(maxT, v.inkLine + v.inkLineDur);
  for (const v of Object.values(gd))
    maxT = Math.max(maxT, v.inkBox + v.inkBoxDur);

  return {
    node: nd,
    edge: ed,
    edgeDir: edDir,
    group: gd,
    totalDur: maxT + 0.5,
  };
}
