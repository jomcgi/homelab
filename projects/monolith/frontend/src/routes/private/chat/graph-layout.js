import * as dagre from "@dagrejs/dagre";

const CHAR_WIDTH = 6.5;
const NODE_PAD = 12;
const HH = 18;

function computeHW(label) {
  return Math.max(
    24,
    Math.ceil((label.length * CHAR_WIDTH) / 2) + NODE_PAD / 2,
  );
}

/**
 * Manages incremental graph layout.
 * Call addNode/addEdge as SSE events arrive, then call layout()
 * to get positioned nodes with smooth transitions.
 */
export function createGraphState() {
  let nodes = [];
  let edges = [];
  let nodeMap = {};
  let prevPositions = {};

  function addNode(node) {
    if (nodeMap[node.note_id]) return false;
    const entry = {
      id: node.note_id,
      label: node.title,
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

    // Save previous positions for lerping
    prevPositions = {};
    for (const n of nodes) {
      if (n.x !== undefined) {
        prevPositions[n.id] = { x: n.x, y: n.y };
      }
    }

    const g = new dagre.graphlib.Graph();
    g.setGraph({
      rankdir: "TB",
      nodesep: 50,
      ranksep: 60,
      marginx: 40,
      marginy: 40,
    });
    g.setDefaultEdgeLabel(() => ({}));

    for (const node of nodes) {
      const hw = computeHW(node.label);
      g.setNode(node.id, {
        width: hw * 2 + NODE_PAD,
        height: HH * 2 + 6,
      });
    }

    for (const edge of edges) {
      if (g.hasNode(edge.from) && g.hasNode(edge.to)) {
        g.setEdge(edge.from, edge.to);
      }
    }

    dagre.layout(g);

    const positioned = nodes.map((n) => {
      const pos = g.node(n.id);
      if (!pos) return n;
      const hw = computeHW(n.label);
      const prev = prevPositions[n.id];
      return {
        ...n,
        x: pos.x,
        y: pos.y,
        hw,
        prevX: prev?.x,
        prevY: prev?.y,
        isNew: prev === undefined,
      };
    });

    // Update stored positions
    for (const p of positioned) {
      if (nodeMap[p.id]) {
        nodeMap[p.id].x = p.x;
        nodeMap[p.id].y = p.y;
      }
    }

    return {
      nodes: positioned,
      edges: edges.filter((e) => g.hasNode(e.from) && g.hasNode(e.to)),
      nodeMap,
    };
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
