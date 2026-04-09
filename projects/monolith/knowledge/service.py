"""Startup hook that registers the knowledge scheduled jobs."""

import logging
import os
from datetime import datetime
from pathlib import Path

from sqlmodel import Session

from knowledge.reconciler import Reconciler
from knowledge.store import KnowledgeStore
from shared.embedding import EmbeddingClient

logger = logging.getLogger(__name__)

_VAULT_ROOT_ENV = "VAULT_ROOT"
_DEFAULT_VAULT_ROOT = "/vault"
# 5-minute reconcile cycle. The companion _TTL_SECS=600 ensures at
# most one missed run before alerting fires (the scheduler considers
# a job stale after ttl_secs).
_INTERVAL_SECS = 300
_TTL_SECS = 600


async def garden_handler(session: Session) -> datetime | None:
    """Scheduler handler: run the knowledge vault gardener."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("knowledge.garden: ANTHROPIC_API_KEY not set, skipping")
        return None

    import anthropic

    from knowledge.gardener import Gardener

    vault_root = Path(os.environ.get(_VAULT_ROOT_ENV, _DEFAULT_VAULT_ROOT))
    gardener = Gardener(
        vault_root=vault_root,
        anthropic_client=anthropic.Anthropic(api_key=api_key),
        store=KnowledgeStore(session=session),
        embed_client=EmbeddingClient(),
    )
    stats = await gardener.run()
    logger.info(
        "knowledge.garden complete",
        extra={
            "ingested": stats.ingested,
            "failed": stats.failed,
            "ttl_cleaned": stats.ttl_cleaned,
        },
    )
    return None


async def reconcile_handler(session: Session) -> datetime | None:
    """Scheduler handler: run the knowledge vault reconciler."""
    vault_root = Path(os.environ.get(_VAULT_ROOT_ENV, _DEFAULT_VAULT_ROOT))
    reconciler = Reconciler(
        store=KnowledgeStore(session=session),
        embed_client=EmbeddingClient(),
        vault_root=vault_root,
    )
    stats = await reconciler.run()
    logger.info(
        "knowledge.reconcile complete",
        extra={
            "upserted": stats.upserted,
            "deleted": stats.deleted,
            "unchanged": stats.unchanged,
            "failed": stats.failed,
            "skipped_locked": stats.skipped_locked,
        },
    )
    return None


def on_startup(session: Session) -> None:
    """Register knowledge jobs with the scheduler."""
    from shared.scheduler import register_job

    # The scheduler claims one job per tick (LIMIT 1) and polls every 30s,
    # so the two jobs always run in separate ticks — there is no hard
    # ordering guarantee between them within a single cycle, and Postgres
    # gives no tiebreaker for identical next_run_at values. Registration
    # order is documentary rather than load-bearing. The eventual
    # consistency is fine: any file the gardener writes to _processed/ is
    # picked up by the reconciler on its next tick (~30s later).
    register_job(
        session,
        name="knowledge.garden",
        interval_secs=_INTERVAL_SECS,
        handler=garden_handler,
        ttl_secs=_TTL_SECS,
    )
    register_job(
        session,
        name="knowledge.reconcile",
        interval_secs=_INTERVAL_SECS,
        handler=reconcile_handler,
        ttl_secs=_TTL_SECS,
    )
