<script>
  import rough from "roughjs";
  import { marked } from "marked";
  import { createGraphState } from "./graph-layout.js";

  let messages = $state([]);
  let graphEvents = $state([]);
  let inputText = $state("");
  let isStreaming = $state(false);
  let chatLog;
  let hoveredNode = $state(null);
  let selectedNode = $state(null);
  let drawerNote = $state(null);
  let drawerLoading = $state(false);

  const graphState = createGraphState();
  let layoutResult = $state({ nodes: [], edges: [], nodeMap: {} });
  let svgEl;
  let processedCount = $state(0);

  const TYPE_COLORS = {
    note: { fill: "#dbeafe", border: "#3b82f6", pencil: "#93c5fd" },
    paper: { fill: "#dcfce7", border: "#22c55e", pencil: "#86efac" },
    article: { fill: "#fef3c7", border: "#f59e0b", pencil: "#fcd34d" },
    recipe: { fill: "#ffe4e6", border: "#f43f5e", pencil: "#fda4af" },
  };

  /** Remove all child nodes from an element. */
  function clearChildren(el) {
    if (!el) return;
    while (el.firstChild) {
      el.removeChild(el.firstChild);
    }
  }

  function scrollToBottom() {
    if (chatLog) {
      requestAnimationFrame(() => {
        chatLog.scrollTop = chatLog.scrollHeight;
      });
    }
  }

  async function sendMessage() {
    const text = inputText.trim();
    if (!text || isStreaming) return;

    inputText = "";
    messages.push({ role: "user", content: text });
    messages.push({ role: "assistant", content: "" });
    isStreaming = true;
    scrollToBottom();

    try {
      const res = await fetch("/private/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          history: messages.slice(0, -2).map((m) => ({
            role: m.role,
            content: m.content,
          })),
        }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6));

            if (event.type === "text_chunk") {
              messages[messages.length - 1].content += event.data.text;
              scrollToBottom();
            } else if (event.type === "error") {
              messages[messages.length - 1].content +=
                `\n[Error: ${event.data.message}]`;
            } else if (event.type === "done") {
              // Stream complete
            } else {
              // Graph events: node_discovered, node_discarded, edge_traversed
              graphEvents.push(event);
            }
          } catch {
            // Skip malformed events
          }
        }
      }
    } catch (err) {
      messages[messages.length - 1].content +=
        `\n[Connection error: ${err.message}]`;
    } finally {
      isStreaming = false;
    }
  }

  function onKeydown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  function onGlobalKeydown(e) {
    if (e.key === "Escape" && selectedNode) {
      selectedNode = null;
    }
  }

  // Fetch note content when a node is selected
  $effect(() => {
    if (!selectedNode) {
      drawerNote = null;
      return;
    }
    drawerLoading = true;
    fetch(`/private/chat?note_id=${encodeURIComponent(selectedNode)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((note) => {
        drawerNote = note;
        drawerLoading = false;
      })
      .catch(() => {
        drawerNote = null;
        drawerLoading = false;
      });
  });

  // Process new graph events into layout (declared before drawing effect)
  $effect(() => {
    if (graphEvents.length <= processedCount) return;

    for (let i = processedCount; i < graphEvents.length; i++) {
      const evt = graphEvents[i];
      if (evt.type === "node_discovered") {
        graphState.addNode(evt.data);
        for (const edge of evt.data.edges || []) {
          graphState.addEdge(
            evt.data.note_id,
            edge.target_id,
            edge.edge_type || "link",
          );
        }
      } else if (evt.type === "edge_traversed") {
        graphState.addEdge(
          evt.data.from_id,
          evt.data.to_id,
          evt.data.edge_type,
        );
      } else if (evt.type === "node_discarded") {
        graphState.discardNode(evt.data.note_id);
      }
    }
    processedCount = graphEvents.length;

    layoutResult = graphState.layout();
  });

  /** Return the set of node IDs connected to focusId (including itself). */
  function getConnectedNodes(focusId) {
    if (!focusId) return null;
    const connected = new Set([focusId]);
    for (const edge of layoutResult.edges) {
      if (edge.from === focusId) connected.add(edge.to);
      if (edge.to === focusId) connected.add(edge.from);
    }
    return connected;
  }

  // Draw rough.js elements when layout changes
  $effect(() => {
    if (!svgEl || layoutResult.nodes.length === 0) return;
    const rc = rough.svg(svgEl);

    const nodeG = svgEl.querySelector(".graph-nodes");
    const edgeG = svgEl.querySelector(".graph-edges");
    const discardG = svgEl.querySelector(".graph-discards");
    clearChildren(nodeG);
    clearChildren(edgeG);
    clearChildren(discardG);

    const focusId = selectedNode || hoveredNode;
    const connected = getConnectedNodes(focusId);

    // Compute viewBox to fit all nodes
    let minX = Infinity,
      minY = Infinity,
      maxX = -Infinity,
      maxY = -Infinity;
    for (const n of layoutResult.nodes) {
      minX = Math.min(minX, n.x - n.hw - 10);
      maxX = Math.max(maxX, n.x + n.hw + 10);
      minY = Math.min(minY, n.y - 21);
      maxY = Math.max(maxY, n.y + 21);
    }
    const pad = 40;
    svgEl.setAttribute(
      "viewBox",
      `${minX - pad} ${minY - pad} ${maxX - minX + pad * 2} ${maxY - minY + pad * 2}`,
    );

    // Draw edges
    for (const edge of layoutResult.edges) {
      const from = layoutResult.nodeMap[edge.from];
      const to = layoutResult.nodeMap[edge.to];
      if (!from?.x || !to?.x) continue;

      const edgeDimmed =
        connected && !connected.has(edge.from) && !connected.has(edge.to);
      const line = rc.line(from.x, from.y, to.x, to.y, {
        stroke: "#8a8070",
        strokeWidth: 1.5,
        roughness: 0.8,
      });
      line.style.opacity = edgeDimmed ? "0.25" : "1";
      edgeG.appendChild(line);

      const midX = (from.x + to.x) / 2;
      const midY = (from.y + to.y) / 2;
      const label = document.createElementNS(
        "http://www.w3.org/2000/svg",
        "text",
      );
      label.setAttribute("x", midX);
      label.setAttribute("y", midY - 6);
      label.setAttribute("text-anchor", "middle");
      label.setAttribute("class", "edge-label");
      label.textContent = edge.type || "";
      label.style.opacity = edgeDimmed ? "0.25" : "1";
      edgeG.appendChild(label);
    }

    // Draw nodes
    for (const node of layoutResult.nodes) {
      const colors = TYPE_COLORS[node.type] || TYPE_COLORS.note;
      const w = node.hw * 2 + 12;
      const h = 42;

      const rect = rc.rectangle(node.x - w / 2, node.y - h / 2, w, h, {
        fill: node.discarded ? "#e5e5e5" : colors.fill,
        stroke: node.discarded ? "#999" : colors.border,
        strokeWidth: 2,
        roughness: 1,
        fillStyle: "solid",
      });

      const dimmed = connected && !connected.has(node.id);
      const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      g.style.opacity = dimmed ? "0.25" : "1";
      if (node.isNew) {
        g.classList.add("node-enter");
      }
      g.appendChild(rect);

      const text = document.createElementNS(
        "http://www.w3.org/2000/svg",
        "text",
      );
      text.setAttribute("x", node.x);
      text.setAttribute("y", node.y + 4);
      text.setAttribute("text-anchor", "middle");
      text.setAttribute(
        "class",
        `node-label${node.discarded ? " node-label--discarded" : ""}`,
      );
      text.textContent = node.label;
      g.appendChild(text);

      nodeG.appendChild(g);

      // Discard strikethrough
      if (node.discarded) {
        const x1 = node.x - w / 2 + 4;
        const y1 = node.y - h / 2 + 4;
        const x2 = node.x + w / 2 - 4;
        const y2 = node.y + h / 2 - 4;

        const strike1 = rc.line(x1, y1, x2, y2, {
          stroke: "#dc2626",
          strokeWidth: 2.5,
          roughness: 1.5,
        });
        const strike2 = rc.line(x2, y1, x1, y2, {
          stroke: "#dc2626",
          strokeWidth: 2.5,
          roughness: 1.5,
        });
        discardG.appendChild(strike1);
        discardG.appendChild(strike2);
      }
    }
  });
</script>

<svelte:window onkeydown={onGlobalKeydown} />

<svelte:head>
  <title>Knowledge Explorer</title>
</svelte:head>

<div class="explorer">
  <header class="explorer-header">
    <span class="header-title">KNOWLEDGE EXPLORER</span>
    <span class="header-sub">powered by gemma-4</span>
  </header>

  <div class="chat-card">
    <div class="chat-log" bind:this={chatLog}>
      {#each messages as msg, i}
        <div class="chat-msg chat-msg--{msg.role}">
          <span class="chat-role">{msg.role === "user" ? "you" : "gemma"}</span>
          <span class="chat-text">{msg.content}</span>
          {#if i === messages.length - 1 && isStreaming && msg.role === "assistant"}
            <span class="chat-cursor">|</span>
          {/if}
        </div>
      {/each}
      {#if messages.length === 0}
        <p class="chat-empty">Ask a question to start exploring your knowledge graph</p>
      {/if}
    </div>
    <div class="chat-input-bar">
      <input
        type="text"
        bind:value={inputText}
        onkeydown={onKeydown}
        placeholder="explore your knowledge..."
        disabled={isStreaming}
      />
      <button onclick={sendMessage} disabled={isStreaming || !inputText.trim()}>
        &rarr;
      </button>
    </div>
  </div>

  <hr class="graph-rule" />

  <div class="graph-area">
    {#if graphState.getNodeCount() === 0}
      <p class="graph-empty">Ask a question to start exploring</p>
    {:else}
      <svg bind:this={svgEl} class="graph-svg" xmlns="http://www.w3.org/2000/svg">
        <g class="graph-edges"></g>
        <g class="graph-nodes"></g>
        <g class="graph-discards"></g>
        <g class="graph-hit-areas">
          {#each layoutResult.nodes as node}
            {#if !node.discarded}
              <rect
                x={node.x - (node.hw + 6)}
                y={node.y - 21}
                width={(node.hw + 6) * 2}
                height={42}
                fill="transparent"
                style="cursor: pointer;"
                role="button"
                tabindex="0"
                aria-label={node.label}
                onmouseenter={() => (hoveredNode = node.id)}
                onmouseleave={() => (hoveredNode = null)}
                onclick={() => (selectedNode = selectedNode === node.id ? null : node.id)}
              />
            {/if}
          {/each}
        </g>
      </svg>
    {/if}
  </div>

  {#if selectedNode}
    <div
      class="note-drawer"
      role="complementary"
      aria-label="Note details"
    >
      <button class="drawer-close" onclick={() => (selectedNode = null)}>
        &times;
      </button>
      {#if drawerLoading}
        <p class="drawer-loading">Loading...</p>
      {:else if drawerNote}
        <h2 class="drawer-title">{drawerNote.title}</h2>
        <div class="drawer-meta">
          <span class="drawer-type">{drawerNote.type}</span>
          {#each drawerNote.tags || [] as tag}
            <span class="drawer-tag">{tag}</span>
          {/each}
        </div>
        <div class="drawer-content">
          {@html marked(drawerNote.content || "")}
        </div>
        {#if drawerNote.edges?.length > 0}
          <div class="drawer-edges">
            <h3 class="drawer-edges-title">EDGES</h3>
            {#each drawerNote.edges as edge}
              <div class="drawer-edge">
                <span class="drawer-edge-type">{edge.edge_type || edge.kind || "link"}</span>
                <span class="drawer-edge-target">{edge.target_title || edge.target_id}</span>
              </div>
            {/each}
          </div>
        {/if}
      {:else}
        <p class="drawer-loading">Note not found</p>
      {/if}
    </div>
  {/if}
</div>

<style>
  :global(body) {
    margin: 0;
    padding: 0;
  }
  .explorer {
    display: flex;
    flex-direction: column;
    height: 100vh;
    background: #faf8f4;
  }
  .explorer-header {
    background: #1a1a1a;
    color: #fff;
    font-family: monospace;
    padding: 0.5rem 1rem;
    display: flex;
    align-items: center;
    gap: 1rem;
    flex-shrink: 0;
  }
  .header-title {
    font-weight: 700;
    letter-spacing: 0.05em;
  }
  .header-sub {
    opacity: 0.5;
    font-size: 0.8em;
  }
  .chat-card {
    margin: 1rem 1rem 0 1rem;
    border: 2px solid #1a1a1a;
    background: #f5f0e8;
    display: flex;
    flex-direction: column;
    max-height: 35vh;
    font-family: monospace;
    flex-shrink: 0;
  }
  .chat-log {
    flex: 1;
    overflow-y: auto;
    padding: 1rem;
    min-height: 80px;
  }
  .chat-msg {
    margin-bottom: 0.75rem;
    line-height: 1.5;
  }
  .chat-msg--user {
    text-align: right;
  }
  .chat-msg--assistant {
    border-left: 3px solid #1a1a1a;
    padding-left: 0.75rem;
  }
  .chat-role {
    font-weight: 700;
    text-transform: uppercase;
    font-size: 0.75em;
    letter-spacing: 0.05em;
    display: block;
    margin-bottom: 0.1rem;
    opacity: 0.5;
  }
  .chat-text {
    white-space: pre-wrap;
    word-break: break-word;
  }
  .chat-cursor {
    animation: blink 0.8s step-end infinite;
  }
  @keyframes blink {
    50% {
      opacity: 0;
    }
  }
  .chat-empty {
    text-align: center;
    opacity: 0.4;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-size: 0.85em;
    padding: 1rem;
  }
  .chat-input-bar {
    border-top: 2px solid #1a1a1a;
    display: flex;
  }
  .chat-input-bar input {
    flex: 1;
    padding: 0.75rem 1rem;
    font-family: monospace;
    font-size: 0.95rem;
    border: none;
    background: transparent;
    outline: none;
  }
  .chat-input-bar button {
    padding: 0.75rem 1.25rem;
    font-family: monospace;
    font-weight: 700;
    font-size: 1.1rem;
    border: none;
    border-left: 2px solid #1a1a1a;
    background: transparent;
    cursor: pointer;
  }
  .chat-input-bar button:disabled {
    opacity: 0.3;
    cursor: default;
  }
  .graph-rule {
    border: none;
    border-top: 1.5px solid #c0b8a8;
    margin: 1rem 1rem 0 1rem;
  }
  .graph-area {
    flex: 1;
    min-height: 0;
    overflow: auto;
    position: relative;
  }
  .graph-empty {
    font-family: monospace;
    text-align: center;
    padding: 3rem;
    opacity: 0.4;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 0.85em;
  }
  .graph-svg {
    width: 100%;
    height: 100%;
    min-height: 300px;
  }
  .node-label {
    font-family: monospace;
    font-size: 11px;
    font-weight: 600;
    fill: #1a1a1a;
    pointer-events: none;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }
  .node-label--discarded {
    text-decoration: line-through;
    opacity: 0.5;
  }
  .edge-label {
    font-family: monospace;
    font-size: 9px;
    fill: #8a8070;
    pointer-events: none;
  }
  .node-enter {
    animation: fadeIn 400ms ease-out;
  }
  @keyframes fadeIn {
    from {
      opacity: 0;
      transform: scale(0.9);
    }
    to {
      opacity: 1;
      transform: scale(1);
    }
  }
  .note-drawer {
    position: fixed;
    right: 0;
    top: 0;
    bottom: 0;
    width: 420px;
    max-width: 90vw;
    background: #f5f0e8;
    border-left: 2px solid #1a1a1a;
    overflow-y: auto;
    padding: 1.5rem;
    font-family: monospace;
    z-index: 100;
    box-shadow: -4px 0 12px rgba(0, 0, 0, 0.1);
    animation: slideIn 200ms ease-out;
  }
  @keyframes slideIn {
    from {
      transform: translateX(100%);
    }
    to {
      transform: translateX(0);
    }
  }
  .drawer-close {
    position: absolute;
    top: 0.75rem;
    right: 0.75rem;
    background: none;
    border: none;
    font-size: 1.5rem;
    cursor: pointer;
    font-family: monospace;
    line-height: 1;
  }
  .drawer-title {
    font-size: 1.1rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin: 0 0 0.75rem 0;
  }
  .drawer-meta {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
    margin-bottom: 1rem;
  }
  .drawer-type {
    background: #1a1a1a;
    color: #fff;
    padding: 0.15rem 0.5rem;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .drawer-tag {
    background: #e5e0d8;
    padding: 0.15rem 0.5rem;
    font-size: 0.75rem;
  }
  .drawer-content {
    font-size: 0.85rem;
    line-height: 1.6;
    border-top: 1px solid #c0b8a8;
    padding-top: 1rem;
  }
  .drawer-content :global(h1),
  .drawer-content :global(h2),
  .drawer-content :global(h3) {
    font-size: 0.95rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    margin: 1rem 0 0.5rem 0;
  }
  .drawer-content :global(p) {
    margin: 0.5rem 0;
  }
  .drawer-content :global(code) {
    background: #e5e0d8;
    padding: 0.1rem 0.3rem;
    font-size: 0.8rem;
  }
  .drawer-content :global(pre) {
    background: #1a1a1a;
    color: #f5f0e8;
    padding: 0.75rem;
    overflow-x: auto;
    font-size: 0.8rem;
    margin: 0.5rem 0;
  }
  .drawer-edges {
    border-top: 1px solid #c0b8a8;
    padding-top: 1rem;
    margin-top: 1rem;
  }
  .drawer-edges-title {
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    margin: 0 0 0.5rem 0;
    opacity: 0.5;
  }
  .drawer-edge {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    padding: 0.25rem 0;
    font-size: 0.8rem;
  }
  .drawer-edge-type {
    opacity: 0.5;
    min-width: 80px;
  }
  .drawer-loading {
    text-align: center;
    opacity: 0.4;
    padding: 2rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
</style>
