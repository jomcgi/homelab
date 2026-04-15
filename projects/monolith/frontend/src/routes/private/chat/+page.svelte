<script>
  let messages = $state([]);
  let inputText = $state("");
  let isStreaming = $state(false);
</script>

<svelte:head>
  <title>Knowledge Explorer</title>
</svelte:head>

<div class="explorer">
  <header class="explorer-header">
    <span class="header-title">KNOWLEDGE EXPLORER</span>
    <span class="header-sub">powered by gemma-4</span>
  </header>

  <main class="explorer-body">
    <p style="font-family: monospace; padding: 2rem;">Page skeleton — chat and graph coming next.</p>
  </main>
</div>

<style>
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
  }
  .header-title {
    font-weight: 700;
    letter-spacing: 0.05em;
  }
  .header-sub {
    opacity: 0.5;
    font-size: 0.8em;
  }
  .explorer-body {
    flex: 1;
    overflow: hidden;
  }
</style>
