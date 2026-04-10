<script>
  import { tick } from "svelte";

  let { data } = $props();

  // ── Capture ──────────────────────────────────
  let note = $state("");
  let sent = $state(false);
  let captureRef = $state(null);

  $effect(() => {
    captureRef?.focus();
  });

  let error = $state(false);

  // ── Knowledge search overlay ─────────────────
  let searchOpen = $state(false);
  let searchQuery = $state("");
  let searchResults = $state([]);
  let selectedNote = $state(null);
  let activeIndex = $state(-1);
  let searching = $state(false);
  let searchType = $state("all");
  let savedCapture = $state("");
  let searchInputRef = $state(null);

  function openSearch() {
    savedCapture = note;
    searchOpen = true;
    tick().then(() => searchInputRef?.focus());
  }

  function closeSearch() {
    searchOpen = false;
    note = savedCapture;
    searchQuery = "";
    searchResults = [];
    selectedNote = null;
    activeIndex = -1;
    searching = false;
    tick().then(() => captureRef?.focus());
  }

  $effect(() => {
    function handleGlobalKeyDown(e) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        if (!searchOpen) openSearch();
      }
      if (e.key === "Escape" && searchOpen) {
        e.preventDefault();
        closeSearch();
      }
      if (searchOpen && e.key === "ArrowDown") {
        e.preventDefault();
        activeIndex = Math.min(activeIndex + 1, searchResults.length - 1);
      }
      if (searchOpen && e.key === "ArrowUp") {
        e.preventDefault();
        activeIndex = Math.max(activeIndex - 1, -1);
      }
      if (searchOpen && e.key === "Enter" && activeIndex >= 0) {
        e.preventDefault();
        const result = searchResults[activeIndex];
        if (result) {
          fetch(`/api/knowledge/notes/${result.note_id}`)
            .then((res) => (res.ok ? res.json() : null))
            .then((data) => {
              if (data) selectedNote = data;
            });
        }
      }
    }
    document.addEventListener("keydown", handleGlobalKeyDown);
    return () => document.removeEventListener("keydown", handleGlobalKeyDown);
  });

  // ── Debounced search ───────────────────────────
  let searchTimer;
  $effect(() => {
    clearTimeout(searchTimer);
    const q = searchQuery;
    const type = searchType;
    if (q.length < 2) {
      searchResults = [];
      searching = false;
      return;
    }
    searching = true;
    searchTimer = setTimeout(async () => {
      const params = new URLSearchParams({ q });
      if (type !== "all") params.set("type", type);
      const res = await fetch(`/api/knowledge/search?${params}`);
      if (res.ok) {
        searchResults = (await res.json()).results;
        activeIndex = -1;
      }
      searching = false;
    }, 300);
  });

  async function submitCapture() {
    if (!note.trim()) return;
    try {
      const formData = new FormData();
      formData.append("content", note);
      const res = await fetch("?/capture", {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error();
      sent = true;
      setTimeout(() => {
        note = "";
        sent = false;
        captureRef?.focus();
      }, 500);
    } catch {
      error = true;
      setTimeout(() => {
        error = false;
        captureRef?.focus();
      }, 2000);
    }
  }

  function captureKeyDown(e) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      submitCapture();
    }
  }

  // ── Schedule ─────────────────────────────────
  let events = $state(data.schedule);
  let eventListRef = $state(null);

  const LINKS = [
    { label: "ArgoCD", url: "#" },
    { label: "Grafana", url: "#" },
    { label: "SigNoz", url: "#" },
    { label: "BuildBuddy", url: "#" },
    { label: "Notion", url: "#" },
    { label: "GitHub", url: "#" },
  ];

  function timeToMinutes(timeStr) {
    const [h, m] = timeStr.split(":").map(Number);
    return h * 60 + m;
  }

  function nowMinutes(d) {
    return d.getHours() * 60 + d.getMinutes();
  }

  function isPast(ev, d) {
    if (ev.allDay) return false;
    const end = ev.endTime ?? ev.time;
    return nowMinutes(d) >= timeToMinutes(end);
  }

  function isActive(ev, d) {
    if (ev.allDay || !ev.endTime) return false;
    const n = nowMinutes(d);
    return n >= timeToMinutes(ev.time) && n < timeToMinutes(ev.endTime);
  }

  // Scroll to the first active/upcoming event, re-run every 10 minutes
  let scrollTick = $state(0);
  $effect(() => {
    const id = setInterval(() => (scrollTick = Date.now()), 600_000);
    return () => clearInterval(id);
  });

  function scrollToRelevant() {
    if (!eventListRef) return;
    const rows = eventListRef.querySelectorAll(".event-row");
    let target = rows.length - 1;
    for (let i = 0; i < rows.length; i++) {
      if (
        rows[i].classList.contains("event-row--active") ||
        (!rows[i].classList.contains("event-row--past") &&
          !rows[i].classList.contains("event-row--allday"))
      ) {
        target = Math.max(0, i - 1);
        break;
      }
    }
    rows[target]?.scrollIntoView({ block: "start" });
  }

  $effect(() => {
    scrollTick;
    scrollToRelevant();
  });

  // ── Todo ─────────────────────────────────────
  let goal = $state(data.todo.weekly.task);
  let goalDone = $state(data.todo.weekly.done);
  let daily = $state(data.todo.daily.map((d) => d.task));
  let dailyDone = $state(data.todo.daily.map((d) => d.done));
  let editing = $state(false);

  let goalRef = $state(null);
  let dailyRefs = $state([null, null, null]);

  let saveTimer;
  function scheduleSave() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      const body = JSON.stringify({
        weekly: { task: goal, done: goalDone },
        daily: daily.map((text, i) => ({ task: text, done: dailyDone[i] })),
      });
      const formData = new FormData();
      formData.append("body", body);
      fetch("?/save", {
        method: "POST",
        body: formData,
      });
    }, 400);
  }

  function setGoal(text) {
    goal = text;
    scheduleSave();
  }

  function toggleGoal() {
    goalDone = !goalDone;
    scheduleSave();
  }

  function setDailyText(i, text) {
    daily[i] = text;
    scheduleSave();
  }

  function toggleDaily(i) {
    dailyDone[i] = !dailyDone[i];
    scheduleSave();
  }

  function startEditing() {
    editing = true;
    setTimeout(() => goalRef?.focus(), 0);
  }

  function handleKeyDown(e, nextRef) {
    if (e.key === "Enter") {
      e.preventDefault();
      nextRef?.focus();
    }
    if (e.key === "Escape") {
      editing = false;
    }
  }

  function handleReadOnlyKeyDown(e, hasText, toggleFn) {
    if (e.key === " " || e.key === "Enter") {
      e.preventDefault();
      hasText ? toggleFn() : startEditing();
    }
  }

  // ── Clock ────────────────────────────────────
  let now = $state(new Date());
  $effect(() => {
    const id = setInterval(() => (now = new Date()), 60_000);
    return () => clearInterval(id);
  });

  function formatDate(d) {
    return d.toLocaleDateString("en-GB", {
      weekday: "short",
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  }

  function formatTime(d) {
    return d.toLocaleTimeString("en-GB", {
      hour: "2-digit",
      minute: "2-digit",
    });
  }
</script>

<div class="root">
  <!-- Left pane: Capture -->
  <section class="capture">
    <textarea
      bind:this={captureRef}
      class="capture-input"
      class:capture-input--sent={sent}
      value={note}
      oninput={(e) => (note = e.target.value)}
      onkeydown={captureKeyDown}
      placeholder="write something..."
      spellcheck="false"
      aria-label="Quick note"
    ></textarea>
    <footer class="capture-footer">
      <span class="capture-hint" class:capture-hint--error={error}>
        {#if error}
          failed
        {:else if sent}
          sent
        {:else if note.trim()}
          ⌘ enter
        {:else}
          &nbsp;
        {/if}
      </span>
      {#if note.length > 0}
        <span class="capture-count">{note.length}</span>
      {/if}
    </footer>
  </section>

  <!-- Right pane -->
  <aside class="panel">
    <header class="panel-header">
      <span class="date">{formatDate(now)}</span>
      <span class="clock">{formatTime(now)}</span>
    </header>

    <!-- Schedule -->
    <section class="panel-section">
      <h2 class="section-label">today</h2>
      <ul class="event-list" bind:this={eventListRef}>
        {#each events as ev}
          <li
            class="event-row"
            class:event-row--past={isPast(ev, now)}
            class:event-row--active={isActive(ev, now)}
            class:event-row--allday={ev.allDay}
          >
            {#if ev.allDay}
              <span class="event-time"></span>
              <span class="event-title">{ev.title}</span>
              <span class="event-meta">all day</span>
            {:else}
              <span class="event-time">{ev.time}</span>
              <span class="event-title">{ev.title}</span>
              <span class="event-meta">{ev.endTime ? ev.endTime : ""}</span>
            {/if}
          </li>
        {/each}
      </ul>
    </section>

    <!-- Links -->
    <section class="panel-section">
      <h2 class="section-label">links</h2>
      <div class="links-grid">
        {#each LINKS as lk}
          <a href={lk.url} class="link">{lk.label}</a>
        {/each}
      </div>
    </section>

    <!-- Todo -->
    <section class="panel-section">
      <h2
        class="section-label section-label--interactive"
        role="button"
        tabindex="0"
        onclick={() => (editing ? (editing = false) : startEditing())}
        onkeydown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            editing ? (editing = false) : startEditing();
          }
        }}
      >
        {editing ? "done" : "todo"}
      </h2>

      <!-- Weekly goal -->
      <input
        bind:this={goalRef}
        class="todo-field todo-field--goal"
        class:todo-field--done={goalDone && !editing}
        class:todo-field--empty={!goal && !editing}
        value={editing ? goal : goal || "set weekly goal"}
        readonly={!editing}
        oninput={(e) => setGoal(e.target.value)}
        onclick={() => {
          if (!editing && goal) toggleGoal();
          else if (!editing) startEditing();
        }}
        onkeydown={(e) =>
          editing
            ? handleKeyDown(e, dailyRefs[0])
            : handleReadOnlyKeyDown(e, goal, toggleGoal)}
        placeholder="weekly goal"
        spellcheck="false"
        tabindex="0"
      />

      <!-- 3 daily goals -->
      {#each daily as text, i}
        {@const allDailyEmpty = !editing && daily.every((d) => !d)}
        {@const emptyLabel =
          allDailyEmpty && i === 0 && goal ? "set daily goals" : "..."}
        <div class="todo-daily-row">
          <span class="todo-dash" class:todo-dash--empty={!text && !editing}>
            &ndash;
          </span>
          <input
            bind:this={dailyRefs[i]}
            class="todo-field"
            class:todo-field--done={dailyDone[i] && !editing}
            class:todo-field--empty={!text && !editing}
            value={editing ? text : text || emptyLabel}
            readonly={!editing}
            oninput={(e) => setDailyText(i, e.target.value)}
            onclick={() => {
              if (!editing && text) toggleDaily(i);
              else if (!editing) startEditing();
            }}
            onkeydown={(e) =>
              editing
                ? handleKeyDown(e, dailyRefs[i + 1] || null)
                : handleReadOnlyKeyDown(e, text, () => toggleDaily(i))}
            placeholder="daily goal"
            spellcheck="false"
            tabindex="0"
          />
        </div>
      {/each}
    </section>
  </aside>
</div>

{#if searchOpen}
  <div class="search-overlay">
    <div class="search-container">
      <input
        type="text"
        class="search-input"
        placeholder="search knowledge..."
        bind:value={searchQuery}
        bind:this={searchInputRef}
      />
      <div class="search-type-filters">
        {#each ["all", "note", "paper", "article", "recipe"] as type}
          <button
            class="search-type-pill"
            class:active={searchType === type}
            onclick={() => (searchType = type)}
          >
            {type}
          </button>
        {/each}
      </div>
      {#if searching && searchResults.length === 0}
        <p class="search-status">searching...</p>
      {:else if !searching && searchQuery.length >= 2 && searchResults.length === 0}
        <p class="search-status">no results</p>
      {/if}
      {#if searchResults.length > 0}
        <ul
          class="search-results"
          class:search-results--stale={searching}
        >
          {#each searchResults as result, i}
            <li
              class="search-result"
              class:active={activeIndex === i}
              onclick={() => {
                activeIndex = i;
                fetch(`/api/knowledge/notes/${result.note_id}`)
                  .then((res) => (res.ok ? res.json() : null))
                  .then((data) => {
                    if (data) selectedNote = data;
                  });
              }}
            >
              <div class="search-result-title">
                {result.title}
                {#if result.type}
                  <span class="search-result-badge">{result.type}</span>
                {/if}
              </div>
              {#if result.section || result.tags?.length}
                <div class="search-result-meta">
                  {#if result.section}{result.section}{/if}
                  {#if result.section && result.tags?.length}
                    &nbsp;&middot;&nbsp;
                  {/if}
                  {#if result.tags?.length}
                    {result.tags.join(" \u00b7 ")}
                  {/if}
                </div>
              {/if}
              {#if result.snippet}
                <div class="search-result-snippet">{result.snippet}</div>
              {/if}
            </li>
          {/each}
        </ul>
      {/if}
    </div>
  </div>
{/if}

<style>
  /* ── Layout ────────────────────────────────── */

  .root {
    display: flex;
    height: 100vh;
    width: 100%;
    font-family: var(--font);
    font-size: 1rem;
    line-height: 1.5;
    color: var(--fg);
    background: var(--bg);
    overflow: hidden;
    -webkit-font-feature-settings: "liga" 0;
    font-feature-settings: "liga" 0;
  }

  /* ── Capture (left pane) ───────────────────── */

  .capture {
    flex: 1 1 0%;
    display: flex;
    flex-direction: column;
    padding: 2.5rem;
    padding-bottom: 1.25rem;
    min-width: 0;
  }

  .capture-input {
    flex: 1;
    resize: none;
    border: none;
    outline: none;
    background: transparent;
    font-family: var(--font);
    font-size: 1.15rem;
    line-height: 1.8;
    color: var(--fg);
    padding: 0;
    letter-spacing: -0.01em;
    transition: opacity 0.3s ease;
  }

  .capture-input::placeholder {
    color: var(--fg-tertiary);
  }

  .capture-input--sent {
    opacity: 0.1;
  }

  .capture-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-top: 0.75rem;
  }

  .capture-hint {
    font-size: 0.75rem;
    color: var(--fg-tertiary);
    letter-spacing: 0.04em;
    transition: opacity 0.2s ease;
  }

  .capture-hint--error {
    color: var(--danger);
  }

  .capture-count {
    font-size: 0.75rem;
    color: var(--fg-tertiary);
    opacity: 0.6;
    font-variant-numeric: tabular-nums;
  }

  /* ── Right panel ───────────────────────────── */

  .panel {
    flex: 0 0 38%;
    max-width: 22rem;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    padding: 2.5rem 2rem;
    overflow-y: auto;
    scrollbar-width: none;
    border-left: 0.06rem solid var(--fg);
  }

  .panel::-webkit-scrollbar {
    display: none;
  }

  .panel-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }

  .date {
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .clock {
    font-size: 0.8rem;
    font-weight: 700;
    color: var(--fg);
    font-variant-numeric: tabular-nums;
  }

  /* ── Sections ──────────────────────────────── */

  .panel-section {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .section-label {
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: var(--fg);
    margin-bottom: 0.25rem;
    padding-bottom: 0.4rem;
    border-bottom: 0.04rem solid var(--border);
  }

  /* ── Schedule ──────────────────────────────── */

  .event-list {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    max-height: 10rem;
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: var(--fg-tertiary) transparent;
  }

  .event-list::-webkit-scrollbar {
    width: 4px;
  }

  .event-list::-webkit-scrollbar-thumb {
    background: var(--fg-tertiary);
    border-radius: 2px;
  }

  .event-row {
    display: flex;
    align-items: baseline;
    gap: 0.8rem;
    padding: 0.3rem 0;
  }

  .event-time {
    font-size: 0.8rem;
    color: var(--fg-secondary);
    font-variant-numeric: tabular-nums;
    min-width: 3.2rem;
    flex-shrink: 0;
  }

  .event-title {
    font-size: 1rem;
    flex: 1;
    min-width: 0;
  }

  .event-meta {
    font-size: 0.6rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--fg-tertiary);
    flex-shrink: 0;
  }

  .event-row--active {
    font-weight: 700;
  }

  .event-row--active .event-time {
    color: var(--fg);
  }

  .event-row--past .event-time,
  .event-row--past .event-title,
  .event-row--past .event-meta {
    text-decoration: line-through;
    opacity: 0.3;
  }

  /* ── Links ─────────────────────────────────── */

  .links-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.3rem 0;
  }

  .link {
    font-size: 0.85rem;
    color: var(--fg-secondary);
    padding: 0.1rem 0;
    transition: color 0.15s ease;
  }

  .link:hover {
    color: var(--fg);
  }

  .link:focus-visible {
    outline: 1.5px solid var(--fg);
    outline-offset: 2px;
  }

  /* ── Todos ─────────────────────────────────── */

  .section-label--interactive {
    cursor: pointer;
    transition: color 0.15s ease;
  }

  .section-label--interactive:hover {
    color: var(--fg-secondary);
  }

  .todo-field {
    font-family: var(--font);
    font-size: 0.85rem;
    line-height: 1.5;
    color: var(--fg);
    background: transparent;
    border: none;
    outline: none;
    width: 100%;
    padding: 0.2rem 0;
    cursor: pointer;
  }

  .todo-field--goal {
    font-weight: 700;
  }

  .todo-field--done {
    text-decoration: line-through;
    opacity: 0.3;
  }

  .todo-field--empty {
    color: var(--danger);
  }

  .todo-field::placeholder {
    color: var(--danger);
  }

  .todo-field:focus-visible {
    outline: none;
  }

  .todo-daily-row {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
  }

  .todo-dash {
    color: var(--fg-tertiary);
    flex-shrink: 0;
  }

  .todo-dash--empty {
    color: var(--danger);
  }

  /* ── Knowledge search overlay ───────────────── */

  .search-overlay {
    position: fixed;
    inset: 0;
    background: var(--bg);
    z-index: 100;
    overflow-y: auto;
  }

  .search-container {
    max-width: 72ch;
    margin: 0 auto;
    padding: 2.5rem;
  }

  .search-input {
    width: 100%;
    font-family: var(--font);
    font-size: 1.1rem;
    background: transparent;
    border: none;
    border-bottom: 0.06rem solid var(--border);
    padding: 0.5rem 0;
    color: var(--fg);
    outline: none;
  }

  .search-input::placeholder {
    color: var(--fg-tertiary);
  }

  .search-type-filters {
    display: flex;
    gap: 1rem;
    margin: 1rem 0;
  }

  .search-type-pill {
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: var(--fg-tertiary);
    cursor: pointer;
    background: none;
    border: none;
    padding: 0;
    font-family: var(--font);
  }

  .search-type-pill.active {
    color: var(--fg);
  }

  .search-results {
    list-style: none;
    padding: 0;
    margin: 1rem 0 0 0;
  }

  .search-results--stale {
    opacity: 0.5;
  }

  .search-result {
    padding: 0.75rem 0;
    border-bottom: 0.04rem solid var(--border);
    cursor: pointer;
  }

  .search-result.active {
    background: var(--surface);
  }

  .search-result-title {
    font-weight: 700;
    color: var(--fg);
  }

  .search-result-badge {
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: var(--fg-tertiary);
    margin-left: 0.5rem;
  }

  .search-result-meta {
    font-size: 0.75rem;
    color: var(--fg-tertiary);
    margin-top: 0.25rem;
  }

  .search-result-snippet {
    font-size: 0.85rem;
    color: var(--fg-secondary);
    margin-top: 0.25rem;
    line-height: 1.5;
  }

  .search-status {
    color: var(--fg-tertiary);
    margin-top: 1rem;
    font-size: 0.85rem;
  }
</style>
