<script>
  /** @type {{ route?: string }} */
  let { route = "home" } = $props();

  const items = [
    { slug: "home", label: "HOME", href: "/public" },
    { slug: "engineering", label: "ENGINEERING", href: "https://jomcgi.dev/engineering/" },
    { slug: "cv", label: "CV", href: "https://jomcgi.dev/cv/" },
  ];
</script>

<nav class="md-nav">
  <div class="md-nav-inner">
    <div class="md-nav-links">
      {#each items as item}
        <a
          href={item.href}
          class="md-nav-link"
          class:active={route === item.slug}
        >
          {item.label}
        </a>
      {/each}
    </div>
  </div>
</nav>

<style>
  .md-nav {
    position: sticky;
    top: 0;
    z-index: 50;
    background: var(--paper);
    border-bottom: 2px solid var(--ink);
  }

  .md-nav-inner {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: center;
    padding: 14px 32px;
    max-width: 1360px;
    margin: 0 auto;
  }

  .md-nav-links {
    grid-column: 2;
    display: flex;
    gap: 4px;
    justify-self: center;
    align-items: center;
  }

  .md-nav-link {
    padding: 8px 12px;
    font-family: var(--mono);
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.1em;
    color: var(--ink-2);
    transition: color 160ms ease;
    position: relative;
  }

  .md-nav-link::after {
    content: "";
    position: absolute;
    left: 12px;
    right: 12px;
    bottom: 2px;
    height: 2px;
    background: var(--coral);
    transform: scaleX(0);
    transition: transform 160ms ease;
  }

  .md-nav-link:hover {
    color: var(--ink);
  }

  .md-nav-link:hover::after {
    transform: scaleX(1);
  }

  .md-nav-link.active {
    color: var(--ink);
  }

  .md-nav-link.active::after {
    background: var(--ink);
    transform: scaleX(1);
  }

  @media (max-width: 768px) {
    .md-nav-inner {
      gap: 12px;
      padding: 10px 16px;
    }
    .md-nav-links {
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
      scrollbar-width: none;
      gap: 0;
    }
    .md-nav-links::-webkit-scrollbar {
      display: none;
    }
    .md-nav-link {
      padding: 6px 8px;
      font-size: 10px;
      white-space: nowrap;
    }
  }
</style>
