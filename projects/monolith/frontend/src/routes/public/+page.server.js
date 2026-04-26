import { PAGE_CACHE_CONTROL } from "$lib/cache-headers.js";

const API_BASE = process.env.API_BASE || "http://localhost:8000";

const STATIC_TOPOLOGY = {
  groups: [
    {
      id: "monolith",
      label: "MONOLITH",
      tier: "critical",
      description: "fastapi + sveltekit",
      children: ["home", "knowledge", "chat", "mcp"],
      slo: { target: 98.0, current: null },
      ingress: true,
    },
    {
      id: "cluster",
      label: "CLUSTER",
      tier: "infra",
      description: "k3s infrastructure",
      children: [
        "argocd",
        "signoz",
        "envoy-gateway",
        "longhorn",
        "seaweedfs",
        "otel-operator",
        "linkerd",
      ],
      slo: { target: 99.0, current: null },
    },
  ],
  nodes: [
    {
      id: "external",
      label: "EXTERNAL",
      tier: "ingress",
      description: "webpage \u00b7 claude \u00b7 cli",
    },
    {
      id: "discord",
      label: "DISCORD",
      tier: "ingress",
      description: "discord api",
    },
    {
      id: "cloudflare",
      label: "CLOUDFLARE TUNNEL",
      tier: "critical",
      description: "cloudflare tunnel",
      slo: { target: 98.0, current: null },
    },
    {
      id: "home",
      label: "HOME",
      tier: "critical",
      description: "dashboard + notes + schedule",
      group: "monolith",
      slo: { target: 98.0, current: null },
    },
    {
      id: "knowledge",
      label: "KNOWLEDGE",
      tier: "critical",
      description: "search \u00b7 ingest \u00b7 gardener",
      group: "monolith",
      slo: { target: 98.0, current: null },
    },
    {
      id: "chat",
      label: "CHAT",
      tier: "critical",
      description: "discord backfill + summarization",
      group: "monolith",
      slo: { target: 98.0, current: null },
    },
    {
      id: "mcp",
      label: "MCP",
      tier: "critical",
      description: "model context protocol server",
      group: "monolith",
      slo: { target: 98.0, current: null },
    },
    {
      id: "postgres",
      label: "POSTGRES",
      tier: "critical",
      description: "cnpg + pgvector",
      slo: { target: 98.0, current: null },
    },
    {
      id: "nats",
      label: "NATS",
      tier: "critical",
      description: "jetstream message bus",
      slo: { target: 98.0, current: null },
    },
    {
      id: "agent-platform",
      label: "AGENT PLATFORM",
      tier: "critical",
      description: "orchestrator + mcp clients",
      ingress: true,
      slo: { target: 98.0, current: null },
    },
    {
      id: "context-forge",
      label: "CONTEXT FORGE",
      tier: "critical",
      description: "mcp gateway",
      ingress: true,
      slo: { target: 98.0, current: null },
    },
    {
      id: "llama-cpp",
      label: "GEMMA 4",
      tier: "critical",
      description: "gemma 4 inference",
      slo: { target: 98.0, current: null },
    },
    {
      id: "voyage-embedder",
      label: "VOYAGE EMBEDDER",
      tier: "critical",
      description: "voyage-4 embedding",
      slo: { target: 98.0, current: null },
    },
    {
      id: "argocd",
      label: "ARGOCD",
      tier: "infra",
      description: "gitops controller",
      group: "cluster",
      slo: { target: 98.0, current: null },
    },
    {
      id: "signoz",
      label: "SIGNOZ",
      tier: "infra",
      description: "observability platform",
      group: "cluster",
      slo: { target: 98.0, current: null },
    },
    {
      id: "envoy-gateway",
      label: "ENVOY GATEWAY",
      tier: "infra",
      description: "api gateway",
      group: "cluster",
      slo: { target: 98.0, current: null },
    },
    {
      id: "longhorn",
      label: "LONGHORN",
      tier: "infra",
      description: "distributed storage",
      group: "cluster",
      slo: { target: 98.0, current: null },
    },
    {
      id: "seaweedfs",
      label: "SEAWEEDFS",
      tier: "infra",
      description: "object storage",
      group: "cluster",
      slo: { target: 98.0, current: null },
    },
    {
      id: "otel-operator",
      label: "OTEL OPERATOR",
      tier: "infra",
      description: "opentelemetry operator",
      group: "cluster",
      slo: { target: 98.0, current: null },
    },
    {
      id: "linkerd",
      label: "LINKERD",
      tier: "infra",
      description: "service mesh",
      group: "cluster",
      slo: { target: 98.0, current: null },
    },
  ],
  edges: [
    { from: "external", to: "cloudflare" },
    { from: "cloudflare", to: "monolith" },
    { from: "cloudflare", to: "agent-platform" },
    { from: "cloudflare", to: "context-forge" },
    { from: "knowledge", to: "postgres" },
    { from: "knowledge", to: "voyage-embedder" },
    { from: "knowledge", to: "llama-cpp" },
    { from: "chat", to: "llama-cpp" },
    { from: "chat", to: "discord" },
    { from: "chat", to: "knowledge" },
    { from: "mcp", to: "knowledge" },
    { from: "nats", to: "agent-platform", bidi: true },
    { from: "agent-platform", to: "context-forge" },
    { from: "context-forge", to: "mcp" },
  ],
};

async function _fetchJson(fetchFn, path) {
  try {
    const resp = await fetchFn(`${API_BASE}${path}`, {
      signal: AbortSignal.timeout(5_000),
    });
    if (!resp.ok) return null;
    return await resp.json();
  } catch {
    return null;
  }
}

export async function load({ fetch, setHeaders }) {
  const [topology, stats] = await Promise.all([
    _fetchJson(fetch, "/api/home/observability/topology"),
    _fetchJson(fetch, "/api/home/observability/stats"),
  ]);
  setHeaders({ "cache-control": PAGE_CACHE_CONTROL });
  return {
    topology: topology ?? STATIC_TOPOLOGY,
    stats,
  };
}
