"""Mirror chat summary rows to the Obsidian vault for human reasoning.

Each summary row in the database (UserChannelSummary, ChannelSummary) is
mirrored to a markdown file under ``_discord/{channel_id}/`` in the vault.
Files are replaced in-place when the row updates -- there are no dated
snapshots. These files are intentionally NOT ingested by the knowledge
graph; they exist so a human can browse what the bot understands.
"""

import logging
import os
from datetime import datetime
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_VAULT_ROOT_ENV = "VAULT_ROOT"
_DEFAULT_VAULT_ROOT = "/vault"
_SYNC_READY_SENTINEL = ".sync-ready"
_DISCORD_ROOT = "_discord"


def _vault_root() -> Path:
    return Path(os.environ.get(_VAULT_ROOT_ENV, _DEFAULT_VAULT_ROOT))


def _vault_ready() -> bool:
    return (_vault_root() / _SYNC_READY_SENTINEL).exists()


def _render(frontmatter: dict, body: str) -> str:
    fm = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
    return f"---\n{fm}---\n\n{body.rstrip()}\n"


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def write_user_summary(
    *,
    channel_id: str,
    user_id: str,
    username: str,
    summary: str,
    last_message_id: int,
    updated_at: datetime,
) -> None:
    """Mirror a UserChannelSummary row to ``_discord/{channel_id}/users/{user_id}.md``."""
    if not _vault_ready():
        logger.debug(
            "Vault not ready; skipping user summary export for %s/%s",
            channel_id,
            user_id,
        )
        return
    path = _vault_root() / _DISCORD_ROOT / channel_id / "users" / f"{user_id}.md"
    content = _render(
        {
            "type": "discord-user-summary",
            "channel_id": channel_id,
            "user_id": user_id,
            "username": username,
            "last_message_id": last_message_id,
            "updated_at": updated_at.isoformat(),
        },
        summary,
    )
    try:
        _write_atomic(path, content)
    except OSError:
        logger.exception("Failed to write user summary file %s", path)


def write_channel_summary(
    *,
    channel_id: str,
    summary: str,
    message_count: int,
    last_message_id: int,
    updated_at: datetime,
) -> None:
    """Mirror a ChannelSummary row to ``_discord/{channel_id}/channel.md``."""
    if not _vault_ready():
        logger.debug(
            "Vault not ready; skipping channel summary export for %s",
            channel_id,
        )
        return
    path = _vault_root() / _DISCORD_ROOT / channel_id / "channel.md"
    content = _render(
        {
            "type": "discord-channel-summary",
            "channel_id": channel_id,
            "message_count": message_count,
            "last_message_id": last_message_id,
            "updated_at": updated_at.isoformat(),
        },
        summary,
    )
    try:
        _write_atomic(path, content)
    except OSError:
        logger.exception("Failed to write channel summary file %s", path)
