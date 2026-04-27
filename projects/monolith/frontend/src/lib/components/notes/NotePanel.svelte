<script>
  import { renderMarkdown } from "./markdown.js";
  import { colorFor } from "./clusters.js";

  let { selectedId, nodes, edges, onSelect, onClose } = $props();

  let byId = $derived(new Map(nodes.map((n) => [n.id, n])));
  let titleMap = $derived(
    new Map(nodes.map((n) => [n.title, { id: n.id }])),
  );
  let selectedNode = $derived(byId.get(selectedId));

  let backlinks = $derived(
    edges
      .filter((e) => e.target === selectedId)
      .map((e) => byId.get(e.source))
      .filter(Boolean),
  );
  let outgoing = $derived(
    edges
      .filter((e) => e.source === selectedId)
      .map((e) => byId.get(e.target))
      .filter(Boolean),
  );

  let body = $state("");
  let loading = $state(false);
  let error = $state("");

  $effect(() => {
    if (!selectedId) {
      body = "";
      error = "";
      loading = false;
      return;
    }
    const controller = new AbortController();
    loading = true;
    error = "";
    body = "";
    fetch(`/api/knowledge/notes/${encodeURIComponent(selectedId)}`, {
      signal: controller.signal,
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("fetch failed"))))
      .then((data) => {
        body = data.content ?? "";
      })
      .catch((e) => {
        if (e.name !== "AbortError") error = "couldn't load note body";
      })
      .finally(() => {
        if (!controller.signal.aborted) loading = false;
      });
    return () => controller.abort();
  });

  function handleBodyClick(e) {
    const a = e.target.closest("a.wl[data-id]");
    if (!a) return;
    e.preventDefault();
    onSelect(a.dataset.id);
  }
</script>

