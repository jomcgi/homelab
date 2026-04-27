<script>
  import KnowledgeGraph from "$lib/components/notes/KnowledgeGraph.svelte";
  import NotePanel from "$lib/components/notes/NotePanel.svelte";
  import GraphLegend from "$lib/components/notes/GraphLegend.svelte";
  import GraphSearch from "$lib/components/notes/GraphSearch.svelte";
  import StatusBar from "$lib/components/notes/StatusBar.svelte";

  let { data } = $props();

  // Drop nodes without a recognised cluster type (Note.type IS NULL or
  // an unmapped value): these are usually pre-pipeline imports that
  // haven't been classified yet. They have no useful colour or label
  // affordance, so excluding them keeps the legend clean and the canvas
  // free of "what is this thing" mystery dots.
  const KNOWN_TYPES = new Set([
    "atom",
    "fact",
    "raw",
    "gap",
    "active",
    "paper",
  ]);
  let nodes = $derived(
    data.graph.nodes.filter((n) => n.type && KNOWN_TYPES.has(n.type)),
  );
  let edges = $derived(
    (() => {
      const ids = new Set(
        data.graph.nodes
          .filter((n) => n.type && KNOWN_TYPES.has(n.type))
          .map((n) => n.id),
      );
      return data.graph.edges.filter(
        (e) => ids.has(e.source) && ids.has(e.target),
      );
    })(),
  );
  let indexedAt = $derived(data.graph.indexed_at);

  // Compute degree once per (filtered) graph payload.
  let nodesWithDegree = $derived.by(() => {
    const ns = nodes;
    const es = edges;
    const deg = new Map(ns.map((n) => [n.id, 0]));
    for (const e of es) {
      deg.set(e.source, (deg.get(e.source) ?? 0) + 1);
      deg.set(e.target, (deg.get(e.target) ?? 0) + 1);
    }
    return ns.map((n) => ({ ...n, degree: deg.get(n.id) ?? 0 }));
  });

  // activeClusters is initialised from the *initial* graph (a one-time
  // snapshot), then mutated locally as the user toggles. Reading data
  // (a $props value) inside $state() captures cleanly; reading a
  // $derived inside $state() trips state_referenced_locally.
  let activeClusters = $state(
    new Set(
      data.graph.nodes
        .map((n) => n.type)
        .filter((t) => t && KNOWN_TYPES.has(t)),
    ),
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
    height: calc(100vh - 48px);
    display: flex;
    flex-direction: column;
    background: #f1ebdc;
    color: #141414;
    font-family: "JetBrains Mono", ui-monospace, "SF Mono", monospace;
    font-size: 13px;
    line-height: 1.45;
  }
  .notes-stage {
    flex: 1;
    position: relative;
    overflow: hidden;
  }
</style>
