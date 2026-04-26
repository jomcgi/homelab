import * as dagre from "@dagrejs/dagre";

const HH = 14; // half-height of a node (matches DagRenderer.svelte)
const CHAR_WIDTH = 6.5; // approximate monospace character width at 11px
const NODE_PAD = 12; // padding around label text (used in both computeHW and box width)
const DOT_RESERVE = 10; // extra left-side space for the status dot, added to box width only
const GROUP_PAD = 16; // padding inside group boundary around children
const GROUP_LABEL_H = 14; // extra top padding for group label

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
 * Run dagre layout on the topology config, with compound graph support for groups.
 *
 * @param {Object} topology - The topology.json structure ({ nodes, edges, groups })
 * @param {"LR"|"TB"} rankdir - Layout direction
 * @returns {{ nodes: Array, edges: Array, groups: Array, nodeById: Object, groupById: Object }}
 */
export function computeLayout(topology, rankdir) {
  const g = new dagre.graphlib.Graph({ compound: true });
  g.setGraph({
    rankdir,
    nodesep: rankdir === "LR" ? 40 : 50,
    ranksep: rankdir === "LR" ? 60 : 45,
    marginx: 40,
    marginy: 40,
  });
  g.setDefaultEdgeLabel(() => ({}));

  const groups = topology.groups || [];
  const groupIds = new Set(groups.map((g) => g.id));
  const childToGroup = {};
  for (const group of groups) {
    for (const childId of group.children) {
      childToGroup[childId] = group.id;
    }
  }

  // Only add non-infra nodes to dagre — infra nodes are positioned manually
  const infraNodeIds = new Set(
    topology.nodes.filter((n) => n.tier === "infra").map((n) => n.id),
  );

  // Register group nodes in dagre (compound parents)
  // Groups need explicit padding so dagre leaves room for the boundary
  for (const group of groups) {
    g.setNode(group.id, {
      clusterLabelPos: "top",
      paddingTop: GROUP_PAD + GROUP_LABEL_H,
      paddingBottom: GROUP_PAD,
      paddingLeft: GROUP_PAD,
      paddingRight: GROUP_PAD,
    });
  }

  // Register child + standalone nodes
  for (const node of topology.nodes) {
    if (infraNodeIds.has(node.id)) continue;
    const hw = computeHW(node.label);
    g.setNode(node.id, {
      width: hw * 2 + NODE_PAD + DOT_RESERVE,
      height: HH * 2 + 6,
      tier: node.tier,
    });
    // Set parent for compound grouping
    if (childToGroup[node.id]) {
      g.setParent(node.id, childToGroup[node.id]);
    }
  }

  // Map group IDs to a representative child for dagre layout proxying.
  // Dagre can't route edges to compound parents, so we pick the first child
  // as a proxy target — the renderer still draws to the group boundary.
  const groupProxy = {};
  for (const group of groups) {
    if (group.children.length > 0) {
      groupProxy[group.id] = group.children[0];
    }
  }

  // Add edges — proxy group-targeted edges through a child node for layout.
  // Edges with sameRank:true are rendered but excluded from dagre so they
  // don't force a rank dependency between the endpoints.
  for (const edge of topology.edges) {
    if (edge.sameRank) continue;
    let from = edge.from;
    let to = edge.to;
    // Skip edges involving infra nodes
    if (infraNodeIds.has(from) || infraNodeIds.has(to)) continue;
    // Proxy group IDs to a child node for dagre positioning
    if (groupIds.has(from)) from = groupProxy[from] || from;
    if (groupIds.has(to)) to = groupProxy[to] || to;
    // Skip if either endpoint is still a group (no children) or missing
    if (groupIds.has(from) || groupIds.has(to)) continue;
    if (!g.hasNode(from) || !g.hasNode(to)) continue;
    g.setEdge(from, to);
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
    if (!pos) continue;
    positioned.push({ ...n, x: pos.x, y: pos.y, hw: computeHW(n.label) });
    maxY = Math.max(maxY, pos.y);
    maxX = Math.max(maxX, pos.x + computeHW(n.label));
    minX = Math.min(minX, pos.x - computeHW(n.label));
  }

  // Position infra nodes in a row below the critical path (before group boundary computation)
  const infraNodes = topology.nodes.filter((n) => n.tier === "infra");
  const infraGap = 90; // gap below last critical rank (accounts for group boundary padding above)
  const infraSep = 18; // spacing between infra nodes
  if (infraNodes.length > 0) {
    const infraWidths = infraNodes.map(
      (n) => computeHW(n.label) * 2 + NODE_PAD + DOT_RESERVE,
    );
    const totalInfraW =
      infraWidths.reduce((a, b) => a + b, 0) +
      infraSep * (infraNodes.length - 1);

    // When the subgraph has no critical-path nodes (e.g. focusing on
    // an infra-only group like "cluster"), maxY/minX/maxX stay at
    // ±Infinity. Fall back to sensible defaults so the row renders.
    const safeMinX = isFinite(minX) ? minX : 0;
    const safeMaxX = isFinite(maxX) ? maxX : 0;
    const safeMaxY = isFinite(maxY) ? maxY : -infraGap;
    const critCenterX = (safeMinX + safeMaxX) / 2;
    let infraX = critCenterX - totalInfraW / 2;
    const infraY = safeMaxY + infraGap + HH * 2 + 6;

    infraNodes.forEach((n, i) => {
      const hw = computeHW(n.label);
      const w = hw * 2 + NODE_PAD + DOT_RESERVE;
      positioned.push({ ...n, x: infraX + w / 2, y: infraY, hw });
      infraX += w + infraSep;
    });
  }

  // Compute group boundaries from their children's positioned bounding boxes
  // (runs after all nodes — including infra — are positioned)
  const positionedGroups = [];
  for (const group of groups) {
    const children = positioned.filter((n) => childToGroup[n.id] === group.id);
    if (children.length === 0) continue;

    let gMinX = Infinity,
      gMinY = Infinity,
      gMaxX = -Infinity,
      gMaxY = -Infinity;
    for (const c of children) {
      const w = c.hw + (NODE_PAD + DOT_RESERVE) / 2;
      gMinX = Math.min(gMinX, c.x - w);
      gMaxX = Math.max(gMaxX, c.x + w);
      gMinY = Math.min(gMinY, c.y - HH - 3);
      gMaxY = Math.max(gMaxY, c.y + HH + 3);
    }

    // Add padding for the group boundary
    gMinX -= GROUP_PAD;
    gMaxX += GROUP_PAD;
    gMinY -= GROUP_PAD + GROUP_LABEL_H;
    gMaxY += GROUP_PAD;

    const cx = (gMinX + gMaxX) / 2;
    const cy = (gMinY + gMaxY) / 2;
    const hw = (gMaxX - gMinX) / 2;
    const hh = (gMaxY - gMinY) / 2;

    positionedGroups.push({
      ...group,
      x: cx,
      y: cy,
      hw,
      hh,
      bounds: { minX: gMinX, minY: gMinY, maxX: gMaxX, maxY: gMaxY },
    });
  }

  const nodes = positioned;
  const nodeById = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const groupById = Object.fromEntries(positionedGroups.map((g) => [g.id, g]));

  return {
    nodes,
    edges: topology.edges,
    groups: positionedGroups,
    nodeById,
    groupById,
  };
}
