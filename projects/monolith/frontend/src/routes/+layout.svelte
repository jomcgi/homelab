<script>
  import "$lib/global.css";
  import Nav from "../../../websites/shared/nav/Nav.svelte";
  let { children } = $props();
</script>

<Nav />

{@render children()}
