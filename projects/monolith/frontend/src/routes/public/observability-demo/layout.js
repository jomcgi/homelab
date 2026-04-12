import dagre from "@dagrejs/dagre";

const HH = 18; // half-height of a node (matches +page.svelte)
const CHAR_WIDTH = 6.5; // approximate monospace character width at 11px
const NODE_PAD = 12; // padding around label text

/**
 * Compute half-width from label length.
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
 * @returns {{ nodes: Array, edges: Array, nodeById: Object }}
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

  for (const node of topology.nodes) {
    const hw = computeHW(node.label);
    g.setNode(node.id, {
      width: hw * 2 + NODE_PAD,
      height: HH * 2 + 6,
      tier: node.tier,
    });
  }

  for (const edge of topology.edges) {
    g.setEdge(edge.from, edge.to);
  }

  // Pin infra nodes to a separate rank band via invisible anchor edges
  const infraNodes = topology.nodes.filter((n) => n.tier === "infra");
  if (infraNodes.length > 0) {
    g.setNode("__infra_anchor", { width: 0, height: 0 });
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
