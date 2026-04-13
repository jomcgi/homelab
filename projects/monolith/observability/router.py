from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path

from fastapi import APIRouter

from observability.clickhouse import ClickHouseClient
from observability.config import load_config, NodeConfig, GroupConfig, TopologyConfig
from observability.slo import (
    aggregate_group,
    compute_brief,
    compute_budget,
    compute_status,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/public/observability", tags=["observability"])

_cache: dict | None = None
_cache_time: float = 0.0
_config: TopologyConfig | None = None


def _get_config() -> TopologyConfig:
    global _config
    if _config is None:
        config_path = Path(__file__).parent / "topology.yaml"
        _config = load_config(config_path)
    return _config


async def _query_node(client: ClickHouseClient, node: NodeConfig) -> dict:
    """Execute all queries for a single node and return topology JSON."""
    result: dict = {
        "id": node.id,
        "label": node.label,
        "tier": node.tier,
        "description": node.description,
    }
    if node.group:
        result["group"] = node.group
    if node.ingress:
        result["ingress"] = True

    # SLO query
    availability = None
    if node.slo and node.slo.query:
        try:
            availability = await client.query_scalar(node.slo.query)
        except Exception:
            logger.exception("SLO query failed for %s", node.id)

    if node.slo:
        result["slo"] = {"target": node.slo.target, "current": availability}
        if availability is not None:
            result["status"] = compute_status(availability, node.slo.target)
            result["budget"] = compute_budget(
                availability, node.slo.target, node.slo.window_days
            )
        else:
            result["status"] = "degraded"
    else:
        result["status"] = "healthy"

    # Metric queries
    metrics = []
    for m in node.metrics:
        if m.static is not None:
            metrics.append({"k": m.key, "v": m.static})
        elif m.query:
            try:
                val = await client.query_scalar(m.query)
                suffix = m.unit or ""
                v = f"{val}{suffix}" if val is not None else "—"
                metrics.append({"k": m.key, "v": v})
            except Exception:
                logger.exception("Metric query failed for %s.%s", node.id, m.key)
                metrics.append({"k": m.key, "v": "—"})
    result["metrics"] = metrics

    # Brief
    metrics_dict = {m["k"]: m["v"] for m in metrics}
    result["brief"] = compute_brief(availability, metrics_dict)

    # Spark query
    if node.spark:
        try:
            rows = await client.query_rows(node.spark.query)
            result["spark"] = [r.get("value", 0) for r in rows]
        except Exception:
            logger.exception("Spark query failed for %s", node.id)

    return result


async def build_topology() -> dict:
    """Execute all queries and build the full topology response."""
    cfg = _get_config()
    ch_url = os.environ.get(
        "CLICKHOUSE_URL",
        "http://chi-signoz-clickhouse-cluster-0-0.signoz.svc.cluster.local:8123",
    )
    client = ClickHouseClient(base_url=ch_url)

    try:
        # Query all nodes in parallel
        node_results = await asyncio.gather(
            *[_query_node(client, n) for n in cfg.nodes],
            return_exceptions=True,
        )

        # Build node lookup, handling exceptions
        nodes = []
        node_map: dict[str, dict] = {}
        for i, r in enumerate(node_results):
            if isinstance(r, Exception):
                logger.error("Node %s failed: %s", cfg.nodes[i].id, r)
                fallback = {
                    "id": cfg.nodes[i].id,
                    "label": cfg.nodes[i].label,
                    "tier": cfg.nodes[i].tier,
                    "description": cfg.nodes[i].description,
                    "status": "degraded",
                    "brief": "query error",
                    "metrics": [],
                }
                if cfg.nodes[i].group:
                    fallback["group"] = cfg.nodes[i].group
                nodes.append(fallback)
                node_map[cfg.nodes[i].id] = fallback
            else:
                nodes.append(r)
                node_map[r["id"]] = r

        # Aggregate groups
        groups = []
        for g in cfg.groups:
            children = [node_map[cid] for cid in g.children if cid in node_map]
            target = g.slo.target if g.slo else 99.0
            window = g.slo.window_days if g.slo else 30
            agg = aggregate_group(children, target, window)

            group_result = {
                "id": g.id,
                "label": g.label,
                "tier": g.tier,
                "description": g.description,
                "children": g.children,
                **agg,
            }
            if g.ingress:
                group_result["ingress"] = True
            groups.append(group_result)

        # Edges
        edges = []
        for e in cfg.edges:
            edge = {"from": e.source, "to": e.target}
            if e.bidi:
                edge["bidi"] = True
            edges.append(edge)

        return {"groups": groups, "nodes": nodes, "edges": edges}
    finally:
        await client.close()


@router.get("/topology")
async def get_topology():
    """Return topology with live metrics, cached for cache_ttl seconds."""
    global _cache, _cache_time
    cfg = _get_config()
    now = time.monotonic()
    if _cache is not None and (now - _cache_time) < cfg.cache_ttl:
        return _cache
    result = await build_topology()
    _cache = result
    _cache_time = now
    return result
