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
    auth_token = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    if not auth_token:
        logger.warning("knowledge.garden: ANTHROPIC_AUTH_TOKEN not set, skipping")
        return None

    import anthropic

    from knowledge.gardener import Gardener

    vault_root = Path(os.environ.get(_VAULT_ROOT_ENV, _DEFAULT_VAULT_ROOT))
    # Env-overridable cap so operators can throttle without a chart change.
    try:
        max_files = int(os.environ.get("GARDENER_MAX_FILES_PER_RUN", "10"))
    except ValueError:
        logger.warning(
            "knowledge.garden: GARDENER_MAX_FILES_PER_RUN is not an integer, "
            "falling back to default",
        )
        max_files = 10
    gardener = Gardener(
        vault_root=vault_root,
        anthropic_client=anthropic.Anthropic(auth_token=auth_token),
        store=KnowledgeStore(session=session),
        embed_client=EmbeddingClient(),
        max_files_per_run=max_files,
    )
    stats = await gardener.run()
    extra = {
        "ingested": stats.ingested,
        "failed": stats.failed,
        "ttl_cleaned": stats.ttl_cleaned,
    }
    # When every ingest attempt failed (e.g. Anthropic API outage, auth error,
    # or the whole batch hit malformed content), promote the summary log to
    # ERROR so log-level-based alerting surfaces the outage even though the
    # handler itself returns cleanly (we don't want to poison the scheduler's
    # last_status for recoverable data errors).
    if stats.ingested == 0 and stats.failed > 0:
        logger.error("knowledge.garden complete (all failed)", extra=extra)
    else:
        logger.info("knowledge.garden complete", extra=extra)
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
