<script>
  import { onMount } from "svelte";

  let { value = "", onChange } = $props();
  let inputRef;

  onMount(() => {
    function onKey(e) {
      if (e.key === "/" && document.activeElement !== inputRef) {
        e.preventDefault();
        inputRef?.focus();
        inputRef?.select();
      } else if (e.key === "Escape" && document.activeElement === inputRef) {
        inputRef.blur();
        onChange("");
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });
</script>

<div class="search">
  <label for="graph-search-input">SEARCH NOTES</label>
  <input
    id="graph-search-input"
    type="text"
    bind:this={inputRef}
    {value}
    oninput={(e) => onChange(e.target.value)}
    placeholder="filename or substring…"
    autocomplete="off"
    spellcheck="false"
  />
  <div class="search-hint">
    <kbd>/</kbd> focus &nbsp; <kbd>esc</kbd> clear
  </div>
</div>

<style>
  .search {
    position: absolute;
    top: 20px;
    left: 20px;
    background: var(--bg);
    border: var(--border-heavy);
    box-shadow: 4px 4px 0 var(--fg);
    padding: 10px 12px;
    width: 280px;
    z-index: 5;
    font-family: var(--font-mono);
  }
  label {
    display: block;
    font-size: 9px;
    letter-spacing: 0.12em;
    margin-bottom: 6px;
    color: var(--muted);
  }
  input {
    width: 100%;
    border: none;
    outline: none;
    background: transparent;
    font-family: inherit;
    font-size: 14px;
    color: var(--fg);
    padding: 0;
    caret-color: var(--accent);
  }
  input::placeholder {
    color: rgba(0, 0, 0, 0.32);
  }
  .search-hint {
    margin-top: 6px;
    font-size: 9px;
    letter-spacing: 0.1em;
    color: var(--muted);
  }
  kbd {
    font-family: inherit;
    font-size: 9px;
    border: 1px solid var(--fg);
    padding: 1px 5px;
    background: var(--surface);
  }
</style>
