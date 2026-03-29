<script>
  let { data } = $props();
</script>

<h1>Todo</h1>

<section>
  <h2>Weekly</h2>
  <p>{data.todo.weekly.task || "(none)"}</p>
</section>

<section>
  <h2>Daily</h2>
  <ul>
    {#each data.todo.daily as task}
      <li class:done={task.done}>
        <input type="checkbox" checked={task.done} disabled />
        {task.task || "(empty)"}
      </li>
    {/each}
  </ul>
</section>

<section>
  <h2>History</h2>
  <ul>
    {#each data.dates as d}
      <li><a href="/todo/archive/{d}">{d}</a></li>
    {/each}
  </ul>
</section>

<style>
  .done { text-decoration: line-through; opacity: 0.6; }
  ul { list-style: none; padding: 0; }
  li { padding: 0.25rem 0; }
</style>