{#if selectedNode}
  <aside class="panel">
    <div class="panel-head">
      <span class="panel-dot" style:background={colorFor(selectedNode.type)}></span>
      <div class="panel-titlewrap">
        <div class="panel-eyebrow">
          {(selectedNode.type ?? "other").toUpperCase()}
        </div>
        <div class="panel-title">{selectedNode.title}</div>
      </div>
      <button class="panel-close" onclick={onClose} aria-label="close">×</button>
    </div>

    <div
      class="panel-body"
      onclick={handleBodyClick}
      onkeydown={(e) => {
        if (e.key === "Enter" || e.key === " ") handleBodyClick(e);
      }}
      role="presentation"
    >
      {#if loading}
        <p class="panel-loading">loading…</p>
      {:else if error}
        <p class="panel-error">{error}</p>
      {:else}
        {@html renderMarkdown(body, titleMap)}
      {/if}
    </div>

    <div class="panel-foot">
      <div>
        <h5>BACKLINKS</h5>
        <ul class="link-list">
          {#each backlinks.slice(0, 10) as nb}
            <li
              onclick={() => onSelect(nb.id)}
              onkeydown={(e) => {
                if (e.key === "Enter" || e.key === " ") onSelect(nb.id);
              }}
              role="button"
              tabindex="0"
            >
              <span class="swatch" style:background={colorFor(nb.type)}></span>
              <span>{nb.title}</span>
            </li>
          {/each}
          {#if backlinks.length === 0}
            <li class="empty">— none</li>
          {/if}
          {#if backlinks.length > 10}
            <li class="more">+ {backlinks.length - 10} more</li>
          {/if}
        </ul>
      </div>
      <div>
        <h5>OUTGOING</h5>
        <ul class="link-list">
          {#each outgoing.slice(0, 10) as nb}
            <li
              onclick={() => onSelect(nb.id)}
              onkeydown={(e) => {
                if (e.key === "Enter" || e.key === " ") onSelect(nb.id);
              }}
              role="button"
              tabindex="0"
            >
              <span class="swatch" style:background={colorFor(nb.type)}></span>
              <span>{nb.title}</span>
            </li>
          {/each}
          {#if outgoing.length === 0}
            <li class="empty">— none</li>
          {/if}
          {#if outgoing.length > 10}
            <li class="more">+ {outgoing.length - 10} more</li>
          {/if}
        </ul>
      </div>
    </div>
  </aside>
{/if}

<style>
  .panel {
    position: absolute;
    top: 20px;
    right: 20px;
    width: 440px;
    max-height: calc(100% - 40px);
    background: var(--bg);
    border: var(--border-heavy);
    box-shadow: 4px 4px 0 var(--fg);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    z-index: 6;
    font-family: var(--font-mono);
  }
  .panel-head {
    padding: 14px 16px;
    border-bottom: 1.5px dashed var(--fg);
    display: flex;
    align-items: flex-start;
    gap: 10px;
  }
  .panel-dot {
    width: 12px;
    height: 12px;
    border: 1.5px solid var(--fg);
    margin-top: 4px;
    flex-shrink: 0;
  }
  .panel-titlewrap {
    flex: 1;
    min-width: 0;
  }
  .panel-eyebrow {
    font-size: 9px;
    letter-spacing: 0.14em;
    color: var(--muted);
    margin-bottom: 3px;
  }
  .panel-title {
    font-size: 14px;
    font-weight: 500;
    word-break: break-word;
  }
  .panel-close {
    background: var(--surface);
    border: 1.5px solid var(--fg);
    width: 22px;
    height: 22px;
    cursor: pointer;
    padding: 0;
    font-family: var(--font-mono);
    font-size: 12px;
    line-height: 1;
  }
  .panel-close:hover {
    background: var(--fg);
    color: var(--bg);
  }
  .panel-body {
    padding: 14px 18px 18px;
    overflow-y: auto;
    font-size: 12.5px;
    line-height: 1.55;
  }
  .panel-body :global(h2) {
    font-size: 11px;
    letter-spacing: 0.16em;
    font-weight: 700;
    margin: 16px 0 8px;
    text-transform: uppercase;
    border-top: 1px dashed var(--fg);
    padding-top: 10px;
  }
  .panel-body :global(h2:first-child) {
    border-top: none;
    padding-top: 0;
    margin-top: 0;
  }
  .panel-body :global(h3) {
    font-size: 11px;
    letter-spacing: 0.1em;
    font-weight: 700;
    margin: 12px 0 6px;
    color: var(--muted);
  }
  .panel-body :global(p) {
    margin: 0 0 10px;
  }
  .panel-body :global(ul) {
    margin: 0 0 10px;
    padding-left: 18px;
  }
  .panel-body :global(li) {
    margin-bottom: 3px;
  }
  .panel-body :global(code) {
    background: var(--surface);
    padding: 1px 5px;
    font-family: var(--font-mono);
    font-size: 11.5px;
    border: 1px solid rgba(0, 0, 0, 0.15);
  }
  .panel-body :global(strong) {
    font-weight: 700;
  }
  .panel-body :global(blockquote) {
    margin: 10px 0;
    padding: 8px 12px;
    border-left: 3px solid var(--fg);
    background: var(--surface);
  }
  .panel-body :global(a.wl) {
    color: var(--fg);
    text-decoration: underline;
    text-decoration-color: var(--accent);
    text-underline-offset: 2px;
    cursor: pointer;
  }
  .panel-body :global(a.wl:hover) {
    background: var(--yellow);
  }
  .panel-body :global(a.wl.dead) {
    color: var(--muted);
    text-decoration-style: dotted;
    text-decoration-color: var(--muted);
    cursor: default;
  }
  .panel-body :global(.tag) {
    display: inline-block;
    font-size: 10px;
    padding: 1px 6px;
    border: 1px solid var(--fg);
    background: var(--bg);
    margin-right: 4px;
  }
  .panel-loading,
  .panel-error {
    color: var(--muted);
    font-style: italic;
  }
  .panel-error {
    color: var(--st-err);
  }
  .panel-foot {
    border-top: 1.5px dashed var(--fg);
    padding: 12px 16px;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
    font-size: 11px;
  }
  .panel-foot h5 {
    margin: 0 0 6px;
    font-size: 9px;
    letter-spacing: 0.14em;
    color: var(--muted);
    font-weight: 700;
  }
  .link-list {
    list-style: none;
    padding: 0;
    margin: 0;
  }
  .link-list li {
    padding: 3px 0;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 7px;
    font-size: 11px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .link-list li:hover {
    color: var(--accent);
  }
  .link-list .swatch {
    width: 8px;
    height: 8px;
    border: 1.2px solid var(--fg);
    flex-shrink: 0;
  }
  .link-list .empty,
  .link-list .more {
    color: var(--muted);
    font-size: 10px;
    cursor: default;
  }
</style>
