"""Public stats endpoint — exposes non-sensitive cluster and knowledge metrics.

Gathers data from two sources:
1. Kubernetes API — node, deployment, pod, ArgoCD application counts
2. PostgreSQL — knowledge.notes, knowledge.chunks, knowledge.raw_inputs counts

Cached for 24 hours; warmed on startup via lifespan.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from sqlalchemy import text

from app.db import get_engine
from shared.kubernetes import KubernetesClient

logger = logging.getLogger(__name__)

_CACHE_TTL = 86400  # 24 hours
_cache: dict | None = None
_cache_time: float = 0.0


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
    """Query Kubernetes cluster resource counts."""
    k8s = KubernetesClient()
    try:
        nodes, deployments, pods, argo_apps = await asyncio.gather(
            k8s.count_nodes(),
            k8s.count_deployments(),
            k8s.count_pods(),
            k8s.count_argocd_applications(),
            return_exceptions=True,
        )
        return {
            "nodes": nodes if not isinstance(nodes, Exception) else 0,
            "deployments": deployments if not isinstance(deployments, Exception) else 0,
            "pods": pods if not isinstance(pods, Exception) else 0,
            "argocd_apps": argo_apps if not isinstance(argo_apps, Exception) else 0,
        }
    finally:
        await k8s.close()


async def build_stats() -> dict:
    """Collect all stats and return the response payload."""
    engine = get_engine()

    cluster_counts, knowledge_counts = await asyncio.gather(
        _query_cluster_counts(),
        _query_knowledge_counts(engine),
    )

    return {
        "cluster": cluster_counts,
        "knowledge": knowledge_counts,
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
