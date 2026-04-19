const API_BASE = process.env.API_BASE || "http://localhost:8000";

export async function load({ fetch }) {
  const [todoRes, scheduleRes] = await Promise.all([
    fetch(`${API_BASE}/api/home`, { signal: AbortSignal.timeout(10000) }),
    fetch(`${API_BASE}/api/home/schedule/today`, {
      signal: AbortSignal.timeout(10000),
    }).catch(() => ({ ok: false })),
  ]);
  return {
    todo: await todoRes.json(),
    schedule: scheduleRes.ok ? await scheduleRes.json() : [],
  };
}

export const actions = {
  save: async ({ request, fetch }) => {
    const data = await request.formData();
    const body = data.get("body");
    await fetch(`${API_BASE}/api/home`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body,
      signal: AbortSignal.timeout(10000),
    });
  },
  capture: async ({ request, fetch }) => {
    const data = await request.formData();
    const content = data.get("content");
    const res = await fetch(`${API_BASE}/api/notes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
      signal: AbortSignal.timeout(10000),
    });
    if (!res.ok) return { error: true };
  },
  ingest: async ({ request, fetch }) => {
    const data = await request.formData();
    const url = data.get("url");
    const sourceType = data.get("source_type");
    if (!url) return { error: true };
    const res = await fetch(`${API_BASE}/api/knowledge/ingest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, source_type: sourceType }),
      signal: AbortSignal.timeout(10000),
    });
    if (!res.ok) return { error: true };
  },
  search: async ({ request, fetch }) => {
    const data = await request.formData();
    const q = data.get("q");
    const type = data.get("type");
    if (!q) return { results: [] };
    const params = new URLSearchParams({ q });
    if (type && type !== "all") params.set("type", type);
    try {
      const res = await fetch(`${API_BASE}/api/knowledge/search?${params}`, {
        signal: AbortSignal.timeout(10000),
      });
      if (res.ok) {
        const json = await res.json();
        return { results: json.results };
      }
      if (res.status === 503)
        return { results: [], error: "embedding unavailable" };
      return { results: [], error: `search failed (${res.status})` };
    } catch {
      return { results: [], error: "search unavailable" };
    }
  },
  preview: async ({ request, fetch }) => {
    const data = await request.formData();
    const noteId = data.get("note_id");
    if (!noteId) return { note: null };
    try {
      const res = await fetch(
        `${API_BASE}/api/knowledge/notes/${encodeURIComponent(noteId)}`,
        { signal: AbortSignal.timeout(10000) },
      );
      if (res.ok) return { note: await res.json() };
      return { note: null };
    } catch {
      return { note: null };
    }
  },
};
