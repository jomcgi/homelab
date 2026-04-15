<script>
  let messages = $state([]);
  let graphEvents = $state([]);
  let inputText = $state("");
  let isStreaming = $state(false);
  let chatLog;

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
</script>

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
    {#if graphEvents.length === 0 && messages.length === 0}
      <p class="graph-empty">Ask a question to start exploring</p>
    {:else if graphEvents.length > 0}
      <p class="graph-empty">
        {graphEvents.filter((e) => e.type === "node_discovered").length} nodes discovered
        &middot;
        {graphEvents.filter((e) => e.type === "edge_traversed").length} edges traversed
        {#if graphEvents.some((e) => e.type === "node_discarded")}
          &middot;
          {graphEvents.filter((e) => e.type === "node_discarded").length} discarded
        {/if}
      </p>
    {/if}
  </div>
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
</style>
