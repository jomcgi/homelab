const API = "";

export async function listJobs({ status, tags, limit = 20, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (tags) params.set("tags", tags);
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  const res = await fetch(`${API}/jobs?${params}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json(); // { jobs, total }
}

export async function getJob(id) {
  const res = await fetch(`${API}/jobs/${id}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function submitJob({ task, profile, tags, source = "dashboard" }) {
  const res = await fetch(`${API}/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      task,
      profile: profile || "",
      tags: tags
        ? tags
            .split(",")
            .map((t) => t.trim())
            .filter(Boolean)
        : [],
      source,
    }),
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

export async function listAgents() {
  const res = await fetch(`${API}/agents`);
  if (!res.ok) throw new Error(await res.text());
  return res.json(); // { agents: AgentInfo[] }
}

export async function submitPipeline(spec) {
  const res = await fetch(`${API}/pipeline`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(spec),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json(); // { pipeline_id, jobs }
}
