import * as dagre from "@dagrejs/dagre";

const CHAR_WIDTH = 7;
const NODE_PAD = 28;
const HH = 22;
const NODE_H = 44;
const GAP_X = 60;
const GAP_Y = 60;
const MAX_LABEL_LEN = 22;

function truncateLabel(title) {
  if (!title || title.length <= MAX_LABEL_LEN) return title || "";
  const cut = title.lastIndexOf(" ", MAX_LABEL_LEN);
  return (
    (cut > 8 ? title.slice(0, cut) : title.slice(0, MAX_LABEL_LEN)) + "\u2026"
  );
}

function computeHW(label) {
  return Math.max(
    32,
    Math.ceil((label.length * CHAR_WIDTH) / 2) + NODE_PAD / 2,
  );
}

/** Find connected components via union-find. */
function findComponents(nodes, edges) {
  const parent = {};
  const find = (x) => (parent[x] === x ? x : (parent[x] = find(parent[x])));
  const union = (a, b) => {
    parent[find(a)] = find(b);
  };

  for (const n of nodes) parent[n.id] = n.id;
  for (const e of edges) {
    if (parent[e.from] !== undefined && parent[e.to] !== undefined) {
      union(e.from, e.to);
    }
  }

  const groups = new Map();
  for (const n of nodes) {
    const root = find(n.id);
    if (!groups.has(root)) groups.set(root, []);
    groups.get(root).push(n);
  }
  return [...groups.values()];
}

/** Layout a single connected component with dagre, returns positioned nodes. */
function layoutComponent(compNodes, allEdges) {
  const ids = new Set(compNodes.map((n) => n.id));
  const compEdges = allEdges.filter((e) => ids.has(e.from) && ids.has(e.to));

  if (compNodes.length === 1) {
    const n = compNodes[0];
    const hw = computeHW(n.label);
    return {
      nodes: [{ ...n, x: 0, y: 0, hw }],
      edges: [],
      w: hw * 2 + NODE_PAD,
      h: NODE_H,
    };
  }

  const g = new dagre.graphlib.Graph();
  g.setGraph({
    rankdir: "TB",
    nodesep: GAP_X,
    ranksep: GAP_Y,
    marginx: 0,
    marginy: 0,
  });
  g.setDefaultEdgeLabel(() => ({}));

  for (const node of compNodes) {
    const hw = computeHW(node.label);
    g.setNode(node.id, { width: hw * 2 + NODE_PAD, height: NODE_H });
  }
  for (const e of compEdges) g.setEdge(e.from, e.to);

  dagre.layout(g);

  let minX = Infinity,
    minY = Infinity,
    maxX = -Infinity,
    maxY = -Infinity;
  const positioned = compNodes.map((n) => {
    const pos = g.node(n.id);
    const hw = computeHW(n.label);
    const x = pos?.x ?? 0;
    const y = pos?.y ?? 0;
    minX = Math.min(minX, x - hw - NODE_PAD / 2);
    maxX = Math.max(maxX, x + hw + NODE_PAD / 2);
    minY = Math.min(minY, y - NODE_H / 2);
    maxY = Math.max(maxY, y + NODE_H / 2);
    return { ...n, x, y, hw };
  });

  // Normalize to origin
  for (const n of positioned) {
    n.x -= minX;
    n.y -= minY;
  }

  return {
    nodes: positioned,
    edges: compEdges,
    w: maxX - minX,
    h: maxY - minY,
  };
}

/**
 * Manages incremental graph layout.
 */
export function createGraphState() {
  let nodes = [];
  let edges = [];
  let nodeMap = {};
  let prevPositions = {};

  function addNode(node) {
    if (nodeMap[node.note_id]) return false;
    const fullTitle = node.title || node.note_id || "untitled";
    const entry = {
      id: node.note_id,
      label: truncateLabel(fullTitle),
      fullTitle,
      type: node.type,
      tags: node.tags || [],
      snippet: node.snippet || "",
      sseEdges: node.edges || [],
      discarded: false,
    };
    nodes.push(entry);
    nodeMap[node.note_id] = entry;
    return true;
  }

  function addEdge(from_id, to_id, edge_type) {
    const exists = edges.some((e) => e.from === from_id && e.to === to_id);
    if (exists) return false;
    edges.push({ from: from_id, to: to_id, type: edge_type });
    return true;
  }

  function discardNode(note_id) {
    if (nodeMap[note_id]) {
      nodeMap[note_id].discarded = true;
    }
  }

  function layout() {
    if (nodes.length === 0) return { nodes: [], edges: [], nodeMap };

    prevPositions = {};
    for (const n of nodes) {
      if (n.x !== undefined) {
        prevPositions[n.id] = { x: n.x, y: n.y };
      }
    }

    // Split into connected components, layout each independently
    const components = findComponents(nodes, edges);
    const laid = components.map((comp) => layoutComponent(comp, edges));

    // Sort: larger components first, then isolates
    laid.sort((a, b) => b.nodes.length - a.nodes.length);

    // Pack components into rows with a max width
    const MAX_ROW_W = Math.max(
      600,
      laid.reduce((s, c) => s + c.w, 0) / Math.ceil(Math.sqrt(laid.length)),
    );

    let cx = 0,
      cy = 0,
      rowH = 0;
    for (const comp of laid) {
      if (cx > 0 && cx + comp.w > MAX_ROW_W) {
        // Wrap to next row
        cx = 0;
        cy += rowH + GAP_Y;
        rowH = 0;
      }
      // Offset all nodes in this component
      for (const n of comp.nodes) {
        n.x += cx;
        n.y += cy;
      }
      cx += comp.w + GAP_X;
      rowH = Math.max(rowH, comp.h);
    }

    // Flatten and add metadata
    const allPositioned = laid.flatMap((comp) =>
      comp.nodes.map((n) => {
        const prev = prevPositions[n.id];
        return {
          ...n,
          prevX: prev?.x,
          prevY: prev?.y,
          isNew: prev === undefined,
        };
      }),
    );

    // Update stored positions
    for (const p of allPositioned) {
      if (nodeMap[p.id]) {
        nodeMap[p.id].x = p.x;
        nodeMap[p.id].y = p.y;
      }
    }

    const allEdges = laid.flatMap((c) => c.edges);

    return { nodes: allPositioned, edges: allEdges, nodeMap };
  }

  function getNodeCount() {
    return nodes.length;
  }

  function reset() {
    nodes = [];
    edges = [];
    nodeMap = {};
    prevPositions = {};
  }

  return { addNode, addEdge, discardNode, layout, getNodeCount, reset };
}
