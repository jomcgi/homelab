<script>
  let { children } = $props();
</script>

{@render children()}

<style>
  /* ── Reset ──────────────────────────────────── */
  :global(*),
  :global(*::before),
  :global(*::after) {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
  }

  :global(html) {
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    text-rendering: optimizeLegibility;
    font-size: clamp(16px, max(1.6vw, 2.6vh), 48px);
  }

  :global(body) {
    margin: 0;
    overflow: hidden;
  }

  :global(ul) {
    list-style: none;
  }

  :global(a) {
    color: inherit;
    text-decoration: none;
  }

  /* ── Design system ──────────────────────────── */
  :global(:root) {
    --font: "Space Mono", "SF Mono", monospace;
    --fg: #111;
    --fg-secondary: #555;
    --fg-tertiary: #999;
    --bg: #f2f0ed;
    --border: #ccc;
    --surface: #e8e6e3;
    --danger: #c53030;
  }

  @media (prefers-color-scheme: dark) {
    :global(:root) {
      --fg: #e8e6e3;
      --fg-secondary: #999;
      --fg-tertiary: #666;
      --bg: #111;
      --border: #333;
      --surface: #1a1a1a;
      --danger: #f56565;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    :global(*),
    :global(*::before),
    :global(*::after) {
      transition-duration: 0.01ms !important;
    }
  }
</style>
