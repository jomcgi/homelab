"""Public stats endpoint — exposes non-sensitive cluster and knowledge metrics.

Gathers data from three sources:
1. Kubernetes API — node, deployment, pod, ArgoCD application counts
   plus aggregate CPU/memory usage and capacity from the metrics API.
2. ClickHouse (SigNoz) — DCGM GPU utilization and frame buffer usage.
3. PostgreSQL — knowledge.notes, knowledge.chunks, knowledge.raw_inputs counts.

Cached for 60 seconds so live metrics (CPU/mem/GPU) feel current without
hammering ClickHouse or the metrics-server on every page load.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone

from sqlalchemy import text

from app.db import get_engine
from home.observability.clickhouse import ClickHouseClient
from shared.kubernetes import KubernetesClient

logger = logging.getLogger(__name__)

_CACHE_TTL = 60  # seconds — live CPU/mem/GPU should not be stale by more than a minute
_cache: dict | None = None
_cache_time: float = 0.0


_GPU_UTIL_QUERY = """\
SELECT round(avg(value), 1) AS value
FROM signoz_metrics.distributed_samples_v4
WHERE metric_name = 'DCGM_FI_DEV_GPU_UTIL'
  AND unix_milli >= toUnixTimestamp(now() - INTERVAL 5 MINUTE) * 1000"""

_GPU_FB_USED_QUERY = """\
SELECT round(avg(value), 0) AS value
FROM signoz_metrics.distributed_samples_v4
WHERE metric_name = 'DCGM_FI_DEV_FB_USED'
  AND unix_milli >= toUnixTimestamp(now() - INTERVAL 5 MINUTE) * 1000"""

_GPU_FB_FREE_QUERY = """\
SELECT round(avg(value), 0) AS value
FROM signoz_metrics.distributed_samples_v4
WHERE metric_name = 'DCGM_FI_DEV_FB_FREE'
  AND unix_milli >= toUnixTimestamp(now() - INTERVAL 5 MINUTE) * 1000"""


async def _query_knowledge_counts(engine) -> dict:
    """Query knowledge graph table counts from PostgreSQL."""
    queries = {
        "facts": "SELECT count(*) FROM knowledge.notes",
        "chunks": "SELECT count(*) FROM knowledge.chunks",
        "raw_inputs": "SELECT count(*) FROM knowledge.raw_inputs",
    }
    counts = {}
    from sqlmodel import Session

    with Session(engine) as session:
        for key, query in queries.items():
            try:
                result = session.exec(text(query)).one()
                counts[key] = result[0]
            except Exception:
                logger.exception("Failed to query %s count", key)
                counts[key] = 0
    return counts


async def _query_cluster_counts() -> dict:
    """Query Kubernetes cluster resource counts and aggregate node usage."""
    k8s = KubernetesClient()
    try:
        nodes, deployments, pods, argo_apps, resources = await asyncio.gather(
            k8s.count_nodes(),
            k8s.count_deployments(),
            k8s.count_pods(),
            k8s.count_argocd_applications(),
            k8s.aggregate_node_resources(),
            return_exceptions=True,
        )
        result: dict = {
            "nodes": nodes if not isinstance(nodes, Exception) else 0,
            "deployments": deployments if not isinstance(deployments, Exception) else 0,
            "pods": pods if not isinstance(pods, Exception) else 0,
            "argocd_apps": argo_apps if not isinstance(argo_apps, Exception) else 0,
        }
        if not isinstance(resources, Exception):
            cpu_used = resources["cpu_used_cores"]
            cpu_cap = resources["cpu_capacity_cores"]
            mem_used = resources["memory_used_bytes"] / 1024**3
            mem_cap = resources["memory_capacity_bytes"] / 1024**3
            result.update(
                {
                    "cpu_used_cores": round(cpu_used, 2),
                    "cpu_capacity_cores": round(cpu_cap, 1),
                    "memory_used_gb": round(mem_used, 1),
                    "memory_capacity_gb": round(mem_cap, 1),
                }
            )
        else:
            logger.warning("Node resource aggregation failed: %s", resources)
        return result
    finally:
        await k8s.close()


async def _query_gpu() -> dict:
    """Query DCGM GPU utilization and frame buffer usage from ClickHouse."""
    client = ClickHouseClient(
        base_url=os.environ.get("CLICKHOUSE_URL", ""),
        user=os.environ.get("CLICKHOUSE_USER", ""),
        password=os.environ.get("CLICKHOUSE_PASSWORD", ""),
    )
    try:
        util, fb_used_mib, fb_free_mib = await asyncio.gather(
            client.query_scalar(_GPU_UTIL_QUERY),
            client.query_scalar(_GPU_FB_USED_QUERY),
            client.query_scalar(_GPU_FB_FREE_QUERY),
            return_exceptions=True,
        )

        def _ok(v):
            return None if isinstance(v, Exception) else v

        util_v = _ok(util)
        used_v = _ok(fb_used_mib)
        free_v = _ok(fb_free_mib)
        result: dict = {"utilization_pct": util_v}
        if used_v is not None and free_v is not None:
            result["memory_used_gb"] = round(used_v / 1024, 1)
            result["memory_total_gb"] = round((used_v + free_v) / 1024, 1)
        return result
    except Exception:
        logger.exception("GPU query failed")
        return {"utilization_pct": None}
    finally:
        await client.close()


async def build_stats() -> dict:
    """Collect all stats and return the response payload."""
    engine = get_engine()

    cluster_counts, knowledge_counts, gpu = await asyncio.gather(
        _query_cluster_counts(),
        _query_knowledge_counts(engine),
        _query_gpu(),
    )

    return {
        "cluster": cluster_counts,
        "knowledge": knowledge_counts,
        "gpu": gpu,
        "platform": {
            "in_production_since": "2025-01",
        },
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }


async def warm_stats_cache() -> None:
    """Build stats and populate the module cache. Called at startup."""
    global _cache, _cache_time
    logger.info("Warming stats cache...")
    try:
        result = await build_stats()
        _cache = result
        _cache_time = time.monotonic()
        logger.info("Stats cache warmed")
    except Exception:
        logger.exception("Stats cache warm failed — will retry on first request")


async def get_cached_stats() -> dict:
    """Return stats, using cache if within TTL."""
    global _cache, _cache_time
    now = time.monotonic()
    if _cache is not None and (now - _cache_time) < _CACHE_TTL:
        return _cache
    result = await build_stats()
    _cache = result
    _cache_time = now
    return result
