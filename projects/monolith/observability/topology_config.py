"""Topology configuration defined in Python — no YAML file I/O needed.

Helper functions generate the repeated ClickHouse SQL patterns so each node
definition stays concise.
"""

from __future__ import annotations

from observability.config import (
    EdgeConfig,
    GroupConfig,
    MetricConfig,
    NodeConfig,
    SloConfig,
    TopologyConfig,
)

WINDOW_DAYS = 30
SLO_TARGET = 99.0


def _container_ready_query(namespace: str, container: str) -> str:
    """SLO query: percentage of minutes where k8s.container.ready >= 1."""
    return f"""\
WITH per_minute AS (
  SELECT intDiv(s.unix_milli, 60000) AS mb, max(s.value) AS ready
  FROM signoz_metrics.distributed_samples_v4 s
  WHERE s.fingerprint IN (
    SELECT DISTINCT fingerprint FROM signoz_metrics.distributed_time_series_v4_6hrs
    WHERE metric_name = 'k8s.container.ready'
      AND JSONExtractString(labels, 'k8s.namespace.name') = '{namespace}'
      AND JSONExtractString(labels, 'k8s.container.name') = '{container}'
  ) AND s.unix_milli >= toUnixTimestamp(now() - INTERVAL {WINDOW_DAYS} DAY) * 1000
  GROUP BY mb
)
SELECT round(countIf(ready >= 1) / count() * 100, 4) AS value FROM per_minute"""


def _envoy_success_rate_query(cluster_pattern: str) -> str:
    """SLO query: envoy upstream success rate (only 5xx = bad)."""
    return f"""\
WITH
bad AS (
  SELECT intDiv(unix_milli, 60000) AS mb, sum(value) AS v
  FROM signoz_metrics.distributed_samples_v4
  WHERE fingerprint IN (
    SELECT DISTINCT fingerprint FROM signoz_metrics.distributed_time_series_v4_6hrs
    WHERE metric_name = 'envoy_cluster_upstream_rq_xx'
      AND JSONExtractString(labels, 'envoy_cluster_name') LIKE '%{cluster_pattern}%'
      AND JSONExtractString(labels, 'envoy_response_code_class') = '5'
  ) AND unix_milli >= toUnixTimestamp(now() - INTERVAL {WINDOW_DAYS} DAY) * 1000
  GROUP BY mb
),
total AS (
  SELECT intDiv(unix_milli, 60000) AS mb, sum(value) AS v
  FROM signoz_metrics.distributed_samples_v4
  WHERE fingerprint IN (
    SELECT DISTINCT fingerprint FROM signoz_metrics.distributed_time_series_v4_6hrs
    WHERE metric_name = 'envoy_cluster_upstream_rq_xx'
      AND JSONExtractString(labels, 'envoy_cluster_name') LIKE '%{cluster_pattern}%'
  ) AND unix_milli >= toUnixTimestamp(now() - INTERVAL {WINDOW_DAYS} DAY) * 1000
  GROUP BY mb
)
SELECT round((1 - sum(coalesce(b.v, 0)) / sum(t.v)) * 100, 4) AS value
FROM total t LEFT JOIN bad b ON t.mb = b.mb"""


def _cnpg_up_query() -> str:
    """SLO query: CNPG collector up."""
    return f"""\
WITH per_minute AS (
  SELECT intDiv(s.unix_milli, 60000) AS mb, max(s.value) AS up
  FROM signoz_metrics.distributed_samples_v4 s
  WHERE s.fingerprint IN (
    SELECT DISTINCT fingerprint FROM signoz_metrics.distributed_time_series_v4_6hrs
    WHERE metric_name = 'cnpg_collector_up'
  ) AND s.unix_milli >= toUnixTimestamp(now() - INTERVAL {WINDOW_DAYS} DAY) * 1000
  GROUP BY mb
)
SELECT round(countIf(up >= 1) / count() * 100, 4) AS value FROM per_minute"""


def _slo(query: str) -> SloConfig:
    return SloConfig(target=SLO_TARGET, window_days=WINDOW_DAYS, query=query)


