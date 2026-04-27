<script>
  import "$lib/global.css";
  import { page } from "$app/stores";
  import { Nav } from "$lib/public/components";

  let { children } = $props();

  // Active-state derivation. The hooks.js reroute remaps
  // public.jomcgi.dev/* → /public/* and private.jomcgi.dev/* → /private/*
  // internally, but $page.url reflects the *browser* URL. So:
  // - /notes (any host) → "notes"
  // - any URL on public.jomcgi.dev → "home"
  // - everything else → no active state
  let activeRoute = $derived.by(() => {
    const host = $page.url.hostname;
    const path = $page.url.pathname;
    if (path === "/notes" || path.startsWith("/notes/")) return "notes";
    if (host.startsWith("public.")) return "home";
    return "";
  });
</script>

<Nav route={activeRoute} />

{@render children()}
