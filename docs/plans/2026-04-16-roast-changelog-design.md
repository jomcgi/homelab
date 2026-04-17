# Roast Changelog for ColinCee/homelab

**Date**: 2026-04-16
**Status**: Proposed

## Problem

We have hourly changelog summaries for jomcgi/homelab that post to Discord. We want the same for a friend's public repo (ColinCee/homelab) — but with a roasting tone, posted every 3 hours to the same channel.

## Approach

Generalize `run_changelog_iteration()` to accept a config object instead of reading env vars. Register two scheduled jobs with different configs.

## Design

### ChangelogConfig dataclass

New frozen dataclass in `changelog.py`:

```python
@dataclasses.dataclass(frozen=True)
class ChangelogConfig:
    github_repo: str
    channel_id: str
    system_prompt: str
    embed_title: str
    embed_color: int
    lookback_hours: int = 1
    commit_filter: re.Pattern | None = None  # None = all commits
```

### Two configs

**Existing changelog** (unchanged behavior):

- `github_repo`: from `CHANGELOG_GITHUB_REPO` env var
- `channel_id`: from `CHANGELOG_CHANNEL_ID` env var
- `system_prompt`: existing professional changelog prompt
- `embed_title`: "Homelab Changelog"
- `embed_color`: `0x2ECC71` (green)
- `lookback_hours`: 1
- `commit_filter`: `re.compile(r"^(feat)(\(.+?\))?!?:\s")` (feat only)

**Roast changelog** (new):

- `github_repo`: from `ROAST_CHANGELOG_GITHUB_REPO` env var
- `channel_id`: from `ROAST_CHANGELOG_CHANNEL_ID` env var
- `system_prompt`: roast prompt (see below)
- `embed_title`: "Colin's Homelab Roast"
- `embed_color`: `0xE74C3C` (red)
- `lookback_hours`: 3
- `commit_filter`: `None` (all commits)

### Roast prompt

```
You are Colin's close friend and a cynical senior engineer who has seen
too many homelabs. You're reviewing his recent git commits to roast him
in the group chat. He can take it — don't soften anything.

Below are his recent commits:
<commits>
{{COMMITS}}
</commits>

Write a changelog-style roast. Format:

Colin homelab changelog:
- <entry>
- <entry>
- <entry>

3-5 entries. Each one is a single line written as if it's a real
changelog bullet, but the content is the roast. Examples of the shape:
- "Added three ADRs to justify turning a Beelink on."
- "Replaced working Grafana dashboard with a worse one. Wrote a runbook about it."
- "Four commits to fix one typo. Copilot did the last three."

Target specific things in the commits — pretentious messages, features
added then ripped out, yak-shaving, ADRs for three lines of YAML,
Copilot cleaning up after him, enterprise patterns on a mini-PC,
README brags that are one commit old, bike-shedding. Name the thing.

Rules:
- Past tense, declarative, changelog voice. No "Colin did X" — the
  entries are the changes themselves, deadpan.
- Punch at choices, not at him. "Docker Swarm in 2026" is fair.
  Personal attacks are lazy.
- Dry > loud. A good callback to an earlier entry beats exclamation marks.
- No hedging, no "but seriously", no constructive feedback.
- No markdown headers, no emoji, no preamble or outro. Just the header
  line and bullets.
- If a commit is genuinely boring, skip it. Don't manufacture heat.
Optionally end with one entry in square brackets, e.g. [No breaking changes. Nothing worked in the first place.]
```

### Refactored function signature

`run_changelog_iteration()` changes to:

```python
async def run_changelog_iteration(
    bot: discord.Client,
    llm_call: Callable[[str], Awaitable[str]],
    config: ChangelogConfig,
    store_message: Callable[..., Awaitable[None]] | None = None,
) -> None:
```

- Uses `config.lookback_hours` for the `timedelta`
- Applies `config.commit_filter` if set, otherwise passes all commits
- Passes `config.system_prompt` to `_summarize_with_gemma` (which loses its hardcoded prompt)
- Uses `config.embed_title` and `config.embed_color` in `_build_embed`

### Scheduled jobs

**Existing** (`chat.changelog`): 3600s interval, aligned to hour boundaries. Unchanged.

**New** (`chat.changelog_roast`): 10800s interval, aligned to 3-hour boundaries (0:00, 3:00, 6:00, etc.).

Both registered in `summarizer.py` with the same `store_message` pattern.

### Helm values

```yaml
chat:
  changelog:
    enabled: true
    channelId: "1491186550472708117"
    githubRepo: "jomcgi/homelab"
  roastChangelog:
    enabled: true
    channelId: "1491186550472708117"
    githubRepo: "ColinCee/homelab"
```

### Deployment template additions

New env vars under `chat.roastChangelog.enabled`:

- `ROAST_CHANGELOG_CHANNEL_ID` from `chat.roastChangelog.channelId`
- `ROAST_CHANGELOG_GITHUB_REPO` from `chat.roastChangelog.githubRepo`

Reuses existing `GITHUB_TOKEN` (public repo, token just avoids rate limits).

### Silent when empty

Same as existing — if no commits in the lookback window, no message posted.

## Files changed

1. `projects/monolith/chat/changelog.py` — add `ChangelogConfig`, refactor functions to use it
2. `projects/monolith/chat/summarizer.py` — register second scheduled job
3. `projects/monolith/chart/templates/deployment.yaml` — add roast env vars
4. `projects/monolith/deploy/values.yaml` — add `roastChangelog` config
5. `projects/monolith/chat/changelog_test.py` — update tests for new signature, add roast config tests
