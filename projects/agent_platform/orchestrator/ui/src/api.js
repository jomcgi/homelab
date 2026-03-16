const API = "";

export async function listJobs({ status, tags, limit = 20, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (tags) params.set("tags", tags);
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  const res = await fetch(`${API}/jobs?${params}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getJob(id) {
  const res = await fetch(`${API}/jobs/${id}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function submitJob(task) {
  const res = await fetch(`${API}/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task, source: "dashboard" }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function cancelJob(id) {
  const res = await fetch(`${API}/jobs/${id}/cancel`, { method: "POST" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getJobOutput(id) {
  const res = await fetch(`${API}/jobs/${id}/output`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function summarizeJob(id) {
  const res = await fetch(`${API}/jobs/${id}/summarize`, { method: "POST" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
