const API_BASE = process.env.API_BASE || "http://localhost:8000";

export async function load({ fetch, setHeaders }) {
  const resp = await fetch(`${API_BASE}/api/public/observability/topology`, {
    signal: AbortSignal.timeout(10_000),
  });
  if (!resp.ok) {
    return { topology: { groups: [], nodes: [], edges: [] } };
  }
  setHeaders({ "cache-control": "public, s-maxage=900, max-age=60" });
  const topology = await resp.json();
  return { topology };
}
