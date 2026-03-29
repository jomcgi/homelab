<script>
  let { children } = $props();
</script>

<nav>
  <a href="/todo">Todo</a>
</nav>

<main>
  {@render children()}
</main>

<style>
  nav {
    padding: 1rem;
    border-bottom: 1px solid #e0e0e0;
  }
  nav a {
    margin-right: 1rem;
    text-decoration: none;
    color: #333;
  }
  main {
    padding: 1rem;
    max-width: 800px;
    margin: 0 auto;
  }
</style>
