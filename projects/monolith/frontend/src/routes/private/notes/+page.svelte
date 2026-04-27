<script>
  import KnowledgeGraph from "$lib/components/notes/KnowledgeGraph.svelte";
  import NotePanel from "$lib/components/notes/NotePanel.svelte";
  import GraphLegend from "$lib/components/notes/GraphLegend.svelte";
  import GraphSearch from "$lib/components/notes/GraphSearch.svelte";
  import StatusBar from "$lib/components/notes/StatusBar.svelte";

  let { data } = $props();
  let graph = $derived(data.graph);
  let nodes = $derived(graph.nodes);
  let edges = $derived(graph.edges);
  let indexedAt = $derived(graph.indexed_at);

  // Compute degree once per graph payload.
  let nodesWithDegree = $derived.by(() => {
    const deg = new Map(nodes.map((n) => [n.id, 0]));
    for (const e of edges) {
      deg.set(e.source, (deg.get(e.source) ?? 0) + 1);
      deg.set(e.target, (deg.get(e.target) ?? 0) + 1);
    }
    return nodes.map((n) => ({ ...n, degree: deg.get(n.id) ?? 0 }));
  });

  let activeClusters = $state(
    new Set(nodes.map((n) => n.type ?? "other")),
  );
  let searchTerm = $state("");
  let selectedId = $state(null);
  let zoom = $state(1);
  let hoverTitle = $state("—");

  let clusterCount = $derived(activeClusters.size);

  function toggleCluster(type) {
    const next = new Set(activeClusters);
    next.has(type) ? next.delete(type) : next.add(type);
    activeClusters = next;
  }

  function selectNode(id) {
    selectedId = id;
  }
</script>

<div class="notes-root">
  <StatusBar
    nodeCount={nodes.length}
    edgeCount={edges.length}
    {clusterCount}
    {zoom}
    {hoverTitle}
    {indexedAt}
  />

  <div class="notes-stage">
    <KnowledgeGraph
      nodes={nodesWithDegree}
      {edges}
      {selectedId}
      {searchTerm}
      {activeClusters}
      onNodeClick={(e) => selectNode(e.id)}
      onNodeHover={(e) => (hoverTitle = e.title ?? "—")}
      onZoom={(k) => (zoom = k)}
    />

    <GraphSearch value={searchTerm} onChange={(v) => (searchTerm = v)} />
    <GraphLegend
      nodes={nodesWithDegree}
      {activeClusters}
      onToggle={toggleCluster}
    />
    <NotePanel
      {selectedId}
      nodes={nodesWithDegree}
      {edges}
      onSelect={selectNode}
      onClose={() => (selectedId = null)}
    />
  </div>
</div>

<style>
  .notes-root {
    /* Total height = viewport - shared Nav. The Nav uses var(--space-xs)
       padding (8px top + bottom) plus 11px font-size with line-height ~1.6
       and a 2px bottom border, landing at ~48px. If the Nav padding is ever
       bumped, adjust this constant. */
    height: calc(100vh - 48px);
    display: flex;
    flex-direction: column;
    background: var(--bg);
    color: var(--fg);
  }
  .notes-stage {
    flex: 1;
    position: relative;
    overflow: hidden;
  }
</style>
