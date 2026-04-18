# Roast Changelog Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Generalize the changelog system to support multiple repos with different prompts, then add a roast changelog for ColinCee/homelab.

**Architecture:** Refactor `changelog.py` to be config-driven via a `ChangelogConfig` dataclass. Helm values defines a list of changelog entries, serialized as a single `CHANGELOG_CONFIGS` JSON env var. Prompts are registered by key in Python code. One scheduled job per config entry.

**Tech Stack:** Python, discord.py, httpx, Helm, pytest

---

### Task 1: Add ChangelogConfig dataclass and PROMPTS registry

**Files:**

- Modify: `projects/monolith/chat/changelog.py:1-16`
- Test: `projects/monolith/chat/changelog_test.py`

**Step 1: Write failing tests for config loading**

Add to `changelog_test.py`:

```python
import json
from chat.changelog import ChangelogConfig, PROMPTS, load_changelog_configs


class TestChangelogConfig:
    def test_load_configs_from_json(self):
        """JSON list is parsed into ChangelogConfig objects."""
        raw = json.dumps([{
            "name": "test",
            "channelId": "123",
            "githubRepo": "owner/repo",
            "prompt": "professional",
            "embedTitle": "Test",
            "embedColor": "0x2ECC71",
            "intervalHours": 1,
        }])
        configs = load_changelog_configs(raw)
        assert len(configs) == 1
        assert configs[0].name == "test"
        assert configs[0].github_repo == "owner/repo"
        assert configs[0].channel_id == "123"
        assert configs[0].embed_color == 0x2ECC71
        assert configs[0].interval_hours == 1
        assert configs[0].commit_filter is None

    def test_load_configs_with_commit_filter(self):
        """commitFilter string is compiled to a regex pattern."""
        raw = json.dumps([{
            "name": "filtered",
            "channelId": "123",
            "githubRepo": "owner/repo",
            "prompt": "professional",
            "embedTitle": "Test",
            "embedColor": "0x2ECC71",
            "intervalHours": 1,
            "commitFilter": "^(feat)(\\(.+?\\))?!?:\\s",
        }])
        configs = load_changelog_configs(raw)
        assert configs[0].commit_filter is not None
        assert configs[0].commit_filter.match("feat: something")
        assert not configs[0].commit_filter.match("fix: something")

    def test_load_configs_empty_json(self):
        """Empty JSON list returns empty config list."""
        assert load_changelog_configs("[]") == []

    def test_load_configs_empty_string(self):
        """Empty string returns empty config list."""
        assert load_changelog_configs("") == []

    def test_prompts_registry_has_professional(self):
        """PROMPTS dict contains 'professional' key."""
        assert "professional" in PROMPTS

    def test_prompts_registry_has_roast(self):
        """PROMPTS dict contains 'roast' key."""
        assert "roast" in PROMPTS

    def test_prompts_contain_commits_placeholder(self):
        """All prompts contain {commits} placeholder."""
        for key, prompt in PROMPTS.items():
            assert "{commits}" in prompt, f"Prompt '{key}' missing {{commits}} placeholder"
```

**Step 2: Run tests to verify they fail**

Run: `bb remote test //projects/monolith:changelog_test --config=ci`
Expected: FAIL — `ChangelogConfig`, `PROMPTS`, `load_changelog_configs` don't exist yet.

**Step 3: Implement ChangelogConfig, PROMPTS, and load_changelog_configs**

In `changelog.py`, add after the imports:

```python
import dataclasses
import json

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
        configs.append(ChangelogConfig(
            name=entry["name"],
            github_repo=entry["githubRepo"],
            channel_id=entry["channelId"],
            prompt=entry["prompt"],
            embed_title=entry["embedTitle"],
            embed_color=int(entry["embedColor"], 16) if isinstance(entry["embedColor"], str) else entry["embedColor"],
            interval_hours=entry.get("intervalHours", 1),
            commit_filter=commit_filter,
        ))
    return configs
```

**Step 4: Run tests to verify they pass**

Run: `bb remote test //projects/monolith:changelog_test --config=ci`
Expected: New tests PASS, existing tests still PASS.

**Step 5: Commit**

```bash
git add projects/monolith/chat/changelog.py projects/monolith/chat/changelog_test.py
git commit -m "feat(monolith): add ChangelogConfig dataclass and prompt registry"
```

---

