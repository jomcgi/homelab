<script>
  import "$lib/global.css";
  import { page } from "$app/stores";
  import { Nav } from "$lib/public/components";

  let { children } = $props();

  // Active-state derivation: map URL pathname to the Nav's slug list.
  // Returns the slug to highlight, or "" for no active link.
  let activeRoute = $derived.by(() => {
    const path = $page.url.pathname;
    if (path === "/notes" || path.startsWith("/notes/")) return "notes";
    if (path === "/public" || path.startsWith("/public/")) return "home";
    return "";
  });
</script>

<Nav route={activeRoute} />

{@render children()}
