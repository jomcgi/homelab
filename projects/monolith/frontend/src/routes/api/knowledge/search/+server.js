import { env } from "$env/dynamic/private";

const API_BASE = env.API_BASE || "http://localhost:8000";

/** @type {import('./$types').RequestHandler} */
export async function GET({ url }) {
  const resp = await fetch(`${API_BASE}/api/knowledge/search${url.search}`, {
    signal: AbortSignal.timeout(10000),
  });

  return new Response(resp.body, {
    status: resp.status,
    headers: { "Content-Type": "application/json" },
  });
}