TOPOLOGY = TopologyConfig(
    cache_ttl=900,
    groups=[
        GroupConfig(
            id="monolith",
            label="MONOLITH",
            tier="critical",
            ingress=True,
            description="fastapi + sveltekit",
            children=["home", "knowledge", "chat"],
            slo=SloConfig(target=SLO_TARGET, window_days=WINDOW_DAYS),
        ),
        GroupConfig(
            id="context-forge",
            label="CONTEXT FORGE",
            tier="critical",
            ingress=True,
            description="mcp gateway",
            children=["k8s-mcp", "argocd-mcp", "signoz-mcp"],
            slo=SloConfig(target=SLO_TARGET, window_days=WINDOW_DAYS),
        ),
        GroupConfig(
            id="cluster",
            label="CLUSTER",
            tier="infra",
            description="k3s infrastructure",
            children=[
                "argocd",
                "signoz",
                "envoy-gateway",
                "longhorn",
                "seaweedfs",
                "otel-operator",
                "linkerd",
            ],
        ),
    ],
    nodes=[
        # --- ingress / external ---
        NodeConfig(
            id="external",
            label="EXTERNAL",
            tier="ingress",
            description="webpage · claude · cli",
            metrics=[MetricConfig(key="clients", static="webpage, claude, cli")],
        ),
        NodeConfig(
            id="discord",
            label="DISCORD",
            tier="ingress",
            description="discord api",
            metrics=[MetricConfig(key="service", static="discord api")],
        ),
        # --- critical path ---
        NodeConfig(
            id="cloudflare",
            label="CLOUDFLARE TUNNEL",
            tier="critical",
            description="cloudflare tunnel",
            slo=_slo(_container_ready_query("envoy-gateway-system", "cloudflared")),
        ),
        NodeConfig(
            id="home",
            label="HOME",
            tier="critical",
            group="monolith",
            description="dashboard + notes + schedule",
            slo=_slo(_envoy_success_rate_query("monolith-public")),
        ),
        NodeConfig(
            id="knowledge",
            label="KNOWLEDGE",
            tier="critical",
            group="monolith",
            description="search · ingest · gardener",
            slo=_slo(_envoy_success_rate_query("monolith-private")),
        ),
        NodeConfig(
            id="chat",
            label="CHAT",
            tier="critical",
            group="monolith",
            description="discord backfill + summarization",
            slo=_slo(_envoy_success_rate_query("monolith-private")),
        ),
        NodeConfig(
            id="postgres",
            label="POSTGRES",
            tier="critical",
            description="cnpg + pgvector",
            slo=_slo(_cnpg_up_query()),
        ),
        NodeConfig(
            id="nats",
            label="NATS",
            tier="critical",
            description="jetstream message bus",
            slo=_slo(_container_ready_query("nats", "nats")),
        ),
        NodeConfig(
            id="agent-platform",
            label="AGENT PLATFORM",
            tier="critical",
            ingress=True,
            description="orchestrator + mcp clients",
            slo=_slo(_envoy_success_rate_query("agent-orchestrator")),
        ),
        NodeConfig(
            id="llama-cpp",
            label="GEMMA 4",
            tier="critical",
            description="gemma 4 inference",
            slo=_slo(_container_ready_query("gpu-operator", "llama-cpp")),
        ),
        NodeConfig(
            id="voyage-embedder",
            label="VOYAGE EMBEDDER",
            tier="critical",
            description="voyage-4 embedding",
            slo=_slo(_container_ready_query("gpu-operator", "voyage-embedder")),
        ),
        # --- context-forge children ---
        NodeConfig(
            id="k8s-mcp",
            label="K8S",
            tier="critical",
            group="context-forge",
            description="kubernetes mcp server",
            slo=_slo(_container_ready_query("mcp", "k8s-mcp")),
        ),
        NodeConfig(
            id="argocd-mcp",
            label="ARGOCD",
            tier="critical",
            group="context-forge",
            description="argocd mcp server",
            slo=_slo(_container_ready_query("mcp", "argocd-mcp")),
        ),
        NodeConfig(
            id="signoz-mcp",
            label="SIGNOZ",
            tier="critical",
            group="context-forge",
            description="signoz mcp server",
            slo=_slo(_container_ready_query("mcp", "signoz-mcp")),
        ),
        # --- cluster / infra ---
        NodeConfig(
            id="argocd",
            label="ARGOCD",
            tier="infra",
            group="cluster",
            description="gitops controller",
            slo=_slo(_container_ready_query("argocd", "application-controller")),
        ),
        NodeConfig(
            id="signoz",
            label="SIGNOZ",
            tier="infra",
            group="cluster",
            description="observability platform",
            slo=_slo(_container_ready_query("signoz", "signoz")),
        ),
        NodeConfig(
            id="envoy-gateway",
            label="ENVOY GATEWAY",
            tier="infra",
            group="cluster",
            description="api gateway",
            slo=_slo(_container_ready_query("envoy-gateway-system", "envoy-gateway")),
        ),
        NodeConfig(
            id="longhorn",
            label="LONGHORN",
            tier="infra",
            group="cluster",
            description="distributed storage",
            slo=_slo(_container_ready_query("longhorn-system", "longhorn-manager")),
        ),
        NodeConfig(
            id="seaweedfs",
            label="SEAWEEDFS",
            tier="infra",
            group="cluster",
            description="object storage",
            slo=_slo(_container_ready_query("seaweedfs", "seaweedfs")),
        ),
        NodeConfig(
            id="otel-operator",
            label="OTEL OPERATOR",
            tier="infra",
            group="cluster",
            description="opentelemetry operator",
            slo=_slo(
                _container_ready_query("opentelemetry-operator-system", "manager")
            ),
        ),
        NodeConfig(
            id="linkerd",
            label="LINKERD",
            tier="infra",
            group="cluster",
            description="service mesh",
            slo=_slo(_container_ready_query("linkerd", "destination")),
        ),
    ],
    edges=[
        EdgeConfig(source="external", target="cloudflare"),
        EdgeConfig(source="cloudflare", target="home"),
        EdgeConfig(source="cloudflare", target="knowledge"),
        EdgeConfig(source="cloudflare", target="agent-platform"),
        EdgeConfig(source="home", target="postgres"),
        EdgeConfig(source="knowledge", target="postgres"),
        EdgeConfig(source="knowledge", target="voyage-embedder"),
        EdgeConfig(source="knowledge", target="llama-cpp"),
        EdgeConfig(source="chat", target="postgres"),
        EdgeConfig(source="chat", target="llama-cpp"),
        EdgeConfig(source="chat", target="discord"),
        EdgeConfig(source="nats", target="agent-platform", bidi=True),
        EdgeConfig(source="agent-platform", target="k8s-mcp"),
        EdgeConfig(source="agent-platform", target="argocd-mcp"),
        EdgeConfig(source="agent-platform", target="signoz-mcp"),
    ],
)
