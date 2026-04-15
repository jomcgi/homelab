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

/** @type {import('@sveltejs/kit').Reroute} */
export function reroute({ url }) {
  for (const [domain, prefix] of Object.entries(DOMAIN_PREFIX_MAP)) {
    if (
      url.hostname.startsWith(domain) &&
      !url.pathname.startsWith(`${prefix}/`)
    ) {
      return `${prefix}${url.pathname}`;
    }
  }
}
