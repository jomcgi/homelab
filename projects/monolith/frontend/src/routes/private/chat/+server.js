const API_BASE = process.env.API_BASE || "http://localhost:8000";

export async function POST({ request }) {
  const body = await request.json();

  const upstream = await fetch(`${API_BASE}/api/chat/explore`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(120000),
  });

  if (!upstream.ok) {
    return new Response(JSON.stringify({ error: "upstream failed" }), {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  }

  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}

export async function GET({ url }) {
  const noteId = url.searchParams.get("note_id");
  if (!noteId) return new Response("missing note_id", { status: 400 });

  const res = await fetch(
    `${API_BASE}/api/knowledge/notes/${encodeURIComponent(noteId)}`,
    { signal: AbortSignal.timeout(10000) },
  );
  return new Response(res.body, {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}
