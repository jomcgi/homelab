<script>
  /**
   * Brutalist-themed detail panel for a single SLO node.
   * Mirrors the data shown on /public/slos but redesigned for the
   * homepage palette: cream paper, JetBrains Mono labels, chunky 2px
   * borders, square accent blocks for the error-budget bar.
   *
   * @type {{
   *   node: object,
   *   edges: object[],
   *   neighborById: Map<string, object>,
   *   onClose: () => void,
   * }}
   */
  let { node, edges, neighborById, onClose } = $props();

  const SLO_BAR_SQUARES = 20;

  function formatDelta(target, current) {
    if (current == null || target == null) return null;
    const delta = current - target;
    return { sign: delta >= 0 ? "▲" : "▼", value: Math.abs(delta).toFixed(2) };
  }

  function formatBudget(node) {
    const consumed = node?.budget?.consumed_pct;
    if (consumed == null) return null;
    const burntPct = Math.round(consumed * 100);
    const filled = Math.min(SLO_BAR_SQUARES, Math.round(burntPct / (100 / SLO_BAR_SQUARES)));
    return { burntPct, filled };
  }

  function statusToken(status) {
    if (status === "degraded") return { label: "DEGRADED", cls: "status-bad" };
    if (status === "warning") return { label: "AT RISK", cls: "status-warn" };
    return { label: "HEALTHY", cls: "status-ok" };
  }

  const delta = $derived(formatDelta(node?.slo?.target, node?.slo?.current));
  const budget = $derived(formatBudget(node));
  const status = $derived(statusToken(node?.status));
  const linkerdEdges = $derived((edges || []).filter((e) => e.linkerd));
  const otherEdges = $derived((edges || []).filter((e) => !e.linkerd));
</script>

