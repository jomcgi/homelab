<script>
  let { data } = $props();

  // Map API shape → internal state
  let goal = $state(data.todo.weekly.task);
  let goalDone = $state(data.todo.weekly.done);
  let daily = $state(data.todo.daily.map((d) => d.task));
  let dailyDone = $state(data.todo.daily.map((d) => d.done));
  let editing = $state(false);

  let goalRef = $state(null);
  let dailyRefs = $state([null, null, null]);

  // Debounced auto-save
  let saveTimer;
  function scheduleSave() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      fetch("/api/todo", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          weekly: { task: goal, done: goalDone },
          daily: daily.map((text, i) => ({ task: text, done: dailyDone[i] })),
        }),
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

  // Date + clock
  let now = $state(new Date());
  $effect(() => {
    const id = setInterval(() => (now = new Date()), 30_000);
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
  <div class="panel">
    <header class="panel-header">
      <span class="date">{formatDate(now)}</span>
      <span class="clock">{formatTime(now)}</span>
    </header>

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
  </div>
</div>

<style>
  .root {
    display: flex;
    justify-content: center;
    align-items: center;
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

  .panel {
    width: 100%;
    max-width: 22rem;
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 2rem;
    padding: 2.5rem 2rem;
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
</style>
