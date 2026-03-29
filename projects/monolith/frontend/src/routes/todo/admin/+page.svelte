<script>
  let { data } = $props();
  let todo = $state(structuredClone(data.todo));
  let saving = $state(false);

  async function save() {
    saving = true;
    await fetch("/api/todo", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(todo),
    });
    saving = false;
  }

  async function resetDaily() {
    if (!confirm("Reset daily tasks?")) return;
    await fetch("/api/todo/reset/daily", { method: "POST" });
    const res = await fetch("/api/todo");
    todo = await res.json();
  }

  async function resetWeekly() {
    if (!confirm("Reset ALL tasks?")) return;
    await fetch("/api/todo/reset/weekly", { method: "POST" });
    const res = await fetch("/api/todo");
    todo = await res.json();
  }
</script>

<h1>Todo Admin</h1>

<section>
  <h2>Weekly</h2>
  <label>
    <input type="checkbox" bind:checked={todo.weekly.done} />
    <input type="text" bind:value={todo.weekly.task} placeholder="Weekly goal..." />
  </label>
</section>

<section>
  <h2>Daily</h2>
  {#each todo.daily as task, i}
    <label>
      <input type="checkbox" bind:checked={task.done} />
      <input type="text" bind:value={task.task} placeholder="Task {i + 1}..." />
    </label>
  {/each}
</section>

<div class="actions">
  <button onclick={save} disabled={saving}>
    {saving ? "Saving..." : "Save"}
  </button>
  <button onclick={resetDaily}>Reset Daily</button>
  <button onclick={resetWeekly}>Reset Weekly</button>
</div>

<style>
  label { display: flex; align-items: center; gap: 0.5rem; margin: 0.5rem 0; }
  input[type="text"] { flex: 1; padding: 0.5rem; border: 1px solid #ccc; border-radius: 4px; }
  .actions { margin-top: 1rem; display: flex; gap: 0.5rem; }
  button { padding: 0.5rem 1rem; border-radius: 4px; border: 1px solid #ccc; cursor: pointer; }
</style>
