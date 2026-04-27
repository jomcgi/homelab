// /notes is a canvas-driven force graph; the page can't render anything
// useful without JS, so SSR adds latency without UX value. Disabling SSR
// also sidesteps Svelte 5 hydration issues with d3-mounted components.
export const ssr = false;
