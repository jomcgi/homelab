import { env } from "$env/dynamic/private";

const API_BASE = env.API_BASE || "http://localhost:8000";

/** @type {import('./$types').RequestHandler} */
export async function GET({ params }) {
  const resp = await fetch(
    `${API_BASE}/api/knowledge/notes/${encodeURIComponent(params.note_id)}`,
    { signal: AbortSignal.timeout(10000) },
  );

  return new Response(resp.body, {
    status: resp.status,
    headers: { "Content-Type": "application/json" },
  });
}
