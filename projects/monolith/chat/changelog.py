"""Hourly changelog notifier — polls GitHub for new feat/fix commits, summarizes via Gemma, posts to Discord."""

import asyncio
import logging
import os
import re
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

import discord
import httpx

logger = logging.getLogger(__name__)

# Conventional commit types we care about
_CHANGELOG_TYPES = re.compile(r"^(feat|fix)(\(.+?\))?!?:\s")

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
    """Keep only feat/fix conventional commits."""
    result = []
    for c in commits:
        msg = c["commit"]["message"].split("\n", 1)[0]
        if _CHANGELOG_TYPES.match(msg):
            result.append(c)
    return result


async def _fetch_ci_status(
    client: httpx.AsyncClient,
    repo: str,
    token: str,
) -> str:
    """Get the conclusion of the last completed check suite on main HEAD."""
    resp = await client.get(
        f"{GITHUB_API}/repos/{repo}/commits/main/check-suites",
        params={"per_page": 10},
        headers=_auth_headers(token),
    )
    resp.raise_for_status()
    suites = resp.json().get("check_suites", [])

    for suite in suites:
        if suite.get("status") == "completed":
            return suite.get("conclusion", "unknown")

    return "pending"


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
        "Below are recent git commits (features and bug fixes only).\n"
        "Write a concise changelog summarizing what changed. "
        "Group by features and fixes. For each item, explain what it does in "
        "one clear sentence — don't just repeat the commit message. "
        "Use plain language. No markdown headers, just plain text with bullet points.\n\n"
        f"Commits:\n{commits_text}"
    )
    return await llm_call(prompt)


def _build_embed(summary: str, ci_status: str, commit_count: int) -> discord.Embed:
    """Build a Discord embed for the changelog notification."""
    ci_emoji = {
        "success": "\u2705",
        "failure": "\u274c",
        "pending": "\u23f3",
    }.get(ci_status, "\u2753")

    embed = discord.Embed(
        title="Homelab Changelog",
        description=summary,
        color=0x2ECC71
        if ci_status == "success"
        else 0xE74C3C
        if ci_status == "failure"
        else 0x95A5A6,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text=f"{ci_emoji} CI: {ci_status} | {commit_count} commit(s)")
    return embed


async def run_changelog_iteration(
    bot: discord.Client,
    llm_call: Callable[[str], Awaitable[str]],
) -> None:
    """Single iteration: fetch recent commits, summarize, post to Discord."""
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
        ci_status = await _fetch_ci_status(client, github_repo, github_token)

    if not changelog_commits:
        logger.info("Changelog: %d new commits but none are feat/fix", len(commits))
        return

    summary = await _summarize_with_gemma(changelog_commits, llm_call)
    embed = _build_embed(summary, ci_status, len(changelog_commits))

    channel = bot.get_channel(int(channel_id))
    if channel:
        await channel.send(embed=embed)
        logger.info("Changelog: posted %d changes to channel %s", len(changelog_commits), channel_id)
    else:
        logger.warning("Changelog: channel %s not found", channel_id)


def _seconds_until_next_hour() -> float:
    """Calculate seconds until the next hour boundary."""
    now = datetime.now(timezone.utc)
    next_hour = now.replace(minute=0, second=0, microsecond=0)
    next_hour += timedelta(hours=1)
    return (next_hour - now).total_seconds()


async def changelog_loop(
    bot: discord.Client,
    llm_call: Callable[[str], Awaitable[str]],
) -> None:
    """Main loop: poll GitHub hourly on the hour, summarize and post changelog."""
    channel_id = os.environ.get("CHANGELOG_CHANNEL_ID", "")
    github_token = os.environ.get("GITHUB_TOKEN", "")
    github_repo = os.environ.get("CHANGELOG_GITHUB_REPO", "")

    if not all([channel_id, github_token, github_repo]):
        logger.warning(
            "Changelog loop disabled: missing CHANGELOG_CHANNEL_ID, GITHUB_TOKEN, or CHANGELOG_GITHUB_REPO"
        )
        return

    # Wait for bot to be initialized (start() is called after sidecar is healthy)
    while not bot.is_ready():
        await asyncio.sleep(2)
    logger.info("Changelog loop started")

    while True:
        sleep_seconds = _seconds_until_next_hour()
        logger.info("Changelog: sleeping %.0fs until next hour", sleep_seconds)
        await asyncio.sleep(sleep_seconds)

        try:
            await run_changelog_iteration(bot, llm_call)
        except Exception:
            logger.exception("Changelog loop iteration failed")
