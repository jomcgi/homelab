"""Hourly changelog notifier — polls GitHub for new feat commits, summarizes via Gemma, posts to Discord."""

import dataclasses
import json
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


@dataclasses.dataclass(frozen=True)
class ChangelogConfig:
    name: str
    github_repo: str
    channel_id: str
    prompt: str
    embed_title: str
    embed_color: int
    interval_hours: int = 1
    commit_filter: re.Pattern | None = None


PROMPTS: dict[str, str] = {
    "professional": (
        "You are a changelog writer for a Kubernetes homelab project.\n"
        "Below are recent git commits (new features only).\n"
        "Write a concise changelog summarizing what changed. "
        "For each item, explain what it does in "
        "one clear sentence — don't just repeat the commit message. "
        "Use plain language. No markdown headers, just plain text with bullet points.\n\n"
        "Commits:\n{commits}"
    ),
    "roast": (
        "You are Colin's close friend and a cynical senior engineer who has seen\n"
        "too many homelabs. You're reviewing his recent git commits to roast him\n"
        "in the group chat. He can take it — don't soften anything.\n\n"
        "Below are his recent commits:\n"
        "<commits>\n{commits}\n</commits>\n\n"
        "Write a changelog-style roast. Format:\n\n"
        "Colin homelab changelog:\n"
        "- <entry>\n- <entry>\n- <entry>\n\n"
        "3-5 entries. Each one is a single line written as if it's a real\n"
        "changelog bullet, but the content is the roast. Examples of the shape:\n"
        '- "Added three ADRs to justify turning a Beelink on."\n'
        '- "Replaced working Grafana dashboard with a worse one. Wrote a runbook about it."\n'
        '- "Four commits to fix one typo. Copilot did the last three."\n\n'
        "Target specific things in the commits — pretentious messages, features\n"
        "added then ripped out, yak-shaving, ADRs for three lines of YAML,\n"
        "Copilot cleaning up after him, enterprise patterns on a mini-PC,\n"
        "README brags that are one commit old, bike-shedding. Name the thing.\n\n"
        "Rules:\n"
        '- Past tense, declarative, changelog voice. No "Colin did X" — the\n'
        "  entries are the changes themselves, deadpan.\n"
        '- Punch at choices, not at him. "Docker Swarm in 2026" is fair.\n'
        "  Personal attacks are lazy.\n"
        "- Dry > loud. A good callback to an earlier entry beats exclamation marks.\n"
        '- No hedging, no "but seriously", no constructive feedback.\n'
        "- No markdown headers, no emoji, no preamble or outro. Just the header\n"
        "  line and bullets.\n"
        "- If a commit is genuinely boring, skip it. Don't manufacture heat.\n"
        "Optionally end with one entry in square brackets, e.g. "
        "[No breaking changes. Nothing worked in the first place.]"
    ),
}


def load_changelog_configs(raw: str) -> list[ChangelogConfig]:
    """Parse a JSON string into a list of ChangelogConfig objects."""
    if not raw:
        return []
    entries = json.loads(raw)
    configs = []
    for entry in entries:
        commit_filter = None
        if "commitFilter" in entry:
            commit_filter = re.compile(entry["commitFilter"])
        configs.append(
            ChangelogConfig(
                name=entry["name"],
                github_repo=entry["githubRepo"],
                channel_id=entry["channelId"],
                prompt=entry["prompt"],
                embed_title=entry["embedTitle"],
                embed_color=int(entry["embedColor"], 16)
                if isinstance(entry["embedColor"], str)
                else entry["embedColor"],
                interval_hours=entry.get("intervalHours", 1),
                commit_filter=commit_filter,
            )
        )
    return configs


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
    prompt_template: str,
) -> str:
    """Ask Gemma to produce a concise changelog from commit data."""
    commit_descriptions = []
    for c in commits:
        msg = c["commit"]["message"].split("\n", 1)[0]
        author = c["commit"]["author"]["name"]
        commit_descriptions.append(f"- {msg} (by {author})")

    commits_text = "\n".join(commit_descriptions)
    prompt = prompt_template.format(commits=commits_text)
    return await llm_call(prompt)


def _build_embed(
    summary: str, commit_count: int, title: str, color: int
) -> discord.Embed:
    """Build a Discord embed for the changelog notification."""
    embed = discord.Embed(
        title=title,
        description=summary,
        color=color,
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

    summary = await _summarize_with_gemma(
        changelog_commits, llm_call, PROMPTS["professional"]
    )
    embed = _build_embed(
        summary, len(changelog_commits), title="Homelab Changelog", color=0x2ECC71
    )

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
