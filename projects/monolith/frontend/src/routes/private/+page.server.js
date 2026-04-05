const API_BASE = process.env.API_BASE || "http://localhost:8000";

export async function load({ fetch }) {
  const [todoRes, scheduleRes] = await Promise.all([
    fetch(`${API_BASE}/api/home`, { signal: AbortSignal.timeout(10000) }),
    fetch(`${API_BASE}/api/schedule/today`, {
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
};