<aside class="panel" aria-label="Node detail">
  <header class="panel-header">
    <button class="panel-close" type="button" onclick={onClose} aria-label="Close detail panel">
      <span class="panel-close-arr">←</span>
      <span>esc</span>
    </button>
  </header>

  {#if node?.group}
    <p class="eyebrow">PART OF {node.group.toUpperCase()}</p>
  {/if}

  <h3 class="panel-title">
    {node.label}
    <span class="status-pill {status.cls}">{status.label}</span>
  </h3>
  {#if node.description}
    <p class="panel-sub">{node.description}</p>
  {/if}

  {#if node.slo}
    <section class="card">
      <p class="eyebrow">SLO — {node.slo.target}%</p>
      <div class="slo-row">
        <span class="slo-current">
          {node.slo.current != null ? node.slo.current.toFixed(2) : "—"}<span class="slo-pct">%</span>
        </span>
        {#if delta}
          <span class="slo-delta {node.slo.current >= node.slo.target ? 'delta-ok' : 'delta-bad'}">
            {delta.sign} {delta.value}
          </span>
        {/if}
      </div>
      {#if budget}
        <div class="budget-row">
          <span class="budget-label">error budget</span>
          <span class="budget-pct {budget.burntPct >= 100 ? 'budget-burnt-bad' : 'budget-burnt-ok'}">
            {budget.burntPct}% burnt
          </span>
        </div>
        <div class="budget-bar" aria-hidden="true">
          {#each Array(SLO_BAR_SQUARES) as _, i}
            <span
              class="budget-square"
              class:filled={i < budget.filled}
              class:bad={budget.burntPct >= 100}
            ></span>
          {/each}
        </div>
      {/if}
    </section>
  {/if}

  {#if node.metrics?.length}
    <section class="block">
      <p class="eyebrow">METRICS</p>
      <ul class="metric-list">
        {#each node.metrics as m}
          <li class="metric-row">
            <span class="metric-key">{m.k}</span>
            <span class="metric-val">{m.v}</span>
          </li>
        {/each}
      </ul>
    </section>
  {/if}

  {#if linkerdEdges.length || otherEdges.length}
    <section class="block">
      <p class="eyebrow">EDGES <span class="eyebrow-soft">P99 · 7D</span></p>
      <ul class="edge-list">
        {#each linkerdEdges as e}
          {@const partner = e.from === node.id ? e.to : e.from}
          {@const partnerNode = neighborById.get(partner)}
          <li class="edge-row">
            <span class="edge-arrow">{e.from === node.id ? "→" : "←"}</span>
            <span class="edge-chip">{partnerNode?.label ?? partner.toUpperCase()}</span>
            <span class="edge-stats">
              {#if e.linkerd?.rps != null}<span>{e.linkerd.rps}/s</span>{/if}
              {#if e.linkerd?.p99_ms != null}<span class="edge-stat-divider">·</span><span>{e.linkerd.p99_ms} ms</span>{/if}
              {#if e.linkerd?.error_pct != null}<span class="edge-stat-divider">·</span><span>{e.linkerd.error_pct}% err</span>{/if}
            </span>
          </li>
        {/each}
        {#each otherEdges as e}
          {@const partner = e.from === node.id ? e.to : e.from}
          {@const partnerNode = neighborById.get(partner)}
          <li class="edge-row edge-row-plain">
            <span class="edge-arrow">{e.bidi ? "↔" : e.from === node.id ? "→" : "←"}</span>
            <span class="edge-chip edge-chip-muted">{partnerNode?.label ?? partner.toUpperCase()}</span>
          </li>
        {/each}
      </ul>
    </section>
  {/if}
</aside>

<style>
  .panel {
    background: var(--paper);
    border: 2px solid var(--ink);
    padding: 22px 24px 28px;
    font-family: var(--mono);
    color: var(--ink);
    box-shadow: 6px 6px 0 var(--ink);
    overflow-y: auto;
    max-height: 100%;
  }

  .panel-header {
    display: flex;
    justify-content: flex-start;
    margin-bottom: 18px;
  }

  .panel-close {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: transparent;
    border: 2px solid var(--ink);
    padding: 6px 12px;
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--ink);
    cursor: pointer;
    transition:
      transform 120ms ease,
      box-shadow 120ms ease;
  }

  .panel-close:hover {
    transform: translate(-2px, -2px);
    box-shadow: 2px 2px 0 var(--ink);
  }

  .panel-close-arr {
    font-size: 13px;
  }

  .eyebrow {
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--ink-3);
    margin: 0 0 10px;
  }

  .eyebrow-soft {
    color: var(--ink-3);
    font-weight: 400;
    margin-left: 8px;
    letter-spacing: 0.1em;
  }

  .panel-title {
    font-family: var(--mono);
    font-size: 26px;
    font-weight: 800;
    letter-spacing: -0.01em;
    text-transform: uppercase;
    margin: 0 0 6px;
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }

  .status-pill {
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    padding: 3px 8px;
    border: 1.5px solid var(--ink);
  }

  .status-ok {
    background: var(--teal);
    color: var(--paper);
  }

  .status-warn {
    background: var(--accent);
    color: var(--ink);
  }

  .status-bad {
    background: var(--coral);
    color: var(--paper);
  }

  .panel-sub {
    font-family: var(--mono);
    font-size: 13px;
    color: var(--ink-2);
    margin: 0 0 22px;
  }

  .card {
    background: var(--cream);
    border: 2px solid var(--ink);
    padding: 16px 18px;
    margin-bottom: 22px;
  }

  .slo-row {
    display: flex;
    align-items: baseline;
    gap: 14px;
    margin: 4px 0 14px;
  }

  .slo-current {
    font-size: 38px;
    font-weight: 800;
    letter-spacing: -0.02em;
    line-height: 1;
  }

  .slo-pct {
    font-size: 18px;
    font-weight: 600;
    color: var(--ink-2);
    margin-left: 2px;
  }

  .slo-delta {
    font-size: 16px;
    font-weight: 700;
  }

  .delta-ok {
    color: var(--teal);
  }

  .delta-bad {
    color: var(--coral);
  }

  .budget-row {
    display: flex;
    justify-content: space-between;
    font-size: 13px;
    margin-bottom: 8px;
  }

  .budget-label {
    color: var(--ink-2);
  }

  .budget-burnt-ok {
    color: var(--ink-2);
    font-weight: 700;
  }

  .budget-burnt-bad {
    color: var(--coral);
    font-weight: 700;
  }

  .budget-bar {
    display: grid;
    grid-template-columns: repeat(20, 1fr);
    gap: 2px;
  }

  .budget-square {
    height: 14px;
    border: 1.5px solid var(--ink);
    background: var(--paper);
  }

  .budget-square.filled {
    background: var(--teal);
  }

  .budget-square.filled.bad {
    background: var(--coral);
  }

  .block {
    margin-bottom: 22px;
  }

  .metric-list,
  .edge-list {
    list-style: none;
    padding: 0;
    margin: 0;
  }

  .metric-row {
    display: flex;
    justify-content: space-between;
    padding: 10px 0;
    border-bottom: 1px solid var(--rule);
    font-size: 14px;
  }

  .metric-row:last-child {
    border-bottom: none;
  }

  .metric-key {
    color: var(--ink-2);
  }

  .metric-val {
    font-weight: 700;
  }

  .edge-row {
    display: grid;
    grid-template-columns: 16px auto 1fr;
    align-items: center;
    gap: 10px;
    padding: 8px 0;
    font-size: 13px;
  }

  .edge-row-plain {
    grid-template-columns: 16px auto;
  }

  .edge-arrow {
    color: var(--ink-3);
  }

  .edge-chip {
    display: inline-flex;
    align-items: center;
    background: var(--accent);
    border: 1.5px solid var(--ink);
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .edge-chip-muted {
    background: var(--paper);
    color: var(--ink-2);
  }

  .edge-stats {
    color: var(--ink-2);
    font-size: 12px;
    text-align: right;
  }

  .edge-stat-divider {
    margin: 0 4px;
    color: var(--ink-3);
  }
</style>
