/**
 * Surface the real SSR error message to the client/HTML response.
 * The default `handleError` masks all errors as "Internal Error" once
 * NODE_ENV=production, which is unhelpful when chasing why the public
 * homepage 500s only in the cluster pod and not under local pnpm/vite.
 *
 * @type {import('@sveltejs/kit').HandleServerError}
 */
export function handleError({ error, message }) {
  // eslint-disable-next-line no-console
  console.error("SSR error:", error?.stack || error);
  return {
    message: error instanceof Error ? error.message : message,
  };
}
