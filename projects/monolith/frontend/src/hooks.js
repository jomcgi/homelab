/** @type {import('@sveltejs/kit').Reroute} */
export function reroute({ url }) {
  // public.jomcgi.dev/foo → internally route to /public/foo
  if (
    url.hostname.startsWith("public.") &&
    !url.pathname.startsWith("/public/")
  ) {
    return `/public${url.pathname}`;
  }
}
