"""Hourly changelog notifier — polls GitHub for new feat commits, summarizes via Gemma, posts to Discord."""

import logging
import os
import re
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

import discord
import httpx

logger = logging.getLogger(__name__)

# Conventional commit types we care about
_CHANGELOG_TYPES = re.compile(r"^(feat)(\(.+?\))?!?:\s")

GITHUB_API = "https://api.github.com"
_GITHUB_HEADERS = {"Accept": "application/vnd.github+json"}


def _auth_headers(token: str) -> dict[str, str]:
    return {**_GITHUB_HEADERS, "Authorization": f"token {token}"}


async def _fetch_commits_since(
    client: httpx.AsyncClient,
    repo: str,
    token: str,
    since: datetime,
) -> list[dict]:
    """Fetch commits on main since the given timestamp."""
    resp = await client.get(
        f"{GITHUB_API}/repos/{repo}/commits",
        params={"sha": "main", "since": since.isoformat(), "per_page": 100},
        headers=_auth_headers(token),
    )
    resp.raise_for_status()
    return resp.json()


def _filter_changelog_commits(commits: list[dict]) -> list[dict]:
    """Keep only feat conventional commits."""
    result = []
    for c in commits:
        msg = c["commit"]["message"].split("\n", 1)[0]
        if _CHANGELOG_TYPES.match(msg):
            result.append(c)
    return result


async def _summarize_with_gemma(
    commits: list[dict],
    llm_call: Callable[[str], Awaitable[str]],
) -> str:
    """Ask Gemma to produce a concise changelog from commit data."""
    commit_descriptions = []
    for c in commits:
        msg = c["commit"]["message"].split("\n", 1)[0]
        author = c["commit"]["author"]["name"]
        commit_descriptions.append(f"- {msg} (by {author})")

    commits_text = "\n".join(commit_descriptions)
    prompt = (
        "You are a changelog writer for a Kubernetes homelab project.\n"
        "Below are recent git commits (new features only).\n"
        "Write a concise changelog summarizing what changed. "
        "For each item, explain what it does in "
        "one clear sentence — don't just repeat the commit message. "
        "Use plain language. No markdown headers, just plain text with bullet points.\n\n"
        f"Commits:\n{commits_text}"
    )
    return await llm_call(prompt)


def _build_embed(summary: str, commit_count: int) -> discord.Embed:
    """Build a Discord embed for the changelog notification."""
    embed = discord.Embed(
        title="Homelab Changelog",
        description=summary,
        color=0x2ECC71,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text=f"{commit_count} commit(s)")
    return embed


async def run_changelog_iteration(
    bot: discord.Client,
    llm_call: Callable[[str], Awaitable[str]],
    store_message: "Callable[[str, str, str, str, str], Awaitable[None]] | None" = None,
) -> None:
    """Single iteration: fetch recent commits, summarize, post to Discord.

    store_message, if provided, is called with (discord_message_id, channel_id,
    user_id, username, content) after a successful send so the changelog message
    is searchable in history.
    """
    channel_id = os.environ.get("CHANGELOG_CHANNEL_ID", "")
    github_token = os.environ.get("GITHUB_TOKEN", "")
    github_repo = os.environ.get("CHANGELOG_GITHUB_REPO", "")

    if not all([channel_id, github_token, github_repo]):
        logger.warning("Changelog disabled: missing env vars")
        return

    since = datetime.now(timezone.utc) - timedelta(hours=1)

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        commits = await _fetch_commits_since(client, github_repo, github_token, since)

        if not commits:
            logger.info("Changelog: no new commits in the last hour")
            return

        changelog_commits = _filter_changelog_commits(commits)

    if not changelog_commits:
        logger.info("Changelog: %d new commits but none are feat", len(commits))
        return

    summary = await _summarize_with_gemma(changelog_commits, llm_call)
    embed = _build_embed(summary, len(changelog_commits))

    channel = bot.get_channel(int(channel_id))
    if channel:
        sent = await channel.send(embed=embed)
        logger.info(
            "Changelog: posted %d changes to channel %s",
            len(changelog_commits),
            channel_id,
        )
        if store_message is not None and bot.user is not None:
            try:
                await store_message(
                    str(sent.id),
                    channel_id,
                    str(bot.user.id),
                    bot.user.display_name,
                    f"Homelab Changelog\n{summary}",
                )
            except Exception:
                logger.exception("Changelog: failed to store sent message %s", sent.id)
    else:
        logger.warning("Changelog: channel %s not found", channel_id)
