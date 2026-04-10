"""Startup hook that registers the knowledge scheduled jobs."""

import logging
import os
import subprocess
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
_BACKUP_INTERVAL_SECS = 86400  # 24 hours
_BACKUP_TTL_SECS = 3600  # 1 hour timeout


async def clone_vault() -> None:
    """Clone the vault repo to pre-seed the emptyDir volume.

    Skips if VAULT_GIT_REMOTE is not set or if the vault already has a .git dir.
    Embeds GITHUB_TOKEN in the clone URL for auth.
    """
    remote = os.environ.get("VAULT_GIT_REMOTE", "")
    if not remote:
        logger.info("VAULT_GIT_REMOTE not set, skipping clone")
        return

    vault_root = Path(os.environ.get(_VAULT_ROOT_ENV, _DEFAULT_VAULT_ROOT))
    if (vault_root / ".git").exists():
        logger.info("Vault at %s already initialised, skipping clone", vault_root)
        return

    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        remote = remote.replace("https://", f"https://x-access-token:{token}@")

    try:
        subprocess.run(
            ["git", "clone", "--depth=1", remote, str(vault_root)],
            capture_output=True,
            text=True,
            check=True,
        )
        logger.info("Vault cloned from git to %s", vault_root)
    except subprocess.CalledProcessError as exc:
        logger.warning(
            "Vault clone failed, proceeding without pre-seed: %s", exc.stderr
        )


def _git_in_vault(*args: str) -> subprocess.CompletedProcess:
    vault_root = Path(os.environ.get(_VAULT_ROOT_ENV, _DEFAULT_VAULT_ROOT))
    return subprocess.run(
        ["git", *args],
        cwd=vault_root,
        capture_output=True,
        text=True,
        check=True,
    )


async def vault_backup_handler(session: Session) -> datetime | None:
    """Scheduler handler: commit and push vault changes to GitHub."""
    vault_root = Path(os.environ.get(_VAULT_ROOT_ENV, _DEFAULT_VAULT_ROOT))
    if not (vault_root / ".git").exists():
        logger.info("knowledge.vault-backup: no .git dir, skipping")
        return None

    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=vault_root,
        capture_output=True,
        text=True,
    )
    if not status.stdout.strip():
        logger.info("knowledge.vault-backup: no changes to commit")
        return None

    try:
        _git_in_vault("add", "-A")
        _git_in_vault("commit", "-m", "sync: vault backup")
        _git_in_vault("push")
        logger.info("knowledge.vault-backup: committed and pushed")
    except subprocess.CalledProcessError as exc:
        logger.warning("knowledge.vault-backup: push failed: %s", exc.stderr)
    return None


async def garden_handler(session: Session) -> datetime | None:
    """Scheduler handler: run the knowledge vault gardener."""
    if not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        logger.warning("knowledge.garden: CLAUDE_CODE_OAUTH_TOKEN not set, skipping")
        return None

    from knowledge.gardener import Gardener

    vault_root = Path(os.environ.get(_VAULT_ROOT_ENV, _DEFAULT_VAULT_ROOT))
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
        max_files_per_run=max_files,
    )
    stats = await gardener.run()
    extra = {
        "ingested": stats.ingested,
        "failed": stats.failed,
        "ttl_cleaned": stats.ttl_cleaned,
    }
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
    register_job(
        session,
        name="knowledge.vault-backup",
        interval_secs=_BACKUP_INTERVAL_SECS,
        handler=vault_backup_handler,
        ttl_secs=_BACKUP_TTL_SECS,
    )
