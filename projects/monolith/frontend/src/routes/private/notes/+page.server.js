import { error } from "@sveltejs/kit";
import { PAGE_CACHE_CONTROL } from "$lib/cache-headers.js";

const API_BASE = process.env.API_BASE || "http://localhost:8000";

export async function load({ fetch, setHeaders }) {
  setHeaders({ "cache-control": PAGE_CACHE_CONTROL });
  const res = await fetch(`${API_BASE}/api/knowledge/graph`, {
    signal: AbortSignal.timeout(10_000),
  });
  if (!res.ok) {
    throw error(503, "graph unavailable");
  }
  return { graph: await res.json() };
}
