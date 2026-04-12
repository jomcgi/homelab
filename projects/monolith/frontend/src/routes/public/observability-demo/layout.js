import * as dagre from "@dagrejs/dagre";

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
  const g = new dagre.graphlib.Graph();
  g.setGraph({
    rankdir,
    nodesep: rankdir === "LR" ? 40 : 50,
    ranksep: rankdir === "LR" ? 60 : 45,
    marginx: 40,
    marginy: 40,
  });
  g.setDefaultEdgeLabel(() => ({}));

  // Only add non-infra nodes to dagre — infra nodes are positioned manually
  const infraNodeIds = new Set(
    topology.nodes.filter((n) => n.tier === "infra").map((n) => n.id),
  );

  for (const node of topology.nodes) {
    if (infraNodeIds.has(node.id)) continue;
    const hw = computeHW(node.label);
    g.setNode(node.id, {
      width: hw * 2 + NODE_PAD,
      height: HH * 2 + 6,
      tier: node.tier,
    });
  }

  for (const edge of topology.edges) {
    if (!infraNodeIds.has(edge.from) && !infraNodeIds.has(edge.to)) {
      g.setEdge(edge.from, edge.to);
    }
  }

  dagre.layout(g);

  // Collect dagre-positioned nodes and find the bounding box
  const positioned = [];
  let maxY = -Infinity;
  let maxX = -Infinity;
  let minX = Infinity;
  for (const n of topology.nodes) {
    if (infraNodeIds.has(n.id)) continue;
    const pos = g.node(n.id);
    positioned.push({ ...n, x: pos.x, y: pos.y, hw: computeHW(n.label) });
    maxY = Math.max(maxY, pos.y);
    maxX = Math.max(maxX, pos.x + computeHW(n.label));
    minX = Math.min(minX, pos.x - computeHW(n.label));
  }

  // Position infra nodes in a row below the critical path
  const infraNodes = topology.nodes.filter((n) => n.tier === "infra");
  const infraGap = 30; // gap below last critical rank
  const infraSep = 18; // spacing between infra nodes
  if (infraNodes.length > 0) {
    // Calculate total width of all infra nodes
    const infraWidths = infraNodes.map(
      (n) => computeHW(n.label) * 2 + NODE_PAD,
    );
    const totalInfraW =
      infraWidths.reduce((a, b) => a + b, 0) +
      infraSep * (infraNodes.length - 1);

    // Center the infra row under the critical path
    const critCenterX = (minX + maxX) / 2;
    let infraX = critCenterX - totalInfraW / 2;
    const infraY = maxY + infraGap + HH * 2 + 6;

    infraNodes.forEach((n, i) => {
      const hw = computeHW(n.label);
      const w = hw * 2 + NODE_PAD;
      positioned.push({ ...n, x: infraX + w / 2, y: infraY, hw });
      infraX += w + infraSep;
    });
  }

  const nodes = positioned;

  const nodeById = Object.fromEntries(nodes.map((n) => [n.id, n]));

  return { nodes, edges: topology.edges, nodeById };
}