### Task 2: Refactor \_summarize_with_gemma and \_build_embed to accept config

**Files:**

- Modify: `projects/monolith/chat/changelog.py:51-84`
- Test: `projects/monolith/chat/changelog_test.py`

**Step 1: Update existing tests to pass config parameters**

Update `TestSummarizeWithGemma` — `_summarize_with_gemma` now takes a `prompt_template` string parameter instead of hardcoding the prompt. Update calls:

```python
class TestSummarizeWithGemma:
    @pytest.mark.asyncio
    async def test_prompt_includes_commit_messages(self):
        commits = [_make_commit("feat: add search", "Bob")]
        mock_llm = AsyncMock(return_value="Added search functionality.")
        await _summarize_with_gemma(commits, mock_llm, PROMPTS["professional"])
        call_args = mock_llm.call_args[0][0]
        assert "feat: add search" in call_args
```

(Same pattern for all tests in this class — add `PROMPTS["professional"]` as third arg.)

Update `TestBuildEmbed` — `_build_embed` now takes `title` and `color` parameters:

```python
class TestBuildEmbed:
    def test_embed_title(self):
        embed = _build_embed("Some summary", commit_count=3, title="Homelab Changelog", color=0x2ECC71)
        assert embed.title == "Homelab Changelog"

    def test_embed_color(self):
        embed = _build_embed("Some summary", commit_count=3, title="Homelab Changelog", color=0x2ECC71)
        assert embed.colour.value == 0x2ECC71

    def test_custom_title_and_color(self):
        embed = _build_embed("Roast", commit_count=1, title="Colin's Homelab Roast", color=0xE74C3C)
        assert embed.title == "Colin's Homelab Roast"
        assert embed.colour.value == 0xE74C3C
```

(Update all other `_build_embed` calls to include `title` and `color` kwargs.)

**Step 2: Run tests to verify they fail**

Run: `bb remote test //projects/monolith:changelog_test --config=ci`
Expected: FAIL — function signatures don't match yet.

**Step 3: Update function signatures**

In `changelog.py`:

```python
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


def _build_embed(summary: str, commit_count: int, title: str, color: int) -> discord.Embed:
    """Build a Discord embed for the changelog notification."""
    embed = discord.Embed(
        title=title,
        description=summary,
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text=f"{commit_count} commit(s)")
    return embed
```

**Step 4: Run tests to verify they pass**

Run: `bb remote test //projects/monolith:changelog_test --config=ci`
Expected: PASS

**Step 5: Commit**

```bash
git add projects/monolith/chat/changelog.py projects/monolith/chat/changelog_test.py
git commit -m "refactor(monolith): parameterize _summarize_with_gemma and _build_embed"
```

---

### Task 3: Refactor run_changelog_iteration to accept ChangelogConfig

**Files:**

- Modify: `projects/monolith/chat/changelog.py:87-145`
- Test: `projects/monolith/chat/changelog_test.py`

**Step 1: Update TestRunChangelogIteration tests**

All tests in `TestRunChangelogIteration` need to:

