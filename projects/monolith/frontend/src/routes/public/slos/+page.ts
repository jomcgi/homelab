export const ssr = false;

export async function load({ fetch }) {
  const resp = await fetch("/api/public/observability/topology", {
    signal: AbortSignal.timeout(10_000),
  });
  if (!resp.ok) {
    return { topology: { groups: [], nodes: [], edges: [] } };
  }
  const topology = await resp.json();
  return { topology };
}
