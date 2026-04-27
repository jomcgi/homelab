/**
 * Maps subdomain prefixes to SvelteKit route prefixes.
 * Requests to `<subdomain>.jomcgi.dev/foo` are rerouted internally
 * to `/<prefix>/foo` so SvelteKit's file-based router resolves them
 * from `src/routes/<prefix>/`.
 *
 * This replaces gateway-level ReplacePrefixMatch rewrites which have
 * inconsistent slash-joining behaviour across implementations.
 */
const DOMAIN_PREFIX_MAP = {
  "public.": "/public",
  "private.": "/private",
};

// Top-level routes that intentionally live outside /public and /private.
// The browser OTEL exporter posts to same-origin /otel/v1/traces and the
// handler proxies to the cluster-internal SigNoz collector, so it must
// not be swept under a subdomain prefix.
const PASSTHROUGH_PREFIXES = ["/otel/"];

/** @type {import('@sveltejs/kit').Reroute} */
export function reroute({ url }) {
  if (PASSTHROUGH_PREFIXES.some((p) => url.pathname.startsWith(p))) {
    return;
  }
  for (const [domain, prefix] of Object.entries(DOMAIN_PREFIX_MAP)) {
    if (
      url.hostname.startsWith(domain) &&
      !url.pathname.startsWith(`${prefix}/`)
    ) {
      return `${prefix}${url.pathname}`;
    }
  }
}