1. Pass a `ChangelogConfig` instead of relying on env vars
2. Remove `patch.dict("os.environ", ...)` for changelog-specific vars (keep `GITHUB_TOKEN` as env var since it's shared)

Create a test helper:

```python
def _make_config(**overrides) -> "ChangelogConfig":
    from chat.changelog import ChangelogConfig
    defaults = {
        "name": "test",
        "github_repo": "owner/repo",
        "channel_id": "123",
        "prompt": "professional",
        "embed_title": "Test Changelog",
        "embed_color": 0x2ECC71,
        "interval_hours": 1,
        "commit_filter": None,
    }
    defaults.update(overrides)
    return ChangelogConfig(**defaults)
```

Update test: `test_missing_all_env_vars_returns_early` → `test_missing_github_token_returns_early`:

```python
@pytest.mark.asyncio
async def test_missing_github_token_returns_early(self):
    """When GITHUB_TOKEN is absent the function exits without error."""
    bot = MagicMock(spec=discord.Client)
    mock_llm = AsyncMock()
    config = _make_config()

    with patch.dict("os.environ", {}, clear=True):
        import os
        os.environ.pop("GITHUB_TOKEN", None)
        await run_changelog_iteration(bot, mock_llm, config)

    mock_llm.assert_not_called()
```

Remove `test_missing_single_env_var_returns_early` (no longer applicable — config fields are required).

Update remaining tests to pass `config=_make_config(channel_id="999", ...)` and set only `GITHUB_TOKEN` in env.

Add new test for commit_filter=None (all commits pass through):

```python
@pytest.mark.asyncio
async def test_no_commit_filter_passes_all_commits(self):
    """When commit_filter is None, all commits are included."""
    config = _make_config(commit_filter=None)
    # ... setup with fix: and chore: commits ...
    # Assert llm_call IS called (all commits pass through)
```

Add test for lookback_hours:

```python
@pytest.mark.asyncio
async def test_lookback_hours_used_for_since(self):
    """The since parameter uses config.interval_hours for lookback."""
    config = _make_config(interval_hours=3)
    # ... verify _fetch_commits_since is called with since ~3 hours ago
```

**Step 2: Run tests to verify they fail**

Run: `bb remote test //projects/monolith:changelog_test --config=ci`
Expected: FAIL — `run_changelog_iteration` doesn't accept `config` yet.

**Step 3: Refactor run_changelog_iteration**

```python
async def run_changelog_iteration(
    bot: discord.Client,
    llm_call: Callable[[str], Awaitable[str]],
    config: ChangelogConfig,
    store_message: "Callable[[str, str, str, str, str], Awaitable[None]] | None" = None,
) -> None:
    """Single iteration: fetch recent commits, summarize, post to Discord."""
    github_token = os.environ.get("GITHUB_TOKEN", "")

    if not github_token:
        logger.warning("Changelog[%s] disabled: missing GITHUB_TOKEN", config.name)
        return

    since = datetime.now(timezone.utc) - timedelta(hours=config.interval_hours)

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        commits = await _fetch_commits_since(client, config.github_repo, github_token, since)

        if not commits:
            logger.info("Changelog[%s]: no new commits in the last %dh", config.name, config.interval_hours)
            return

        if config.commit_filter is not None:
            commits = _filter_changelog_commits(commits, config.commit_filter)

    if not commits:
        logger.info("Changelog[%s]: commits found but none match filter", config.name)
        return

    prompt_template = PROMPTS[config.prompt]
    summary = await _summarize_with_gemma(commits, llm_call, prompt_template)
    embed = _build_embed(summary, len(commits), title=config.embed_title, color=config.embed_color)

    channel = bot.get_channel(int(config.channel_id))
    if channel:
        sent = await channel.send(embed=embed)
        logger.info("Changelog[%s]: posted %d changes to channel %s", config.name, len(commits), config.channel_id)
        if store_message is not None and bot.user is not None:
            try:
                await store_message(
                    str(sent.id),
                    config.channel_id,
                    str(bot.user.id),
                    bot.user.display_name,
                    f"{config.embed_title}\n{summary}",
                )
            except Exception:
                logger.exception("Changelog[%s]: failed to store sent message %s", config.name, sent.id)
    else:
        logger.warning("Changelog[%s]: channel %s not found", config.name, config.channel_id)
```

Also update `_filter_changelog_commits` to accept a pattern parameter:

```python
def _filter_changelog_commits(commits: list[dict], pattern: re.Pattern) -> list[dict]:
    """Keep only commits matching the given pattern."""
    result = []
    for c in commits:
        msg = c["commit"]["message"].split("\n", 1)[0]
        if pattern.match(msg):
            result.append(c)
    return result
```

**Step 4: Run tests to verify they pass**

Run: `bb remote test //projects/monolith:changelog_test --config=ci`
Expected: PASS

**Step 5: Commit**

```bash
git add projects/monolith/chat/changelog.py projects/monolith/chat/changelog_test.py
git commit -m "refactor(monolith): make run_changelog_iteration config-driven"
```

---

### Task 4: Update summarizer.py to register jobs from config list

**Files:**

- Modify: `projects/monolith/chat/summarizer.py:220-260`

**Step 1: Update the changelog job registration**

Replace the single changelog job registration with a loop over configs:

```python
    if bot is not None:
        from chat.changelog import ChangelogConfig, load_changelog_configs, run_changelog_iteration
        from shared.embedding import EmbeddingClient

        changelog_configs = load_changelog_configs(
            os.environ.get("CHANGELOG_CONFIGS", "")
        )

        for cfg in changelog_configs:
            def _make_handler(config: ChangelogConfig):
                async def _changelog_handler(session: "Session") -> datetime | None:
                    embed_client = EmbeddingClient()

                    async def _store_message(
                        discord_message_id: str,
                        channel_id: str,
                        user_id: str,
                        username: str,
                        content: str,
                    ) -> None:
                        from chat.store import MessageStore
                        store = MessageStore(session=session, embed_client=embed_client)
                        await store.save_message(
                            discord_message_id=discord_message_id,
                            channel_id=channel_id,
                            user_id=user_id,
                            username=username,
                            content=content,
                            is_bot=True,
                        )

                    await run_changelog_iteration(bot, llm_call, config, store_message=_store_message)
                    now = datetime.now(timezone.utc)
                    interval = timedelta(hours=config.interval_hours)
                    # Align to next interval boundary
                    epoch = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    elapsed = now - epoch
                    periods = int(elapsed / interval) + 1
                    return epoch + interval * periods

                return _changelog_handler

            register_job(
                session,
                name=f"chat.changelog.{cfg.name}",
                interval_secs=cfg.interval_hours * 3600,
                handler=_make_handler(cfg),
                ttl_secs=300,
            )
```

Note: `_make_handler` closure is needed to capture `cfg` by value, not by reference (classic Python loop variable capture bug).

**Step 2: Run all tests**

Run: `bb remote test //projects/monolith/... --config=ci`
Expected: PASS

**Step 3: Commit**

```bash
git add projects/monolith/chat/summarizer.py
git commit -m "feat(monolith): register changelog jobs from CHANGELOG_CONFIGS list"
```

---

### Task 5: Update Helm chart and values

**Files:**

- Modify: `projects/monolith/chart/templates/deployment.yaml:84-94`
- Modify: `projects/monolith/deploy/values.yaml:95-98`
- Modify: `projects/monolith/chart/Chart.yaml` (version bump)
- Modify: `projects/monolith/deploy/application.yaml` (targetRevision bump)

**Step 1: Update deployment template**

Replace lines 84-94 in `deployment.yaml`:

```yaml
            {{- if .Values.chat.changelogs }}
            - name: GITHUB_TOKEN
              valueFrom:
                secretKeyRef:
                  name: {{ include "monolith.fullname" . }}-chat-secrets
                  key: GITHUB_TOKEN
            - name: CHANGELOG_CONFIGS
              value: {{ .Values.chat.changelogs | toJson | quote }}
            {{- end }}
```

**Step 2: Update values.yaml**

Replace the `changelog` block (lines 95-98) with:

```yaml
changelogs:
  - name: "homelab"
    channelId: "1491186550472708117"
    githubRepo: "jomcgi/homelab"
    prompt: "professional"
    embedTitle: "Homelab Changelog"
    embedColor: "0x2ECC71"
    intervalHours: 1
    commitFilter: "^(feat)(\\(.+?\\))?!?:\\s"
  - name: "roast"
    channelId: "1491186550472708117"
    githubRepo: "ColinCee/homelab"
    prompt: "roast"
    embedTitle: "Colin's Homelab Roast"
    embedColor: "0xE74C3C"
    intervalHours: 3
```

**Step 3: Verify Helm renders correctly**

Run: `helm template monolith projects/monolith/chart/ -f projects/monolith/deploy/values.yaml | grep -A5 CHANGELOG`
Expected: `CHANGELOG_CONFIGS` env var with JSON array value.

**Step 4: Bump chart version**

Bump version in `projects/monolith/chart/Chart.yaml` and update `targetRevision` in `projects/monolith/deploy/application.yaml` to match.

**Step 5: Commit**

```bash
git add projects/monolith/chart/ projects/monolith/deploy/
git commit -m "feat(monolith): switch changelog config to list-based CHANGELOG_CONFIGS env var"
```

---

### Task 6: Run full test suite and verify helm rendering

**Step 1: Run all monolith tests**

Run: `bb remote test //projects/monolith/... --config=ci`
Expected: All PASS

**Step 2: Verify Helm template renders cleanly**

Run: `helm template monolith projects/monolith/chart/ -f projects/monolith/deploy/values.yaml`
Expected: No errors, valid YAML, `CHANGELOG_CONFIGS` env var present with JSON.

**Step 3: Run format**

Run: `format`
Expected: No changes (or auto-fixed formatting).

**Step 4: Commit any format fixes**

```bash
git add -A && git commit -m "style(monolith): format fixes"
```
