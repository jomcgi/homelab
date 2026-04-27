<script>
  import { page } from "$app/stores";
  import { NAV_LINKS } from "./routes.js";
  import "./nav.css";

  function isActive(linkHref, currentUrl) {
    try {
      const a = new URL(linkHref);
      return a.origin === currentUrl.origin && a.pathname === currentUrl.pathname;
    } catch {
      return false;
    }
  }
</script>

<nav class="nav">
  {#each NAV_LINKS as link}
    <a href={link.href} class={isActive(link.href, $page.url) ? "active" : ""}>
      {link.label}
    </a>
  {/each}
</nav>
